import json
import os
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent

SOURCES = {
    'dimbreath': {
        'label': 'DimbreathBot/AnimeGameData',
        'url': 'https://github.com/DimbreathBot/AnimeGameData.git',
        'branch': 'main',
        'cache': 'AnimeGameData',
        'commits_api': 'https://api.github.com/repos/DimbreathBot/AnimeGameData/commits?sha=main&per_page={limit}',
    },
    'gura': {
        'label': 'GuraFoundation/YuanShenResources',
        'url': 'https://gitlab.com/GuraFoundation/YuanShenResources.git',
        'branch': 'main',
        'cache': 'YuanShenResources',
        'commits_api': 'https://gitlab.com/api/v4/projects/GuraFoundation%2FYuanShenResources/repository/commits?ref_name=main&per_page={limit}',
    },
}
# ExcelSource also supplies the TextMaps, because Excel text hashes must resolve against the same build.
SOURCE_SETTINGS = {'excel': ('ExcelSource', 'dimbreath'), 'binoutput': ('BinOutputSource', 'gura')}
# "latest" follows the source branch; a full commit hash pins that revision.
REVISION_SETTINGS = {'excel': 'ExcelRevision', 'binoutput': 'BinOutputRevision'}
LATEST = 'latest'
REMOTE_MODES = ('remote', 'github')


def config_path():
    return Path(os.environ.get('GENSHIN_TOOLS_CONFIG', ROOT / 'scriptconfig.json')).resolve()


def data_root(path):
    return path.parent / '.data'


def cache_path(path, source='dimbreath'):
    return data_root(path) / SOURCES[source]['cache']


def is_remote(config):
    return config.get('DataSource', 'local') in REMOTE_MODES


def selected_sources(config):
    selected = {}
    for role, (key, default) in SOURCE_SETTINGS.items():
        source = config.get(key, default)
        if source not in SOURCES:
            raise ValueError(f'{key} must be one of: {", ".join(SOURCES)}.')
        selected[role] = source
    return selected


def selected_revisions(config):
    selected = {}
    for role, key in REVISION_SETTINGS.items():
        revision = config.get(key, LATEST)
        if revision != LATEST and not (isinstance(revision, str) and re.fullmatch(r'[0-9a-f]{40}', revision)):
            raise ValueError(f'{key} must be "{LATEST}" or a full 40-character commit hash.')
        selected[role] = revision
    return selected


def _commit(revision):
    commit = revision.get('commit', '')
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid dataset commit in setup metadata.')
    return commit


def excel_dataset_path(path, revision):
    pipeline = revision.get('pipeline', '')
    if not isinstance(pipeline, str) or not re.fullmatch(r'[0-9a-f]{64}', pipeline):
        raise ValueError('Invalid preprocessing version in setup metadata.')
    return cache_path(path, revision['source']) / 'datasets' / f'{_commit(revision)}-{pipeline[:12]}'


def binoutput_path(path, revision):
    return cache_path(path, revision['source']) / 'binoutput' / _commit(revision)


def load_config(path=None, *, require_prepared=True, prepared=None):
    '''The profile with RepoPath and BinPath resolved to the prepared dataset.

    `prepared` ({'excel': revision, 'binoutput': revision}, as in ready.json) picks another downloaded
    dataset instead of the active one, regardless of the sources and revisions the profile selects.
    '''
    path = Path(path).resolve() if path is not None else config_path()
    with path.open(encoding='utf-8') as file:
        config = json.load(file)

    source = config.get('DataSource', 'local')
    if source not in ('local', *REMOTE_MODES):
        raise ValueError('DataSource must be "local" or "remote" ("github" is accepted as "remote").')
    if source == 'local':
        return config
    selected = selected_sources(config)
    selected_revisions(config)
    if not require_prepared:
        return config

    try:
        if prepared is not None:
            ready, selected = prepared, {}
        else:
            with (data_root(path) / 'ready.json').open(encoding='utf-8') as file:
                ready = json.load(file)
        revisions = selected_revisions(config)
        for role, choice in selected.items():
            if not isinstance(ready.get(role), dict) or ready[role].get('source') not in SOURCES:
                raise FileNotFoundError(role)
            if ready[role]['source'] != choice:
                raise ValueError(
                    f'The prepared {role} data comes from {SOURCES[ready[role]["source"]]["label"]}, but '
                    f'{SOURCE_SETTINGS[role][0]} selects {SOURCES[choice]["label"]}. Run quickSetup.bat again.'
                )
            if revisions[role] != LATEST and ready[role].get('commit') != revisions[role]:
                raise ValueError(
                    f'The prepared {role} data is not the revision {REVISION_SETTINGS[role]} selects '
                    f'({revisions[role][:8]}). Run quickSetup.bat again.'
                )
        excel = excel_dataset_path(path, ready['excel'])
        binoutput = binoutput_path(path, ready['binoutput'])
        for role, directory in (('excel', excel), ('binoutput', binoutput)):
            with (directory / '.prepared.json').open(encoding='utf-8') as file:
                if json.load(file) != ready[role]:
                    raise ValueError('Dataset setup metadata does not match. Run quickSetup.bat again.')
    except FileNotFoundError as error:
        raise FileNotFoundError(
            'Remote data is not prepared. Run quickSetup.bat (or python setupData.py) first.'
        ) from error
    config['RepoPath'] = str(excel)
    config['BinPath'] = str(binoutput / 'BinOutput')
    return config
