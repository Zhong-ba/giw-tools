import json
import argparse
import os
import re
import OLGen
from OLGen import gen_ol
from PIL import Image

from utils.redirect import file_redirect
from utils.files import write_file
from utils.pageinfo import pageinfo
from getConfig import CONFIG

LINK_KEYWORDS = [
    'Nightsoul point',
    'Liquid Phlogiston',
    'Phlogiston',
    'Nightsoul\'s Blessing',
    'ATK',
    'DEF',
    'HP',
    'Elemental Mastery',
    'Energy Recharge',
    'CRIT Rate',
    'CRIT DMG',
    'Healing Bonus',
    'Shield Strength',
    'Interruption resistance',
    'Interruption Resistance',
    'Healing',
    'Heal',
    'Talent',
    'Sprinting',
    'Climbing',
    'Swimming',
    'Party',
    'Elemental RES',
    'RES',
    'Movement SPD',
    'Conversion',
    'Sprint',
    'Water',
    'Stamina',
    'CD',
    'Energy',
    'Nightsoul Burst',
    'Nightsoul Transmission',
    'Natlan',
]

parser = argparse.ArgumentParser()
parser.add_argument('--id', type=int)
parser.add_argument('--ver', type=float)
parser.add_argument('--files', type=bool)
parser.add_argument('--elem', type=str)
parser.add_argument('--natlan', type=bool)
parser.add_argument('--traveler', type=int)
parser.add_argument('--skilldepot', type=int)

args = parser.parse_args()

OLGen.load_data()


def extract_last_digits(input_str):
    last_three_digits = input_str[-3:]
    
    if last_three_digits[0] == '0':
        return last_three_digits[-2:]
    else:
        return last_three_digits
    

with open(f'{CONFIG.EXCEL_PATH}/AvatarSkillExcelConfigData.json', 'r', encoding='utf-8') as file:
    skillexcel = json.load(file)
        
with open(f'{CONFIG.EXCEL_PATH}/ProudSkillExcelConfigData.json', 'r', encoding='utf-8') as file:
    proudskillexcel = json.load(file)
    
with open(f'{CONFIG.EXCEL_PATH}/AvatarTalentExcelConfigData.json', 'r', encoding='utf-8') as file:
    talentexcel = json.load(file)
    
with open(f'{CONFIG.EXCEL_PATH}/HyperLinkNameExcelConifgData.json', 'r', encoding='utf-8') as file:
    hyperlinkexcel = json.load(file)
    

char_id = extract_last_digits(str(args.id))
ver = str(args.ver)
files = args.files
bg_element = args.elem

ability_list = [
    [lambda depot: depot['Skills'][0], 'NA', 'Normal Attack'],
    [lambda depot: depot['Skills'][1], 'E', 'Elemental Skill'],
    [lambda depot: depot['EnergySkill'], 'Q', 'Elemental Burst']
]

passive_list = [
    [lambda depot: depot['InherentProudSkillOpens'][0]['ProudSkillGroupId'], 'A1', '1st Ascension Passive'],
    [lambda depot: depot['InherentProudSkillOpens'][1]['ProudSkillGroupId'], 'A4', '4th Ascension Passive'],
]
if args.natlan:
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'], 'NRG', "Night Realm's Gift Passive"])
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][4]['ProudSkillGroupId'], 'UP', 'Utility Passive'])
elif not args.traveler:
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'], 'UP', 'Utility Passive'])
    
cons_list = [['1', 'C1'], ['2', 'C2'], ['3', 'C3'], ['4', 'C4'], ['5', 'C5'], ['6', 'C6']]
cons_list = [
    [lambda depot: depot['Talents'][0], 'C1'],
    [lambda depot: depot['Talents'][1], 'C2'],
    [lambda depot: depot['Talents'][2], 'C3'],
    [lambda depot: depot['Talents'][3], 'C4'],
    [lambda depot: depot['Talents'][4], 'C5'],
    [lambda depot: depot['Talents'][5], 'C6']
]

character = ''

passive_effects = {}
cons_effects = {}
        

def processIcon(path, type, name, folder):
    try:
        icon = Image.open(f'{CONFIG.IMAGE_PATH}/{path}.png').convert('RGBA')
        bg = Image.open(f'{CONFIG.TALENT_BG_PATH}/{type} {bg_element}.png').convert('RGBA')

        x = (bg.width - icon.width) // 2
        y = (bg.height - icon.height) // 2

        base_image = Image.new('RGBA', bg.size, (0, 0, 0, 0))

        base_image.paste(icon, (x, y), None)

        final_image = Image.alpha_composite(bg, base_image)

        output_path = f'{CONFIG.OUTPUT_PATH}/Images/{folder}'
        if not os.path.exists(output_path):
            os.makedirs(output_path)
            
        file_name_clean = name.replace(":", "").replace("\"", "").replace('?', '')
        
        if file_name_clean != name:
            file_redirect(f'{name}.png', f'{file_name_clean}.png')

        final_image.save(f'{output_path}/{file_name_clean}.png')
        print(f'Processed icon saved to: {output_path}/{file_name_clean}.png')
    except FileNotFoundError as error:
        print(f'The file was not found: {error.filename}')
        
        
def parse_hyperlink(desc):
    hyperlinks = re.findall(r'\{LINK#N.*?\}.*?\{/LINK\}', desc)
    
    for hyperlink in hyperlinks:
        hyperlink_id = re.search(r'\{LINK#N(\d+)\}', hyperlink).group(1)
        text = re.search(r'\{LINK#N\d+\}(.*?)\{/LINK\}', hyperlink).group(1)
        
        for block in hyperlinkexcel:
            if block['Id'] == int(hyperlink_id):
                title = block['NameTextMapHash']
                content = block['DescTextMapHash']
                replace = f'{{{{Extra Effect|{text}|{title}|{content}}}}}'
                
                desc = desc.replace(hyperlink, replace)
                
    desc = re.sub(r'\{LINK#.*?\}(.*?)\{/LINK\}', r'\1', desc)
            
    return desc
        
        
def add_wikilinks(ability_description):
    extra_effect_blocks = []
    def mask_extra_effect(match):
        extra_effect_blocks.append(match.group(0))
        return f"__EXTRA_EFFECT_{len(extra_effect_blocks)-1}__"
    masked_desc = re.sub(r'\{LINK#N.*?\}.*?\{/LINK\}', mask_extra_effect, ability_description)

    for keyword in LINK_KEYWORDS:
        pattern = r'(?<!\[\[)\b(' + re.escape(keyword) + r')(\b|(?=s))(?!\]\])'
        masked_desc = re.sub(pattern, r'[[\1]]', masked_desc, count=1, flags=re.IGNORECASE)

    def unmask_extra_effect(match):
        idx = int(match.group(1))
        return extra_effect_blocks[idx]
    result = re.sub(r'__EXTRA_EFFECT_(\d+)__', unmask_extra_effect, masked_desc)
    return result


def parse_skill(id, ver, type = None, ability_dict = None):        
    for block in avatarconfig:
        if block['Id'] == args.id:
            character = block['NameTextMapHash']
    
    for block in skillexcel:
        if block['Id'] == id:
            name = block['NameTextMapHash']
            
            if not type:
                if id % 10 == 1:
                    type = 'Normal Attack'
                elif id % 10 == 2:
                    type = 'Elemental Skill'
                elif id % 10 == 5:
                    type = 'Elemental Burst'
                
            if files and type != 'Normal Attack':
                icon = block['SkillIcon']
                if type == 'Elemental Burst':
                    icon = icon + '_HD'
                processIcon(icon, 'Talent', f'Talent {name}', f'{character} Talent Icons')
            
            try:
                energyCost = block['CostElemVal']
            except KeyError:
                energyCost = ''
                
            if block['CdTime']:
                cd = str(block['CdTime']) + 's'
            else:
                cd = ''
                
            desc = block['DescTextMapHash']
            
            extradesc = block.get('ExtraDescTextMapHash')
            
            if isinstance(extradesc, str):
                flavortxt_wikitext = f'\n{{{{Description|{extradesc[11:-4]}}}}}'
            else:
                flavortxt_wikitext = ''
            
            ol_text = gen_ol(name)
            vo_text = '==Voice-Overs==\n{{Talent VO}}\n\n'
                
            for checktype, ability in ability_dict.items():
                if checktype == type:
                    continue
                
                if ability in desc:
                    desc = desc.replace(ability, f'[[{ability}]]', 1)
                    
            desc = add_wikilinks(desc)
            desc = parse_hyperlink(desc)
            
            # talent note
            passive_effect_wikitext = ''
            cons_effects_wikitext = ''
            
            if passive_effects.get(str(id)):
                for name, i in passive_effects[str(id)]:
                    passive_effect_wikitext = f'{passive_effect_wikitext}\n* {{{{Talent Note|ascension|{i}|{name}}}}}'

            if passive_effect_wikitext:
                passive_effect_wikitext = f';<big>Passive Effects</big>{passive_effect_wikitext}\n'
            else:
                passive_effect_wikitext = ';<big>Passive Effects</big>\n* {{Talent Note|ascension||}}\n'
            
            if cons_effects.get(str(id)):
                for name, i in cons_effects[str(id)]:
                    cons_effects_wikitext = f'{cons_effects_wikitext}\n* {{{{Talent Note|constellation|{i}|{name}}}}}'
            
            if cons_effects_wikitext:
                cons_effects_wikitext = f';<big>Constellation Effects</big>{cons_effects_wikitext}\n'
            else:
                cons_effects_wikitext = ';<big>Constellation Effects</big>\n* {{Talent Note|constellation||}}\n'
            
            passive_effect_wikitext = f'{passive_effect_wikitext}\n'
            cons_effects_wikitext = f'{cons_effects_wikitext}\n'
            
    page_content = f"""{pageinfo(name)}
{{{{Talent Infobox
|image         = Talent {name}.png
|character     = {character}
|type          = {type}
|info          = {desc}
|CD            = {cd}
|energyCost    = {energyCost}
|scale_att1    = 
|scale_att2    = 
|utility1      = 
|utility2      = 
|arkhe         = 
}}}}{flavortxt_wikitext}
'''{name}''' is [[{character}]]'s [[{type}]].

==Gameplay Notes==
{passive_effect_wikitext}{cons_effects_wikitext}==Advanced Properties==


==Preview==
{{{{Preview
|file1 = {name} Preview
}}}}

==Attribute Scaling==


==Talent Leveling==
{{{{Talent Upgrade|{character}}}}}

{vo_text}==Other Languages==
{ol_text}

==Change History==
{{{{Change History|{ver}}}}}

==Navigation==
{{{{Talent Navbox|{character}}}}}"""
    
    return(page_content)


def parse_passive(id, ver, type = None, ability_dict = None):
    for block in avatarconfig:
        if block['Id'] == args.id:
            character = block['NameTextMapHash']
            
    for block in proudskillexcel:
        if block['ProudSkillId'] == id or block.get('ProudSkillGroupId') == id:
            
            name = block['NameTextMapHash']
            desc = block['DescTextMapHash']

            if not type:
                try:
                    if block['BreakLevel'] == 1:
                        type = '1st Ascension Passive'
                    elif block['BreakLevel'] == 4:
                        type = '4th Ascension Passive'
                except KeyError:
                    if args.natlan and "Night Realm's Gift" in name:
                        type = "Night Realm's Gift Passive"
                    else:
                        type = 'Utility Passive'
            
            ol_text = gen_ol(name)
            
            if type == "Night Realm's Gift Passive":
                name = name[20:]
             
            if files:
                icon = block['Icon']
                processIcon(icon, 'Talent', f'Talent {name}', f'{character} Talent Icons')
                
            for checktype, ability in ability_dict.items():
                if checktype == type:
                    continue
                
                if ability in desc:
                    desc = desc.replace(ability, f'[[{ability}]]', 1)
    
    desc = add_wikilinks(desc)
    desc = parse_hyperlink(desc)

    page_content = f"""{pageinfo(name)}
{{{{Talent Infobox
|image         = Talent {name}.png
|character     = {character}
|type          = {type}
|info          = {desc}
|scale_att1    = 
|scale_att2    = 
|utility1      = 
|utility2      = 
}}}}
'''{name}''' is [[{character}]]'s [[{type}]].
<!--
==Gameplay Notes==
-->
==Other Languages==
{ol_text}

==Change History==
{{{{Change History|{ver}}}}}

==Navigation==
{{{{Talent Navbox|{character}}}}}
"""
    
    return(page_content)


def parse_cons(id, ver, ability_dict):
    for block in avatarconfig:
        if block['Id'] == args.id:
            character = block['NameTextMapHash']
    
    for block in talentexcel:
        if block['TalentId'] == id:
            name = block['NameTextMapHash']
            rank = id % 10
            desc = block['DescTextMapHash']
            
            if files:
                icon = block['Icon']
                processIcon(icon, 'Constellation', f'Constellation {name}', f'{character} Constellation Icons')
                
            ol_text = gen_ol(name)
            
            utility1 = ''
            utility2 = ''
            
            if ability_dict['Normal Attack'] in desc:
                desc = desc.replace(ability_dict['Normal Attack'], f'[[{ability_dict["Normal Attack"]}]]', 1)
                if rank in [3, 5]:
                    utility2 = 'Normal Attack Level Increase'
                
            if ability_dict['Elemental Skill'] in desc:
                desc = desc.replace(ability_dict['Elemental Skill'], f'[[{ability_dict["Elemental Skill"]}]]', 1)
                if rank in [3, 5]:
                    utility2 = 'Elemental Skill Level Increase'
            
            if ability_dict['Elemental Burst'] in desc:
                desc = desc.replace(ability_dict['Elemental Burst'], f'[[{ability_dict["Elemental Burst"]}]]', 1)
                if rank in [3, 5]:
                    utility2 = 'Elemental Burst Level Increase'
                
            if utility2:
                utility1 = 'Talent Level Increase'         
    
    desc = add_wikilinks(desc)
    desc = parse_hyperlink(desc)
    
    page_content = f"""{pageinfo(name)}
{{{{Constellation Infobox
|image         = Constellation {name}.png
|character     = {character}
|level         = {rank}
|description   = {desc}
|scale_att1    = 
|scale_att2    = 
|utility1      = {utility1}
|utility2      = {utility2}
}}}}
'''{name}''' is [[{character}]]'s [[Level {rank} Constellation]].
<!--
==Gameplay Notes==
--><!--
==Preview==
{{{{Preview
|file = {name} Preview
}}}}
-->
==Other Languages==
{ol_text}

==Change History==
{{{{Change History|{ver}}}}}

==Navigation==
{{{{Talent Navbox|{character}}}}}
"""
    
    return(page_content)


def get_skill_name(id):
    for block in skillexcel:
        if block['Id'] == id:
            name = block['NameTextMapHash']
    
    return name


def get_passive_name(id):
    for block in proudskillexcel:
        if block['ProudSkillId'] == id or block.get('ProudSkillGroupId') == id:
            name = block['NameTextMapHash']
    
    return name


def get_cons_name(id):
    for block in talentexcel:
        if block['TalentId'] == id:
            name = block['NameTextMapHash']
    
    return name


def get_cons_desc(id):
    for block in talentexcel:
        if block['TalentId'] == id:
            desc = block['DescTextMapHash']
    
    return desc


def get_passive_effects(id, i):
    for block in proudskillexcel:
        if block['ProudSkillId'] == id or block.get('ProudSkillGroupId') == id:
            name = block['NameTextMapHash']
            desc = block['DescTextMapHash']
            
            affected_abilities = re.findall(r'\{LINK#S(\d+)\}', desc)
            affected_abilities = list(set(affected_abilities))
            
            for ability in affected_abilities:
                if passive_effects.get(ability) is None:
                    passive_effects[ability] = []
                    
                passive_effects[ability].append([name, i + 1])
                

def get_cons_effects(id, i):
    for block in talentexcel:
        if block['TalentId'] == id:
            name = block['NameTextMapHash']
            desc = block['DescTextMapHash']
            
            affected_abilities = re.findall(r'\{LINK#S(\d+)\}', desc)
            affected_abilities = list(set(affected_abilities))
            
            for ability in affected_abilities:
                if cons_effects.get(ability) is None:
                    cons_effects[ability] = []
                    
                cons_effects[ability].append([name, i + 1])


with open(f'{CONFIG.EXCEL_PATH}/AvatarExcelConfigData.json', 'r', encoding='utf-8') as file:
    avatarconfig = json.load(file)
    
with open(f'{CONFIG.EXCEL_PATH}/AvatarSkillDepotExcelConfigData.json', 'r', encoding='utf-8') as file:
    skilldepotconfig = json.load(file)
    
with open(f'{CONFIG.EXCEL_PATH}/FetterInfoExcelConfigData.json', 'r', encoding='utf-8') as file:
    fetterinfoconfig = json.load(file)
     
if not char_id == "None":
    for block in avatarconfig:
        if block['Id'] == args.id:
            character = block['NameTextMapHash']
            
    if not bg_element:
        for block in fetterinfoconfig:
            if block['AvatarId'].get('Name', block['AvatarId'].get('name')) == character:
                bg_element = block['AvatarVisionBeforTextMapHash']
    
    if not args.skilldepot:
        skilldepotid = int(char_id + '01')
    else:
        skilldepotid = args.skilldepot
        
    for block in skilldepotconfig:
        if block['Id'] == skilldepotid:
            skilldepot: dict = block

    if not os.path.exists(f'{CONFIG.OUTPUT_PATH}/{character}/Skills'):
        os.makedirs(f'{CONFIG.OUTPUT_PATH}/{character}/Skills')
    if not os.path.exists(f'{CONFIG.OUTPUT_PATH}/{character}/Passives'):
        os.makedirs(f'{CONFIG.OUTPUT_PATH}/{character}/Passives')
    if not os.path.exists(f'{CONFIG.OUTPUT_PATH}/{character}/Constellations'):
        os.makedirs(f'{CONFIG.OUTPUT_PATH}/{character}/Constellations')
        
    ability_dict = {}
    
    ability_dict['Normal Attack'] = get_skill_name(ability_list[0][0](skilldepot))
    ability_dict['Elemental Skill'] = get_skill_name(ability_list[1][0](skilldepot))
    ability_dict['Elemental Burst'] = get_skill_name(ability_list[2][0](skilldepot))
    ability_dict['1st Ascension Passive'] = get_passive_name(passive_list[0][0](skilldepot))
    ability_dict['4th Ascension Passive'] = get_passive_name(passive_list[1][0](skilldepot))
    
    for i, passive in enumerate(passive_list):
        if i < 2:
            get_passive_effects(passive[0](skilldepot), i)
    print('Passive effects:', passive_effects)
    
    for i, cons in enumerate(cons_list):
        get_cons_effects(cons[0](skilldepot), i)
    print('Constellation effects:', cons_effects)
        
    for ability in ability_list:
        file_write_path = f'{CONFIG.OUTPUT_PATH}/{character}/Skills/{ability[1]}.wikitext'
        id = ability[0](skilldepot)
        
        write_file(file_write_path, parse_skill(id, ver, ability[2], ability_dict), overwrite = True)
        
    for passive in passive_list:
        file_write_path = f'{CONFIG.OUTPUT_PATH}/{character}/Passives/{passive[1]}.wikitext'
        id = passive[0](skilldepot)
        
        write_file(file_write_path, parse_passive(id, ver, passive[2], ability_dict), overwrite = True)
        
    for cons in cons_list:
        file_write_path = f'{CONFIG.OUTPUT_PATH}/{character}/Constellations/{cons[1]}.wikitext'
        id = cons[0](skilldepot)
        
        write_file(file_write_path, parse_cons(id, ver, ability_dict), overwrite = True)
    