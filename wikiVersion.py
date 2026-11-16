'''Looks up release versions on the wiki: a character's from the Change History section of their article, and a
date's from Template:Date to Version.'''
import json
import re
import urllib.parse
import urllib.request

API = 'https://genshin-impact.fandom.com/api.php'
CHANGE_HISTORY = re.compile(r'\{\{\s*Change History\s*\|\s*([^|}=]+?)\s*[|}]')
DATE = re.compile(r'\d{4}-\d{2}-\d{2}')
# Fandom rejects requests without a browser-like User-Agent.
HEADERS = {'User-Agent': 'Mozilla/5.0 PainmeloTools'}


def release_version(name: str, timeout: float = 10) -> str | None:
    """The first {{Change History}} version on the article (e.g. 4.6 or Luna II), or None if there is none."""
    query = urllib.parse.urlencode({'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main',
                                    'format': 'json', 'redirects': 1, 'titles': name})
    request = urllib.request.Request(f'{API}?{query}', headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        pages = json.load(response).get('query', {}).get('pages', {})
    for page in pages.values():
        text = (page.get('revisions') or [{}])[0].get('slots', {}).get('main', {}).get('*', '')
        section = re.search(r'==\s*Change History\s*==(.*?)(?:\n==[^=]|\Z)', text, re.S)
        match = CHANGE_HISTORY.search(section.group(1) if section else '')
        if match:
            return match.group(1)
    return None


def page_texts(titles, timeout: float = 20) -> dict[str, str]:
    """{title: current wikitext} for existing pages, fetched in one request."""
    titles = list(dict.fromkeys(titles))
    query = urllib.parse.urlencode({'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main',
                                    'format': 'json', 'titles': '|'.join(titles)})
    request = urllib.request.Request(f'{API}?{query}', headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response).get('query', {})
    # The API normalizes titles (underscores, capitalization); map them back to the requested ones.
    names = {item['to']: item['from'] for item in data.get('normalized') or []}
    return {names.get(page.get('title'), page.get('title')): page['revisions'][0]['slots']['main']['*']
            for page in (data.get('pages') or {}).values() if page.get('revisions')}


def date_versions(dates, timeout: float = 10) -> dict[str, str]:
    """{YYYY-MM-DD: version} from the wiki's {{Date to Version}} (e.g. 7.2 or Luna III), in one request. Dates after the
    newest release the template knows get that release, as on the wiki."""
    dates = list(dict.fromkeys(date for date in dates if DATE.fullmatch(date)))
    if not dates:
        return {}
    text = '\n'.join(f'{date}={{{{Date to Version|{date}}}}}' for date in dates)
    body = urllib.parse.urlencode({'action': 'expandtemplates', 'text': text, 'prop': 'wikitext', 'format': 'json'}).encode()
    with urllib.request.urlopen(urllib.request.Request(API, data=body, headers=HEADERS), timeout=timeout) as response:
        expanded = json.load(response).get('expandtemplates', {}).get('wikitext', '')
    result = {}
    for line in expanded.splitlines():
        date, _, version = line.partition('=')
        if date in dates and version.strip():
            result[date] = version.strip()
    return result
