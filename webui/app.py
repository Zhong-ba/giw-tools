from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, JsonValue, ValidationError
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from dataSource import (
    LATEST, REVISION_SETTINGS, ROOT, SOURCE_SETTINGS, SOURCES, cache_path, config_path, data_root, is_remote, load_config,
    selected_revisions, selected_sources,
)
from enemyList import added_monsters, has_name, monster_set, version_options
from setupData import excel_table_at, game_version, list_revisions
from webui.bot import BotManager, BotState, QueueItem, RelayLogin, RelayPost, SettingsUpdate, WikiError, WikiRelay
from webui.datasets import parse_choice, prepared_datasets, resolve_choice
from webui.jobs import Job, JobManager, QueueFullError
from webui.references import (
    binoutput_path, binoutput_tree, character_references, enemy_references, gadget_references, gadget_rows, read_reference,
)
from webui.tools import TOOLS, LanguageInputs
from webui.languages import language_results


BUILD = r'^(current|config|[0-9a-f]{40})$'
# How long the hosted site keeps finished jobs for browsers to collect.
HOSTED_JOB_AGE = 24 * 3600


def env_list(name: str) -> list[str]:
    return [item.strip().rstrip('/') for item in os.environ.get(name, '').split(',') if item.strip()]


class RunRequest(BaseModel):
    tool_id: str
    parameters: dict[str, JsonValue] = Field(default_factory=dict)


class TextBody(BaseModel):
    text: str = Field(max_length=1048576)


class LanguageResult(BaseModel):
    textmap_hash: str
    text: str


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
    excel_source: str | None = None
    binoutput_source: str | None = None
    binoutput_path: str | None = None
    binoutput_commit: str | None = None
    excel_revision: str = LATEST
    binoutput_revision: str = LATEST
    excel_title: str | None = None
    binoutput_title: str | None = None
    sources: dict[str, str] = Field(default_factory=lambda: {key: value['label'] for key, value in SOURCES.items()})


class SourceChoice(BaseModel):
    excel: str
    binoutput: str
    excel_revision: str = LATEST
    binoutput_revision: str = LATEST


class Revision(BaseModel):
    commit: str
    title: str
    date: str
    downloaded: bool = False


class Character(BaseModel):
    id: int
    name: str
    skill_depot: int | None = None


class QueueFiles(BaseModel):
    job_id: str
    paths: list[str] = Field(min_length=1, max_length=1000)


class QueueIds(BaseModel):
    ids: list[str] = Field(max_length=10000)


class PostRequest(BaseModel):
    ids: list[str] | None = Field(None, max_length=10000)


class QueueEdit(BaseModel):
    title: str | None = Field(None, max_length=255)
    content: str | None = Field(None, max_length=2097152)


class ServerConfig(BaseModel):
    hosted: bool
    working_directory: str | None = None
    default_working_directory: str | None = None


class ConfigUpdate(BaseModel):
    # An empty string goes back to the default.
    working_directory: str = Field(max_length=1000)


class PreparedRevision(BaseModel):
    source: str
    commit: str
    title: str | None = None
    active: bool = False


class PreparedDatasets(BaseModel):
    excel: list[PreparedRevision]
    binoutput: list[PreparedRevision]


def create_app(config: Path | None = None, jobs_root: Path | None = None,
               frontend: Path | None = None, hosted: bool | None = None) -> FastAPI:
    '''The web UI's API. Locally it keeps jobs and the bot queue in the working directory; hosted
    (PAINMELO_HOSTED=1) it only runs jobs for anonymous browsers, which save results and post to
    the wiki themselves.'''
    profile = (config or config_path()).resolve()
    hosted = os.environ.get('PAINMELO_HOSTED', '').lower() in ('1', 'true', 'yes') if hosted is None else hosted
    assets = frontend or ROOT / 'frontend' / 'dist'
    settings_file = data_root(profile) / 'webui.json'
    default_directory = jobs_root.parent if jobs_root else data_root(profile) / 'webui'

    def working_directory() -> Path:
        try:
            saved = json.loads(settings_file.read_text(encoding='utf-8')).get('working_directory')
            if isinstance(saved, str) and saved:
                return Path(saved)
        except (OSError, ValueError, AttributeError):
            pass
        return default_directory

    def jobs_folder(directory: Path) -> Path:
        return jobs_root if jobs_root and directory == default_directory else directory / 'jobs'

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        if hosted:
            store = Path(os.environ.get('PAINMELO_JOBS_DIR') or data_root(profile) / 'hosted-jobs')
            application.state.jobs = JobManager(profile, store, per_client=3)
            application.state.jobs.purge(HOSTED_JOB_AGE)
            application.state.bot = None
        else:
            directory = working_directory()
            application.state.jobs = JobManager(profile, jobs_folder(directory))
            application.state.bot = BotManager(directory / 'bot')
        application.state.relay = WikiRelay(public_only=hosted)
        yield
        if application.state.bot:
            application.state.bot.stop()
        application.state.relay.close()
        application.state.jobs.close()

    origins = env_list('PAINMELO_CORS_ORIGINS')
    hosts = env_list('PAINMELO_ALLOWED_HOSTS') or (['*'] if hosted else [])
    application = FastAPI(title='Genshin Wiki Workshop', lifespan=lifespan)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', 'testserver', *hosts])

    @application.middleware('http')
    async def same_origin(request: Request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            origin = origin.rstrip('/')
            if origin != str(request.base_url).rstrip('/') and origin not in origins:
                return JSONResponse({'detail': 'Cross-origin requests are not allowed.'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    if origins:
        # Added last so it runs first and answers preflight requests from the hosted frontend.
        application.add_middleware(
            CORSMiddleware, allow_origins=origins, allow_methods=['*'],
            allow_headers=['Content-Type', 'X-Client-Id', 'X-Dataset'], expose_headers=['Content-Disposition'],
        )

    def local_only():
        if hosted:
            raise HTTPException(403, 'This is only available when running the tools on your own computer.')

    def client(request: Request) -> str | None:
        '''The anonymous browser a hosted request comes from; jobs are only visible to the browser that ran them.'''
        if not hosted:
            return None
        value = request.headers.get('x-client-id', '')
        if not re.fullmatch(r'[A-Za-z0-9-]{16,64}', value):
            raise HTTPException(400, 'Missing or invalid X-Client-Id header.')
        return hashlib.sha256(value.encode()).hexdigest()

    def resolve(request: Request, require_prepared: bool = True) -> dict:
        '''The profile for this request, using the dataset chosen in the X-Dataset header if any.'''
        choice = request.headers.get('x-dataset')
        if not choice:
            return load_config(profile, require_prepared=require_prepared)
        return load_config(profile, prepared=resolve_choice(profile, parse_choice(choice)))

    def manager(request: Request) -> JobManager:
        return request.app.state.jobs

    def get_job(request: Request, job_id: str) -> Job:
        try:
            return manager(request).get(job_id, client(request))
        except KeyError:
            raise HTTPException(404, 'Job not found.') from None

    def submit(request: Request, tool_id: str, parameters: dict[str, JsonValue]) -> Job:
        try:
            tool = TOOLS.get(tool_id)
            config = resolve(request, require_prepared=bool(tool and tool.requires_dataset)) if tool else None
            return manager(request).submit(tool_id, parameters, config, client(request))
        except KeyError:
            raise HTTPException(404, 'Tool not found.') from None
        except ValidationError as error:
            raise HTTPException(422, jsonable_encoder(error.errors(), custom_encoder={ValueError: str})) from error
        except QueueFullError as error:
            raise HTTPException(409, str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(409, str(error)) from error

    @application.get('/api/config', response_model=ServerConfig)
    def server_config():
        if hosted:
            return ServerConfig(hosted=True)
        return ServerConfig(hosted=False, working_directory=str(working_directory()),
                            default_working_directory=str(default_directory))

    @application.put('/api/config', response_model=ServerConfig, dependencies=[Depends(local_only)])
    def update_config(body: ConfigUpdate, request: Request):
        value = body.working_directory.strip()
        directory = Path(value).expanduser() if value else default_directory
        if not directory.is_absolute():
            raise HTTPException(422, 'Enter a full path, for example D:\\Painmelo.')
        bot = request.app.state.bot
        if bot.running():
            raise HTTPException(409, 'Wait for posting to finish before changing the working directory.')
        try:
            jobs_folder(directory).mkdir(parents=True, exist_ok=True)
            manager(request).set_root(jobs_folder(directory))
            request.app.state.bot = BotManager(directory / 'bot')
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            settings_file.write_text(json.dumps({'working_directory': str(directory) if value else ''}, indent=2), encoding='utf-8')
        except (OSError, ValueError) as error:
            raise HTTPException(409, str(error)) from error
        return server_config()

    @application.get('/api/tools', response_model=list[ToolInfo])
    def tools():
        return [
            ToolInfo(id=tool.id, name=tool.name, category=tool.category, description=tool.description,
                     requires_dataset=tool.requires_dataset, schema_=tool.model.model_json_schema())
            for tool in TOOLS.values() if not tool.hidden
        ]

    revision_cache: dict[str, tuple[float, list[dict]]] = {}

    def commit_title(source: str | None, commit: str | None) -> str | None:
        if not source or not commit:
            return None
        result = subprocess.run(
            ['git', '--git-dir', str(cache_path(profile, source) / 'repository.git'), 'log', '-1', '--format=%s', commit],
            capture_output=True, text=True, check=False,
        )
        return result.stdout.strip().strip("'") or None if result.returncode == 0 else None

    @application.get('/api/dataset/revisions', response_model=list[Revision])
    def revisions(source: str):
        if source not in SOURCES:
            raise HTTPException(404, 'Unknown source.')
        cached = revision_cache.get(source)
        if cached is None or time.monotonic() - cached[0] > 600:
            try:
                revision_cache[source] = cached = (time.monotonic(), list_revisions(source))
            except (OSError, ValueError, KeyError) as error:
                raise HTTPException(502, f'Could not list revisions of {SOURCES[source]["label"]}: {error}') from error
        cache = cache_path(profile, source)
        downloaded = {path.name[:40] for path in (cache / 'datasets').glob('*')} | {path.name for path in (cache / 'binoutput').glob('*')}
        return [Revision(**item, downloaded=item['commit'] in downloaded) for item in cached[1]]

    @application.get('/api/datasets', response_model=PreparedDatasets)
    def datasets():
        '''The datasets already downloaded and prepared on this server, which requests can pick with X-Dataset.'''
        try:
            found = prepared_datasets(profile)
            active = load_config(profile)
            excel_marker = Path(active['RepoPath']) / '.prepared.json'
            active_excel = json.loads(excel_marker.read_text(encoding='utf-8'))['commit'] if excel_marker.is_file() else None
            bin_marker = Path(active['BinPath']).parent / '.prepared.json' if active.get('BinPath') else None
            active_bin = json.loads(bin_marker.read_text(encoding='utf-8'))['commit'] if bin_marker and bin_marker.is_file() else None
        except (OSError, ValueError, KeyError):
            found, active_excel, active_bin = prepared_datasets(profile), None, None
        return PreparedDatasets(
            excel=[PreparedRevision(source=item['source'], commit=item['commit'], title=commit_title(item['source'], item['commit']),
                                    active=item['commit'] == active_excel) for item in found['excel']],
            binoutput=[PreparedRevision(source=item['source'], commit=item['commit'], title=commit_title(item['source'], item['commit']),
                                        active=item['commit'] == active_bin) for item in found['binoutput']],
        )

    @application.get('/api/dataset', response_model=DatasetStatus)
    def dataset(request: Request):
        status = DatasetStatus()
        try:
            raw = load_config(profile, require_prepared=False)
            status.source = raw.get('DataSource', 'local')
            if is_remote(raw):
                selected = selected_sources(raw)
                status.excel_source, status.binoutput_source = selected['excel'], selected['binoutput']
                revisions = selected_revisions(raw)
                status.excel_revision, status.binoutput_revision = revisions['excel'], revisions['binoutput']
            resolved = resolve(request)
            path = Path(resolved['RepoPath'])
            if not (path / 'MappedExcelBinOutput_EN').is_dir() or not (path / 'TextMap').is_dir():
                raise FileNotFoundError('The selected dataset is not prepared. Run dataset setup first.')
            marker = path / '.prepared.json'
            if marker.is_file():
                status.commit = json.loads(marker.read_text(encoding='utf-8'))['commit']
                status.excel_title = commit_title(status.excel_source, status.commit)
            if resolved.get('BinPath'):
                status.binoutput_path = resolved['BinPath']
                marker = Path(resolved['BinPath']).parent / '.prepared.json'
                if marker.is_file():
                    status.binoutput_commit = json.loads(marker.read_text(encoding='utf-8'))['commit']
                    status.binoutput_title = commit_title(status.binoutput_source, status.binoutput_commit)
            status.ready, status.path = True, str(path)
            status.tables = len(list((path / 'MappedExcelBinOutput_EN').glob('*.json')))
            status.languages = sum((path / 'TextMap' / f'TextMap{lang}.json').is_file() for lang in (
                'CHS', 'CHT', 'DE', 'EN', 'ES', 'FR', 'ID', 'JP', 'KR', 'PT', 'RU', 'TH', 'VI', 'TR', 'IT',
            ))
        except (OSError, ValueError, KeyError) as error:
            status.error = str(error)
        return status

    @application.put('/api/dataset/sources', response_model=DatasetStatus, dependencies=[Depends(local_only)])
    def choose_sources(body: SourceChoice, request: Request):
        if body.excel not in SOURCES or body.binoutput not in SOURCES:
            raise HTTPException(422, f'Sources must be one of: {", ".join(SOURCES)}.')
        if any(job.tool_id == 'dataset-setup' and job.status in ('queued', 'running') for job in manager(request).list_jobs()):
            raise HTTPException(409, 'Wait for dataset setup to finish before changing sources.')
        try:
            config = json.loads(profile.read_text(encoding='utf-8'))
            if not is_remote(config):
                raise HTTPException(409, 'Sources apply to downloaded data. Set "DataSource": "remote" in the profile first.')
            config[SOURCE_SETTINGS['excel'][0]] = body.excel
            config[SOURCE_SETTINGS['binoutput'][0]] = body.binoutput
            config[REVISION_SETTINGS['excel']] = body.excel_revision
            config[REVISION_SETTINGS['binoutput']] = body.binoutput_revision
            selected_revisions(config)
            temporary = profile.with_name(f'.{profile.name}.tmp')
            temporary.write_text(json.dumps(config, indent=4, ensure_ascii=False) + '\n', encoding='utf-8')
            temporary.replace(profile)
        except (OSError, ValueError) as error:
            raise HTTPException(409, str(error)) from error
        return dataset(request)

    def prepared(request: Request) -> dict:
        try:
            return resolve(request)
        except (OSError, ValueError, KeyError) as error:
            raise HTTPException(409, str(error)) from error

    @application.post('/api/other-languages', response_model=list[LanguageResult])
    def other_languages(body: LanguageInputs, config: dict = Depends(prepared)):
        try:
            directory = Path(config['RepoPath']) / 'TextMap'
            results = language_results(directory, data_root(profile) / 'ol', body.text.strip(), body.input_lang)
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            raise HTTPException(409, f'Could not look up Other Languages: {error}') from error
        if not results:
            raise HTTPException(404, f'No matching name or TextMapHash found in the {body.input_lang} TextMap.')
        return [LanguageResult(textmap_hash=result['textmap_hash'], text='\n'.join(
            line for line in result['text'].split('\n')
            if not (not body.translation and re.match(r'\|\w+_tl\s*=', line))
            and not (not body.romanization and re.match(r'\|\w+_rm\s*=', line))
        )) for result in results]

    @application.get('/api/characters', response_model=list[Character])
    def characters(config: dict = Depends(prepared)):
        try:
            path = Path(config['RepoPath']) / 'MappedExcelBinOutput_EN' / 'AvatarExcelConfigData.json'
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

    @application.get('/api/characters/{character_id}/version')
    def character_version(character_id: int, config: dict = Depends(prepared)):
        from wikiVersion import release_version

        character = next((item for item in characters(config) if item.id == character_id), None)
        if character is None:
            raise HTTPException(404, 'Character not found.')
        try:
            return {'character': character.name, 'version': release_version(character.name)}
        except (OSError, ValueError) as error:
            raise HTTPException(502, f'Could not reach the wiki: {error}') from error

    @application.get('/api/characters/{character_id}/passives')
    def character_passives(character_id: int, config: dict = Depends(prepared)):
        from passiveTypes import character_passive_types

        try:
            return {'types': character_passive_types(character_id, Path(config['RepoPath']) / 'MappedExcelBinOutput_EN')}
        except ValueError as error:
            raise HTTPException(404, str(error)) from error
        except OSError as error:
            raise HTTPException(409, str(error)) from error

    def found_references(config: dict, character_id: int):
        try:
            return character_references(config, character_id)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise HTTPException(409, str(error)) from error

    def reference_text(found: list[dict], key: str) -> dict:
        item = next((item for item in found if item['key'] == key), None)
        if item is None:
            raise HTTPException(404, 'Reference file not found.')
        try:
            return {'text': read_reference(item)}
        except OverflowError as error:
            raise HTTPException(413, str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(409, str(error)) from error

    def reference_list(name: str, found: list[dict], warnings=()) -> dict:
        return {'character': name, 'warnings': warnings, 'files': [
            {key: item[key] for key in ('key', 'relative', 'group', 'name', 'size', 'reasons')} for item in found]}

    @application.get('/api/characters/{character_id}/references')
    def character_reference_list(character_id: int, config: dict = Depends(prepared)):
        return reference_list(*found_references(config, character_id))

    @application.get('/api/characters/{character_id}/references/{key:path}')
    def character_reference(character_id: int, key: str, config: dict = Depends(prepared)):
        return reference_text(found_references(config, character_id)[1], key)

    def binoutput_references(config, character_id, enemy_id, gadget_id):
        if sum(value is not None for value in (character_id, enemy_id, gadget_id)) > 1:
            raise HTTPException(422, 'Choose only one character, enemy, or gadget.')
        try:
            if character_id is not None:
                return character_references(config, character_id)
            if enemy_id is not None:
                return enemy_references(config, enemy_id)
            if gadget_id is not None:
                return gadget_references(config, gadget_id)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise HTTPException(409, str(error)) from error
        raise HTTPException(422, 'Choose a character, enemy, or gadget.')

    @application.get('/api/binoutput/tree')
    def binoutput_directory(path: str = Query('', max_length=4096), config: dict = Depends(prepared)):
        try:
            return binoutput_tree(config, path)
        except FileNotFoundError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except OSError as error:
            raise HTTPException(409, str(error)) from error

    @application.get('/api/binoutput/references')
    def binoutput_reference_list(character_id: int | None = Query(None, ge=1),
                                 enemy_id: int | None = Query(None, ge=1),
                                 gadget_id: int | None = Query(None, ge=1), config: dict = Depends(prepared)):
        name, found, warnings = binoutput_references(config, character_id, enemy_id, gadget_id)
        result = reference_list(name, found, warnings)
        for item in result['files']:
            item['key'] = item['relative']
        return result

    @application.get('/api/binoutput/file')
    def binoutput_file(path: str = Query(..., min_length=1, max_length=4096),
                       character_id: int | None = Query(None, ge=1), enemy_id: int | None = Query(None, ge=1),
                       gadget_id: int | None = Query(None, ge=1),
                       config: dict = Depends(prepared)):
        if character_id is not None or enemy_id is not None or gadget_id is not None:
            found = binoutput_references(config, character_id, enemy_id, gadget_id)[1]
            return reference_text([{**item, 'key': item['relative']} for item in found], path)
        try:
            file = binoutput_path(config, path)
            return {'text': read_reference({'path': file})}
        except OverflowError as error:
            raise HTTPException(413, str(error)) from error
        except FileNotFoundError as error:
            raise HTTPException(404, str(error)) from error
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        except OSError as error:
            raise HTTPException(409, str(error)) from error

    def mapped_table(config: dict, name: str, setting: str = 'RepoPath') -> list[dict]:
        path = Path(config[setting]) / 'MappedExcelBinOutput_EN' / f'{name}.json'
        if not path.is_file():
            raise FileNotFoundError(f'{setting} has no mapped {name} table: {path}')
        return json.loads(path.read_text(encoding='utf-8'))

    # (ids, names) of an older build's monsters per revision and dataset; raw tables are fetched from Git.
    monster_builds: dict[tuple[str, str], tuple[set, set]] = {}

    def monster_build(config: dict, value: str) -> tuple[set, set]:
        if value == 'current':
            return monster_set(mapped_table(config, 'MonsterExcelConfigData'))
        if value == 'config':
            return monster_set(mapped_table(config, 'MonsterExcelConfigData', 'RepoPathOld'))
        key = (value, config['RepoPath'])
        if key not in monster_builds:
            describe = {row['Id']: row.get('NameTextMapHash') for row in mapped_table(config, 'MonsterDescribeExcelConfigData')}
            monster_builds[key] = monster_set(excel_table_at(value, 'MonsterExcelConfigData', profile), describe)
        return monster_builds[key]

    # Row IDs of a table per build, revision and dataset; raw tables are fetched from Git.
    id_builds: dict[tuple[str, str, str], set] = {}

    def build_ids(config: dict, value: str, table: str) -> set:
        if value == 'current':
            rows = mapped_table(config, table)
        elif value == 'config':
            rows = mapped_table(config, table, 'RepoPathOld')
        else:
            key = (value, table, config['RepoPath'])
            if key not in id_builds:
                id_builds[key] = {row.get('Id', row.get('id')) for row in excel_table_at(value, table, profile)}
            return id_builds[key]
        return {row.get('Id', row.get('id')) for row in rows}

    def added_ids(config: dict, table: str, older: str | None, newer: str) -> set | None:
        '''IDs in the newer build but not the older one, or None when not comparing.'''
        if not older:
            return None
        return build_ids(config, newer, table) - build_ids(config, older, table)

    @application.get('/api/versions')
    def versions(request: Request, table: str = Query('MonsterExcelConfigData', pattern=r'^\w+$')):
        return build_versions(request, table)

    @application.get('/api/enemies/versions')
    def enemy_versions(request: Request):
        return build_versions(request, 'MonsterExcelConfigData')

    def build_versions(request: Request, table: str):
        try:
            raw = load_config(profile, require_prepared=False)
            options, older = [{'value': 'current', 'label': 'Active dataset', 'version': None}], None
            if is_remote(raw):
                source, active = selected_sources(raw)['excel'], dataset(request).commit
                cached = revision_cache.get(f'{source}:100')
                if cached is None or time.monotonic() - cached[0] > 600:
                    revision_cache[f'{source}:100'] = cached = (time.monotonic(), list_revisions(source, 100))
                options, older = version_options(cached[1], active, game_version)
            old_path = raw.get('RepoPathOld')
            if old_path and (Path(old_path) / 'MappedExcelBinOutput_EN' / f'{table}.json').is_file():
                options.append({'value': 'config', 'label': 'RepoPathOld (scriptconfig.json)', 'version': None})
                older = older or 'config'
        except (OSError, ValueError, KeyError) as error:
            raise HTTPException(502, f'Could not list versions: {error}') from error
        return {'options': options, 'older': older, 'newer': 'current'}

    @application.get('/api/enemies')
    def enemies(older: str | None = Query(None, pattern=BUILD), newer: str = Query('current', pattern=BUILD),
                new_names_only: bool = False, config: dict = Depends(prepared)):
        try:
            rows = mapped_table(config, 'MonsterExcelConfigData')
            if older:
                rows = added_monsters(rows, monster_build(config, older),
                                      None if newer == 'current' else monster_build(config, newer), new_names_only)
            else:
                rows = [row for row in rows if has_name(row)]
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
            raise HTTPException(409, str(error)) from error
        return sorted(({'id': row['Id'], 'name': row['DescribeName'], 'internal': row.get('MonsterName') or ''}
                       for row in rows), key=lambda item: (item['name'].lower(), item['id']))

    @application.get('/api/gadgets')
    def gadgets(config: dict = Depends(prepared)):
        try:
            rows = gadget_rows(config)
            return sorted(({'id': row['Id'], 'name': row.get('JsonName') or 'Unnamed Gadget',
                            'internal': row.get('Type') or ''} for row in rows),
                          key=lambda item: (item['name'].casefold(), item['id']))
        except (OSError, ValueError, KeyError) as error:
            raise HTTPException(409, str(error)) from error

    @application.get('/api/fishing-points')
    def fishing_point_list(older: str | None = Query(None, pattern=BUILD), newer: str = Query('current', pattern=BUILD),
                           config: dict = Depends(prepared)):
        from utils.fishing import city_names, fishing_points

        try:
            pools = mapped_table(config, 'FishPoolExcelConfigData')
            cities = city_names(mapped_table(config, 'CityConfigData'))
            added = added_ids(config, 'FishPoolExcelConfigData', older, newer)
            regions = {pool['Id']: cities.get(pool.get('CityId'), '') for pool in pools}
            items = [{'id': pool_id, 'name': title, 'internal': regions[pool_id]}
                     for pool_id, title in fishing_points(pools).items() if added is None or pool_id in added]
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
            raise HTTPException(409, str(error)) from error
        return sorted(items, key=lambda item: (item['name'].lower(), item['id']))

    @application.get('/api/bounties')
    def bounty_items(older: str | None = Query(None, pattern=BUILD), newer: str = Query('current', pattern=BUILD),
                     config: dict = Depends(prepared)):
        from utils.fishing import city_names
        from utils.hunting import bounty_list

        try:
            table = 'HuntingV2MonsterBundleExcelConfigData'
            added = added_ids(config, table, older, newer)
            items = bounty_list(mapped_table(config, table), mapped_table(config, 'HuntingV2RegionExcelConfigData'),
                                mapped_table(config, 'MonsterExcelConfigData'),
                                city_names(mapped_table(config, 'CityConfigData')))
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
            raise HTTPException(409, str(error)) from error
        return [item for item in items if added is None or item['id'] in added]

    @application.get('/api/periods/{kind}')
    def period_list(kind: str, config: dict = Depends(prepared)):
        '''Spiral Abyss rotations or Stygian Onslaught events of the dataset, newest first.'''
        from utils.periods import PERIODS

        if kind not in PERIODS:
            raise HTTPException(404, f'Unknown period list: {kind}')
        table, listing = PERIODS[kind]
        try:
            return listing(mapped_table(config, table))
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise HTTPException(409, str(error)) from error

    @application.get('/api/date-versions')
    def date_version_list(dates: str = Query(min_length=10, max_length=2200, pattern=r'^\d{4}-\d{2}-\d{2}(,\d{4}-\d{2}-\d{2})*$')):
        '''{date: version} from the wiki's Date to Version, for comma-separated YYYY-MM-DD dates.'''
        from wikiVersion import date_versions

        try:
            return date_versions(dates.split(','))
        except (OSError, ValueError) as error:
            raise HTTPException(502, f'Could not reach the wiki: {error}') from error

    @application.get('/api/jobs', response_model=list[Job])
    def jobs(request: Request):
        return manager(request).list_jobs(client(request))

    @application.post('/api/jobs', response_model=Job, status_code=202)
    def run_tool(body: RunRequest, request: Request):
        if body.tool_id not in TOOLS:
            raise HTTPException(404, 'Tool not found.')
        if hosted:
            manager(request).purge(HOSTED_JOB_AGE)
        return submit(request, body.tool_id, body.parameters)

    @application.post('/api/dataset/setup', response_model=Job, status_code=202, dependencies=[Depends(local_only)])
    def setup(request: Request, body: dict[str, JsonValue]):
        if body:
            raise HTTPException(422, 'Dataset setup does not accept parameters.')
        return submit(request, 'dataset-setup', {})

    @application.get('/api/jobs/{job_id}', response_model=Job)
    def job_detail(job_id: str, request: Request):
        return get_job(request, job_id)

    @application.delete('/api/jobs/{job_id}', status_code=204)
    def delete_job(job_id: str, request: Request):
        try:
            manager(request).delete(job_id, client(request))
        except KeyError:
            raise HTTPException(404, 'Job not found.') from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @application.put('/api/jobs/{job_id}/files/{name:path}', response_model=Job)
    def save_file(job_id: str, name: str, body: TextBody, request: Request):
        try:
            return manager(request).save_text(job_id, name, body.text, client(request))
        except (KeyError, FileNotFoundError):
            raise HTTPException(404, 'Output file not found.') from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @application.get('/api/jobs/{job_id}/logs')
    def logs(job_id: str, request: Request, full: bool = False):
        get_job(request, job_id)
        path = manager(request).root / job_id / 'log.txt'
        if not path.is_file():
            return {'text': '', 'truncated': False}
        with path.open('rb') as file:
            size = path.stat().st_size
            file.seek(0 if full else max(0, size - 131072))
            text = file.read().decode('utf-8', errors='replace')
        return {'text': text, 'truncated': not full and size > 131072}

    def job_references(request: Request, job_id: str):
        job = get_job(request, job_id)
        if job.tool_id != 'character-kit':
            raise HTTPException(404, 'This job has no game data references.')
        try:
            character_id = int(job.parameters.get('character_id') or json.loads(
                (manager(request).root / job_id / 'request.json').read_text(encoding='utf-8'))['parameters']['character_id'])
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise HTTPException(409, str(error)) from error
        return found_references(prepared(request), character_id)

    @application.get('/api/jobs/{job_id}/references')
    def references(job_id: str, request: Request):
        return reference_list(*job_references(request, job_id))

    @application.get('/api/jobs/{job_id}/references/{key:path}')
    def reference(job_id: str, key: str, request: Request):
        return reference_text(job_references(request, job_id)[1], key)

    def output_path(request: Request, job_id: str, name: str) -> Path:
        try:
            return manager(request).file(job_id, name, client(request))
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

    def bot(request: Request) -> BotManager:
        local_only()
        return request.app.state.bot

    def relay_client(request: Request) -> str:
        identity = client(request)
        if identity is None:
            # Locally there is only one user.
            return 'local'
        return identity

    @application.post('/api/wiki/login')
    def wiki_login(body: RelayLogin, request: Request):
        '''Logs a browser's own bot account in; the server only keeps the session cookie in memory.'''
        try:
            return request.app.state.relay.login(relay_client(request), body)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        except WikiError as error:
            raise HTTPException(502, str(error)) from error

    @application.post('/api/wiki/post')
    def wiki_post(body: RelayPost, request: Request):
        try:
            return request.app.state.relay.post(relay_client(request), body)
        except KeyError:
            raise HTTPException(401, 'The wiki session expired. Log in again.') from None

    @application.post('/api/wiki/logout', status_code=204)
    def wiki_logout(request: Request, body: dict[str, JsonValue]):
        session = body.get('session')
        if isinstance(session, str):
            request.app.state.relay.logout(relay_client(request), session)

    @application.get('/api/bot', response_model=BotState)
    def bot_state(request: Request):
        return bot(request).state()

    @application.put('/api/bot/settings', response_model=BotState)
    def bot_settings(body: SettingsUpdate, request: Request):
        try:
            return bot(request).update_settings(body)
        except (OSError, ValueError) as error:
            raise HTTPException(409, str(error)) from error

    @application.post('/api/bot/login')
    def bot_login(request: Request):
        try:
            return {'username': bot(request).test_login()}
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        except WikiError as error:
            raise HTTPException(502, str(error)) from error

    @application.post('/api/bot/queue', status_code=201)
    def bot_enqueue(body: QueueFiles, request: Request):
        job = get_job(request, body.job_id)
        if job.status in ('queued', 'running'):
            raise HTTPException(409, 'Wait for the job to finish before queueing its files.')
        files = [(name, output_path(request, job.id, name)) for name in dict.fromkeys(body.paths)]
        try:
            added, skipped = bot(request).add(f'{job.name} {job.id[:8]}', job.id, files)
        except (OSError, ValueError) as error:
            raise HTTPException(409, str(error)) from error
        return {'added': added, 'skipped': skipped}

    @application.get('/api/bot/queue/{item_id}', response_model=QueueItem)
    def bot_item(item_id: str, request: Request):
        try:
            return bot(request).get(item_id)
        except KeyError:
            raise HTTPException(404, 'Queued page not found.') from None

    @application.get('/api/bot/queue/{item_id}/media')
    def bot_media(item_id: str, request: Request):
        try:
            return FileResponse(bot(request).media(item_id))
        except KeyError:
            raise HTTPException(404, 'Queued file not found.') from None

    @application.patch('/api/bot/queue/{item_id}', response_model=QueueItem)
    def bot_edit(item_id: str, body: QueueEdit, request: Request):
        try:
            return bot(request).update(item_id, body.title, body.content)
        except KeyError:
            raise HTTPException(404, 'Queued page not found.') from None
        except (OSError, ValueError) as error:
            raise HTTPException(409, str(error)) from error

    @application.post('/api/bot/queue/remove', response_model=BotState)
    def bot_remove(body: QueueIds, request: Request):
        try:
            bot(request).remove(body.ids)
        except (OSError, ValueError) as error:
            raise HTTPException(409, str(error)) from error
        return bot(request).state()

    @application.post('/api/bot/queue/reset', response_model=BotState)
    def bot_reset(body: QueueIds, request: Request):
        bot(request).reset(body.ids)
        return bot(request).state()

    @application.post('/api/bot/post', response_model=BotState, status_code=202)
    def bot_post(body: PostRequest, request: Request):
        try:
            return bot(request).start(body.ids)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @application.post('/api/bot/stop', response_model=BotState)
    def bot_stop(request: Request):
        bot(request).stop()
        return bot(request).state()

    if assets.is_dir():
        application.mount('/', StaticFiles(directory=assets, html=True), name='frontend')
    else:
        @application.get('/')
        def missing_frontend():
            raise HTTPException(503, 'Build the frontend first: npm --prefix frontend run build')

    return application


app = create_app()
