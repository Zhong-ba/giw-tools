"""Browse prepared BinOutput JSON and resolve character/enemy/gadget references."""
from collections import defaultdict, deque
from functools import lru_cache
from itertools import islice
import json
import os
from pathlib import Path
import re
from time import monotonic

from travelerKits import TRAVELER_IDS


ATTENUATION = 'AttackAttenuationExcelConfigData.json'
INTERNAL_NAME = re.compile(r'[A-Za-z0-9_]+')
MAX_FILE_SIZE = 16 * 1048576


def binoutput_root(config):
    root = Path(config.get('BinPath') or Path(config['RepoPath']) / 'BinOutput').resolve()
    if not root.is_dir():
        raise FileNotFoundError('BinOutput is not prepared. Run dataset setup first.')
    return root


def binoutput_path(config, key='', *, directory=False):
    root = binoutput_root(config)
    if '\\' in key or ':' in key or key.startswith('/') or any(part in ('.', '..') for part in key.split('/')):
        raise ValueError('Invalid BinOutput path.')
    path = root.joinpath(*key.split('/')).resolve()
    if not path.is_relative_to(root):
        raise ValueError('The path is outside BinOutput.')
    if directory:
        if not path.is_dir():
            raise FileNotFoundError('BinOutput directory not found.')
    elif not path.is_file() or path.suffix.lower() != '.json':
        raise FileNotFoundError('BinOutput JSON file not found.')
    return path


def _visible_children(folder, root):
    for path in folder.iterdir():
        if path.resolve().is_relative_to(root) and (path.is_dir() or path.is_file() and path.suffix.lower() == '.json'):
            yield path


def binoutput_tree(config, key=''):
    root = binoutput_root(config)
    folder = binoutput_path(config, key, directory=True)
    entries = []
    for path in _visible_children(folder, root):
        directory = path.is_dir()
        names, visited = [path.name], {path.resolve()}
        while directory:
            children = list(islice(_visible_children(path, root), 2))
            if len(children) != 1 or not children[0].is_dir() or children[0].resolve() in visited:
                break
            path = children[0]
            visited.add(path.resolve())
            names.append(path.name)
        entries.append({'key': path.relative_to(root).as_posix(), 'name': ' / '.join(names),
                        'directory': directory, 'size': None if directory else path.stat().st_size})
    return {'path': key, 'entries': sorted(entries, key=lambda item: (not item['directory'], item['name'].casefold()))}


@lru_cache(maxsize=4)
def _binoutput_names(root: Path, refresh_window: int) -> tuple[tuple[str, str, str], ...]:
    def fail(error: OSError) -> None:
        raise error

    entries = []
    for folder, directories, files in os.walk(root, onerror=fail):
        parent = Path(folder)
        directories[:] = [name for name in directories if not (parent / name).is_symlink()
                          and (parent / name).resolve().is_relative_to(root)]
        for name in files:
            path = parent / name
            if path.suffix.lower() == '.json' and not path.is_symlink() and path.is_file():
                entries.append((name.casefold(), path.relative_to(root).as_posix(), name))
    return tuple(sorted(entries))


def binoutput_search(config: dict, query: str, limit: int = 100) -> dict:
    root = binoutput_root(config)
    terms = query.casefold().split()
    if not terms:
        raise ValueError('Enter a filename to search.')
    names = _binoutput_names(root, int(monotonic() // 300))
    matches = islice(((key, name) for folded, key, name in names if all(term in folded for term in terms)), limit + 1)
    results = [{'key': key, 'name': name} for key, name in matches]
    return {'entries': results[:limit], 'truncated': len(results) > limit}


def read_reference(item):
    path = item.get('path')
    size = path.stat().st_size if path is not None else len(item['text'].encode('utf-8'))
    if size > MAX_FILE_SIZE:
        raise OverflowError('This file is too large to view (16 MB limit).')
    return path.read_text(encoding='utf-8-sig') if path is not None else item['text']


def _table(config, name, warnings=None):
    path = Path(config['RepoPath']) / 'MappedExcelBinOutput_EN' / f'{name}.json'
    if warnings is not None and not path.is_file():
        warnings.append(f'Reference discovery is limited: {name}.json is missing.')
        return []
    rows = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(rows, list):
        raise ValueError(f'{name}.json must contain a list.')
    return rows


def gadget_rows(config, warnings=None):
    # Text mapping can replace numeric gadget IDs that happen to match text hashes.
    path = Path(config['RepoPath']) / 'ExcelBinOutput' / 'GadgetExcelConfigData.json'
    if path.is_file():
        raw = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(raw, list):
            raise ValueError('GadgetExcelConfigData.json must contain a list.')
        rows = [{'Id': row['id'], 'JsonName': row.get('jsonName'), 'Type': row.get('type')} for row in raw]
    else:
        rows = _table(config, 'GadgetExcelConfigData', warnings)
    if any(not isinstance(row.get('Id'), int) or isinstance(row['Id'], bool) or row['Id'] <= 0 for row in rows):
        raise ValueError('Gadget IDs must be positive integers. Restore the raw ExcelBinOutput/'
                         'GadgetExcelConfigData.json table or run dataset setup again.')
    return rows


def _avatar(config, character_id):
    avatar = next((row for row in _table(config, 'AvatarExcelConfigData') if row.get('Id') == character_id), None)
    if avatar is None:
        raise KeyError(f'Character {character_id} is not in the current dataset.')
    return avatar


def internal_name(config, character_id):
    name = str(_avatar(config, character_id).get('IconName', '')).removeprefix('UI_AvatarIcon_')
    if not INTERNAL_NAME.fullmatch(name):
        raise ValueError(f'Character {character_id} has no usable internal name.')
    return name


def attenuation_rows(config, names):
    path = Path(config['RepoPath']) / 'ExcelBinOutput' / ATTENUATION
    if not path.is_file():
        path = Path(config['RepoPath']) / 'MappedExcelBinOutput_EN' / ATTENUATION
    if not path.is_file():
        return []
    rows = json.loads(path.read_text(encoding='utf-8'))
    lowered = {name.casefold() for name in names}
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get('group', row.get('Group')), str)
            and any(row.get('group', row.get('Group')).casefold() == name
                    or row.get('group', row.get('Group')).casefold().startswith(f'{name}_') for name in lowered)]


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _definitions(data):
    entries = data if isinstance(data, list) else [data]
    for entry in entries:
        if isinstance(entry, dict):
            node = entry.get('Default', entry)
            if isinstance(node, dict) and isinstance(node.get('abilityName'), str):
                yield node['abilityName'], node


@lru_cache(maxsize=4)
def _definition_index(signature, gadget=False):
    found, warnings = defaultdict(set), []
    for filename, _, _ in signature:
        path = Path(filename)
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as error:
            warnings.append(f'Could not index {path.name}: {error}')
            continue
        if gadget:
            definitions = data.items() if isinstance(data, dict) else ()
        else:
            definitions = _definitions(data)
        for name, node in definitions:
            if isinstance(node, dict):
                found[name].add(path)
    return dict(found), warnings


def _index(root, folder, *, gadget=False):
    paths = sorted(path for path in (root / folder).rglob('*.json') if path.resolve().is_relative_to(root))
    signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
    return _definition_index(signature, gadget)


def _gadget_targets(root, index, name):
    if not isinstance(name, str) or not name:
        return {}
    if name in index:
        return {path: name for path in index[name]}
    if not INTERNAL_NAME.fullmatch(name):
        return {}
    return {path: None for path in (root / 'Gadget' / f'{name}.json',
                                   root / 'Gadget' / f'ConfigGadget_{name}.json') if path.is_file()}


def _group(relative):
    parts = relative.parts
    if parts[0] == 'Ability':
        return 'AniEvent' if any('AniEvent' in part for part in parts) else 'Abilities'
    return {'Gadget': 'Skill Objects', 'Talent': 'Talents', 'MonsterPreview': 'Monster Preview'}.get(parts[0], parts[0])


def _resolve(config, names, seeds, warnings, *, gadget_name=None):
    root = binoutput_root(config)
    index, index_warnings = _index(root, 'Ability')
    warnings.extend(index_warnings)
    gadget_index, gadget_warnings = _index(root, 'Gadget', gadget=True)
    warnings.extend(gadget_warnings)
    gadgets = {row['Id']: row.get('JsonName') for row in gadget_rows(config, warnings)}
    found, visited, unresolved, unresolved_gadgets = {}, set(), set(), set()
    pending = deque((path, None, 'Filename or selected kit') for path in seeds)
    if gadget_name is not None:
        targets = _gadget_targets(root, gadget_index, gadget_name)
        if not targets:
            warnings.append(f'No Gadget config found for {gadget_name}.')
        pending.extend((path, entry, f'Selected gadget: {gadget_name}') for path, entry in targets.items())
    while pending:
        path, definition, reason = pending.popleft()
        if not path.resolve().is_relative_to(root):
            raise ValueError(f'Referenced file is outside BinOutput: {path.name}')
        found.setdefault(path, set()).add(reason)
        key = (path, definition)
        if key in visited:
            continue
        visited.add(key)
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as error:
            warnings.append(f'Could not inspect {path.name}: {error}')
            continue
        if definition is not None:
            data = data[definition] if path.relative_to(root).parts[0] == 'Gadget' \
                else [node for name, node in _definitions(data) if name == definition]
        for node in _walk(data):
            linked = node.get('abilityName')
            if isinstance(linked, str):
                for target in index.get(linked, ()):
                    pending.append((target, linked, f'Referenced ability: {linked}'))
                if linked not in index and not (node.get('modifiers') or node.get('abilityMixins')):
                    unresolved.add(linked)
            for field in ('gadgetID', 'gadgetId', 'gadgetIds', 'gadgetIDs'):
                values = node.get(field, [])
                for identifier in values if isinstance(values, list) else [values]:
                    if not isinstance(identifier, int) or isinstance(identifier, bool) or identifier <= 0:
                        continue
                    targets = _gadget_targets(root, gadget_index, gadgets.get(identifier))
                    if not targets:
                        unresolved_gadgets.add(identifier)
                    pending.extend((target, entry, f'Referenced gadget: {identifier}')
                                   for target, entry in targets.items())
    if unresolved:
        warnings.append(f'{len(unresolved)} referenced abilities have no definition in the prepared BinOutput files.')
    if unresolved_gadgets:
        warnings.append(f'{len(unresolved_gadgets)} referenced gadget IDs have no config in the prepared dataset.')
    references, keys = [], set()
    for path in sorted(found, key=lambda path: path.relative_to(root).as_posix().casefold()):
        relative = path.relative_to(root)
        group = _group(relative)
        key = f'{group}/{path.name}'
        if key in keys:
            key = f'{group}/{relative.as_posix()}'
        keys.add(key)
        references.append({'key': key, 'relative': relative.as_posix(), 'group': group, 'name': path.name,
                           'size': path.stat().st_size, 'path': path, 'reasons': sorted(found[path])})
    rows = attenuation_rows(config, names)
    if rows:
        text = json.dumps(rows, indent=2, ensure_ascii=False)
        references.append({'key': f'Attenuation/{ATTENUATION}', 'relative': f'@Excel/{ATTENUATION}',
                           'group': 'Attenuation', 'name': ATTENUATION, 'size': len(text.encode('utf-8')),
                           'path': None, 'text': text, 'reasons': ['Matching attenuation groups']})
    order = {group: index for index, group in enumerate(('Avatar', 'Monster', 'Abilities', 'AniEvent', 'Skill Objects', 'Talents'))}
    references.sort(key=lambda item: (order.get(item['group'], 99), item['relative'].casefold()))
    return references


def character_references(config, character_id):
    """Include all Traveler elements/genders and follow explicit ability and gadget references."""
    avatar = _avatar(config, character_id)
    name = internal_name(config, character_id)
    names = {'Player', 'PlayerBoy', 'PlayerGirl'} if character_id in TRAVELER_IDS else {name}
    warnings = []
    depots = _table(config, 'AvatarSkillDepotExcelConfigData', warnings)
    depot_ids = set(avatar.get('CandSkillDepotIds') or [avatar.get('SkillDepotId')])
    selected = [depot for depot in depots if depot.get('Id') in depot_ids]
    skill_ids, groups, talents = set(), set(), set()
    for depot in selected:
        skill_ids.update(depot.get('Skills') or [])
        skill_ids.add(depot.get('EnergySkill'))
        groups.update(item.get('ProudSkillGroupId') for item in
                      [*(depot.get('InherentProudSkillOpens') or []), *(depot.get('SpecialProudSkillOpens') or [])])
        talents.update(depot.get('Talents') or [])
    for skill in _table(config, 'AvatarSkillExcelConfigData', warnings):
        if skill.get('Id') in skill_ids:
            groups.add(skill.get('ProudSkillGroupId'))
    configs = {row.get('OpenConfig') for row in _table(config, 'ProudSkillExcelConfigData', warnings)
               if row.get('ProudSkillGroupId') in groups and row.get('ProudSkillGroupId')}
    configs.update(row.get('OpenConfig') for row in _table(config, 'AvatarTalentExcelConfigData', warnings)
                   if row.get('TalentId') in talents)
    for config_name in configs - {None, ''}:
        if isinstance(config_name, str):
            alias = re.sub(r'_(?:SkillUpgrade|ProudSkill|Talent|Constellation|PermanentSkill)_?\d*$', '', config_name,
                           flags=re.IGNORECASE)
            if INTERNAL_NAME.fullmatch(alias):
                names.add(alias)
    root = binoutput_root(config)
    seeds = set()
    for alias in names:
        for folder, prefix in (('Avatar', 'ConfigAvatar_'), ('Ability/Temp/AvatarAbilities', 'ConfigAbility_Avatar_'),
                               ('Ability/Temp/AvatarAniEventAbilities', 'ConfigAbility_Avatar_'),
                               ('Gadget', 'ConfigGadget_SkillObj_'), ('Talent/AvatarTalents', 'ConfigTalent_')):
            directory = root.joinpath(*folder.split('/'))
            for pattern in (f'{prefix}{alias}.json', f'{prefix}{alias}_*.json'):
                seeds.update(path for path in directory.glob(pattern) if path.is_file())
    return name, _resolve(config, names, seeds, warnings), list(dict.fromkeys(warnings))


def enemy_references(config, enemy_id):
    row = next((row for row in _table(config, 'MonsterExcelConfigData') if row.get('Id') == enemy_id), None)
    if row is None:
        raise KeyError(f'Enemy {enemy_id} is not in the current dataset.')
    name = row.get('MonsterName')
    if not isinstance(name, str) or not INTERNAL_NAME.fullmatch(name):
        raise ValueError(f'Enemy {enemy_id} has no usable internal name.')
    root = binoutput_root(config)
    seeds = {path for pattern in (f'{name}.json', f'{name}_*.json',
                                 f'ConfigMonster_{name}.json', f'ConfigMonster_{name}_*.json',
                                 f'{enemy_id}.json', f'*_{enemy_id}.json')
             for path in (root / 'Monster').glob(pattern) if path.is_file()}
    warnings = []
    if not seeds:
        warnings.append(f'No Monster configs found for {name}.')
    return name, _resolve(config, {name}, seeds, warnings), warnings


def gadget_references(config, gadget_id):
    row = next((row for row in gadget_rows(config) if row['Id'] == gadget_id), None)
    if row is None:
        raise KeyError(f'Gadget {gadget_id} is not in the current dataset.')
    name = row.get('JsonName')
    if not isinstance(name, str) or not name:
        return str(gadget_id), [], [f'Gadget {gadget_id} has no JsonName in the current dataset.']
    warnings = []
    found = _resolve(config, {name}, (), warnings, gadget_name=name)
    found.sort(key=lambda item: (f'Selected gadget: {name}' not in item['reasons'], item['relative'].casefold()))
    return name, found, list(dict.fromkeys(warnings))
