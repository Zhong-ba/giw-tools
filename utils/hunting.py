import json
import re

from getConfig import CONFIG
from utils.files import write_file


def _load(name):
    with open(f'{CONFIG.EXCEL_PATH}/{name}.json', 'r', encoding = 'utf-8') as file:
        return json.load(file)


def bundle_regions(regions):
    '''Bundle ID -> the hunting region listing it. The region's bundle list has no stable field name across builds.'''
    result = {}
    for region in regions:
        for value in region.values():
            if isinstance(value, list):
                for bundle_id in value:
                    if isinstance(bundle_id, int):
                        result[bundle_id] = region
    return result


def bounty_list(bundles, regions, monsters, cities):
    '''Picker rows: [{id, name, internal}] with the enemy name and region of each bounty.'''
    names = {monster['Id']: monster.get('DescribeName') for monster in monsters}
    located = bundle_regions(regions)
    return [{'id': bundle['Id'], 'name': names.get(bundle.get('MonsterId')) or str(bundle.get('MonsterId')),
             'internal': cities.get(located.get(bundle['Id'], {}).get('CityId'), '')} for bundle in bundles]


def _traits(trait):
    # Builds separate traits with <br /> or <br>, sometimes inside <ul><li> lists.
    parts = [re.sub(r'</?(?:ul|li)>', '', part).strip() for part in re.split(r'<br\s*/?>', trait)]
    parts = [part for part in parts if part]
    strength = next((part for part in parts if part.startswith('Invulnerability')), '')
    strength = re.sub(r'^Invulnerability to (.+)$', r'Immune to {{Color|\1}}', strength)
    weakness = next((part for part in reversed(parts) if 'decreased' in part), '')
    if weakness:
        weakness = re.sub(r'^(.*?) decreased', r'{{Color|\1}} decreased', weakness) + " by '''120<nowiki>%</nowiki>'''."
    return strength, weakness


def _nowiki_percent(text):
    return text.replace('%', '<nowiki>%</nowiki>')


def bounty_blocks(bundle_ids = None):
    '''Region name -> {{Bounty}} blocks of the given bundles (all when None), in table order.'''
    from utils.fishing import city_names

    bundles = _load('HuntingV2MonsterBundleExcelConfigData')
    located = bundle_regions(_load('HuntingV2RegionExcelConfigData'))
    monsters = {item['Id']: item for item in _load('MonsterExcelConfigData')}
    cities = city_names()
    if bundle_ids is not None:
        known = {bundle['Id'] for bundle in bundles}
        missing = [bundle_id for bundle_id in bundle_ids if bundle_id not in known]
        if missing:
            raise ValueError(f'Bounty {missing[0]} does not exist.')
        wanted = set(bundle_ids)
        bundles = [bundle for bundle in bundles if bundle['Id'] in wanted]

    sections = {}
    for bundle in bundles:
        bundle_id = bundle['Id']
        enemy = monsters.get(bundle['MonsterId'], {}).get('DescribeName') or ''
        region = located.get(bundle_id, {})
        location = region.get('RegionInfoTextMapHash')
        lore = str(bundle.get('NewsTextTextMapHash') or '').replace('{0}', location if isinstance(location, str) else '')
        strength, weakness = _traits(str(bundle.get('TraitTextTextMapHash') or ''))
        for number in (1, 2):
            title, desc = bundle.get(f'MechanismTitle{number}TextMapHash'), bundle.get(f'MechanismDesc{number}TextMapHash')
            if isinstance(title, str) and title:
                strength += f';[[{title}]]: {_nowiki_percent(desc) if isinstance(desc, str) else ""}'

        sections.setdefault(cities.get(region.get('CityId'), ''), []).append(f'''{{{{Bounty
|enemy      = {enemy}
|difficulty = Player's Choice
|strength   = {strength}
|weakness   = {weakness}
|desc       = {lore.replace(chr(10), '<br>')}
|notes      = 
}}}}''')
    return sections


def bounties_wikitext(bundle_ids = None):
    return '\n\n'.join((f'=={region}==\n' if region else '') + '\n'.join(blocks)
                       for region, blocks in bounty_blocks(bundle_ids).items())


def parse_hunting_v2(bundle_ids = None, file_name = 'Bounties_V2_Output.wikitext'):
    text = bounties_wikitext(bundle_ids)
    write_file(f'{CONFIG.OUTPUT_PATH}/{file_name}', text + '\n')
    return text
