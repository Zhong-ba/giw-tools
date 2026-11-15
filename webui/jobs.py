from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import multiprocessing
import os
from pathlib import Path
import re
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


class QueueFullError(Exception):
    pass


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
    def __init__(self, config: Path, root: Path):
        self.config = config.resolve()
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.jobs: dict[str, Job] = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='wiki-job')
        self.worker = ResidentWorker()
        for path in self.root.glob('*/job.json'):
            job = Job.model_validate_json(path.read_text(encoding='utf-8'))
            if not re.fullmatch(r'[0-9a-f]{32}', job.id) or path.parent.name != job.id:
                raise ValueError(f'Invalid job metadata: {path}')
            if job.status in ('queued', 'running'):
                job.status = 'failed'
                job.error = 'The server stopped before this job completed. Submit the tool again.'
                job.finished_at = now()
                self._save(job)
            self.jobs[job.id] = job

    def _save(self, job: Job) -> None:
        path = self.root / job.id / 'job.json'
        temporary = path.with_suffix('.tmp')
        temporary.write_text(job.model_dump_json(indent=2), encoding='utf-8')
        temporary.replace(path)

    def list_jobs(self) -> list[Job]:
        with self.lock:
            return [job.model_copy(deep=True) for job in sorted(
                self.jobs.values(), key=lambda item: item.created_at, reverse=True,
            )]

    def get(self, job_id: str) -> Job:
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            return self.jobs[job_id].model_copy(deep=True)

    def submit(self, tool_id: str, parameters: dict[str, JsonValue]) -> Job:
        tool = TOOLS.get(tool_id)
        if tool is None and tool_id != 'dataset-setup':
            raise KeyError(tool_id)
        validated = tool.model.model_validate(parameters).model_dump(mode='json') if tool else {}
        config = load_config(self.config, require_prepared=bool(tool and tool.requires_dataset))
        with self.lock:
            if sum(job.status in ('queued', 'running') for job in self.jobs.values()) >= 10:
                raise QueueFullError('The queue is full. Wait for a job to finish.')
            if tool_id == 'dataset-setup' and any(
                job.tool_id == tool_id and job.status in ('queued', 'running') for job in self.jobs.values()
            ):
                raise QueueFullError('Dataset setup is already queued or running.')
            job = Job(id=uuid4().hex, tool_id=tool_id, name=tool.name if tool else 'Dataset setup')
            directory = self.root / job.id
            output = directory / 'output'
            output.mkdir(parents=True)
            request = {'tool_id': tool_id, 'parameters': validated, 'config_path': str(self.config)}
            (directory / 'request.json').write_text(json.dumps(request), encoding='utf-8')
            if tool:
                snapshot = dict(
                    config, DataSource='local', OutputPath=str(output),
                    RepoPath=config['RepoPath'] if tool.requires_dataset else str(directory / 'unused-dataset'),
                )
                (directory / 'config.json').write_text(json.dumps(snapshot), encoding='utf-8')
            self._save(job)
            self.jobs[job.id] = job
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
            files = self._artifacts(directory / 'output')
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
        artifacts = []
        for path in sorted(output.rglob('*')):
            if not path.is_file():
                continue
            if not path.resolve().is_relative_to(output.resolve()):
                raise ValueError('A generated file points outside the job output directory.')
            suffix = path.suffix.lower()
            kind = 'text' if suffix in ('.wikitext', '.txt', '.lua', '.json') else (
                'image' if suffix in ('.png', '.jpg', '.jpeg', '.webp') else 'file'
            )
            artifacts.append(Artifact(path=path.relative_to(output).as_posix(), size=path.stat().st_size, kind=kind))
        return artifacts

    def file(self, job_id: str, name: str) -> Path:
        job = self.get(job_id)
        if name not in {artifact.path for artifact in job.files}:
            raise FileNotFoundError(name)
        root = (self.root / job_id / 'output').resolve()
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise FileNotFoundError(name)
        return path

    def close(self) -> None:
        self.executor.shutdown(wait=True)
        self.worker.stop()
