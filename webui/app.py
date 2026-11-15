from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, JsonValue, ValidationError
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from dataSource import ROOT, config_path, load_config
from webui.jobs import Job, JobManager, QueueFullError
from webui.tools import TOOLS


class RunRequest(BaseModel):
    tool_id: str
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class ToolInfo(BaseModel):
    id: str
    name: str
    category: str
    description: str
    requires_dataset: bool
    schema_: dict[str, JsonValue] = Field(serialization_alias='schema')


class DatasetStatus(BaseModel):
    source: str | None = None
    ready: bool = False
    path: str | None = None
    commit: str | None = None
    tables: int = 0
    languages: int = 0
    error: str | None = None


class Character(BaseModel):
    id: int
    name: str
    skill_depot: int | None = None


def create_app(config: Path | None = None, jobs_root: Path | None = None,
               frontend: Path | None = None) -> FastAPI:
    profile = (config or config_path()).resolve()
    store = jobs_root or profile.parent / '.data' / 'webui' / 'jobs'
    assets = frontend or ROOT / 'frontend' / 'dist'

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.jobs = JobManager(profile, store)
        yield
        application.state.jobs.close()

    application = FastAPI(title='Genshin Wiki Workshop', lifespan=lifespan)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver'])

    @application.middleware('http')
    async def same_origin(request: Request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            if origin.rstrip('/') != str(request.base_url).rstrip('/'):
                from fastapi.responses import JSONResponse
                return JSONResponse({'detail': 'Cross-origin requests are not allowed.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    def manager(request: Request) -> JobManager:
        return request.app.state.jobs

    def get_job(request: Request, job_id: str) -> Job:
        try:
            return manager(request).get(job_id)
        except KeyError:
            raise HTTPException(404, 'Job not found.') from None

    def submit(request: Request, tool_id: str, parameters: dict[str, JsonValue]) -> Job:
        try:
            return manager(request).submit(tool_id, parameters)
        except KeyError:
            raise HTTPException(404, 'Tool not found.') from None
        except ValidationError as error:
            raise HTTPException(422, jsonable_encoder(error.errors(), custom_encoder={ValueError: str})) from error
        except QueueFullError as error:
            raise HTTPException(409, str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(409, str(error)) from error

    @application.get('/api/tools', response_model=list[ToolInfo])
    def tools():
        return [
            ToolInfo(id=tool.id, name=tool.name, category=tool.category, description=tool.description,
                     requires_dataset=tool.requires_dataset, schema_=tool.model.model_json_schema())
            for tool in TOOLS.values()
        ]

    @application.get('/api/dataset', response_model=DatasetStatus)
    def dataset():
        source = None
        try:
            source = load_config(profile, require_prepared=False).get('DataSource', 'local')
            resolved = load_config(profile)
            path = Path(resolved['RepoPath'])
            if not (path / 'MappedExcelBinOutput_EN').is_dir() or not (path / 'TextMap').is_dir():
                raise FileNotFoundError('The selected dataset is not prepared. Run dataset setup first.')
            commit = None
            marker = path / '.prepared.json'
            if marker.is_file():
                commit = json.loads(marker.read_text(encoding='utf-8'))['commit']
            return DatasetStatus(
                source=source, ready=True, path=str(path), commit=commit,
                tables=len(list((path / 'MappedExcelBinOutput_EN').glob('*.json'))),
                languages=sum((path / 'TextMap' / f'TextMap{lang}.json').is_file() for lang in (
                    'CHS', 'CHT', 'DE', 'EN', 'ES', 'FR', 'ID', 'JP', 'KR', 'PT', 'RU', 'TH', 'VI', 'TR', 'IT',
                )),
            )
        except (OSError, ValueError, KeyError) as error:
            return DatasetStatus(source=source, error=str(error))

    @application.get('/api/characters', response_model=list[Character])
    def characters():
        try:
            path = Path(load_config(profile)['RepoPath']) / 'MappedExcelBinOutput_EN' / 'AvatarExcelConfigData.json'
            records = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(records, list):
                raise ValueError('The avatar table must contain a list.')
            result = []
            for item in records:
                if not isinstance(item, dict):
                    raise ValueError('Invalid entry in the avatar table.')
                name, identifier, depot = item.get('NameTextMapHash'), item.get('Id'), item.get('SkillDepotId')
                if isinstance(name, str) and isinstance(identifier, int):
                    result.append(Character(id=identifier, name=name, skill_depot=depot if isinstance(depot, int) else None))
            return sorted(result, key=lambda character: character.name)
        except (OSError, ValueError, KeyError) as error:
            raise HTTPException(409, str(error)) from error

    @application.get('/api/jobs', response_model=list[Job])
    def jobs(request: Request):
        return manager(request).list_jobs()

    @application.post('/api/jobs', response_model=Job, status_code=202)
    def run_tool(body: RunRequest, request: Request):
        if body.tool_id not in TOOLS:
            raise HTTPException(404, 'Tool not found.')
        return submit(request, body.tool_id, body.parameters)

    @application.post('/api/dataset/setup', response_model=Job, status_code=202)
    def setup(request: Request, body: dict[str, JsonValue]):
        if body:
            raise HTTPException(422, 'Dataset setup does not accept parameters.')
        return submit(request, 'dataset-setup', {})

    @application.get('/api/jobs/{job_id}', response_model=Job)
    def job_detail(job_id: str, request: Request):
        return get_job(request, job_id)

    @application.get('/api/jobs/{job_id}/logs')
    def logs(job_id: str, request: Request):
        get_job(request, job_id)
        path = manager(request).root / job_id / 'log.txt'
        if not path.is_file():
            return {'text': '', 'truncated': False}
        with path.open('rb') as file:
            size = path.stat().st_size
            file.seek(max(0, size - 131072))
            text = file.read().decode('utf-8', errors='replace')
        return {'text': text, 'truncated': size > 131072}

    def output_path(request: Request, job_id: str, name: str) -> Path:
        try:
            return manager(request).file(job_id, name)
        except (KeyError, FileNotFoundError):
            raise HTTPException(404, 'Output file not found.') from None

    @application.get('/api/jobs/{job_id}/preview/{name:path}')
    def preview(job_id: str, name: str, request: Request):
        path = output_path(request, job_id, name)
        if path.suffix.lower() not in ('.wikitext', '.txt', '.lua', '.json'):
            raise HTTPException(415, 'This file does not have a text preview.')
        if path.stat().st_size > 1048576:
            raise HTTPException(413, 'This file is too large to preview. Download it instead.')
        return {'text': path.read_text(encoding='utf-8')}

    @application.get('/api/jobs/{job_id}/files/{name:path}')
    def download(job_id: str, name: str, request: Request, inline: bool = False):
        path = output_path(request, job_id, name)
        image = path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')
        return FileResponse(path, filename=path.name, content_disposition_type='inline' if inline and image else 'attachment')

    @application.get('/api/jobs/{job_id}/archive')
    def archive(job_id: str, request: Request):
        job = get_job(request, job_id)
        if job.status in ('queued', 'running') or not job.files:
            raise HTTPException(409, 'Wait for the job to finish and produce files.')
        with tempfile.NamedTemporaryFile(suffix='.zip', dir=manager(request).root / job_id, delete=False) as file:
            path = Path(file.name)
        try:
            with ZipFile(path, 'w', compression=ZIP_DEFLATED) as zipped:
                for artifact in job.files:
                    zipped.write(output_path(request, job_id, artifact.path), artifact.path)
        except (OSError, HTTPException):
            path.unlink(missing_ok=True)
            raise
        return FileResponse(path, filename=f'{job.tool_id}-{job_id[:8]}.zip',
                            background=BackgroundTask(path.unlink, missing_ok=True))

    @application.get('/api/health')
    def health():
        return {'status': 'ok'}

    if assets.is_dir():
        application.mount('/', StaticFiles(directory=assets, html=True), name='frontend')
    else:
        @application.get('/')
        def missing_frontend():
            raise HTTPException(503, 'Build the frontend first: npm --prefix frontend run build')

    return application


app = create_app()
