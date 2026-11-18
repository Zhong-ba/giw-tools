"""Shared human-readable logging and optional per-job progress snapshots."""
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timezone
import io
import json
import logging
from pathlib import Path
import sys
import time
from typing import TextIO, TypedDict, TypeVar


class ProgressState(TypedDict):
    stage: str
    completed: int | None
    total: int | None
    message: str
    warnings: int

T = TypeVar('T')
logger = logging.getLogger('painmelo.tools')
logger.propagate = False
logger.setLevel(logging.DEBUG)
_started = time.monotonic()
_path: Path | None = None
_state: ProgressState = {'stage': 'Preparing', 'completed': None, 'total': None, 'message': '', 'warnings': 0}
_published = 0.0
_logged = 0.0


def format_message(level: str, message: str, elapsed: float) -> str:
    seconds = max(0, int(elapsed))
    prefix = f'[{seconds // 60:02d}:{seconds % 60:02d}] {level:<7} '
    return '\n'.join(prefix + line for line in message.splitlines())


class _Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return format_message(record.levelname, super().format(record), time.monotonic() - _started)


class _ConsoleHandler(logging.StreamHandler):
    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stdout
        super().emit(record)


def configure(stream: TextIO | None = None, progress_path: Path | None = None, started_at: str | None = None) -> None:
    global _started, _path, _state, _published, _logged
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(started_at)).total_seconds() if started_at else 0
    _started, _path = time.monotonic() - elapsed, progress_path
    _state = {'stage': 'Preparing', 'completed': None, 'total': None, 'message': '', 'warnings': 0}
    _published = _logged = 0
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler(stream) if stream is not None else _ConsoleHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(_Formatter())
    logger.addHandler(handler)


def _ready() -> None:
    if not logger.handlers:
        configure()


def write_progress(path: Path, state: Mapping[str, object]) -> None:
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state), encoding='utf-8')
    for attempt in range(5):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            # Windows readers can briefly hold the destination without delete sharing.
            time.sleep(0.01 * (attempt + 1))


def _publish(force: bool = False) -> None:
    global _published
    now = time.monotonic()
    if _path is not None and (force or now - _published >= 0.2):
        write_progress(_path, _state)
        _published = now


def info(message: str) -> None:
    _ready()
    logger.info(message)


def warning(message: str) -> None:
    _ready()
    _state['warnings'] += 1
    logger.warning(message)
    _publish(True)


def error(message: str) -> None:
    _ready()
    logger.error(message)


def debug(message: str, *args: object) -> None:
    _ready()
    logger.debug(message, *args)


def stage(message: str, total: int | None = None) -> None:
    _ready()
    if total is not None and total < 0:
        raise ValueError('Progress total cannot be negative.')
    _state.update(stage=message, completed=0 if total is not None else None, total=total, message='')
    info(message + (f' (0/{total})' if total is not None else ''))
    _publish(True)


def advance(completed: int, message: str = '') -> None:
    global _logged
    total = _state['total']
    if total is None or not 0 <= completed <= total:
        raise ValueError('Progress must be within the current stage total.')
    _state.update(completed=completed, message=message)
    now = time.monotonic()
    if completed == total or now - _logged >= 1:
        info(f'{_state["stage"]}: {completed}/{total}' + (f' - {message}' if message else ''))
        _logged = now
    _publish(completed == total)


def track(items: Sequence[T], message: str) -> Iterator[T]:
    stage(message, len(items))
    for index, item in enumerate(items, 1):
        yield item
        _state.update(stage=message, total=len(items), message='')
        advance(index)


class LogStream(io.TextIOBase):
    """Keep legacy print output readable without interpreting its contents."""
    def __init__(self) -> None:
        self.pending = ''

    @property
    def encoding(self) -> str:
        return 'utf-8'

    def write(self, text: str) -> int:
        self.pending += text
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            if line.strip():
                info(line.rstrip('\r'))
        return len(text)

    def flush(self) -> None:
        if self.pending:
            info(self.pending)
            self.pending = ''
