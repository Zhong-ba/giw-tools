from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import multiprocessing
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from threading import RLock
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, JsonValue

from dataSource import ROOT, load_config
from webui.tools import TOOLS
from webui.worker import serve


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Artifact(BaseModel):
    path: str
    size: int
    kind: Literal['text', 'image', 'file']
    # The File page text designated for a media file (see utils.files.write_file_pages).
    file_page: str | None = None


class Job(BaseModel):
    id: str
    tool_id: str
    name: str
    status: Literal['queued', 'running', 'succeeded', 'failed'] = 'queued'
    created_at: str = Field(default_factory=now)
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    files: list[Artifact] = Field(default_factory=list)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class QueueFullError(Exception):
    pass


# Character Kit pages in kit order: talents, ascension passives, special passives (Nightsoul, Moonsign, Hexerei,
# Stellar), the utility passive, then constellations. Anything else (icons, redirects) follows alphabetically.
KIT_ORDER = {stem: rank for rank, stem in enumerate(
    ('NA', 'E', 'Q', 'A1', 'A4', 'NRG', 'MB', 'WER', 'SP', 'UP', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6'))}


def file_order(tool_id: str, artifacts: list['Artifact']) -> list['Artifact']:
    if tool_id != 'character-kit':
        return artifacts
    return sorted(artifacts, key=lambda artifact: (KIT_ORDER.get(Path(artifact.path).stem, len(KIT_ORDER)), artifact.path))


class ResidentWorker:
    """One long-lived process that keeps loaded TextMaps between tool jobs.

    Only the single job-executor thread uses it, so calls are never concurrent.
    """

    def __init__(self):
        self.context = multiprocessing.get_context('spawn')
        self.process = None
        self.connection = None

    def run(self, directory: Path) -> str | None:
        if self.process is None or not self.process.is_alive():
            self.connection, child = self.context.Pipe()
            self.process = self.context.Process(target=serve, args=(child,), daemon=True, name='wiki-tools-worker')
            self.process.start()
            child.close()
        try:
            self.connection.send(str(directory))
            return self.connection.recv()
        except (EOFError, OSError):
            self.stop()
            with (directory / 'log.txt').open('a', encoding='utf-8') as log:
                log.write('\nThe worker process exited unexpectedly (possibly out of memory).\n')
            return 'The worker process exited unexpectedly. Open the log for details.'

    def stop(self) -> None:
        if self.process is None:
            return
        try:
            self.connection.send(None)
        except (OSError, ValueError):
            pass
        self.process.join(10)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join()
        self.connection.close()
        self.process = self.connection = None


class JobManager:
    def __init__(self, config: Path, root: Path, per_client: int | None = None):
        self.config = config.resolve()
        self.lock = RLock()
        self.jobs: dict[str, Job] = {}
        # Which browser submitted each job, on the hosted site; None locally.
        self.owners: dict[str, str | None] = {}
        self.per_client = per_client
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='wiki-job')
        self.worker = ResidentWorker()
        self._load(root)

    def _load(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs, self.owners = {}, {}
        for leftover in self.root.glob('.deleting-*'):
            shutil.rmtree(leftover, ignore_errors=True)
        for path in self.root.glob('*/job.json'):
            if path.parent.name.startswith('.'):
                continue
            job = Job.model_validate_json(path.read_text(encoding='utf-8'))
            if not re.fullmatch(r'[0-9a-f]{32}', job.id) or path.parent.name != job.id:
                raise ValueError(f'Invalid job metadata: {path}')
            if job.status in ('queued', 'running'):
                job.status = 'failed'
                job.error = 'The server stopped before this job completed. Submit the tool again.'
                job.finished_at = now()
                self._save(job)
            job.files = file_order(job.tool_id, job.files)
            self.jobs[job.id] = job
            try:
                self.owners[job.id] = json.loads((path.parent / 'request.json').read_text(encoding='utf-8')).get('client')
            except (OSError, ValueError, AttributeError):
                self.owners[job.id] = None

    def set_root(self, root: Path) -> None:
        '''Switches to another job folder (the working directory), loading the jobs already in it.'''
        with self.lock:
            if any(job.status in ('queued', 'running') for job in self.jobs.values()):
                raise ValueError('Wait for running jobs to finish before changing the working directory.')
            self._load(root)

    def _save(self, job: Job) -> None:
        path = self.root / job.id / 'job.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(job.model_dump_json(indent=2), encoding='utf-8')
        temporary.replace(path)

    def _owned(self, job_id: str, client: str | None) -> Job:
        job = self.jobs.get(job_id)
        if job is None or self.owners.get(job_id) != client:
            raise KeyError(job_id)
        return job

    def list_jobs(self, client: str | None = None) -> list[Job]:
        with self.lock:
            return [job.model_copy(deep=True) for job in sorted(
                self.jobs.values(), key=lambda item: item.created_at, reverse=True,
            ) if self.owners.get(job.id) == client]

    def get(self, job_id: str, client: str | None = None) -> Job:
        with self.lock:
            return self._owned(job_id, client).model_copy(deep=True)

    def submit(self, tool_id: str, parameters: dict[str, JsonValue], config: dict | None = None,
               client: str | None = None) -> Job:
        tool = TOOLS.get(tool_id)
        if tool is None and tool_id != 'dataset-setup':
            raise KeyError(tool_id)
        validated = tool.model.model_validate(parameters).model_dump(mode='json') if tool else {}
        if config is None:
            config = load_config(self.config, require_prepared=bool(tool and tool.requires_dataset))
        with self.lock:
            if sum(job.status in ('queued', 'running') for job in self.jobs.values()) >= 10:
                raise QueueFullError('The queue is full. Wait for a job to finish.')
            if self.per_client is not None and sum(
                job.status in ('queued', 'running') and self.owners.get(job.id) == client for job in self.jobs.values()
            ) >= self.per_client:
                raise QueueFullError(f'You can have {self.per_client} jobs queued at a time. Wait for one to finish.')
            if tool_id == 'dataset-setup' and any(
                job.tool_id == tool_id and job.status in ('queued', 'running') for job in self.jobs.values()
            ):
                raise QueueFullError('Dataset setup is already queued or running.')
            job = Job(id=uuid4().hex, tool_id=tool_id, name=tool.name if tool else 'Dataset setup', parameters=validated)
            directory = self.root / job.id
            output = directory / 'output'
            output.mkdir(parents=True)
            request = {'tool_id': tool_id, 'parameters': validated, 'config_path': str(self.config), 'client': client}
            (directory / 'request.json').write_text(json.dumps(request), encoding='utf-8')
            if tool:
                snapshot = dict(
                    config, DataSource='local', OutputPath=str(output),
                    RepoPath=config['RepoPath'] if tool.requires_dataset else str(directory / 'unused-dataset'),
                )
                (directory / 'config.json').write_text(json.dumps(snapshot), encoding='utf-8')
            self._save(job)
            self.jobs[job.id] = job
            self.owners[job.id] = client
            self.executor.submit(self._run, job.id)
            return job.model_copy(deep=True)

    def _run(self, job_id: str) -> None:
        directory = self.root / job_id
        with self.lock:
            job = self.jobs[job_id]
            job.status = 'running'
            job.started_at = now()
            self._save(job)
        try:
            if job.tool_id == 'dataset-setup':
                # Free the loaded TextMaps; they would be stale after a new revision anyway.
                self.worker.stop()
                with (directory / 'log.txt').open('wb') as log:
                    result = subprocess.run(
                        [sys.executable, '-u', '-m', 'webui.worker', str(directory)],
                        cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                        stdout=log, stderr=subprocess.STDOUT, check=False,
                    )
                error = f'The tool exited with code {result.returncode}. Open the log for details.' if result.returncode else None
            else:
                error = self.worker.run(directory)
            files = file_order(job.tool_id, self._artifacts(directory / 'output'))
            with self.lock:
                job.files = files
                job.status = 'failed' if error else 'succeeded'
                job.error = error
        except (OSError, ValueError) as error:
            with self.lock:
                job.status = 'failed'
                job.error = str(error)
        finally:
            with self.lock:
                job.finished_at = now()
                self._save(job)

    @staticmethod
    def _artifacts(output: Path) -> list[Artifact]:
        from utils.files import read_file_page

        artifacts = []
        for path in sorted(output.rglob('*')):
            if not path.is_file() or any(part.startswith('.') for part in path.relative_to(output).parts):
                continue
            if not path.resolve().is_relative_to(output.resolve()):
                raise ValueError('A generated file points outside the job output directory.')
            suffix = path.suffix.lower()
            kind = 'text' if suffix in ('.wikitext', '.txt', '.lua', '.json') else (
                'image' if suffix in ('.png', '.jpg', '.jpeg', '.webp') else 'file'
            )
            artifacts.append(Artifact(path=path.relative_to(output).as_posix(), size=path.stat().st_size, kind=kind,
                                      file_page=read_file_page(path) if kind == 'image' else None))
        return artifacts

    def file(self, job_id: str, name: str, client: str | None = None) -> Path:
        job = self.get(job_id, client)
        if name not in {artifact.path for artifact in job.files}:
            raise FileNotFoundError(name)
        root = (self.root / job_id / 'output').resolve()
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise FileNotFoundError(name)
        return path

    def delete(self, job_id: str, client: str | None = None) -> None:
        with self.lock:
            job = self._owned(job_id, client)
            if job.status in ('queued', 'running'):
                raise ValueError('Wait for the job to finish before deleting it.')
            directory = self.root / job_id
            # Rename first so a partially failed removal never leaves a half-deleted job visible.
            trash = directory.with_name(f'.deleting-{job_id}')
            directory.rename(trash)
            del self.jobs[job_id]
            self.owners.pop(job_id, None)
        shutil.rmtree(trash, ignore_errors=True)

    def purge(self, max_age: float) -> None:
        '''Deletes finished jobs older than max_age seconds (the hosted site keeps them only until browsers save them).'''
        cutoff = datetime.now(timezone.utc).timestamp() - max_age
        with self.lock:
            stale = [job.id for job in self.jobs.values() if job.status in ('succeeded', 'failed')
                     and datetime.fromisoformat(job.finished_at or job.created_at).timestamp() < cutoff]
        for job_id in stale:
            try:
                self.delete(job_id, self.owners.get(job_id))
            except (KeyError, ValueError, OSError):
                continue

    def save_text(self, job_id: str, name: str, text: str, client: str | None = None) -> Job:
        with self.lock:
            job = self._owned(job_id, client)
            if job.status in ('queued', 'running'):
                raise ValueError('Wait for the job to finish before editing its files.')
            path = self.file(job_id, name, client)
            if path.suffix.lower() != '.wikitext':
                raise ValueError('Only .wikitext files can be edited.')
            content = text.replace('\r\n', '\n')
            if b'\r\n' in path.read_bytes():
                content = content.replace('\n', '\r\n')
            data = content.encode('utf-8')
            temporary = path.with_name(f'.{path.name}.tmp')
            temporary.write_bytes(data)
            temporary.replace(path)
            for artifact in job.files:
                if artifact.path == name:
                    artifact.size = len(data)
            self._save(job)
            return job.model_copy(deep=True)

    def close(self) -> None:
        self.executor.shutdown(wait=True)
        self.worker.stop()
