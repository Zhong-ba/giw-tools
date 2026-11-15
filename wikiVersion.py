'''Looks up a character's release version in the Change History section of their wiki article.'''
import json
import re
import urllib.parse
import urllib.request

API = 'https://genshin-impact.fandom.com/api.php'
CHANGE_HISTORY = re.compile(r'\{\{\s*Change History\s*\|\s*([^|}=]+?)\s*[|}]')


def release_version(name: str, timeout: float = 10) -> str | None:
    """The first {{Change History}} version on the article (e.g. 4.6 or Luna II), or None if there is none."""
    query = urllib.parse.urlencode({'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'rvslots': 'main',
                                    'format': 'json', 'redirects': 1, 'titles': name})
    # Fandom rejects requests without a browser-like User-Agent.
    request = urllib.request.Request(f'{API}?{query}', headers={'User-Agent': 'Mozilla/5.0 PainmeloTools'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        pages = json.load(response).get('query', {}).get('pages', {})
    for page in pages.values():
        text = (page.get('revisions') or [{}])[0].get('slots', {}).get('main', {}).get('*', '')
        section = re.search(r'==\s*Change History\s*==(.*?)(?:\n==[^=]|\Z)', text, re.S)
        match = CHANGE_HISTORY.search(section.group(1) if section else '')
        if match:
            return match.group(1)
    return None
