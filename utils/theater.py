'''Imaginarium Theater/Seasons/<date> pages: the season header (opening characters, blessing, elements, guests and
Climactic Showdown bosses), then each Act and Arcana Challenge with its battles, stage effects, descriptions and a
Domain Enemies template of every stage's objective, Star Challenge, level per mode, advantages and enemies.

Many columns of these tables have scrambled names that change between versions, so fields are found by their
values. The game data has no enemy counts, waves or main objective time limits (the server sets those), so the page
marks them with "?" for editors.'''
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from getConfig import CONFIG
from utils.pageinfo import pageinfo
from utils.periods import TIME_FORMAT, seasons as _seasons, times as _times, wiki_version

ROMAN = ('I', 'II', 'III', 'IV', 'V', 'VI')
ELEMENTS = ('Pyro', 'Hydro', 'Dendro', 'Electro', 'Cryo', 'Anemo', 'Geo')
DEFAULT_MODES = {1: 'Easy Mode', 2: 'Normal Mode', 3: 'Hard Mode', 4: 'Visionary Mode', 5: 'Lunar Mode'}
ARCANA = '{{Color|#764bf7|Arcana Challenge}} '
STAR = '{{Color|help|"Star Challenge"}} '
BONUS = '{{Color|bz|"Bonus Challenge"}} '


def _load(name, folder=None):
    with open(f'{folder or CONFIG.EXCEL_PATH}/{name}.json', 'r', encoding='utf-8') as file:
        return json.load(file)


def _number(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _int_lists(row):
    return {key: value for key, value in row.items() if isinstance(value, list) and value and all(map(_number, value))}


def _wiki(text):
    if not isinstance(text, str):
        return ''
    text = text.replace('\\n', '<br>').replace('\n', '<br>')
    text = re.sub(rf'<color=[^>]*>\s*({"|".join(ELEMENTS)})\s*</color>', r'{{Color|\1}}', text, flags=re.IGNORECASE)
    text = re.sub(r'</?color[^>]*>', '', text, flags=re.IGNORECASE)
    return re.sub(r'[ \t]+', ' ', text).strip()


def _fill(text, params):
    return re.sub(r'\{(\d+)\}', lambda match: params[int(match.group(1))] if int(match.group(1)) < len(params) else match.group(0), text)


def seasons():
    '''The schedule rows of each season, oldest first.'''
    return _seasons(_load('RoleCombatScheduleExcelConfigData'))


def _preview(rows):
    '''{entry: [(monster describe ID, danger), ...]} from MonsterPreview_RoleCombatLevel.json, found by shape: each
    entry has its number and a list of monsters, each with a describe ID and, for powerful foes, a true flag.'''
    entries = {}
    for row in rows:
        number = next((value for value in row.values() if _number(value)), None)
        members = next((value for value in row.values() if isinstance(value, list)), [])
        entries[number] = [(next((value for value in member.values() if _number(value)), None),
                            any(value is True for value in member.values()))
                           for member in members if isinstance(member, dict)]
    return entries


class Data:
    '''The season tables, with their scrambled columns resolved.'''

    def __init__(self):
        self.difficulties = {row['DifficultyId']: row for row in _load('RoleCombatDifficultyExcelConfigData')}
        rules = _load('RoleCombatFightRuleExcelConfigData')
        self.pools = {}
        for row in rules:
            self.pools.setdefault(row.get('PoolId'), []).append(row)
        known = {'RuleId', 'PoolId', 'MonsterLevel'}
        # The act number: the only small number on every rule.
        self.act_key = next(key for key in dict.fromkeys(key for row in rules for key in row if key not in known)
                            if all(_number(row.get(key)) and 0 < row[key] <= 20 for row in rules))
        self.levels = {}
        level_rows = _load('RoleCombatLevelExcelConfigData')
        for row in level_rows:
            self.levels.setdefault(row.get('Tag'), []).append(row)
        self.descs = {row['Id']: row for row in _load('RoleCombatLevelDescExcelConfigData')}
        tables = {
            'effects': {row['Id']: row for row in _load('RoleCombatLevelEntityExcelConfigData')},
            'advantages': {row['Id']: row for row in _load('RoleCombatLevelTopicTagExcelConfigData')},
            'stars': {row['Id']: row for row in _load('RoleCombatExtraLevelTargetExcelConfigData')},
        }
        self.tables = tables
        # Each list column refers to the smallest of these tables that has all its IDs; their sizes differ.
        values = {}
        for row in level_rows:
            for key, value in _int_lists(row).items():
                values.setdefault(key, set()).update(value)
        self.columns = {}
        for key, ids in values.items():
            fits = [name for name, table in tables.items() if ids <= table.keys()]
            if fits:
                self.columns.setdefault(min(fits, key=lambda name: len(tables[name])), key)
        numbers = [key for key in dict.fromkeys(key for row in level_rows for key in row)
                   if key not in ('Id', 'Tag', 'MonsterPreviewId') and all(_number(row.get(key, 0)) for row in level_rows)]
        self.desc_key = next(key for key in numbers if all(row.get(key) in self.descs for row in level_rows))
        self.avatars = {row['Id']: row.get('NameTextMapHash') for row in _load('AvatarExcelConfigData')}
        self.monsters = {row['Id']: row.get('NameTextMapHash') for row in _load('MonsterDescribeExcelConfigData')}
        self.element_tags = {row['Tag']: re.sub(r'<[^>]*>', '', str(row.get('TagDescTextMapHash')))
                             for row in _load('RoleCombatAvatarTagExcelConfigData') if 'ELEM' in str(row.values())}
        manual = {row.get('TextMapId'): row.get('TextMapContentTextMapHash') for row in _load('ManualTextMapConfigData')}
        self.modes = {level: manual.get(f'UI_ROLE_COMBAT_DIFFICULTY_TITLE{level}') or name for level, name in DEFAULT_MODES.items()}
        self.tarot = _load('RoleCombatTarotAvatarExcelConfigData')
        path = Path(CONFIG.BIN_PATH) / 'MonsterPreview' / 'MonsterPreview_RoleCombatLevel.json'
        if not path.is_file():
            raise FileNotFoundError(f'{path} does not exist. The Imaginarium Theater tool needs BinOutput/MonsterPreview '
                                    'from GuraFoundation; run the dataset setup again to download it.')
        with path.open(encoding='utf-8') as file:
            self.preview = _preview(json.load(file))

    def pool_ids(self, difficulty):
        '''(main pool, [Arcana pools]) of a difficulty: its numbers that are fight rule pools, the main one with most acts.'''
        pools = sorted((value for key, value in difficulty.items() if _number(value) and key != 'DifficultyId'
                        and value in self.pools), key=lambda pool: -len(self.pools[pool]))
        return (pools[0] if pools else None), pools[1:]

    def tags(self, rule):
        return [tag for entry in next((value for value in rule.values() if isinstance(value, list)
                                       and any(isinstance(item, dict) for item in value)), [])
                if isinstance(entry, dict) for tag in entry.get('TagList') or []]

    def enemies(self, level):
        return [(self.monsters.get(describe) or str(describe), danger)
                for describe, danger in self.preview.get(level.get('MonsterPreviewId'), []) if describe]

    def column(self, level, name):
        table = self.tables[name]
        return [table[item] for item in level.get(self.columns.get(name)) or [] if item in table]


def _modes_line(levels, modes):
    '''"Easy Mode: 75<br>Hard/Visionary Mode: 85" from [(mode level, monster level)], or the level if all are equal.'''
    groups = []
    for mode, level in levels:
        if groups and groups[-1][1] == level:
            groups[-1][0].append(mode)
        else:
            groups.append(([mode], level))
    if len(groups) == 1:
        return str(groups[0][1])
    return '<br>'.join('/'.join(modes[mode].removesuffix(' Mode') for mode in names) + f' Mode: {level}' for names, level in groups)


def _objective(desc, arcana):
    text = _fill(_wiki(desc.get('LevelDescTextMapHash')),
                 next((value for value in desc.values() if isinstance(value, list) and all(isinstance(item, str) for item in value)), []))
    text = text.replace('as many opponents as possible', 'as many opponents as possible (at least ?)')
    text = text.replace('specific number of Bounties', 'specific number of Bounties (?)')
    if desc.get('LevelType') != 'SPECIAL' and re.search(r'time limit|timer|countdown', text):
        text += ' (?s)'
    return (ARCANA if arcana else '') + text


def _row(key, value, width=10):
    return f'|{key:<{width}} = {value}'


def _section(data, title, rules, levels_line, arcana):
    '''Lines of an Act or Arcana Challenge: descriptions, then each battle's stage effects and Domain Enemies.'''
    lines = [f'==={title}===']
    battles = []
    for tag in data.tags(rules[-1]):
        levels = sorted(data.levels.get(tag, []), key=lambda row: row['Id'])
        if levels:
            battles.append(levels)
    described = set()
    for levels in battles:
        for level in levels:
            desc, name = level.get('BossDescTextMapHash'), level.get('BossTitleTextMapHash')
            if isinstance(desc, str) and isinstance(name, str) and desc not in described:
                described.add(desc)
                enemies = data.enemies(level)
                if data.descs[level[data.desc_key]].get('LevelType') == 'BOSS' and len(enemies) == 1:
                    name = enemies[0][0]
                lines.append(f'{{{{Description|{_wiki(desc)}|{_wiki(name)}}}}}')
    for levels in battles:
        desc = data.descs[levels[0][data.desc_key]]
        battle = _wiki(desc.get('LevelNameTextMapHash'))
        if battle.startswith('Battle: '):
            lines.append(f';Battle{{{{Colon}}}} {battle.removeprefix("Battle: ")}')
        elif desc.get('LevelType') == 'BOSS':
            lines.append(';Battle{{Colon}} Climactic Showdown')
        effects = list({row['Id']: row for level in levels for row in data.column(level, 'effects')}.values())
        if effects:
            lines.append("* '''Stage Effects''':")
            lines += [f"** '''{_wiki(row.get('TitleTextMapHash'))}''': {_wiki(row.get('DescTextMapHash'))}" for row in effects]
        lines.append('{{Domain Enemies')
        for number, level in enumerate(levels, 1):
            # Star Challenges have a true flag; older seasons also have Bonus Challenges without it.
            stars = [(STAR if any(value is True for value in row.values()) else BONUS)
                     + _fill(_wiki(row.get('DescTextMapHash')), row.get('DescParamList') or []) for row in data.column(level, 'stars')]
            target = _objective(data.descs[level[data.desc_key]], arcana) + ''.join(f'<br>{star}' for star in stars)
            advantages = '<br>'.join(_wiki(row.get('TitleTextMapHash')) for row in data.column(level, 'advantages'))
            enemies = ';'.join(f'{name}{{ danger = 1 }}' if danger else name for name, danger in data.enemies(level))
            if number > 1:
                lines.append('')
            lines += [_row(f'target{number}', target), _row(f'level{number}', levels_line)]
            if advantages:
                lines.append(_row(f'advantage{number}', advantages))
            lines.append(_row(f'enemies{number}', enemies))
        lines += ['}}', '']
    return lines


def theater_page(start=None, version=''):
    '''(page title, wikitext) for the season starting on start (YYYY-MM-DD), or the newest one.'''
    schedule = seasons()
    if not schedule:
        raise ValueError('RoleCombatScheduleExcelConfigData has no seasons.')
    dates = [_times(row)[0][:10] for row in schedule]
    if start:
        if start not in dates:
            raise ValueError(f'No Imaginarium Theater season starts on {start}. Recent seasons: {", ".join(dates[-6:])}.')
        index = dates.index(start)
    else:
        index = len(schedule) - 1
    season = schedule[index]
    # Without a given version, the wiki's Date to Version gives the one live when the season starts.
    version = version or wiki_version(dates[index])
    opening, closing = _times(season)[0], _times(season)[-1]
    following = dates[index + 1] if index + 1 < len(dates) else \
        (datetime.strptime(closing, TIME_FORMAT) + timedelta(seconds=1)).strftime('%Y-%m-%d')

    data = Data()
    config = next(row for row in _load('RoleCombatAvatarConfigExcelConfigData') if row.get('AvatarConfigId') == season.get('AvatarConfigId'))
    avatar_lists = sorted((value for value in _int_lists(config).values() if all(item in data.avatars for item in value)),
                          key=len, reverse=True)
    characters = avatar_lists[0] if avatar_lists else []
    guests = avatar_lists[1] if len(avatar_lists) > 1 else []
    elements = next((value for value in _int_lists(config).values() if set(value) <= set(data.element_tags) | {0}), [])
    blessing = next((max((value for value in row.values() if isinstance(value, str) and ' ' in value), key=len, default='')
                     for row in data.tarot if row.get('AvatarID') in characters), '')
    blessing = re.sub(r'^\{\{Color\|bp\|(.*)\}\}$', r'\1', blessing)

    # Another short list of small numbers also matches difficulty IDs; the season's difficulties are the longest one.
    difficulty_ids = max((value for value in _int_lists(season).values() if all(item in data.difficulties for item in value)),
                         key=len, default=[])
    difficulties = sorted((data.difficulties[item] for item in difficulty_ids), key=lambda row: row['DifficultyLevel'])
    # Arcana Challenges are fought in the difficulty that has Arcana pools; its acts repeat the hardest other mode.
    main_modes = [row for row in difficulties if not data.pool_ids(row)[1]] or difficulties
    acts = {}
    for row in main_modes:
        pool = data.pool_ids(row)[0]
        for rule in data.pools.get(pool, []):
            acts.setdefault(rule[data.act_key], []).append((row['DifficultyLevel'], rule))
    arcana = {}
    for row in difficulties:
        for pool in data.pool_ids(row)[1]:
            for rule in data.pools.get(pool, []):
                arcana.setdefault(rule[data.act_key], []).append(rule)

    bosses = []
    body = ['==Battles==']
    arcana_count = 0
    for act in sorted(set(acts) | set(arcana)):
        if act in arcana:
            rules = arcana[act]
            body += _section(data, f'Arcana Challenge {ROMAN[arcana_count]}', rules, str(rules[-1]['MonsterLevel'] + 1), True)
            arcana_count += 1
        if act in acts:
            rules = [rule for _, rule in acts[act]]
            line = _modes_line([(mode, rule['MonsterLevel'] + 1) for mode, rule in acts[act]], data.modes)
            body += _section(data, f'Act {act}', rules, line, False)
            for tag in data.tags(rules[-1]):
                for level in data.levels.get(tag, []):
                    if data.descs[level[data.desc_key]].get('LevelType') == 'BOSS':
                        bosses += [f'{name}*Lv. {rules[-1]["MonsterLevel"] + 1}' for name, _ in data.enemies(level)]

    header = [
        '{{Imaginarium Theater Season',
        _row('season', index + 1, 12),
        _row('startVersion', version, 12),
        _row('start', opening, 12),
        _row('end', closing, 12),
        _row('prev', dates[index - 1] if index else '', 12),
        _row('next', following, 12),
        _row('characters', '; '.join(data.avatars[item] for item in characters), 12),
        _row('blessing', _wiki(blessing), 12),
        _row('elements', '; '.join(data.element_tags[item] for item in elements if item in data.element_tags), 12),
        _row('guests', '; '.join(data.avatars[item] for item in guests), 12),
        _row('enemies', ';'.join(dict.fromkeys(bosses)), 12),
        '}}',
    ]
    lines = ['{{Stub|Add enemy counts, waves and the "?" objective values}}', *header, '', *body]
    title = f'Imaginarium Theater/Seasons/{dates[index]}'
    return title, pageinfo(title) + '\n'.join(line.rstrip() for line in lines).rstrip('\n') + '\n'


def write_theater_page(start=None, version='', directory=None):
    '''Writes the season's page to directory (default OutputPath) and returns its path.'''
    title, text = theater_page(start, version)
    path = Path(directory or CONFIG.OUTPUT_PATH) / f'{title.replace("/", " ")}.wikitext'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    print(f'Wrote {title} to {path}.', flush=True)
    return path
