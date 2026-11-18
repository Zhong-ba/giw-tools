import argparse
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import toolLog as report

from dataSource import (
    LATEST, ROOT, SOURCES, binoutput_path, cache_path, config_path, data_root, excel_dataset_path,
    is_remote, load_config, selected_revisions, selected_sources,
)


SCHEMA = ROOT / 'leo' / 'dataSchema.json'
# The viewer browses the complete tree, including enemy abilities and shared gadgets.
BINOUTPUT_PATHS = ['/BinOutput/']
# Bump when BINOUTPUT_PATHS or BinOutput preparation changes so prepared snapshots are refreshed.
BINOUTPUT_LAYOUT = 6
# Scrambled BinOutput keys are recovered by matching values against this source's readable copy.
READABLE_SOURCE = 'dimbreath'
# Only the Excel aliases in SCHEMA affect preparation; they are fingerprinted separately.
PIPELINE_FILES = (
    ROOT / 'setupData.py', ROOT / 'textmapcleanup.py',
    ROOT / 'leo' / 'ExcelMapEN.js', ROOT / 'leo' / 'config.js', ROOT / 'leo' / 'normalize.js',
)


def pipeline_version():
    digest = hashlib.sha256()
    for filename in PIPELINE_FILES:
        digest.update(filename.read_bytes())
    with SCHEMA.open(encoding='utf-8') as file:
        digest.update(json.dumps(json.load(file)['aliases'], sort_keys=True).encode('utf-8'))
    return digest.hexdigest()


def run(command, **kwargs):
    if (kwargs.get('stdout') is not None or not kwargs.get('text', True)
            or set(kwargs) - {'cwd', 'env', 'text', 'stdout'}):
        return subprocess.run(command, check=True, **kwargs)
    options = dict(kwargs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                   text=True, encoding='utf-8', errors='replace')
    with subprocess.Popen(command, **options) as process:
        if process.stdout is None:
            raise RuntimeError('The setup command did not provide an output stream.')
        for line in process.stdout:
            report.info(line.rstrip('\r\n'))
        code = process.wait()
    if code:
        raise subprocess.CalledProcessError(code, command)
    return subprocess.CompletedProcess(command, code)


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


def check_fields(dataset):
    """Warn about fields the tools read that this build does not provide under any known name."""
    with SCHEMA.open(encoding='utf-8') as file:
        required = json.load(file)['required']
    warnings = []
    for table, fields in report.track(list(required.items()), 'Checking required dataset fields'):
        path = dataset / 'MappedExcelBinOutput_EN' / f'{table}.json'
        if not path.is_file():
            warnings.append(f'{table} is not in this build ({", ".join(fields)} unavailable).')
            continue
        with path.open(encoding='utf-8') as file:
            rows = json.load(file)
        present = {key for row in rows if isinstance(row, dict) for key in row}
        missing = [field for field in fields if field not in present]
        if missing:
            warnings.append(f'{table} has no {", ".join(missing)}.')
    for warning in warnings:
        report.warning(f'{warning} Tools using it may fail; add the new field name to {SCHEMA.name}.')
    return warnings


def check_monsters(directory, sample_size=400):
    """Report how many monster configs expose weight and endure type, warning when names look stale."""
    from utils.monsterConfig import monster_property
    files = sorted(directory.glob('*.json'))
    sample = files[::max(1, len(files) // sample_size)]
    readable = 0
    for path in report.track(sample, 'Checking monster config readability'):
        try:
            with path.open(encoding='utf-8') as file:
                found = monster_property(json.load(file))
        except (OSError, ValueError):
            continue
        if found and found.get('endureType') and (found.get('weight') or found.get('bonusRange')):
            readable += 1
    report.info(f'Monster configs with weight and endure type: {readable} of {len(sample)} sampled.')
    if sample and readable < len(sample) * 0.8:
        report.warning('Few monster configs are readable. Scrambled names may have changed; update '
                       f'monsterConfig in {SCHEMA.name}.')
    return readable, len(sample)


def preprocess(config):
    dataset = Path(config['RepoPath']).resolve()
    child_config = dict(config, DataSource='local', RepoPath=str(dataset))
    with tempfile.TemporaryDirectory(prefix='genshin-setup-') as temporary:
        path = Path(temporary) / 'scriptconfig.json'
        path.write_text(json.dumps(child_config), encoding='utf-8')
        environment = dict(os.environ, GENSHIN_TOOLS_CONFIG=str(path))
        report.stage('Merging TextMaps and cleaning English text')
        run([sys.executable, str(ROOT / 'textmapcleanup.py')], cwd=ROOT, env=environment)
        report.stage('Mapping English Excel tables')
        run(['node', str(ROOT / 'leo' / 'ExcelMapEN.js')], cwd=ROOT, env=environment)
    report.stage('Validating mapped Excel tables')
    validate_outputs(dataset)
    check_fields(dataset)
    return dataset


def update_repository(path, source, revision=LATEST):
    spec = SOURCES[source]
    repository = cache_path(path, source) / 'repository.git'
    if not repository.exists():
        report.stage(f'Downloading {spec["label"]}')
        repository.parent.mkdir(parents=True, exist_ok=True)
        run([
            'git', 'clone', '--bare', '--depth=1', '--filter=blob:none',
            '--single-branch', f'--branch={spec["branch"]}', spec['url'], str(repository),
        ])
        reference = 'HEAD'
    else:
        origin = git(repository, 'remote', 'get-url', 'origin', capture=True)
        if origin != spec['url']:
            raise ValueError(f'Unexpected repository origin in {repository}: {origin}')
        reference = None
    git(repository, 'config', 'core.longpaths', 'true')
    if revision != LATEST:
        known = subprocess.run(['git', '--git-dir', str(repository), 'cat-file', '-e', f'{revision}^{{commit}}'],
                               capture_output=True).returncode == 0
        if not known:
            report.stage(f'Downloading {spec["label"]} revision {revision[:8]}')
            git(repository, 'fetch', '--depth=1', '--filter=blob:none', 'origin', revision)
        return repository, revision
    if reference is None:
        report.stage(f'Checking {spec["label"]} for updates')
        git(repository, 'fetch', '--depth=1', '--filter=blob:none', 'origin', spec['branch'])
        reference = 'FETCH_HEAD'
    commit = git(repository, 'rev-parse', reference, capture=True)
    if commit is None:
        raise RuntimeError('Git did not return the downloaded commit.')
    return repository, commit


def list_revisions(source, limit=30, page=1):
    """Recent commits of a source's branch from the hosting API: [{'commit', 'title', 'date'}]."""
    request = urllib.request.Request(SOURCES[source]['commits_api'].format(limit=limit) + f'&page={page}',
                                     headers={'User-Agent': 'genshin-wiki-tools', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        rows = json.load(response)
    revisions = []
    for row in rows:
        if 'sha' in row:  # GitHub
            commit, message, date = row['sha'], row['commit']['message'], row['commit']['committer']['date']
        else:  # GitLab
            commit, message, date = row['id'], row['message'], row['committed_date']
        revisions.append({'commit': commit, 'title': message.strip().splitlines()[0].strip("'"), 'date': date})
    return revisions


def all_revisions(source):
    """List the entire branch history, newest first."""
    page = 1
    result = []
    seen = set()
    while True:
        rows = list_revisions(source, 100, page)
        commits = {row['commit'] for row in rows}
        if seen.intersection(commits) or len(commits) != len(rows):
            raise ValueError(f'The {SOURCES[source]["label"]} revision listing contains duplicate commits.')
        seen.update(commits)
        result.extend(rows)
        if len(rows) < 100:
            return result
        page += 1


@contextmanager
def history_lock(path, exclusive):
    """Prevent hosted servers and historical maintenance from using the data simultaneously."""
    if os.name != 'posix':
        if exclusive:
            raise OSError('Historical maintenance requires POSIX file locking.')
        yield
        return
    import fcntl
    root = data_root(path)
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'history.lock').open('a') as file:
        try:
            fcntl.flock(file.fileno(), (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise OSError('Stop the hosted backend before historical maintenance, and wait for maintenance to finish '
                          'before starting it again.') from error
        try:
            yield
        finally:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)


@contextmanager
def history_reservation(path, size):
    """Reserve disk space while historical datasets are being prepared."""
    root = data_root(path)
    root.mkdir(parents=True, exist_ok=True)
    if not hasattr(os, 'posix_fallocate'):
        raise OSError('Historical setup requires a filesystem supporting posix_fallocate.')
    reservation = root / 'history-reserve'
    with reservation.open('xb') as file:
        try:
            os.posix_fallocate(file.fileno(), 0, size)
            yield
        finally:
            reservation.unlink()


def history_space(path, dates, before, minimum):
    """Make staging space by removing only known older, unprotected worktrees."""
    root = data_root(path)
    protected = set()
    ready = root / 'ready.json'
    if ready.is_file():
        with ready.open(encoding='utf-8') as file:
            active = json.load(file)
        protected.add(excel_dataset_path(path, active['excel']))
        protected.add(binoutput_path(path, active['binoutput']))
    candidates = []
    for source in SOURCES:
        cache = cache_path(path, source)
        for folder, role, locate in (
            ('datasets', 'excel', excel_dataset_path),
            ('binoutput', 'binoutput', binoutput_path),
        ):
            for marker in (cache / folder).glob('*/.prepared.json'):
                directory = marker.parent
                if directory.is_symlink():
                    continue
                with marker.open(encoding='utf-8') as file:
                    revision = json.load(file)
                if revision.get('source') != source or locate(path, revision) != directory:
                    raise ValueError(f'Invalid dataset metadata in {marker}')
                date = dates.get((role, source, revision['commit']))
                if date is not None and date < before:
                    candidates.append((date, source, directory))
                keys = directory / '.keys.json'
                if keys.is_file():
                    with keys.open(encoding='utf-8') as file:
                        protected.add(binoutput_path(path, json.load(file)['reference']))
    for _, source, directory in sorted(candidates):
        if shutil.disk_usage(root).free >= minimum:
            return True
        if directory in protected:
            continue
        report.info(f'Removing older dataset {directory.relative_to(root)} to make space.')
        repository = cache_path(path, source) / 'repository.git'
        git(repository, 'worktree', 'remove', '--force', directory)
    return shutil.disk_usage(root).free >= minimum


VERSION_TITLE = re.compile(r'REL\D*(\d+)\.(\d+)')


def game_version(title):
    """(major, minor) from a release commit title such as CNRELWin7.1.0_R..., or None."""
    match = VERSION_TITLE.search(title)
    return (int(match[1]), int(match[2])) if match else None


def _remote_config(path):
    path = Path(path).resolve() if path is not None else config_path()
    config = load_config(path)
    if not is_remote(config):
        raise ValueError('Comparing against another revision needs the GitHub data source (DataSource "github").')
    return path, config


def earlier_versions(source, commit, count, hint='Choose the revision to compare against.'):
    """The newest revision of each of the `count` game versions before the one `commit` belongs to."""
    if count == 0:
        return []
    revisions = list_revisions(source, 100)
    index = next((index for index, revision in enumerate(revisions) if revision['commit'] == commit), None)
    if index is None:
        raise ValueError(f'The prepared Excel revision {commit[:8]} is not among the 100 newest revisions. {hint}')
    version = game_version(revisions[index]['title'])
    if version is None:
        raise ValueError(f'Cannot tell the game version of revision {commit[:8]} from its title. {hint}')
    found = []
    for revision in revisions[index + 1:]:
        if len(found) == count:
            break
        older = game_version(revision['title'])
        if older and older < version:
            found.append(revision)
            version = older
    if len(found) < count:
        raise ValueError(f'No revision of a version before {version[0]}.{version[1]} is among the 100 newest. {hint}')
    return found


def previous_version_revision(path=None):
    """Newest Excel source revision from an earlier game version than the prepared dataset."""
    path, config = _remote_config(path)
    with (data_root(path) / 'ready.json').open(encoding='utf-8') as file:
        prepared = json.load(file)['excel']['commit']
    return earlier_versions(selected_sources(config)['excel'], prepared, 1)[0]


def excel_table_at(commit, table, path=None):
    """Raw rows of ExcelBinOutput/<table>.json at another revision; only that file is downloaded."""
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('The revision must be a full 40-character commit hash.')
    path, config = _remote_config(path)
    source = selected_sources(config)['excel']
    repository, commit = update_repository(path, source, commit)
    result = subprocess.run(['git', '--git-dir', str(repository), 'show', f'{commit}:ExcelBinOutput/{table}.json'],
                            capture_output=True)
    if result.returncode:
        raise FileNotFoundError(f'{SOURCES[source]["label"]} revision {commit[:8]} has no ExcelBinOutput/{table}.json.')
    return json.loads(result.stdout)


def checkout(repository, directory, commit, paths, cone=True):
    if not directory.exists():
        directory.parent.mkdir(parents=True, exist_ok=True)
        git(repository, 'worktree', 'add', '--detach', '--no-checkout', directory, commit)
    run(['git', '-C', str(directory), 'sparse-checkout', 'set', '--cone' if cone else '--no-cone', *paths])
    # Sparse settings only take effect on checkout.
    run(['git', '-C', str(directory), 'checkout', '--detach', commit])


def is_prepared(directory, revision):
    marker = directory / '.prepared.json'
    if not marker.is_file():
        return False
    with marker.open(encoding='utf-8') as file:
        prepared = json.load(file)
    if prepared == revision:
        return True
    if prepared.get('commit') == revision.get('commit'):
        return False  # Same revision prepared with an older layout; refresh it in place.
    raise ValueError(f'Unexpected preparation metadata in {marker}')


def prepare_binoutput(repository, directory, revision):
    report.stage(f'Preparing BinOutput revision {revision["commit"][:8]}')
    checkout(repository, directory, revision['commit'], BINOUTPUT_PATHS, cone=False)
    # A previous preparation may have rewritten the files.
    run(['git', '-C', str(directory), 'restore', '--source=HEAD', '--worktree', '--', 'BinOutput'])
    if not any((directory / 'BinOutput' / 'Monster').glob('*.json')):
        raise FileNotFoundError(f'{SOURCES[revision["source"]]["label"]} has no BinOutput/Monster files.')


def deobfuscate(path, repositories, directory, dataset):
    """Rewrites scrambled keys in a BinOutput snapshot with names learned from the readable source."""
    import binKeys
    folder = directory / 'BinOutput'
    if not binKeys.looks_scrambled(folder):
        return
    key = (READABLE_SOURCE, LATEST)
    repository, commit = repositories[key] if key in repositories else update_repository(path, *key)
    reference_revision = {'source': READABLE_SOURCE, 'commit': commit, 'layout': BINOUTPUT_LAYOUT}
    reference = binoutput_path(path, reference_revision)
    if not is_prepared(reference, reference_revision):
        report.stage(f'Downloading readable BinOutput from {SOURCES[READABLE_SOURCE]["label"]}')
        prepare_binoutput(repository, reference, reference_revision)
        write_json(reference / '.prepared.json', reference_revision)
    report.stage('Recovering scrambled BinOutput key names by matching values')
    result = binKeys.deobfuscate(reference / 'BinOutput', folder,
                                 dataset / 'MappedExcelBinOutput_EN' / 'MonsterExcelConfigData.json')
    total = result['translated'] + result['remaining']
    share = result['translated'] / total if total else 1
    report.info(f'Recovered {len(result["keys"])} key names and {len(result["types"])} type names from {result["pairs"]} '
                f'file pairs; {share:.0%} of scrambled keys are now readable. Fields the readable source does not '
                'have keep their scrambled names.')
    write_json(directory / '.keys.json', {
        'reference': reference_revision,
        'keys': result['keys'],
        'types': result['types'],
    })


def prepare_remote(config, path, keep_versions=None, keep_history=False):
    selected = selected_sources(config)
    root = data_root(path)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / 'setup.lock'
    try:
        with lock.open('x', encoding='utf-8') as file:
            file.write(str(os.getpid()))
    except FileExistsError as error:
        raise FileExistsError(
            f'Setup is already running, or was interrupted. Check the process recorded in {lock} '
            'before removing that lock file.'
        ) from error

    try:
        revisions = selected_revisions(config)
        history = {}
        dates = {}
        if keep_history:
            if any(value != LATEST for value in revisions.values()):
                raise ValueError('Historical setup requires both sources to follow their latest revision.')
            for role, source in selected.items():
                history[role] = all_revisions(source)
                for revision in history[role]:
                    date = datetime.fromisoformat(revision['date'].replace('Z', '+00:00')).timestamp()
                    dates[(role, source, revision['commit'])] = date
            if not history_space(path, dates, float('inf'), 4 * 1024 ** 3):
                raise OSError('Not enough disk space to prepare the current dataset while preserving the reserve.')
        for role, title in (('excel', 'Excel and TextMap'), ('binoutput', 'BinOutput')):
            pinned = '' if revisions[role] == LATEST else f' (pinned to {revisions[role][:8]})'
            report.info(f'{title} source: {SOURCES[selected[role]]["label"]}{pinned}')
        wanted = dict.fromkeys((selected[role], revisions[role]) for role in selected)
        repositories = {key: update_repository(path, *key) for key in wanted}

        repository, commit = repositories[(selected['excel'], revisions['excel'])]
        dataset, excel_revision = prepare_excel(config, path, selected['excel'], repository, commit)

        repository, commit = repositories[(selected['binoutput'], revisions['binoutput'])]
        binoutput_revision = {'source': selected['binoutput'], 'commit': commit, 'layout': BINOUTPUT_LAYOUT}
        binoutput = binoutput_path(path, binoutput_revision)
        if is_prepared(binoutput, binoutput_revision):
            report.info(f'Using already-prepared BinOutput revision {commit}.')
        else:
            prepare_binoutput(repository, binoutput, binoutput_revision)
            deobfuscate(path, repositories, binoutput, dataset)
            write_json(binoutput / '.prepared.json', binoutput_revision)
        check_monsters(binoutput / 'BinOutput' / 'Monster')

        write_json(root / 'ready.json', {'excel': excel_revision, 'binoutput': binoutput_revision})

        if keep_versions is not None:
            kept = [excel_revision]
            hint = 'Pin ExcelRevision to a release build, or run setup without --keep-versions.'
            for older in earlier_versions(selected['excel'], excel_revision['commit'], keep_versions - 1, hint):
                report.stage(f'Preparing the previous version {older["title"]} ({older["commit"][:8]})')
                repository, commit = update_repository(path, selected['excel'], older['commit'])
                kept.append(prepare_excel(config, path, selected['excel'], repository, commit)[1])
            prune(path, kept, binoutput_revision)
        if keep_history:
            prepare_history(config, path, selected, history, dates, repositories, dataset)
        return dataset
    finally:
        lock.unlink()


def prepare_excel(config, path, source, repository, commit):
    """Checks out and preprocesses one Excel/TextMap revision unless it is already prepared."""
    excel_revision = {'source': source, 'commit': commit, 'pipeline': pipeline_version()}
    dataset = excel_dataset_path(path, excel_revision)
    if is_prepared(dataset, excel_revision):
        validate_outputs(dataset)
        report.info(f'Using already-prepared Excel revision {commit}.')
    else:
        report.stage(f'Preparing Excel revision {commit[:8]}')
        checkout(repository, dataset, commit, ['ExcelBinOutput', 'TextMap'])
        # A failed attempt may have already rewritten some tracked TextMaps.
        run(['git', '-C', str(dataset), 'restore', '--source=HEAD', '--worktree', '--', 'TextMap'])
        preprocess(dict(config, RepoPath=str(dataset)))
        write_json(dataset / '.prepared.json', excel_revision)
    return dataset, excel_revision


def prepare_history(config, path, selected, history, dates, repositories, dataset):
    """Prepare historical snapshots newest first; stop rather than evict a newer one."""
    entries = [
        (dates[(role, selected[role], revision['commit'])], role, revision)
        for role, rows in history.items() for revision in rows
    ]
    for date, role, revision in sorted(entries, key=lambda item: item[0], reverse=True):
        source, commit = selected[role], revision['commit']
        metadata = {'source': source, 'commit': commit}
        if role == 'excel':
            metadata['pipeline'] = pipeline_version()
            directory = excel_dataset_path(path, metadata)
        else:
            metadata['layout'] = BINOUTPUT_LAYOUT
            directory = binoutput_path(path, metadata)
        if is_prepared(directory, metadata):
            continue
        if not history_space(path, dates, date, 4 * 1024 ** 3):
            report.warning('Stopped historical preparation: no older removable datasets can provide enough staging space.')
            return
        report.stage(f'Preparing {role} revision {commit[:8]}: {revision["title"]}')
        repository, commit = update_repository(path, source, commit)
        required = ('ExcelBinOutput', 'TextMap') if role == 'excel' else ('BinOutput/Monster',)
        existing = set(git(repository, 'ls-tree', '--name-only', commit, '--', *required, capture=True).splitlines())
        if not set(required).issubset(existing):
            report.warning(f'Skipping {commit[:8]}: it does not contain the required {role} data.')
            continue
        if role == 'excel':
            prepare_excel(config, path, source, repository, commit)
        else:
            prepare_binoutput(repository, directory, metadata)
            deobfuscate(path, repositories, directory, dataset)
            write_json(directory / '.prepared.json', metadata)


def prune(path, excel_revisions, binoutput_revision):
    """Deletes every downloaded dataset except the given ones (and the BinOutput they were deobfuscated with)."""
    keep = {excel_dataset_path(path, revision) for revision in excel_revisions}
    keep.add(binoutput_path(path, binoutput_revision))
    keys = binoutput_path(path, binoutput_revision) / '.keys.json'
    if keys.is_file():
        with keys.open(encoding='utf-8') as file:
            keep.add(binoutput_path(path, json.load(file)['reference']))
    freed = 0
    for source in SOURCES:
        cache = cache_path(path, source)
        for folder in ('datasets', 'binoutput'):
            for directory in sorted((cache / folder).glob('*')):
                if directory.is_dir() and directory not in keep:
                    freed += sum(item.stat().st_size for item in directory.rglob('*') if item.is_file())
                    report.info(f'Removing {directory.relative_to(data_root(path))}')
                    shutil.rmtree(directory)
        if (cache / 'repository.git').is_dir():
            git(cache / 'repository.git', 'worktree', 'prune')
    report.info(f'Freed {freed / 1024 ** 3:.2f} GB.')


def prepare(path=None, keep_versions=None, keep_history=False, reserve_gb=5):
    path = Path(path).resolve() if path is not None else config_path()
    config = load_config(path, require_prepared=False)
    if shutil.which('node') is None:
        raise FileNotFoundError('Node.js is required for Excel mapping. Install it before running setup.')
    if is_remote(config):
        if shutil.which('git') is None:
            raise FileNotFoundError('Git is required to download game data.')
        if keep_history:
            if keep_versions is not None:
                raise ValueError('Choose either --keep-versions or --all-revisions.')
            if reserve_gb <= 0:
                raise ValueError('The disk reserve must be greater than zero.')
            with history_lock(path, exclusive=True), history_reservation(path, int(reserve_gb * 1024 ** 3)):
                dataset = prepare_remote(config, path, keep_history=True)
        else:
            dataset = prepare_remote(config, path, keep_versions)
    else:
        if keep_versions is not None or keep_history:
            raise ValueError('Revision retention needs downloaded data (DataSource "remote").')
        dataset = preprocess(config)
    report.info(f'Dataset ready: {dataset}')
    return dataset


def main():
    parser = argparse.ArgumentParser(description='Download selected game data and run the quick-setup pipeline.')
    parser.add_argument('--config', type=Path, help='Configuration file (defaults to scriptconfig.json beside the tools).')
    parser.add_argument('--list-revisions', choices=sorted(SOURCES), metavar='SOURCE',
                        help=f'List recent revisions of a source ({", ".join(SOURCES)}) to pin with ExcelRevision/BinOutputRevision.')
    parser.add_argument('--keep-versions', type=int, metavar='N',
                        help='Also prepare the newest build of each of the N-1 previous game versions, then delete '
                             'every other downloaded dataset (for hosted servers).')
    parser.add_argument('--all-revisions', action='store_true',
                        help='Prepare historical revisions of both sources, removing older snapshots if space is needed.')
    parser.add_argument('--reserve-gb', type=int, default=5, metavar='N',
                        help='Disk space in GiB to reserve during historical setup (default: 5).')
    args = parser.parse_args()
    if args.keep_versions is not None and args.keep_versions < 1:
        parser.error('--keep-versions must be at least 1.')
    try:
        if args.list_revisions:
            for revision in list_revisions(args.list_revisions):
                print(f'{revision["commit"]}  {revision["date"][:10]}  {revision["title"]}')
            return
        prepare(args.config, args.keep_versions, args.all_revisions, args.reserve_gb)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Setup failed: {error}\n')


if __name__ == '__main__':
    main()
