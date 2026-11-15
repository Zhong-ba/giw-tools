import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from dataSource import ROOT, cache_path, config_path, dataset_path, load_config


GITHUB_REPOSITORY = 'https://github.com/DimbreathBot/AnimeGameData.git'
PIPELINE_FILES = (
    ROOT / 'setupData.py', ROOT / 'textMapCleanup.py',
    ROOT / 'leo' / 'ExcelMapEN.js', ROOT / 'leo' / 'config.js',
)


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def git(repository, *arguments, capture=False):
    result = run(
        ['git', '--git-dir', str(repository), *map(str, arguments)],
        stdout=subprocess.PIPE if capture else None,
        text=True,
    )
    return result.stdout.strip() if capture else None


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_outputs(dataset):
    excel = dataset / 'ExcelBinOutput'
    if not excel.is_dir():
        raise FileNotFoundError(f'Missing raw Excel directory: {excel}')
    expected = [
        path.name for path in excel.glob('*.json')
        if path.name != 'DialogExcelConfigData.json'
    ]
    if not expected:
        raise ValueError(f'No Excel tables found in {excel}')
    missing = [
        name for name in expected
        if not (dataset / 'MappedExcelBinOutput_EN' / name).is_file()
    ]
    if missing:
        raise FileNotFoundError(f'Excel mapping did not produce: {", ".join(missing)}')
    if not (dataset / 'MappedToID' / 'AvatarExcelConfigData.json').is_file():
        raise FileNotFoundError('Excel mapping did not produce the avatar ID index.')


def preprocess(config):
    dataset = Path(config['RepoPath']).resolve()
    child_config = dict(config, DataSource='local', RepoPath=str(dataset))
    with tempfile.TemporaryDirectory(prefix='genshin-setup-') as temporary:
        path = Path(temporary) / 'scriptconfig.json'
        path.write_text(json.dumps(child_config), encoding='utf-8')
        environment = dict(os.environ, GENSHIN_TOOLS_CONFIG=str(path))
        print('Merging TextMaps and cleaning English text...', flush=True)
        run([sys.executable, str(ROOT / 'textMapCleanup.py')], cwd=ROOT, env=environment)
        print('Mapping English Excel tables...', flush=True)
        run(['node', str(ROOT / 'leo' / 'ExcelMapEN.js')], cwd=ROOT, env=environment)
    validate_outputs(dataset)
    return dataset


def prepare_github(config, path):
    cache = cache_path(path)
    cache.mkdir(parents=True, exist_ok=True)
    lock = cache / 'setup.lock'
    try:
        with lock.open('x', encoding='utf-8') as file:
            file.write(str(os.getpid()))
    except FileExistsError as error:
        raise FileExistsError(
            f'Setup is already running, or was interrupted. Check the process recorded in {lock} '
            'before removing that lock file.'
        ) from error

    try:
        repository = cache / 'repository.git'
        if not repository.exists():
            print('Initializing the GitHub data cache...', flush=True)
            run([
                'git', 'clone', '--bare', '--depth=1', '--filter=blob:none',
                '--single-branch', '--branch=main', GITHUB_REPOSITORY, str(repository),
            ])
            reference = 'HEAD'
        else:
            origin = git(repository, 'remote', 'get-url', 'origin', capture=True)
            if origin != GITHUB_REPOSITORY:
                raise ValueError(f'Unexpected repository origin in {repository}: {origin}')
            print('Checking GitHub main for updates...', flush=True)
            git(repository, 'fetch', '--depth=1', '--filter=blob:none', 'origin', 'main')
            reference = 'FETCH_HEAD'

        commit = git(repository, 'rev-parse', reference, capture=True)
        if commit is None:
            raise RuntimeError('Git did not return the downloaded commit.')
        git(repository, 'config', 'core.longpaths', 'true')
        digest = hashlib.sha256()
        for filename in PIPELINE_FILES:
            digest.update(filename.read_bytes())
        revision = {'commit': commit, 'pipeline': digest.hexdigest()}
        dataset = dataset_path(cache, revision)
        marker = dataset / '.prepared.json'

        if marker.is_file():
            with marker.open(encoding='utf-8') as file:
                if json.load(file) != revision:
                    raise ValueError(f'Unexpected preparation metadata in {marker}')
            validate_outputs(dataset)
            print(f'Using already-prepared GitHub revision {commit}.', flush=True)
        else:
            if not dataset.exists():
                dataset.parent.mkdir(parents=True, exist_ok=True)
                git(repository, 'worktree', 'add', '--detach', '--no-checkout', dataset, commit)
            run([
                'git', '-C', str(dataset), 'sparse-checkout', 'set', '--cone',
                'ExcelBinOutput', 'TextMap', str(Path('BinOutput') / 'Monster'),
            ])
            run(['git', '-C', str(dataset), 'checkout', '--detach', commit])
            # A failed attempt may have already rewritten some tracked TextMaps.
            run(['git', '-C', str(dataset), 'restore', '--source=HEAD', '--worktree', '--', 'TextMap'])
            preprocess(dict(config, RepoPath=str(dataset)))
            write_json(marker, revision)

        write_json(cache / 'ready.json', revision)
        return dataset
    finally:
        lock.unlink()


def prepare(path=None):
    path = Path(path).resolve() if path is not None else config_path()
    config = load_config(path, require_prepared=False)
    if shutil.which('node') is None:
        raise FileNotFoundError('Node.js is required for Excel mapping. Install it before running setup.')
    if config.get('DataSource', 'local') == 'github':
        if shutil.which('git') is None:
            raise FileNotFoundError('Git is required to download AnimeGameData.')
        dataset = prepare_github(config, path)
    else:
        dataset = preprocess(config)
    print(f'Dataset ready: {dataset}', flush=True)
    return dataset


def main():
    parser = argparse.ArgumentParser(description='Download selected game data and run the quick-setup pipeline.')
    parser.add_argument('--config', type=Path, help='Configuration file (defaults to scriptconfig.json beside the tools).')
    args = parser.parse_args()
    try:
        prepare(args.config)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Setup failed: {error}\n')


if __name__ == '__main__':
    main()
