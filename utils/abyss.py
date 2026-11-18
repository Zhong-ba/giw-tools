'''Spiral Abyss/Floors/<date> pages: the Abyssal Moon Spire header, Ley Line Disorder and each chamber's level,
target and enemies, in the layout of the wiki's current rotation pages.

Newer chambers name a BinOutput/MonsterPreview file and an entry in it for each half; older ones list their enemies
in the Excel data. The game data has no enemy counts, waves or spawn notes, so editors add those.'''
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from getConfig import CONFIG
import toolLog as report
from utils.pageinfo import pageinfo
from utils.periods import DAY_START, TIME_FORMAT, opening as _opening, rotations as _rotations, wiki_version

# Ley Line Disorder for each half sits in two scrambled floor fields referring to effect groups just before the
# floor's FloorLevelConfigId group; the lower one is the first half.
HALF_GROUP_RANGE = 10
HALVES = ('First Half', 'Second Half')
FLOORS_WITH_HEADER_FLAGS = (9, 10, 11, 12)


def _load(name):
    with open(f'{CONFIG.EXCEL_PATH}/{name}.json', 'r', encoding='utf-8') as file:
        return json.load(file)


def rotations():
    '''Rotations with a start time, oldest first.'''
    return _rotations(_load('TowerScheduleExcelConfigData'))


def _plain(text):
    text = re.sub(r'</?color[^>]*>', '', text, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', text.replace('\\n', ' ')).strip()


def _effects(groups, group_id):
    '''The visible effect texts of a DungeonLevelEntityConfigData group; hidden rows (like opponent HP increases) have none.'''
    return [_plain(row['DescTextMapHash']) for row in groups.get(group_id, [])
            if row.get('Show') and isinstance(row.get('DescTextMapHash'), str)]


def _ley_line_disorder(floor, groups):
    floor_group = floor.get('FloorLevelConfigId')
    lines = [f'** {text}' for text in _effects(groups, floor_group)]
    halves = sorted(value for key, value in floor.items()
                    if isinstance(value, int) and not isinstance(value, bool) and value != floor_group
                    and key not in ('FloorId', 'LevelGroupId') and not key.startswith('Reward') and floor_group
                    and 0 < floor_group - value <= HALF_GROUP_RANGE and _effects(groups, value))
    if len(halves) == 2:
        for half, group in zip(HALVES, halves):
            lines += [f'** {{{{Color|menu|{half}}}}}: {text}' for text in _effects(groups, group)]
    else:
        lines += [f'** {text}' for group in halves for text in _effects(groups, group)]
    return lines


def _target(conditions):
    values = '/'.join(str(condition['ArgumentList'][-1]) for condition in conditions)
    kind = conditions[0].get('TowerCondType') if conditions else None
    if kind == 'TOWER_COND_CHALLENGE_LEFT_TIME_MORE_THAN':
        return f'Remaining challenge time longer than ({values}) sec.'
    if kind == 'TOWER_COND_LEFT_HP_GREATER_THAN':
        return f'Target defense progress greater than ({values})%.'
    return f'({values})'


def preview_entries(rows):
    '''{entry number: [monster describe ID, ...]} from a MonsterPreview file. Its keys are scrambled and may change
    between versions, so fields are found by shape: each entry has a level, its number and a list of monsters that
    each repeat the level beside their describe ID.'''
    entries = {}
    for row in rows:
        lists = [value for value in row.values() if isinstance(value, list)]
        numbers = {key: value for key, value in row.items() if isinstance(value, int) and not isinstance(value, bool)}
        members = [member for member in lists[0] if isinstance(member, dict)] if len(lists) == 1 else []
        if not members:
            continue
        level_key = next((key for key, value in numbers.items() if all(value in member.values() for member in members)), None)
        number = [value for key, value in numbers.items() if key != level_key]
        if level_key is None or len(number) != 1:
            continue
        level = numbers[level_key]
        entries[number[0]] = [value for member in members for value in member.values()
                              if isinstance(value, int) and not isinstance(value, bool) and value != level][:len(members)]
    return entries


def _preview(name, cache):
    if name not in cache:
        path = Path(CONFIG.BIN_PATH) / 'MonsterPreview' / f'MonsterPreview_{name}.json'
        if not path.is_file():
            raise FileNotFoundError(f'{path} does not exist. The Spiral Abyss tool needs BinOutput/MonsterPreview from '
                                    'GuraFoundation; run the dataset setup again to download it.')
        with path.open(encoding='utf-8') as file:
            cache[name] = preview_entries(json.load(file))
    return cache[name]


def _unique(names):
    return list(dict.fromkeys(name for name in names if name))


def _halves(chamber, describe_names, monster_names, cache):
    '''The enemy names of a chamber's first and second half.'''
    if chamber.get('TowerMonsterPreview'):
        entries = _preview(chamber['TowerMonsterPreview'], cache)
        return [_unique(describe_names.get(i, str(i)) for i in entries.get(chamber.get(key), []))
                for key in ('TowerMonsterPreviewId1', 'TowerMonsterPreviewId2')]
    return [_unique(item if isinstance(item, str) else monster_names.get(item, str(item)) for item in chamber.get(key) or [])
            for key in ('FirstMonsterList', 'SecondMonsterList')]


def _row(key, value, width):
    return f'|{key:<{width}} = {value}'.rstrip(' ') + (' ' if value == '' else '')


def _chambers(chambers, describe_names, monster_names, cache):
    lines = ['{{Domain Enemies']
    for number, chamber in enumerate(chambers, 1):
        first, second = _halves(chamber, describe_names, monster_names, cache)
        lines += [
            _row(f'level{number}', chamber['MonsterLevel'] + 1, 11),
            _row(f'target{number}', _target(chamber.get('Conds') or []), 11),
            _row(f'enemies{number}_1', '; '.join(first), 11),
            _row(f'enemies{number}_2', '; '.join(second), 11),
            _row(f'note{number}', '', 11),
        ]
    return lines + ['}}']


def abyss_page(start=None, version=''):
    '''(page title, wikitext) for the rotation starting on start (YYYY-MM-DD), or the newest one.'''
    schedule = rotations()
    if not schedule:
        raise ValueError('TowerScheduleExcelConfigData has no rotations.')
    dates = [_opening(row).strftime('%Y-%m-%d') for row in schedule]
    if start:
        if start not in dates:
            raise ValueError(f'No Spiral Abyss rotation starts on {start}. Recent rotations: {", ".join(dates[-6:])}.')
        index = dates.index(start)
    else:
        index = len(schedule) - 1
    current = schedule[index]
    # Without a given version, the wiki's Date to Version gives the one live when the rotation starts.
    version = version or wiki_version(dates[index])
    opening = _opening(current)
    following = _opening(schedule[index + 1]) if index + 1 < len(schedule) else None
    closing = datetime.strptime(current['CloseTime'], TIME_FORMAT) if current.get('CloseTime') else following
    if closing is None:
        raise ValueError(f'The rotation starting on {dates[index]} has no end time.')

    floors = {row['FloorId']: row for row in _load('TowerFloorExcelConfigData')}
    levels = _load('TowerLevelExcelConfigData')
    groups = {}
    for row in _load('DungeonLevelEntityConfigData'):
        groups.setdefault(row['Id'], []).append(row)
    describe_names = {row['Id']: row.get('NameTextMapHash') for row in _load('MonsterDescribeExcelConfigData')
                      if isinstance(row.get('NameTextMapHash'), str)}
    monster_names = {row['Id']: row.get('DescribeName') for row in _load('MonsterExcelConfigData')
                     if isinstance(row.get('DescribeName'), str)}

    floor_ids = current['Schedules'][0].get('FloorList') or []
    previous_ids = set(schedule[index - 1]['Schedules'][0].get('FloorList') or []) if index else set()
    changed = [floors[floor_id] for floor_id in floor_ids if floor_id in floors and floor_id not in previous_ids]

    header = [
        '{{Abyssal Moon Spire',
        _row('startVersion', version, 14),
        _row('start', dates[index], 14),
        _row('end', (closing - DAY_START).strftime('%Y-%m-%d'), 14),
        _row('prev', dates[index - 1] if index else '', 14),
        _row('next', dates[index + 1] if following else (closing + timedelta(seconds=1)).strftime('%Y-%m-%d'), 14),
    ]
    header += [_row(f'floor{floor["FloorIndex"]}Changed', 1, 14) for floor in changed
               if floor['FloorIndex'] in FLOORS_WITH_HEADER_FLAGS]
    blessing = [f'<!-- {_plain(current["BuffnameTextMapHash"])}: {text} -->'
                for text in _effects(groups, current.get('MonthlyLevelConfigId'))
                if isinstance(current.get('BuffnameTextMapHash'), str)]
    lines = [
        '{{Stub|Add enemy counts, waves and spawn notes}}',
        *header, '}}', '',
        '==Blessings of the Abyssal Moon==',
        '{{Blessing of the Abyssal Moon Schedule}}',
        *blessing, '',
        '==Abyssal Moon Spire==',
    ]
    cache = {}
    for floor in changed:
        chambers = sorted((row for row in levels if row['LevelGroupId'] == floor['LevelGroupId']), key=lambda row: row['LevelIndex'])
        disorder = _ley_line_disorder(floor, groups)
        lines += [f'===Floor {floor["FloorIndex"]}===']
        if disorder:
            lines += ["* '''Ley Line Disorder'''", *disorder]
        lines += ['', *_chambers(chambers, describe_names, monster_names, cache), '']
    title = f'Spiral Abyss/Floors/{dates[index]}'
    return title, pageinfo(title) + '\n'.join(lines).rstrip('\n') + '\n'


def write_abyss_page(start=None, version='', directory=None):
    '''Writes the rotation's page to directory (default OutputPath) and returns its path.'''
    report.stage(f'Building Spiral Abyss rotation: {start or "latest"}')
    title, text = abyss_page(start, version)
    path = Path(directory or CONFIG.OUTPUT_PATH) / f'{title.replace("/", " ")}.wikitext'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    report.info(f'Wrote {title} to {path.name}.')
    return path
