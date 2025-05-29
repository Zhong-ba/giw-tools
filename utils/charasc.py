'''THIS IS UNFINISHED AND IM TOO LAZY TO FINISH IT'''

import json

from getConfig import CONFIG


def parse_charasc():
    with open(f'{CONFIG.EXCEL_PATH}/AvatarExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        avatarjson = json.load(file)
    
    with open(f'{CONFIG.EXCEL_PATH}/AvatarPromoteExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        promotejson = json.load(file)
    
    banned_names = ['Kate']
    out = {
        ['Test Character']: {
            ['quality']: 4,
            ['gem']: 'Brilliant Diamond',
            ['boss']: None,
            ['local']: 'Windwheel Aster',
            ['common']: { 'Damaged Mask', 'Stained Mask', 'Ominous Mask' },
            ['spec']: None,
            ['spec_base']: None,
            ['base_hp']: None,
            ['asc_hp']: None,
            ['base_atk']: None,
            ['asc_atk']: None,
            ['base_def']: None,
            ['asc_def']: None
        },
    }
    out_new = {}
    
    for item in avatarjson:
        name = item['NameTextMapHash']
        if name in banned_names:
            continue
        
        base_hp = item['HpBase']
        base_atk = item['AttackBase']
        base_def = item['DefenseBase']
        
        promote_id = item['AvatarPromoteId']
        promote = {}
        
        for promote_item in promotejson:
            if promote_item['AvatarPromoteId'] == promote_id and promote_item['PromoteLevel'] == 6:
                promote = promote_item
        
        continue
    
    return