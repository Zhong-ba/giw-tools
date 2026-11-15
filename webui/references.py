'''Locates the BinOutput and Excel game files associated with a character.'''
import json
from pathlib import Path
import re


ATTENUATION = 'AttackAttenuationExcelConfigData.json'


def internal_name(config, character_id):
    '''Internal file name of a character (e.g. "Ambor" for Amber), from its avatar icon.'''
    with (Path(config['RepoPath']) / 'MappedExcelBinOutput_EN' / 'AvatarExcelConfigData.json').open(encoding='utf-8') as file:
        avatar = next((row for row in json.load(file) if row.get('Id') == character_id), None)
    if avatar is None:
        raise KeyError(f'Character {character_id} is not in the current dataset.')
    name = str(avatar.get('IconName', '')).removeprefix('UI_AvatarIcon_')
    if not re.fullmatch(r'[A-Za-z0-9_]+', name):
        raise ValueError(f'Character {character_id} has no usable internal name.')
    return name


def attenuation_rows(config, name):
    with (Path(config['RepoPath']) / 'ExcelBinOutput' / ATTENUATION).open(encoding='utf-8') as file:
        rows = json.load(file)
    lowered = name.lower()
    return [row for row in rows if isinstance(row, dict) and isinstance(row.get('group'), str)
            and (row['group'].lower() == lowered or row['group'].lower().startswith(f'{lowered}_'))]


def character_references(config, character_id):
    '''Returns (internal name, [{key, group, name, size, path}]); attenuation rows have no path.'''
    name = internal_name(config, character_id)
    binoutput = Path(config.get('BinPath') or Path(config['RepoPath']) / 'BinOutput')
    groups = (
        ('Avatar', binoutput / 'Avatar', [f'ConfigAvatar_{name}.json']),
        ('Abilities', binoutput / 'Ability' / 'Temp' / 'AvatarAbilities',
         [f'ConfigAbility_Avatar_{name}.json', f'ConfigAbility_Avatar_{name}_*.json']),
        ('AniEvent', binoutput / 'Ability' / 'Temp' / 'AvatarAniEventAbilities', [f'ConfigAbility_Avatar_{name}_AniEvent_*.json']),
        ('Skill Objects', binoutput / 'Gadget', [f'ConfigGadget_SkillObj_{name}.json', f'ConfigGadget_SkillObj_{name}_*.json']),
    )
    references = []
    for group, directory, patterns in groups:
        found = sorted({path for pattern in patterns for path in directory.glob(pattern) if path.is_file()})
        references += [{'key': f'{group}/{path.name}', 'group': group, 'name': path.name,
                        'size': path.stat().st_size, 'path': path} for path in found]
    try:
        rows = attenuation_rows(config, name)
    except FileNotFoundError:
        rows = []
    if rows:
        text = json.dumps(rows, indent=2, ensure_ascii=False)
        references.append({'key': f'Attenuation/{ATTENUATION}', 'group': 'Attenuation', 'name': ATTENUATION,
                           'size': len(text.encode('utf-8')), 'path': None, 'text': text})
    return name, references
