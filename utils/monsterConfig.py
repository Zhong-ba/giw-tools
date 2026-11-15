'''Reads combat properties from BinOutput/Monster configs.

Some sources keep readable keys (combat.property.weight); others scramble every key per build.
'''
from functools import lru_cache
import json
from pathlib import Path
import re


SCHEMA = Path(__file__).resolve().parents[1] / 'leo' / 'dataSchema.json'
FIELDS = ('weight', 'bonusRange', 'endureType')
SCRAMBLED = re.compile(r'[A-Z]{11}')


@lru_cache(maxsize=1)
def scrambled_names():
    with SCHEMA.open(encoding='utf-8') as file:
        return json.load(file)['monsterConfig']


def is_endure_type(value):
    return isinstance(value, str) and value.startswith('Monster_') and not value.startswith('Monster_TauntLevel')


def readable_property(block):
    names = scrambled_names()
    result = {}
    for field in FIELDS:
        key = next((key for key in (field, *names.get(field, [])) if key in block), None)
        if key is not None:
            result[field] = block[key]
    endure_type = next((value for value in block.values() if is_endure_type(value)), None)
    if endure_type is not None:
        result.setdefault('endureType', endure_type)
    if 'weight' not in result and 'bonusRange' not in result:
        # Nearly every property block has exactly one number: the weight (or bonus range).
        numbers = [value for value in block.values() if isinstance(value, (int, float)) and not isinstance(value, bool)]
        if len(numbers) == 1:
            result['weight'] = numbers[0]
    return result


def complete(block):
    return 'endureType' in block and ('weight' in block or 'bonusRange' in block)


def monster_property(config):
    if not isinstance(config, dict):
        return None
    if 'combat' in config:
        combat = config['combat']
        if not isinstance(combat, dict):
            return None
        property_dict = combat.get('property')
        if not isinstance(property_dict, dict):
            return None
        # Deobfuscated configs may keep a few fields scrambled; recover them structurally.
        return property_dict if complete(property_dict) else {**readable_property(property_dict), **property_dict}
    if not any(SCRAMBLED.fullmatch(key) for key in config):
        return None  # Readable config without combat properties.
    # Scrambled build: the property block is the nested object holding the endure type.
    for combat in config.values():
        if isinstance(combat, dict):
            for block in combat.values():
                if isinstance(block, dict) and any(is_endure_type(value) for value in block.values()):
                    return readable_property(block)
    return None
    # Scrambled build: the property block is the nested object holding the endure type.
    for combat in config.values():
        if isinstance(combat, dict):
            for block in combat.values():
                if isinstance(block, dict) and any(is_endure_type(value) for value in block.values()):
                    return readable_property(block)
    return None
