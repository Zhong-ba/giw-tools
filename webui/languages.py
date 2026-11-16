"""Persistent, dataset-specific indexes for direct Other Languages lookups."""

from contextlib import closing
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3

from utils.ol import lookup_ol
from webui.tools import LANGUAGES


INDEX_VERSION = 1
logger = logging.getLogger(__name__)


def _signature(directory: Path) -> str:
    files = []
    for language in LANGUAGES:
        stat = (directory / f'TextMap{language}.json').stat()
        files.append((language, stat.st_mtime_ns, stat.st_size))
    return json.dumps((INDEX_VERSION, files))


def _load_textmap(path: Path) -> dict[str, str]:
    with path.open(encoding='utf-8') as file:
        values = json.load(file)
    if not isinstance(values, dict) or not all(isinstance(value, str) for value in values.values()):
        raise ValueError(f'{path.name} must contain a mapping of hashes to text.')
    return values


def _search_key(text: str) -> bytes:
    # Descriptions can be very long; index fixed-size keys, then verify casefolded text on lookup.
    return hashlib.sha256(text.casefold().encode('utf-8')).digest()


def ensure_index(directory: Path, cache: Path) -> Path:
    directory = directory.resolve()
    signature = _signature(directory)
    identity = hashlib.sha256(os.path.normcase(str(directory)).encode('utf-8')).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f'{identity}.sqlite3'
    with closing(sqlite3.connect(path, timeout=600, isolation_level=None)) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS metadata (signature TEXT NOT NULL)')

        def current():
            row = connection.execute('SELECT signature FROM metadata').fetchone()
            return row is not None and row[0] == signature

        if current():
            return path
        # SQLite serializes rebuilds across threads and server processes. Readers see only committed indexes.
        connection.execute('BEGIN IMMEDIATE')
        if current():
            connection.rollback()
            return path
        connection.execute('PRAGMA cache_size = -65536')
        logger.info('Building Other Languages index for %s', directory)
        connection.execute('DROP TABLE IF EXISTS texts')
        connection.execute(
            'CREATE TABLE texts (identifier TEXT NOT NULL, language TEXT NOT NULL, text TEXT NOT NULL, '
            'search_key BLOB NOT NULL, position INTEGER NOT NULL, PRIMARY KEY (identifier, language)) WITHOUT ROWID'
        )
        for language in LANGUAGES:
            values = _load_textmap(directory / f'TextMap{language}.json')
            connection.executemany(
                'INSERT INTO texts VALUES (?, ?, ?, ?, ?)',
                ((identifier, language, value, _search_key(value), position)
                 for position, (identifier, value) in enumerate(values.items())),
            )
            logger.info('Indexed TextMap%s: %s entries', language, len(values))
            del values
        connection.execute('CREATE INDEX name_lookup ON texts (language, search_key, position)')
        if _signature(directory) != signature:
            raise OSError('TextMaps changed while indexing. Wait for dataset setup to finish and retry.')
        connection.execute('DELETE FROM metadata')
        connection.execute('INSERT INTO metadata VALUES (?)', (signature,))
        connection.commit()
        logger.info('Other Languages index ready: %s', path)
    return path


def language_results(directory: Path, cache: Path, text: str, input_lang: str) -> list[dict[str, str]]:
    path = ensure_index(directory, cache)
    with closing(sqlite3.connect(path, timeout=600, isolation_level=None)) as connection:
        connection.execute('BEGIN')
        matches = connection.execute(
            'SELECT identifier, text FROM texts WHERE identifier = ? AND language = ?', (text, input_lang)
        ).fetchall()
        if not matches:
            folded = text.casefold()
            matches = [
                (identifier, value) for identifier, value in connection.execute(
                    'SELECT identifier, text FROM texts WHERE language = ? AND search_key = ? ORDER BY position',
                    (input_lang, _search_key(text)),
                ) if value.casefold() == folded
            ]
        maps = {language: {} for language in LANGUAGES}
        for identifier, _ in matches:
            for language, value in connection.execute(
                'SELECT language, text FROM texts WHERE identifier = ?', (identifier,)
            ):
                maps[language][identifier] = value
        return lookup_ol(text, maps, input_lang)


if __name__ == '__main__':
    from dataSource import config_path, data_root, load_config

    logging.basicConfig(level=logging.INFO, format='%(message)s')
    profile = config_path()
    config = load_config(profile)
    print(ensure_index(Path(config['RepoPath']) / 'TextMap', data_root(profile) / 'ol'))
