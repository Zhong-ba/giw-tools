import json
import re

from getConfig import CONFIG
from utils.files import write_file


def parse_hunting_v2():
    with open(f'{CONFIG.EXCEL_PATH}/HuntingV2MonsterBundleExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        bundleexcel = {item['Id']: item for item in json.load(file)}
    
    with open(f'{CONFIG.EXCEL_PATH}/HuntingV2RegionExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        regionexcel = {item['Id']: item for item in json.load(file)}
        
    with open(f'{CONFIG.EXCEL_PATH}/MonsterExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        monsterexcel = {item['Id']: item for item in json.load(file)}
        
    file_write = ''        
        
    for id, item in bundleexcel.items():
        mons_id = item['MonsterId']
        mons_name = monsterexcel.get(mons_id).get('DescribeName')
        
        mechanism_name = item['MechanismTitle1TextMapHash']
        mechanism_desc = item['MechanismDesc1TextMapHash']
        
        lore_desc = item['NewsTextTextMapHash']
        location = ''
        for region_item in regionexcel.values():
            if id in region_item['MOLHJPBEIKK']:
                location = region_item['RegionInfoTextMapHash']
        lore_desc = lore_desc.replace(r'{0}', location)
        
        trait = item['TraitTextTextMapHash']
        print(trait.split('<br />'))
        strength = trait.split('<br />')[1]
        strength = re.sub(r'Invulnerability to (.*)? ', r'Immune to {{Color|\1}}', strength)
        weakness = trait.split('<br />')[4] + "by '''120<nowiki>%</nowiki>'''."
        weakness = re.sub(r'^(.*)? decreased', r'{{Color|\1}} decreased', weakness)
        
        file_write = file_write + f'''
{{{{Bounty
|enemy      = {mons_name}
|difficulty = Player's Choice
|strength   = {strength};[[{mechanism_name}]]: {mechanism_desc}
|weakness   = {weakness}
|desc       = {lore_desc}
|notes      = 
}}}}'''

    file_write_path = f'{CONFIG.OUTPUT_PATH}/Bounties_V2_Output.wikitext'
    
    write_file(file_write_path, file_write)