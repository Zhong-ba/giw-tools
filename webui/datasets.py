'''Prepared datasets on disk, so each request can pick which downloaded revision it uses.'''
import json
from pathlib import Path
import re
import time

from dataSource import SOURCES, binoutput_path, cache_path, excel_dataset_path

_listing: dict[Path, tuple[float, dict[str, list[dict]]]] = {}


def prepared_datasets(profile: Path) -> dict[str, list[dict]]:
    '''Every fully prepared Excel dataset (made by the current pipeline) and BinOutput snapshot, per role.'''
    cached = _listing.get(profile)
    if cached and time.monotonic() - cached[0] < 30:
        return cached[1]
    from setupData import BINOUTPUT_LAYOUT, pipeline_version

    pipeline = pipeline_version()
    found: dict[str, list[dict]] = {'excel': [], 'binoutput': []}
    for source in SOURCES:
        cache = cache_path(profile, source)
        for role, folder, matches, locate in (
            ('excel', 'datasets', lambda item: item.get('pipeline') == pipeline, excel_dataset_path),
            ('binoutput', 'binoutput', lambda item: item.get('layout') == BINOUTPUT_LAYOUT, binoutput_path),
        ):
            for marker in sorted((cache / folder).glob('*/.prepared.json')):
                try:
                    revision = json.loads(marker.read_text(encoding='utf-8'))
                    if isinstance(revision, dict) and revision.get('source') == source and matches(revision) \
                            and locate(profile, revision) == marker.parent:
                        found[role].append(revision)
                except (OSError, ValueError):
                    continue
    _listing[profile] = (time.monotonic(), found)
    return found


def parse_choice(value: str) -> dict[str, str]:
    '''The X-Dataset header: "<Excel commit>.<BinOutput commit>".'''
    match = re.fullmatch(r'([0-9a-f]{40})\.([0-9a-f]{40})', value.strip())
    if not match:
        raise ValueError('The dataset choice must be "<Excel commit>.<BinOutput commit>".')
    return {'excel': match.group(1), 'binoutput': match.group(2)}


def resolve_choice(profile: Path, choice: dict[str, str]) -> dict[str, dict]:
    '''The ready.json-style revisions for a choice of downloaded commits.'''
    available = prepared_datasets(profile)
    prepared = {}
    for role, commit in choice.items():
        revision = next((item for item in available[role] if item['commit'] == commit), None)
        if revision is None:
            raise FileNotFoundError(f'The {"Excel" if role == "excel" else "BinOutput"} revision {commit[:8]} '
                                    'is not available on this server. Choose another dataset.')
        prepared[role] = revision
    return prepared
