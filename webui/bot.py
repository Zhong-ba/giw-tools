'''A queue of generated pages and a MediaWiki client that posts them with a bot password.'''
import base64
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import shutil
import socket
from threading import Event, RLock, Thread
import time
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field

from utils.files import read_file_page

DEFAULT_WIKI = 'https://genshin-impact.fandom.com'
# Fandom rejects requests without a browser-like User-Agent.
USER_AGENT = 'Mozilla/5.0 PainmeloTools'
PAGE_INFO = re.compile(r'\A\ufeff?(?:--\[=\[)?<%--\s*\[PAGE_INFO\](.*?)\[END_PAGE_INFO\]\s*--%>(?:--\]=\])?[ \t]*(?:\n\n?|\Z)', re.S)
INVALID_TITLE = re.compile(r'[#<>\[\]|{}]')
POSTABLE = ('.wikitext', '.lua')
MEDIA = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
# Tests swap this for an httpx.MockTransport.
transport: httpx.BaseTransport | None = None


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_page(text: str) -> tuple[dict[str, str], str]:
    '''Splits a generated file into its [PAGE_INFO] fields and the page content that gets posted.'''
    text = text.replace('\r\n', '\n')
    match = PAGE_INFO.match(text)
    if not match:
        return {}, text
    info = {}
    for line in match.group(1).split('\n'):
        if '=' in line:
            key, value = line.split('=', 1)
            info[key.strip()] = value.strip().strip('#')
    return info, text[match.end():]


def check_title(title: str | None) -> str | None:
    title = (title or '').strip()
    if not title:
        return None
    if INVALID_TITLE.search(title):
        raise ValueError(f'"{title}" contains characters MediaWiki does not allow in titles (# < > [ ] | {{ }}).')
    return title


def file_title(name: str | None) -> str | None:
    '''A File: title for an upload, adding the namespace when it is missing.'''
    title = check_title(name)
    if title is None:
        return None
    if not title.lower().startswith(('file:', 'image:')):
        title = f'File:{title}'
    if not title.split(':', 1)[1].strip():
        raise ValueError('Enter the file name to upload as.')
    return title


class WikiError(Exception):
    pass


class Wiki:
    '''Just enough of the MediaWiki Action API to log in with a bot password and save pages.'''

    def __init__(self, url: str, timeout: float = 30):
        self.client = httpx.Client(headers={'User-Agent': USER_AGENT}, timeout=timeout, follow_redirects=True, transport=transport)
        self.csrf: str | None = None
        try:
            self.api = self._discover(url)
        except Exception:
            self.client.close()
            raise

    def close(self) -> None:
        self.client.close()

    def _discover(self, url: str) -> str:
        url = url.strip().rstrip('/')
        if not re.match(r'https?://', url, re.I):
            url = f'https://{url}'
        if url.endswith('api.php'):
            candidates = [url]
        else:
            base = re.sub(r'/(?:wiki|index\.php)(?:[/?].*)?$', '', url)
            candidates = [f'{base}/api.php', f'{base}/w/api.php']
        for candidate in candidates:
            try:
                response = self.client.get(candidate, params={'action': 'query', 'meta': 'siteinfo', 'format': 'json', 'formatversion': 2})
                if response.is_success and response.json().get('query', {}).get('general'):
                    return candidate
            except (httpx.HTTPError, ValueError):
                continue
        raise WikiError(f'Could not find a MediaWiki API at {url}.')

    def call(self, post: bool = False, **params) -> dict:
        params.update(format='json', formatversion=2)
        for attempt in range(3):
            try:
                response = self.client.post(self.api, data=params) if post else self.client.get(self.api, params=params)
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPError as error:
                raise WikiError(f'Could not reach the wiki: {error}') from error
            except ValueError as error:
                raise WikiError('The wiki returned an invalid response.') from error
            error = data.get('error')
            if not error:
                return data
            if error.get('code') in ('ratelimited', 'maxlag') and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise WikiError(f"{error.get('info', 'Unknown error')} ({error.get('code', 'error')})")
        raise WikiError('The wiki kept rate limiting the request.')

    def login(self, username: str, password: str) -> str:
        token = self.call(action='query', meta='tokens', type='login')['query']['tokens']['logintoken']
        result = self.call(post=True, action='login', lgname=username, lgpassword=password, lgtoken=token).get('login', {})
        if result.get('result') != 'Success':
            raise WikiError(result.get('reason') or 'Login failed. Use a bot password from Special:BotPasswords (Name@BotName).')
        self.csrf = self.call(action='query', meta='tokens')['query']['tokens']['csrftoken']
        return result.get('lgusername', username)

    def page(self, title: str) -> str | None:
        '''The current wikitext of a page, or None if it does not exist.'''
        pages = self.call(action='query', prop='revisions', rvprop='content', rvslots='main', titles=title)['query']['pages']
        page = pages[0] if pages else {}
        if page.get('invalid'):
            raise WikiError(page.get('invalidreason', 'Invalid title.'))
        if page.get('missing'):
            return None
        return page['revisions'][0]['slots']['main'].get('content', '')

    def edit(self, title: str, text: str, summary: str, bot: bool, watch: bool) -> bool:
        '''Saves the page and returns False when the wiki recorded no change.'''
        params = {'action': 'edit', 'title': title, 'text': text, 'summary': summary, 'token': self.csrf,
                  'watchlist': 'watch' if watch else 'nochange', 'assert': 'user'}
        if bot:
            params['bot'] = 1
        result = self.call(post=True, **params).get('edit', {})
        if result.get('result') != 'Success':
            raise WikiError(f'The edit was not saved: {result}')
        return not result.get('nochange')

    def file_sha1(self, title: str) -> str | None:
        '''The SHA-1 of the current version of a file, or None if the wiki has no such file.'''
        pages = self.call(action='query', prop='imageinfo', iiprop='sha1', titles=title)['query']['pages']
        page = pages[0] if pages else {}
        if page.get('invalid'):
            raise WikiError(page.get('invalidreason', 'Invalid title.'))
        info = page.get('imageinfo') or []
        return info[0].get('sha1') if info else None

    def upload(self, filename: str, data: bytes, text: str, summary: str, watch: bool, overwrite: bool) -> None:
        '''Uploads a file; text becomes the File page when the file is new.'''
        params = {'action': 'upload', 'filename': filename, 'text': text, 'comment': summary, 'token': self.csrf,
                  'watchlist': 'watch' if watch else 'nochange', 'assert': 'user', 'format': 'json', 'formatversion': 2}
        if overwrite:
            params['ignorewarnings'] = 1
        try:
            response = self.client.post(self.api, data=params, files={'file': (filename, data)})
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPError as error:
            raise WikiError(f'Could not reach the wiki: {error}') from error
        except ValueError as error:
            raise WikiError('The wiki returned an invalid response.') from error
        if result.get('error'):
            error = result['error']
            raise WikiError(f"{error.get('info', 'Unknown error')} ({error.get('code', 'error')})")
        upload = result.get('upload', {})
        if upload.get('result') != 'Success':
            warnings = ', '.join(f'{key}: {value}' if value not in ('', True) else key for key, value in (upload.get('warnings') or {}).items())
            raise WikiError(f'The upload was not saved ({warnings or upload.get("result", "unknown result")}).')

    def protect(self, title: str, reason: str) -> None:
        file = title.lower().startswith(('file:', 'image:'))
        self.call(post=True, action='protect', title=title,
                  protections='edit=sysop|move=sysop' + ('|upload=sysop' if file else ''),
                  expiry='infinite|infinite' + ('|infinite' if file else ''), reason=reason, token=self.csrf)


def post_page(wiki: Wiki, title: str, content: str, settings: 'BotSettings', summary: str) -> tuple['Status', str | None]:
    '''Saves one page; returns its queue status and message. Raises WikiError when it fails.'''
    current = wiki.page(title)
    if current is not None and settings.skip_existing:
        return 'skipped', 'The page already exists.'
    if current is not None and settings.skip_unchanged and current.rstrip() == content.rstrip():
        return 'skipped', 'No change from the live page.'
    changed = wiki.edit(title, content, summary, settings.bot_edit, settings.watch)
    message = None if changed else 'Saved with no change (null edit).'
    if settings.protect:
        try:
            wiki.protect(title, f'Automatically locked by script. {summary}'.strip())
            message = 'Protected (edit and move: administrators only).'
        except WikiError as error:
            message = f'Posted, but protecting failed: {error}'
    return 'posted', message


def post_file(wiki: Wiki, title: str, data: bytes, content: str, settings: 'BotSettings', summary: str) -> tuple['Status', str | None]:
    '''Uploads one media file; returns its queue status and message. Raises WikiError when it fails.'''
    current = wiki.file_sha1(title)
    if current is not None and settings.skip_existing:
        return 'skipped', 'The file already exists.'
    if current is not None and settings.skip_unchanged and current == hashlib.sha1(data).hexdigest():
        return 'skipped', 'The live file is identical.'
    wiki.upload(title.split(':', 1)[1], data, content, summary, settings.watch, overwrite=current is not None)
    # MediaWiki only uses the text for new File pages; a new version leaves the existing page as it is.
    message = 'Uploaded a new version; the File page text was left unchanged.' if current is not None else None
    if settings.protect:
        try:
            wiki.protect(title, f'Automatically locked by script. {summary}'.strip())
            message = 'Protected (edit, move and upload: administrators only).'
        except WikiError as error:
            message = f'Uploaded, but protecting failed: {error}'
    return 'posted', message


class BotSettings(BaseModel):
    wiki: str = Field(DEFAULT_WIKI, max_length=500)
    username: str = Field('', max_length=255)
    remember: bool = False
    summary: str = Field('//Batch Posted', max_length=500)
    skip_existing: bool = False
    skip_unchanged: bool = True
    bot_edit: bool = True
    watch: bool = True
    protect: bool = False


class SettingsUpdate(BotSettings):
    # None keeps the current password; an empty string forgets it.
    password: str | None = Field(None, max_length=500)


Status = Literal['pending', 'posting', 'posted', 'skipped', 'failed']


class QueueEntry(BaseModel):
    id: str
    kind: Literal['page', 'file'] = 'page'
    title: str | None = None
    source: str
    job_id: str | None = None
    path: str | None = None
    status: Status = 'pending'
    message: str | None = None
    added_at: str = Field(default_factory=now)
    posted_at: str | None = None
    size: int = 0


class QueueItem(QueueEntry):
    content: str


class BotState(BaseModel):
    settings: BotSettings
    has_password: bool
    running: bool
    stopping: bool
    log: list[str]
    items: list[QueueEntry]


class RelayLogin(BaseModel):
    wiki: str = Field(DEFAULT_WIKI, max_length=500)
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=500)


class RelayPost(BaseModel):
    session: str = Field(pattern=r'^[0-9a-f]{32}$')
    kind: Literal['page', 'file'] = 'page'
    title: str = Field(max_length=255)
    content: str = Field('', max_length=2097152)
    # Base64 media for uploads.
    data: str | None = Field(None, max_length=67108864)
    settings: BotSettings = Field(default_factory=BotSettings)


def public_wiki(url: str) -> None:
    '''Stops the hosted relay from being pointed at the server's own network.'''
    url = url.strip()
    host = urlsplit(url if re.match(r'https?://', url, re.I) else f'https://{url}').hostname
    if not host:
        raise ValueError('Enter the wiki address, for example https://genshin-impact.fandom.com.')
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, 443)}
    except OSError:
        raise ValueError(f'Could not find the wiki {host}.') from None
    if not all(ipaddress.ip_address(address.split('%')[0]).is_global for address in addresses):
        raise ValueError(f'{host} is not a public wiki.')


class WikiRelay:
    '''Posts on behalf of browsers that keep their own queue and login (the hosted site).

    Only the logged-in wiki session is held, in memory, and it is dropped after 30 idle minutes.
    '''

    IDLE = 1800

    def __init__(self, public_only: bool = True):
        self.lock = RLock()
        self.sessions: dict[str, tuple[Wiki, str, float]] = {}
        self.public_only = public_only

    def _expire(self) -> None:
        cutoff = time.monotonic() - self.IDLE
        for key, (wiki, _, used) in list(self.sessions.items()):
            if used < cutoff:
                del self.sessions[key]
                wiki.close()

    def login(self, client: str, body: RelayLogin) -> dict[str, str]:
        if self.public_only:
            public_wiki(body.wiki)
        wiki = Wiki(body.wiki)
        try:
            username = wiki.login(body.username.strip(), body.password)
        except Exception:
            wiki.close()
            raise
        with self.lock:
            self._expire()
            if len(self.sessions) >= 500:
                wiki.close()
                raise WikiError('The server has too many open wiki sessions. Try again later.')
            key = uuid4().hex
            self.sessions[key] = (wiki, client, time.monotonic())
        return {'session': key, 'username': username, 'api': wiki.api}

    def _session(self, client: str, key: str) -> Wiki:
        with self.lock:
            self._expire()
            found = self.sessions.get(key)
            if found is None or found[1] != client:
                raise KeyError(key)
            self.sessions[key] = (found[0], client, time.monotonic())
            return found[0]

    def post(self, client: str, body: RelayPost) -> dict[str, str | None]:
        wiki = self._session(client, body.session)
        try:
            title = file_title(body.title) if body.kind == 'file' else check_title(body.title)
        except ValueError as error:
            return {'status': 'failed', 'message': str(error)}
        if not title:
            return {'status': 'failed', 'message': 'Set the target page first.'}
        summary = body.settings.summary.strip()
        content = body.content.replace('\r\n', '\n')
        try:
            if body.kind == 'file':
                if not body.data:
                    return {'status': 'failed', 'message': 'The queued file is missing; add it to the queue again.'}
                status, message = post_file(wiki, title, base64.b64decode(body.data, validate=True), content, body.settings, summary)
            else:
                status, message = post_page(wiki, title, content, body.settings, summary)
        except (WikiError, ValueError) as error:
            return {'status': 'failed', 'message': str(error)}
        return {'status': status, 'message': message}

    def logout(self, client: str, key: str) -> None:
        with self.lock:
            found = self.sessions.get(key)
            if found and found[1] == client:
                del self.sessions[key]
                found[0].close()

    def close(self) -> None:
        with self.lock:
            for wiki, _, _ in self.sessions.values():
                wiki.close()
            self.sessions.clear()

class BotManager:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.password = ''
        self.settings = BotSettings()
        self.items: list[QueueItem] = []
        self.log: list[str] = []
        self.thread: Thread | None = None
        self.stop_event = Event()
        settings = self.root / 'settings.json'
        if settings.is_file():
            data = json.loads(settings.read_text(encoding='utf-8'))
            self.password = data.pop('password', '') or ''
            self.settings = BotSettings.model_validate(data)
        queue = self.root / 'queue.json'
        if queue.is_file():
            self.items = [QueueItem.model_validate(item) for item in json.loads(queue.read_text(encoding='utf-8'))]
            for item in self.items:
                if item.status == 'posting':
                    item.status, item.message = 'failed', 'The server stopped while this page was being posted.'
            self._save_queue()

    @staticmethod
    def _write(path: Path, data) -> None:
        temporary = path.with_name(f'.{path.name}.tmp')
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)

    def _save_queue(self) -> None:
        self._write(self.root / 'queue.json', [item.model_dump() for item in self.items])

    def _save_settings(self) -> None:
        data = self.settings.model_dump()
        if self.settings.remember:
            data['password'] = self.password
        else:
            data['username'] = ''
        self._write(self.root / 'settings.json', data)

    def _note(self, line: str) -> None:
        with self.lock:
            self.log.append(f'{datetime.now().strftime("%H:%M:%S")}  {line}')
            del self.log[:-300]

    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def state(self) -> BotState:
        with self.lock:
            return BotState(settings=self.settings.model_copy(), has_password=bool(self.password), running=self.running(),
                            stopping=self.stop_event.is_set(), log=list(self.log),
                            items=[QueueEntry.model_validate(item.model_dump(exclude={'content'})) for item in self.items])

    def update_settings(self, update: SettingsUpdate) -> BotState:
        with self.lock:
            if self.running():
                raise ValueError('Wait for posting to finish before changing settings.')
            if not re.match(r'(?:https?://)?[\w.-]+\.[a-z]{2,}(?::\d+)?(?:/\S*)?$', update.wiki.strip(), re.I):
                raise ValueError('Enter the wiki address, for example https://genshin-impact.fandom.com.')
            if update.password is not None:
                self.password = update.password
            self.settings = BotSettings.model_validate(update.model_dump(exclude={'password'}))
            self.settings.wiki = self.settings.wiki.strip().rstrip('/')
            self.settings.username = self.settings.username.strip()
            self._save_settings()
            return self.state()

    def test_login(self) -> str:
        with self.lock:
            settings, password = self.settings.model_copy(), self.password
        if not settings.username or not password:
            raise ValueError('Enter the bot username and password first.')
        wiki = Wiki(settings.wiki)
        try:
            return wiki.login(settings.username, password)
        finally:
            wiki.close()

    def add(self, source: str, job_id: str, files: list[tuple[str, Path]]) -> tuple[int, int]:
        '''Queues generated pages and media, skipping ones already queued from the same job. Returns (added, skipped).'''
        added = skipped = 0
        with self.lock:
            existing = {(item.job_id, item.path) for item in self.items}
            for name, path in files:
                suffix = path.suffix.lower()
                if suffix not in POSTABLE + MEDIA:
                    raise ValueError(f'{name} is not a page (.wikitext or .lua) or media file ({", ".join(MEDIA)}).')
            for name, path in files:
                if (job_id, name) in existing:
                    skipped += 1
                    continue
                item_id = uuid4().hex
                if path.suffix.lower() in MEDIA:
                    content = read_file_page(path) or ''
                    try:
                        title = file_title(path.name)
                    except ValueError:
                        title = None
                    self.media_dir.mkdir(exist_ok=True)
                    # Keep a copy so the upload survives deleting the job.
                    shutil.copyfile(path, self.media_path(item_id, path.suffix))
                    item = QueueItem(id=item_id, kind='file', title=title, source=source, job_id=job_id,
                                     path=name, content=content, size=path.stat().st_size)
                else:
                    info, content = parse_page(path.read_text(encoding='utf-8'))
                    try:
                        title = check_title(info.get('pageTitle'))
                    except ValueError:
                        title = None
                    item = QueueItem(id=item_id, title=title, source=source, job_id=job_id, path=name,
                                     content=content, size=len(content.encode('utf-8')))
                    if info.get('skip'):
                        item.status, item.message = 'skipped', 'Marked skip in the page info.'
                self.items.append(item)
                existing.add((job_id, name))
                added += 1
            self._save_queue()
        return added, skipped

    @property
    def media_dir(self) -> Path:
        return self.root / 'media'

    def media_path(self, item_id: str, suffix: str) -> Path:
        return self.media_dir / f'{item_id}{suffix.lower()}'

    def media(self, item_id: str) -> Path:
        '''The stored copy of a queued media file.'''
        item = self.get(item_id)
        path = self.media_path(item.id, Path(item.path or '').suffix) if item.kind == 'file' else None
        if path is None or not path.is_file():
            raise KeyError(item_id)
        return path

    def get(self, item_id: str) -> QueueItem:
        with self.lock:
            for item in self.items:
                if item.id == item_id:
                    return item.model_copy()
        raise KeyError(item_id)

    def update(self, item_id: str, title: str | None = None, content: str | None = None, reset: bool = False) -> QueueItem:
        with self.lock:
            item = next((item for item in self.items if item.id == item_id), None)
            if item is None:
                raise KeyError(item_id)
            if item.status == 'posting':
                raise ValueError('This page is being posted right now.')
            if title is not None:
                item.title = file_title(title) if item.kind == 'file' else check_title(title)
            if content is not None:
                item.content = content.replace('\r\n', '\n')
                if item.kind == 'page':
                    item.size = len(item.content.encode('utf-8'))
            if reset or title is not None or content is not None:
                if item.status != 'pending':
                    item.status, item.message, item.posted_at = 'pending', None, None
            self._save_queue()
            return item.model_copy()

    def remove(self, ids: list[str]) -> int:
        with self.lock:
            wanted = set(ids)
            if any(item.id in wanted and item.status == 'posting' for item in self.items):
                raise ValueError('A selected page is being posted right now.')
            before = len(self.items)
            for item in self.items:
                if item.id in wanted and item.kind == 'file':
                    self.media_path(item.id, Path(item.path or '').suffix).unlink(missing_ok=True)
            self.items = [item for item in self.items if item.id not in wanted]
            self._save_queue()
            return before - len(self.items)

    def reset(self, ids: list[str]) -> None:
        with self.lock:
            for item in self.items:
                if item.id in ids and item.status != 'posting':
                    item.status, item.message, item.posted_at = 'pending', None, None
            self._save_queue()

    def start(self, ids: list[str] | None = None) -> BotState:
        with self.lock:
            if self.running():
                raise ValueError('The queue is already being posted.')
            if not self.settings.username or not self.password:
                raise ValueError('Enter the bot username and password in the settings first.')
            chosen = [item.id for item in self.items if item.status in ('pending', 'failed') and item.title and (ids is None or item.id in ids)]
            if not chosen:
                raise ValueError('Nothing to post. Pending pages need a target title before they can be posted.')
            self.stop_event.clear()
            self.log.clear()
            self.thread = Thread(target=self._post, args=(chosen, self.settings.model_copy(), self.password), daemon=True, name='wiki-bot')
            self.thread.start()
            return self.state()

    def stop(self) -> None:
        self.stop_event.set()

    def _finish(self, item: QueueItem, status: Status, message: str | None = None) -> None:
        with self.lock:
            item.status, item.message = status, message
            if status == 'posted':
                item.posted_at = now()
            self._save_queue()
        self._note(f'{status.title()}: {item.title}' + (f' — {message}' if message else ''))

    def _upload(self, wiki: Wiki, item: QueueItem, settings: BotSettings, summary: str) -> int:
        '''Uploads a queued media file; returns 1 when it was uploaded.'''
        try:
            data = self.media(item.id).read_bytes()
        except (KeyError, OSError):
            self._finish(item, 'failed', 'The queued file is missing; add it to the queue again.')
            return 0
        status, message = post_file(wiki, item.title or '', data, item.content, settings, summary)
        self._finish(item, status, message)
        return int(status == 'posted')

    def _post(self, ids: list[str], settings: BotSettings, password: str) -> None:
        wiki = None
        posted = 0
        try:
            self._note(f'Connecting to {settings.wiki}...')
            wiki = Wiki(settings.wiki)
            self._note(f'Logged in as {wiki.login(settings.username, password)} via {wiki.api}.')
            summary = settings.summary.strip()
            for item_id in ids:
                if self.stop_event.is_set():
                    self._note('Stopped.')
                    break
                with self.lock:
                    item = next((item for item in self.items if item.id == item_id), None)
                    if item is None or item.status not in ('pending', 'failed') or not item.title:
                        continue
                    item.status, item.message = 'posting', None
                    title, content, kind = item.title, item.content, item.kind
                try:
                    if kind == 'file':
                        posted += self._upload(wiki, item, settings, summary)
                        continue
                    status, message = post_page(wiki, title, content, settings, summary)
                    posted += status == 'posted'
                    self._finish(item, status, message)
                except WikiError as error:
                    self._finish(item, 'failed', str(error))
        except (WikiError, httpx.HTTPError, KeyError) as error:
            self._note(f'Stopped: {error}')
            with self.lock:
                for item in self.items:
                    if item.status == 'posting':
                        item.status, item.message = 'failed', str(error)
                self._save_queue()
        finally:
            if wiki:
                wiki.close()
            self._note(f'Done. Posted {posted} {"page" if posted == 1 else "pages"}.')
