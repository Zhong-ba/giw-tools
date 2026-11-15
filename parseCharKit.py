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
from talentScaling import scaling_stats
from talentUtilities import utilities, utility_lines

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
parser.add_argument('--ver', type=str, help='Release version; looked up in the wiki article\'s Change History if omitted.')
parser.add_argument('--files', type=bool)
parser.add_argument('--elem', type=str)
parser.add_argument('--natlan', type=bool)
parser.add_argument('--nodkrai', type=bool)
parser.add_argument('--hexerei', type=bool)
parser.add_argument('--stellar', type=bool)
parser.add_argument('--traveler', type=int)
parser.add_argument('--skilldepot', type=int)
parser.add_argument('--levels', type=int, nargs=3, default=[11, 13, 13], metavar=('NA', 'E', 'Q'),
                    help='Max talent levels for the Attribute Scaling tables.')
parser.add_argument('--noscaling', type=bool)
parser.add_argument('--noap', type=bool, help='Leave the Advanced Properties sections empty (talents, passives, constellations).')
parser.add_argument('--nodetect', type=bool, help="Don't detect the special passive type when no --natlan/--nodkrai/--hexerei/--stellar is given.")

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
ver = args.ver
files = args.files
bg_element = args.elem

if args.id and not (args.natlan or args.nodkrai or args.hexerei or args.stellar or args.traveler or args.nodetect):
    from passiveTypes import character_passive_types, passive_types
    if args.skilldepot:
        with open(f'{CONFIG.EXCEL_PATH}/AvatarSkillDepotExcelConfigData.json', 'r', encoding='utf-8') as file:
            detected = passive_types(next((block for block in json.load(file) if block['Id'] == args.skilldepot), {}), proudskillexcel)
    else:
        detected = character_passive_types(args.id)
    for kind in detected:
        setattr(args, kind, True)
        print(f'Detected special passive type: --{kind}')


def special_slot(depot):
    # Stellar Jubilee passives sit in the third inherent slot with the Utility Passive in the fifth, like Night
    # Realm's Gift; other Stellar passives (e.g. Cyno's) are quest-unlocked special passives.
    opens = depot['InherentProudSkillOpens']
    return len(opens) > 4 and bool(opens[4].get('ProudSkillGroupId'))

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
if args.nodkrai:
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'], 'MB', 'Moonsign Benediction Passive'])
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][4]['ProudSkillGroupId'], 'UP', 'Utility Passive'])
if args.hexerei:
    passive_list.append([lambda depot: depot['SpecialProudSkillOpens'][0]['ProudSkillGroupId'], 'WER', "Witch's Eve Rite Passive"])
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'], 'UP', 'Utility Passive'])
if args.stellar:
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'] if special_slot(depot)
                         else depot['SpecialProudSkillOpens'][0]['ProudSkillGroupId'], 'SP', 'Passive'])
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][4 if special_slot(depot) else 2]['ProudSkillGroupId'],
                         'UP', 'Utility Passive'])
elif not args.traveler and not args.natlan and not args.nodkrai and not args.hexerei:
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'], 'UP', 'Utility Passive'])
    
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


def parse_skill(id, ver, type = None, ability_dict = None, scaling = '', advanced = ''):        
    for block in avatarconfig:
        if block['Id'] == args.id:
            character = block['NameTextMapHash']
    
    for block in skillexcel:
        if block['Id'] == id:
            talentname = block['NameTextMapHash']
            
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
                processIcon(icon, 'Talent', f'Talent {talentname}', f'{character} Talent Icons')
            
            energyCost = block.get('CostElemVal', '')
                
            if block.get('CdTime'):
                cd = str(block['CdTime']) + 's'
            else:
                cd = ''
                
            desc = block['DescTextMapHash']
            utility = utility_lines(utilities(desc, 'T'))
            
            extradesc = block.get('ExtraDescTextMapHash')
            flavortxt_wikitext = ''
            
            if isinstance(extradesc, str):
                flavortxt_wikitext = f'\n{{{{Description|{extradesc[11:-4]}}}}}'
            else:
                parts = desc.split('<br><br><i>', 1)
                if len(parts) > 1:
                    desc = parts[0]
                    extradesc = parts[1].split('</i>', 1)[0]
                    flavortxt_wikitext = f'\n{{{{Description|{extradesc}}}}}'
            
            ol_text = gen_ol(talentname)
            vo_text = '==Voice-Overs==\n{{Talent VO}}\n\n'
                
            for checktype, ability in ability_dict.items():
                if checktype == type:
                    continue
                
                if ability in desc:
                    desc = desc.replace(ability, f'[[{ability}]]', 1)
                    
            # "Pneuma-aligned", or "Pneuma- or Ousia-aligned" for attacks that use either.
            arkhe = ';'.join(dict.fromkeys(re.findall(r'\b(Pneuma|Ousia)-(?:aligned|\s+or\b)', desc)))
            
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
    
    stats = scaling_stats(scaling)
    scale_att = ''.join(f'|scale_att{n:<5}= {stat}\n' for n, stat in enumerate(stats + [''] * (2 - len(stats)), 1))
    arkhe_line = f'|arkhe         = {arkhe}\n' if fontaine else ''
    # None means Advanced Properties didn't run, so the section stays for manual filling.
    advanced_wikitext = '==Advanced Properties==\n\n\n' if advanced is None else f'{advanced_section(advanced)}\n' if advanced else ''
            
    page_content = f"""{pageinfo(talentname)}
{{{{Talent Infobox
|image         = Talent {talentname}.png
|character     = {character}
|type          = {type}
|info          = {desc}
|CD            = {cd}
|energyCost    = {energyCost}
{scale_att}{utility}{arkhe_line}}}}}{flavortxt_wikitext}
'''{talentname}''' is [[{character}]]'s [[{type}]].

==Gameplay Notes==
{passive_effect_wikitext}{cons_effects_wikitext}{advanced_wikitext}==Preview==
{{{{Preview
|file1 = {talentname} Preview
}}}}

==Attribute Scaling==
{scaling}

==Talent Leveling==
{{{{Talent Upgrade|{character}}}}}

{vo_text}==Other Languages==
{ol_text}

==Change History==
{{{{Change History|{ver}}}}}

==Navigation==
{{{{Talent Navbox|{character}}}}}"""
    
    return page_content


def advanced_section(advanced):
    return f'==Advanced Properties==\n{advanced}\n' if advanced else ''


def parse_passive(id, ver, type = None, ability_dict = None, advanced = ''):
    for block in avatarconfig:
        if block['Id'] == args.id:
            character = block['NameTextMapHash']
            
    for block in proudskillexcel:
        if block['ProudSkillId'] == id or block.get('ProudSkillGroupId') == id:
            
            name = block['NameTextMapHash']
            desc = block['DescTextMapHash']
            utility = utility_lines(utilities(desc, 'P'))

            if not type:
                try:
                    if block['BreakLevel'] == 1:
                        type = '1st Ascension Passive'
                    elif block['BreakLevel'] == 4:
                        type = '4th Ascension Passive'
                except KeyError:
                    if args.natlan and "Night Realm's Gift" in name:
                        type = "Night Realm's Gift Passive"
                    if args.nodkrai and "Moonsign Benediction" in name:
                        type = "Moonsign Benediction Passive"
                    if args.hexerei and "Witch's Eve Rite" in name:
                        type = "Witch's Eve Rite Passive"
                    else:
                        type = 'Utility Passive'
            
            ol_text = gen_ol(name)
            
            if type == "Night Realm's Gift Passive":
                name = name[20:]
            if type == "Moonsign Benediction Passive":
                name = name[22:]
            if type == "Witch's Eve Rite Passive":
                name = re.sub(r"^Witch's Eve Rite\s*[:·]\s*", '', name)
             
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
{utility}}}}}
'''{name}''' is [[{character}]]'s [[{type}]].
<!--
==Gameplay Notes==
-->
{advanced_section(advanced)}==Other Languages==
{ol_text}

==Change History==
{{{{Change History|{ver}}}}}

==Navigation==
{{{{Talent Navbox|{character}}}}}
"""
    
    return page_content


def parse_cons(id, ver, ability_dict, advanced = ''):
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
                if rank in (3, 5):
                    utility2 = 'Normal Attack Level Increase'
                
            if ability_dict['Elemental Skill'] in desc:
                desc = desc.replace(ability_dict['Elemental Skill'], f'[[{ability_dict["Elemental Skill"]}]]', 1)
                if rank in (3, 5):
                    utility2 = 'Elemental Skill Level Increase'
            
            if ability_dict['Elemental Burst'] in desc:
                desc = desc.replace(ability_dict['Elemental Burst'], f'[[{ability_dict["Elemental Burst"]}]]', 1)
                if rank in (3, 5):
                    utility2 = 'Elemental Burst Level Increase'
                
            if utility2:
                utility1 = 'Talent Level Increase'
            utility = utility_lines([u for u in (utility1, utility2) if u] + utilities(desc, 'C'))
    
    desc = add_wikilinks(desc)
    desc = parse_hyperlink(desc)
    constellation_advanced = f'\n{advanced_section(advanced)}' if advanced else ''
    
    page_content = f"""{pageinfo(name)}
{{{{Constellation Infobox
|image         = Constellation {name}.png
|character     = {character}
|level         = {rank}
|description   = {desc}
|scale_att1    = 
|scale_att2    = 
{utility}}}}}
'''{name}''' is [[{character}]]'s [[Level {rank} Constellation]].
<!--
==Gameplay Notes==
-->{constellation_advanced}<!--
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
    
    return page_content


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


with open(f'{CONFIG.EXCEL_PATH}/AvatarExcelConfigData.json', 'r', encoding='utf-8') as file:
    avatarconfig = json.load(file)
    
with open(f'{CONFIG.EXCEL_PATH}/AvatarSkillDepotExcelConfigData.json', 'r', encoding='utf-8') as file:
    skilldepotconfig = json.load(file)
    
with open(f'{CONFIG.EXCEL_PATH}/FetterInfoExcelConfigData.json', 'r', encoding='utf-8') as file:
    fetterinfoconfig = json.load(file)
     
if char_id != "None":
    for block in avatarconfig:
        if block['Id'] == args.id:
            character = block['NameTextMapHash']

    if not ver:
        from wikiVersion import release_version
        try:
            ver = release_version(character)
        except OSError as error:
            print(f'Could not check the wiki for the release version: {error}')
        if not ver:
            raise SystemExit(f'No release version found for {character} on the wiki; pass --ver.')
        print(f'Release version from the wiki Change History: {ver}')
            
    if not bg_element:
        for block in fetterinfoconfig:
            if block['AvatarId'].get('Name', block['AvatarId'].get('name')) == character:
                bg_element = block['AvatarVisionBeforTextMapHash']
    # Only Fontaine characters' talents have the infobox's arkhe param.
    fontaine = any(block.get('AvatarAssocType') == 'ASSOC_TYPE_FONTAINE' for block in fetterinfoconfig
                   if block['AvatarId'].get('Name', block['AvatarId'].get('name')) == character)
    
    if not args.skilldepot:
        skilldepotid = int(char_id + '01')
    else:
        skilldepotid = args.skilldepot
        
    for block in skilldepotconfig:
        if block['Id'] == skilldepotid:
            skilldepot: dict = block

    for folder in ('Skills', 'Passives', 'Constellations'):
        output_path = f'{CONFIG.OUTPUT_PATH}/{character}/{folder}'
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        
    ability_dict = {
        'Normal Attack': get_skill_name(ability_list[0][0](skilldepot)),
        'Elemental Skill': get_skill_name(ability_list[1][0](skilldepot)),
        'Elemental Burst': get_skill_name(ability_list[2][0](skilldepot)),
        '1st Ascension Passive': get_passive_name(passive_list[0][0](skilldepot)),
        '4th Ascension Passive': get_passive_name(passive_list[1][0](skilldepot)),
    }
    
    from pathlib import Path
    from talentEffects import load_talent_configs, talent_effects
    depot_groups = {block.get('ProudSkillGroupId') for block in skillexcel
                    if block['Id'] in (skilldepot['Skills'][:2] + [skilldepot['EnergySkill']])}
    depot_groups |= {item.get('ProudSkillGroupId') for item in skilldepot.get('InherentProudSkillOpens') or []}
    open_configs = {block.get('OpenConfig') for block in proudskillexcel if block.get('Level', 1) == 1 and block.get('ProudSkillGroupId') in depot_groups}
    open_configs |= {block.get('OpenConfig') for block in talentexcel if block['TalentId'] in skilldepot.get('Talents', [])}
    icon_name = next((block.get('IconName', '') for block in avatarconfig if block['Id'] == args.id), '').removeprefix('UI_AvatarIcon_')
    talent_configs = load_talent_configs(Path(CONFIG.BIN_PATH) / 'Talent' / 'AvatarTalents', open_configs - {None, ''}, icon_name)
    if not talent_configs:
        print('No talent configs in BinOutput/Talent/AvatarTalents; Passive/Constellation Effects use descriptions only.')
    found_passives, found_cons = talent_effects(skilldepot, skillexcel, proudskillexcel, talentexcel, talent_configs)
    passive_effects.update(found_passives)
    cons_effects.update(found_cons)
    print('Passive effects:', passive_effects)
    print('Constellation effects:', cons_effects)
    
    scaling = {}
    if not args.noscaling:
        try:
            from talentScaling import talent_scaling
            scaling = {skill: template for skill, _, template in talent_scaling(args.id, *args.levels)}
        except (OSError, ValueError, RuntimeError) as error:
            print(f'Attribute Scaling skipped: {error}')

    advanced, passive_advanced, cons_advanced = {}, {}, {}
    ran_ap = False
    if not args.noap:
        try:
            from advancedProperties import advanced_properties, talent_advanced_properties
            advanced = advanced_properties(args.id, args.skilldepot)
            ran_ap = True
            passive_advanced, cons_advanced = talent_advanced_properties(args.id, args.skilldepot)
        except (OSError, ValueError) as error:
            print(f'Advanced Properties skipped: {error}')
        
    for ability in ability_list:
        file_write_path = f'{CONFIG.OUTPUT_PATH}/{character}/Skills/{ability[1]}.wikitext'
        id = ability[0](skilldepot)
        
        write_file(file_write_path, parse_skill(id, ver, ability[2], ability_dict, scaling.get(id, ''), advanced.get(id, '') if ran_ap else None), overwrite = True)
        
    for passive in passive_list:
        file_write_path = f'{CONFIG.OUTPUT_PATH}/{character}/Passives/{passive[1]}.wikitext'
        id = passive[0](skilldepot)
        
        write_file(file_write_path, parse_passive(id, ver, passive[2], ability_dict, passive_advanced.get(id, '')), overwrite = True)
        
    for cons in cons_list:
        file_write_path = f'{CONFIG.OUTPUT_PATH}/{character}/Constellations/{cons[1]}.wikitext'
        id = cons[0](skilldepot)
        
        write_file(file_write_path, parse_cons(id, ver, ability_dict, cons_advanced.get(id, '')), overwrite = True)
    