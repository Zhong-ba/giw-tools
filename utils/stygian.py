'''Stygian Onslaught/<date> event pages: the Event infobox, durations, the battlefield summary, each difficulty's
objectives, Ley Line Disturbance and opposing lineup (with the enemies' advantages and mechanics), the enemy
descriptions, gallery, total rewards and Other Languages, in the layout of the wiki's current event pages.

Many columns of these tables have scrambled names that change between versions, so fields are found by their
values. Text the game highlights in gold is kept from TextMapEN_Highlights.json (see textmapcleanup.py) and
rendered as {{Color|help|...}} like the wiki; without that file it stays plain. The announcement's summary and
the HoYoLAB link are not in the game data, so editors add them.'''
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from getConfig import CONFIG
from utils.pageinfo import pageinfo
from utils.periods import DAY_START, TIME_FORMAT, events as _events, stygian_end, times as _times, wiki_version

OUTBREAK_DAYS = 10
KINDS = ('Advantage', 'Disadvantage')
REWARD_ORDER = ('Primogem', 'Mora', 'Dust of Enlightenment', "Hero's Wit")
SEPARATOR = re.compile(r'\s*<color=#FFFFFF40>\s*\|\s*</color>\s*', re.IGNORECASE)
SPRITE = re.compile(r'\{SPRITE_PRESET#(\d+)\}')
# Element names in sprite paths, and the reaction between two elements as named in the wiki's icon files.
ELEMENT_CODES = {'Frost': 'Cryo', 'Ice': 'Cryo', 'Water': 'Hydro', 'Wter': 'Hydro', 'Fire': 'Pyro', 'Elect': 'Electro',
                 'Electric': 'Electro', 'Wind': 'Anemo', 'Rock': 'Geo', 'Roach': 'Geo', 'Grass': 'Dendro'}
REACTIONS = {
    frozenset(('Electro', 'Cryo')): 'Superconduct', frozenset(('Electro', 'Anemo')): 'Electro Swirl',
    frozenset(('Pyro', 'Cryo')): 'Melt', frozenset(('Pyro', 'Anemo')): 'Pyro Swirl', frozenset(('Dendro', 'Hydro')): 'Bloom',
    frozenset(('Hydro', 'Electro')): 'Electro-Charged', frozenset(('Hydro', 'Pyro')): 'Vaporize',
    frozenset(('Cryo', 'Anemo')): 'Cryo Swirl', frozenset(('Hydro', 'Anemo')): 'Hydro Swirl',
    frozenset(('Pyro', 'Electro')): 'Overloaded', frozenset(('Hydro', 'Cryo')): 'Frozen', frozenset(('Dendro', 'Pyro')): 'Burning',
    frozenset(('Dendro', 'Electro')): 'Quicken',
}
# Element text colors, which the wiki writes as {{Color|pyro|...}}.
ELEMENT_COLORS = {'FF9999FF': 'pyro', '80C0FFFF': 'hydro', '80FFD7FF': 'anemo', 'FFACFFFF': 'electro',
                  '99FF88FF': 'dendro', '99FFFFFF': 'cryo', 'FFE699FF': 'geo'}


def _load(name, folder=None):
    with open(f'{folder or CONFIG.EXCEL_PATH}/{name}.json', 'r', encoding='utf-8') as file:
        return json.load(file)


def _numbers(row):
    return {key: value for key, value in row.items() if isinstance(value, int) and not isinstance(value, bool)}


def _lists(row, kind):
    return [(key, value) for key, value in row.items()
            if isinstance(value, list) and value and all(isinstance(item, kind) and not isinstance(item, bool) for item in value)]


class Text:
    '''English text by TextMap hash, preferring the raw highlighted text, converted to wikitext.'''

    def __init__(self):
        folder = Path(CONFIG.EXCEL_PATH).parent / 'TextMap'
        try:
            import OLGen
            self.textmap = OLGen.data.get('EN')
        except ImportError:
            self.textmap = None
        if self.textmap is None:
            with (folder / 'TextMapEN.json').open(encoding='utf-8') as file:
                self.textmap = json.load(file)
        try:
            with (folder / 'TextMapEN_Highlights.json').open(encoding='utf-8') as file:
                self.highlights = json.load(file)
        except FileNotFoundError:
            self.highlights = {}
            print('TextMapEN_Highlights.json is missing; run the dataset setup again to show highlighted text like the wiki.')
        self.sprites = {row['Id']: row for row in _load('SpriteTagExcelConfigData')}

    def raw(self, value):
        key = str(value)
        return self.highlights.get(key) or self.textmap.get(key) or ''

    def get(self, value):
        if isinstance(value, str):
            return self.wiki(value)
        return self.wiki(self.raw(value))

    def sprite(self, match):
        row = self.sprites.get(int(match.group(1)), {})
        fallback = row.get('FallbackPureTextTextMapHash')
        if isinstance(fallback, str) and fallback in ELEMENT_CODES.values():
            return f'[[File:Element {fallback}.png|20px|link=]]'
        name = row.get('SpritePath', '').rsplit('_', 1)[-1]
        elements = [ELEMENT_CODES[part] for part in re.findall(r'[A-Z][a-z]+', name) if part in ELEMENT_CODES]
        reaction = REACTIONS.get(frozenset(elements)) if len(elements) == 2 else None
        if reaction is None and len(elements) == 2 and 'Geo' in elements:
            reaction = 'Crystallize'
        if reaction:
            return f'[[File:Icon Stygian Onslaught {reaction}.png|40px|link=]]'
        return fallback if isinstance(fallback, str) else ''

    def wiki(self, text):
        text = text.replace('\\n', '<br>')
        text = SEPARATOR.sub(' {{!}} ', text)
        text = SPRITE.sub(self.sprite, text)
        text = re.sub(r'<color=#FFD780FF>(.*?)</color>', r'{{Color|help|\1}}', text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r'<color=#FF5E41(?:FF)?>(.*?)</color>', r'{{Color|old|\1}}', text, flags=re.IGNORECASE | re.DOTALL)
        for code, element in ELEMENT_COLORS.items():
            text = re.sub(rf'<color=#{code}>(.*?)</color>', rf'{{{{Color|{element}|\1}}}}', text, flags=re.IGNORECASE | re.DOTALL)
        # Text the TextMap cleanup already turned into {{Color|Pyro DMG}}.
        text = re.sub(r'\{\{Color\|((Pyro|Hydro|Anemo|Electro|Dendro|Cryo|Geo)\b[^|{}]*)\}\}',
                      lambda match: f'{{{{Color|{match.group(2).lower()}|{match.group(1)}}}}}', text)
        text = re.sub(r'</?color[^>]*>', '', text, flags=re.IGNORECASE)
        text = text.replace('—', '&mdash;').replace('–', '&ndash;')
        return re.sub(r'[ \t]+', ' ', text).strip()


class Columns:
    '''The scrambled LeyLineLevelConfigExcelConfigData columns, found across the whole table: the advantage kinds
    (Advantage/Disadvantage/None), their lines, and three parallel mechanic lists: titles (the shortest texts),
    details (filled exactly where titles are) and bullet summaries.'''

    def __init__(self, rows, text):
        def hashed(key):
            return [[text.raw(item) for item in row[key]] for row in rows if isinstance(row.get(key), list)]
        int_keys = [key for key in dict.fromkeys(key for row in rows for key, _ in _lists(row, int))]
        self.kinds = next((key for key in dict.fromkeys(key for row in rows for key, _ in _lists(row, str))
                           if all(set(row.get(key) or []) <= {*KINDS, 'None'} for row in rows)), None)
        self.lines = next((key for key in int_keys if self.kinds and all(
            len(row.get(key) or []) == len(row.get(self.kinds) or []) for row in rows)), None)
        mechanics = [key for key in int_keys if key != self.lines]

        def average(key):
            lengths = [len(item) for values in hashed(key) for item in values if item]
            return sum(lengths) / max(len(lengths), 1)
        self.titles = min((key for key in mechanics if any(item for values in hashed(key) for item in values)),
                          key=average, default=None)
        rest = [key for key in mechanics if key != self.titles]

        def filled(key, row):
            return tuple(bool(text.raw(item)) for item in row.get(key) or [])

        def score(key):
            return sum(self.titles is not None and filled(key, row) == filled(self.titles, row) for row in rows), average(key)
        rest.sort(key=score, reverse=True)
        self.details = rest[0] if rest else None
        self.bullets = rest[1] if len(rest) > 1 else None


class Variant:
    '''An enemy as it appears at a difficulty: LeyLineLevelConfigExcelConfigData.'''

    def __init__(self, row, text, columns):
        self.name = row['LevelNameTextMapHash']
        # Names that contain a colon themselves end in " - Variant" instead of ": Variant".
        self.enemy = self.name.rsplit(' - ' if ' - ' in self.name else ': ', 1)[0]
        strings = [value for key, value in row.items() if isinstance(value, str) and key != 'LevelNameTextMapHash'
                   and not value.startswith('UI_')]
        self.description = text.get(max(strings, key=len)) if strings else ''
        column = lambda key: [text.get(item) for item in row.get(key) or []] if key else []
        kinds, lines = row.get(columns.kinds) or [], column(columns.lines)
        self.advantage = ', '.join(f'[[File:Icon Stygian Onslaught {kind}.png|20px|link=]] {line}'
                                   for kind, line in zip(kinds, lines) if kind in KINDS and line)
        self.summary_lines = [(kind, part) for kind, line in zip(kinds, lines) if kind in KINDS
                              for part in line.split(' {{!}} ') if part]
        # A colon would end the ;title definition line, so the wiki writes {{Colon}}.
        self.mechanics = [(title.replace(':', '{{Colon}}'), detail)
                          for title, detail in zip(column(columns.titles), column(columns.details)) if title]
        self.bullets = [item for item in column(columns.bullets) if item]


def _schedules():
    return _events(_load('LeyLineChallengeExcelConfigData'))


def _manual(text):
    '''{TextMapId: wikitext} from the raw ManualTextMapConfigData, whose hashes keep highlights.'''
    raw = _load('ManualTextMapConfigData', Path(CONFIG.EXCEL_PATH).parent / 'ExcelBinOutput')
    result = {}
    for row in raw:
        key = next((value for value in row.values() if isinstance(value, str) and value.startswith('UI_')), None)
        number = next(iter(_numbers(row).values()), None)
        if key and number is not None:
            result[key] = number
    return lambda key: text.get(result[key]) if key in result else ''


def _battle_pass(activity_id):
    '''The Battle Pass Missions template for the activity's mission in the newest Battle Pass, or [].'''
    missions = [row for row in _load('BattlePassMissionExcelConfigData') if row.get('ActivityId') == activity_id]
    if not missions:
        return []
    schedule = max(row.get('ScheduleId', 0) for row in missions)
    names = {row['Id']: row.get('TitleNameTextMapHash') for row in _load('BattlePassScheduleExcelConfigData')}
    lines = ['==Battle Pass Missions==', '{{Battle Pass Missions', f'|name     = {names.get(schedule) or ""}']
    for number, row in enumerate((row for row in missions if row.get('ScheduleId') == schedule), 1):
        desc = str(row.get('DescTextMapHash', '')).replace('{param0}', f'{row.get("Progress", 0):,}')
        lines += [f'|mission{number} = {{{{Color|[Event]}}}} {desc}', f'|exp{number}     = {row.get("AddPoint", 0):,}']
    return lines + ['}}', '']


def _date(value, offset=timedelta()):
    return (datetime.strptime(value, TIME_FORMAT) + offset).strftime('%Y/%m/%d %H:%M')


def _rewards(watcher_ids):
    watchers = {row['Id']: row for row in _load('NewActivityWatcherConfigData')}
    totals = {}
    for watcher in watcher_ids:
        for item in (watchers.get(watcher) or {}).get('RewardID') or []:
            if isinstance(item, dict) and item.get('ItemId'):
                totals[item['ItemId']] = totals.get(item['ItemId'], 0) + item.get('ItemCount', 0)
    order = [name for name in REWARD_ORDER if name in totals] + [name for name in totals if name not in REWARD_ORDER]
    return [(name, totals[name]) for name in order]


def _other_languages(name):
    '''Other Languages for "Stygian Onslaught: <name>", composed like the game's reward titles.'''
    import OLGen
    if not OLGen.data:
        OLGen.load_data()
    raw = _load('ManualTextMapConfigData', Path(CONFIG.EXCEL_PATH).parent / 'ExcelBinOutput')
    title = next((next(iter(_numbers(row).values())) for row in raw
                  if 'UI_ACTIVITY_LEYLINEC_REWARDTYPE_SINGLE' in row.values()), None)
    name_id = next((key for key, value in OLGen.data['EN'].items() if value == name), None)
    if title is None or name_id is None:
        return OLGen.gen_ol(f'Stygian Onslaught: {name}')
    texts = {}
    for lang, values in OLGen.data.items():
        prefix, local = values.get(str(title), ''), values.get(name_id)
        if '{0}' in prefix and local:
            # A leading "#" marks TextMap entries with placeholders; it is not part of the text.
            texts[lang] = prefix.split('{0}')[0].removeprefix('#') + local
    return OLGen.format_ol(texts, f'Stygian Onslaught: {name}')


def stygian_page(start=None, version=''):
    '''(page title, wikitext) for the event starting on start (YYYY-MM-DD), or the newest one.'''
    events = _schedules()
    if not events:
        raise ValueError('LeyLineChallengeExcelConfigData has no events.')
    dates = [_times(row)[0][:10] for row in events]
    if start:
        if start not in dates:
            raise ValueError(f'No Stygian Onslaught event starts on {start}. Events: {", ".join(dates[-6:])}.')
        index = dates.index(start)
    else:
        index = len(events) - 1
    event = events[index]
    # Without a given version, the wiki's Date to Version gives the one live when the event starts.
    version = version or wiki_version(dates[index])
    opening = _times(event)[0]
    name = event['ChallengeNameTextMapHash']
    latest = index == len(events) - 1

    text = Text()
    manual = _manual(text)
    configs = {row['Id']: row for row in _load('LeyLineLevelConfigExcelConfigData')}
    columns = Columns(list(configs.values()), text)
    levels = {row['Id']: row for row in _load('LeyLineLevelExcelConfigData')}
    difficulties = sorted(_load('LeyLineDifficultyExcelConfigData'), key=lambda row: row['Id'])
    watcher_ids = {row['Id'] for row in _load('NewActivityWatcherConfigData')}
    variants = {}

    def variant(config_id):
        if config_id not in variants:
            variants[config_id] = Variant(configs[config_id], text, columns)
        return variants[config_id]

    stages = []
    for difficulty, level_id in zip(difficulties, event['LevelIdList']):
        level = levels[level_id]
        lineup = next((value for _, value in _lists(level, int) if all(item in configs for item in value)), [])
        disturbance = next((value for _, value in _lists(difficulty, str)
                            if any(item.startswith('UI_ACTIVITY_LEYLINEC_CHALLENGE_LIMIT') for item in value)), [])
        stages.append((difficulty['NameTextMapHash'], level['ReviseLevel'] + 1, [variant(item) for item in lineup],
                       [line for line in (manual(key) for key in disturbance if key) if line], level.get('WatcherList') or []))
    battlefields = len(stages[0][2]) if stages else 0

    preview = next((row for row in _load('NewActivityPreviewConfigData')
                    if any(value == 'Stygian Onslaught' for value in row.values())), None) if latest else None
    description = text.get(preview['DescTextMapHash']) if preview else ''
    end = stygian_end(event).strftime(TIME_FORMAT)
    outbreak_end = (datetime.strptime(opening, TIME_FORMAT) - DAY_START + timedelta(days=OUTBREAK_DAYS)).replace(
        hour=3, minute=59, second=0).strftime(TIME_FORMAT)
    objective = manual('UI_ACTIVITY_LEYLINEC_CHALLENGE_TARGET_1') or f'Defeat powerful foes on {battlefields} battlefields'
    objective = re.sub(r'\b(\d+)\b(?![^{]*\}\})', r'{{Color|help|\1}}', objective, count=1) if '{{Color' not in objective else objective

    lines = [
        '{{Event',
        f'|name              = Stygian Onslaught: {name}',
        f'|image             = Stygian Onslaught {dates[index]}.png',
        '|type              = In-Game',
        '|group             = Stygian Onslaught',
        '|time_known        = yes',
        f'|time_start        = {opening}',
        f'|time_end          = {end}',
        '|link              = ',
        '}}',
        f'{{{{Description|{description}}}}}' if description else '{{Description|}}<!-- The event description is only in the data while this event is the latest. -->',
        f"'''Stygian Onslaught''' is an [[Event]] in [[Version {version}]].",
        '',
        '==Event Details==',
        '===Duration===',
        f'* Event Duration: {_date(opening)} - {_date(end)}',
        f'* Disturbance Outbreak: {_date(opening)} - {_date(outbreak_end)}',
        '',
        '===Requirements===',
        '* [[Adventure Rank]] 20 or above',
        '* Complete [[Archon Quest]] [[Prologue]]: Act III "[[Song of the Dragon and Freedom]]"',
        '* Complete Archon Quest "[[Perilous Trail]]" first to get the best experience from this event.',
        '',
        '===Summary===',
        '* In this round of Stygian Onslaught, Traveler will face the following opponents and mechanics:',
        ':{|class="article-table thc"',
    ]
    for number in range(battlefields):
        first = stages[0][2][number]
        if number:
            lines.append('|-')
        lines += [f'!Battlefield {number + 1}', f'|{{{{Enemy|{first.enemy}}}}}<hr>',
                  *(f'* {kind}: {part}' for kind, part in first.summary_lines)]
    lines += ['|}', '<!-- Add the rest of the summary from the HoYoLAB announcement, and its link above. -->', '', '==Challenges==']

    for difficulty, level, lineup, disturbance, _ in stages:
        lines += [f'==={difficulty}===', ';Challenge Objectives', f'* {objective}', '', ';Ley Line Disturbance',
                  *(f'* {item}' for item in disturbance), '', ';Opposing Lineup', '{|class="article-table"', '!Enemy',
                  '!Descriptions']
        for enemy in lineup:
            lines += ['|-', f'|{{{{Card|{enemy.enemy}|Lv. {level}|type=Enemy|caption={enemy.name}|show_caption=1}}}}',
                      f'|{enemy.advantage}', '', *(f'* {item}' for item in enemy.bullets)]
            for title, detail in enemy.mechanics:
                lines += ['', f';{title}', detail]
        lines += ['|}', '']

    seen = []
    for number in range(battlefields):
        for stage in stages:
            enemy = stage[2][number]
            if enemy.name not in [item.name for item in seen]:
                seen.append(enemy)
    lines += ['==Descriptions==', *(f'{{{{Description|{enemy.description}|{enemy.name}}}}}' for enemy in seen), '',
              '==Gallery==', '<gallery>',
              *(f'{stages[0][2][number].enemy} Stygian Onslaught Preview.png' for number in range(battlefields)),
              '</gallery>', '']

    extra = [value for key, value in _numbers(event).items() if value in watcher_ids]
    rewards = _rewards([watcher for stage in stages for watcher in stage[4]] + extra)
    if rewards:
        lines += ['==Total Rewards==', '{{Event Rewards', *(f'|{item} = {count}' for item, count in rewards),
                  f'|sort  = {",".join(item for item, _ in rewards)}', '}}', '']
    if preview:
        lines += _battle_pass(preview.get('ActivityID'))
    lines += ['==Other Languages==', _other_languages(name), '', '==Change History==', f'{{{{Change History|{version}}}}}']
    title = f'Stygian Onslaught/{dates[index]}'
    return title, pageinfo(title) + '\n'.join(lines) + '\n'


def write_stygian_page(start=None, version='', directory=None):
    '''Writes the event's page to directory (default OutputPath) and returns its path.'''
    title, text = stygian_page(start, version)
    path = Path(directory or CONFIG.OUTPUT_PATH) / f'{title.replace("/", " ")}.wikitext'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    print(f'Wrote {title} to {path}.', flush=True)
    return path
