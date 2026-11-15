import json
import os
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent


def config_path():
    return Path(os.environ.get('GENSHIN_TOOLS_CONFIG', ROOT / 'scriptconfig.json')).resolve()


def cache_path(path):
    return path.parent / '.data' / 'AnimeGameData'


def dataset_path(cache, revision):
    commit = revision.get('commit', '')
    pipeline = revision.get('pipeline', '')
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid GitHub dataset commit in setup metadata.')
    if not isinstance(pipeline, str) or not re.fullmatch(r'[0-9a-f]{64}', pipeline):
        raise ValueError('Invalid GitHub preprocessing version in setup metadata.')
    return cache / 'datasets' / f'{commit}-{pipeline[:12]}'


def load_config(path=None, *, require_prepared=True):
    path = Path(path).resolve() if path is not None else config_path()
    with path.open(encoding='utf-8') as file:
        config = json.load(file)

    source = config.get('DataSource', 'local')
    if source not in ('local', 'github'):
        raise ValueError('DataSource must be "local" or "github".')

    if source == 'github' and require_prepared:
        cache = cache_path(path)
        try:
            with (cache / 'ready.json').open(encoding='utf-8') as file:
                revision = json.load(file)
            dataset = dataset_path(cache, revision)
            with (dataset / '.prepared.json').open(encoding='utf-8') as file:
                prepared = json.load(file)
        except FileNotFoundError as error:
            raise FileNotFoundError(
                'GitHub data is not prepared. Run quickSetup.bat (or python setupData.py) first.'
            ) from error
        if prepared != revision:
            raise ValueError('GitHub setup metadata does not match. Run quickSetup.bat again.')
        config['RepoPath'] = str(dataset)

    return config
