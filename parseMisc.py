import json
import argparse
import re
import os
import shutil
import Levenshtein # type: ignore
from PIL import Image, ImageDraw
import OLGen
from decimal import Decimal

with open('scriptconfig.json', 'r', encoding = 'utf-8') as file:
    CONFIG_FILE = json.load(file)

IMAGE_PATH = CONFIG_FILE["ImgPath"]
TALENT_BG_PATH = CONFIG_FILE["TalentBGPath"]
EXCEL_PATH = f'{CONFIG_FILE["RepoPath"]}/MappedExcelBinOutput_EN'
EXCEL_PATH_OLD = f'{CONFIG_FILE["RepoPathOld"]}/MappedExcelBinOutput_EN'
BIN_PATH = f'{CONFIG_FILE["RepoPath"]}/BinOutput'
OUTPUT_PATH = CONFIG_FILE["OutputPath"]

gen_ol = OLGen.gen_ol

parser = argparse.ArgumentParser()
parser.add_argument('--blessingscan', type = bool)
parser.add_argument('--tcgicon', type = str)
parser.add_argument('--newenemies', type = str)
parser.add_argument('--fishingpoints', type = str)
parser.add_argument('--huntingv2', type = str)
parser.add_argument('--cookingqte', type = str)
parser.add_argument('--cookingqte2', type = str)
parser.add_argument('--ver', type = str)
parser.add_argument('--capkeys', type = str)
parser.add_argument('--redirectfromstr', type = str)

args = parser.parse_args()

if not os.path.exists(OUTPUT_PATH):
    os.makedirs(OUTPUT_PATH)


def fix_str(str_input):
    return str_input.replace('"', r'\"')


def capitalize_keys_in_json_files():
    for root, dirs, files in os.walk(EXCEL_PATH):
        for file in files:
            if file.endswith('.json'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Function to capitalize keys
                def capitalize_keys(obj):
                    if isinstance(obj, dict):
                        new_obj = {}
                        for k, v in obj.items():
                            new_key = k.capitalize() if k and k[0].islower() else k
                            new_obj[new_key] = capitalize_keys(v)
                        return new_obj
                    elif isinstance(obj, list):
                        return [capitalize_keys(item) for item in obj]
                    else:
                        return obj
                
                # Capitalize keys in the JSON data
                new_data = capitalize_keys(data)
                
                # Save the modified JSON data back to the file
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(new_data, f, indent=2, ensure_ascii=False)


def python_dict_to_lua_table(python_dict, indent = 0):
    indent_str = '\t' * indent  # indentation string
    lua_table = "{\n"
    for key, value in python_dict.items():
        # Assuming keys are strings
        lua_key = f'{indent_str}\t["{fix_str(key)}"]'
        if isinstance(value, str):
            lua_value = f'"{fix_str(value)}"'
        elif isinstance(value, dict):
            # recursive call for nested dictionaries with increased indent
            lua_value = python_dict_to_lua_table(value, indent + 1)
        elif isinstance(value, list):
            # Process list to Lua table format
            list_values = ", ".join([f'"{fix_str(item)}"' if isinstance(item, str) else str(item) for item in value])
            lua_value = "{" + list_values + "}"
        else:
            lua_value = str(value)
        lua_table += f"{lua_key} = {lua_value},\n"
    lua_table += f"{indent_str}}}"

    return lua_table


def write_file(filename, content):
    base, ext = os.path.splitext(filename)
    counter = 1
    new_filename = filename

    while os.path.exists(new_filename):
        counter += 1
        new_filename = f"{base}_{counter}{ext}"

    with open(new_filename, 'w', encoding = 'utf-8') as file:
        file.write(content)
        

def copy_file(source_path, destination_path):
    if os.path.exists(source_path):
        dest_dir = destination_path.replace(destination_path.split('/')[-1], '')
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        shutil.copy(source_path, destination_path)
        print(f"File copied successfully from {source_path} to {destination_path}")
    else:
        print(f"The file {source_path} does not exist.")
        

def file_redirect(target, source):
    if not os.path.exists(f'{OUTPUT_PATH}/Redirects'):
        os.makedirs(f'{OUTPUT_PATH}/Redirects')

    file_write_path = f'{OUTPUT_PATH}/Redirects/{source}.wikitext'
    file_write = (f"<%-- [PAGE_INFO]\n    comment = #Please do not remove this struct. It's record contains some "
                  f"important information of edit. This struct will be removed automatically after you push edits.#\n "
                  f"   pageTitle = #File:{target}#\n    pageID = ##\n    revisionID = ##\n    contentModel = ##\n    "
                  f"contentFormat = ##\n[END_PAGE_INFO] --%>\n\n#REDIRECT [[File:{source}]]\n[[Category:Redirect "
                  f"Pages]]")

    write_file(file_write_path, file_write)
    

def main_redirect(target, source):
    if not os.path.exists(f'{OUTPUT_PATH}/Redirects'):
        os.makedirs(f'{OUTPUT_PATH}/Redirects')
        
    filename = re.sub(r'[^\w\s]', '', source)

    file_write_path = f'{OUTPUT_PATH}/Redirects/{filename}.wikitext'
    file_write = (f"<%-- [PAGE_INFO]\n    comment = #Please do not remove this struct. It's record contains some "
                  f"important information of edit. This struct will be removed automatically after you push edits.#\n "
                  f"   pageTitle = #{source}#\n    pageID = ##\n    revisionID = ##\n    contentModel = ##\n    "
                  f"contentFormat = ##\n[END_PAGE_INFO] --%>\n\n#REDIRECT [[{target}]]\n[[Category:Redirect "
                  f"Pages]]")

    write_file(file_write_path, file_write)


def ls_blessing_scan_targets(type_id):
    valid_list = []

    with open(f'{EXCEL_PATH}/BlessingScanExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        blessingscanexcel = json.load(file)

    with open(f'{EXCEL_PATH}/MonsterExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        monsterexcel = json.load(file)

    with open(f'{EXCEL_PATH}/GadgetExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        gadgetexcel = json.load(file)

    with open(f'{EXCEL_PATH}/AnimalDescribeExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        animaldescribeexcel = json.load(file)

    for item in blessingscanexcel:
        if item['TypeId'] != type_id:
            continue

        ref_id = item['RefId']

        if item['ScanType'] == 'BLESSING_SCAN_TYPE_MONSTER':
            for monster in monsterexcel:
                try:
                    if monster['DescribeId'] == ref_id:
                        try:
                            valid_list.append(monster['DescribeName'])
                        except KeyError:
                            try:
                                for animal in animaldescribeexcel:
                                    if animal['Id'] == ref_id:
                                        valid_list.append(animal['NameTextMapHash'])
                            except KeyError:
                                if isinstance(monster['NameTextMapHash'], str):
                                    valid_list.append(monster['NameTextMapHash'])
                                else:
                                    valid_list.append(monster['MonsterName'])
                except KeyError:
                    continue

        elif item['ScanType'] == 'BLESSING_SCAN_TYPE_GATHER':
            for gadget in gadgetexcel:
                if gadget['Id'] == ref_id:
                    valid_list.append(gadget['InteractNameTextMapHash'])

    return valid_list


def parse_blessing_scan():
    with open(f'{EXCEL_PATH}/BlessingScanTypeExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        blessingscantypeexcel = json.load(file)

    output = ""

    for item in blessingscantypeexcel:
        name = item['TypeNameTextMapHash']
        type_id = item['TypeId']
        valid_list = list(set(ls_blessing_scan_targets(type_id)))

        list_text = ''
        for list_item in valid_list:
            list_text = list_text + f'{list_item}\n'

        output = output + f'=={name}==\n{list_text}\n'

    print(output)


def parse_tcg_icon():
    with open(f'{EXCEL_PATH}/GCGCharExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        gcgcharjson = json.load(file)

    with open(f'{EXCEL_PATH}/GCGSkillExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        gcgskilljson = json.load(file)
        

def parse_charasc():
    with open(f'{EXCEL_PATH}/AvatarExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        avatarjson = json.load(file)
    
    with open(f'{EXCEL_PATH}/AvatarPromoteExcelConfigData.json', 'r', encoding = 'utf-8') as file:
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


def parse_enemy_particles(in_dict: dict):
    particle_ids = {
        22010010: ['None', 0, 1],
        22010011: ['Pyro', 0, 1],
        22010012: ['Hydro', 0, 1],
        22010013: ['Dendro', 0, 1],
        22010014: ['Electro', 0, 1],
        22010015: ['Anemo', 0, 1],
        22010016: ['Cryo', 0, 1],
        22010017: ['Geo', 0, 1],
        22010020: ['None', 0, 2],
        22010021: ['Pyro', 0, 2],
        22010022: ['Hydro', 0, 2],
        22010023: ['Dendro', 0, 2],
        22010024: ['Electro', 0, 2],
        22010025: ['Anemo', 0, 2],
        22010026: ['Cryo', 0, 2],
        22010027: ['Geo', 0, 2],
        22010030: ['None', 1, 0],
        22010031: ['Pyro', 1, 0],
        22010032: ['Hydro', 1, 0],
        22010033: ['Dendro', 1, 0],
        22010034: ['Electro', 1, 0],
        22010035: ['Anemo', 1, 0],
        22010036: ['Cryo', 1, 0],
        22010037: ['Geo', 1, 0],
        22010040: ['None', 1, 1],
        22010041: ['Pyro', 1, 1],
        22010042: ['Hydro', 1, 1],
        22010043: ['Dendro', 1, 1],
        22010044: ['Electro', 1, 1],
        22010045: ['Anemo', 1, 1],
        22010046: ['Cryo', 1, 1],
        22010047: ['Geo', 1, 1],
        22010050: ['None', 1, 3],
        22010051: ['Pyro', 1, 3],
        22010052: ['Hydro', 1, 3],
        22010053: ['Dendro', 1, 3],
        22010054: ['Electro', 1, 3],
        22010055: ['Anemo', 1, 3],
        22010056: ['Cryo', 1, 3],
        22010057: ['Geo', 1, 3],
        22010100: ['Pyro', 0, 2],
        22010200: ['Hydro', 0, 2],
        22010300: ['Dendro', 0, 2],
        22010400: ['Electro', 0, 2],
        22010500: ['Anemo', 0, 2],
        22010600: ['Cryo', 0, 2],
        22010700: ['Geo', 0, 2],
        22010800: ['None', 1, 0],
        22010900: ['Pyro', 1, 1],
        22011000: ['Hydro', 1, 1],
        22011100: ['Dendro', 1, 1],
        22011200: ['Electro', 1, 1],
        22011300: ['Anemo', 1, 1],
        22011400: ['Cryo', 1, 1],
        22011500: ['Geo', 1, 1],
        22011600: ['None', 2.5, 0],
        22011610: ['None', 1, 1],
        22011700: ['None', 0, 1],
        22011800: ['Pyro', 0, 1.3333],
        22011900: ['Hydro', 0, 1.3333],
        22012000: ['Dendro', 0, 1.3333],
        22012100: ['Electro', 0, 1.3333],
        22012200: ['Anemo', 0, 1.3333],
        22012310: ['Cryo', 0, 1.3333],
        22012400: ['Geo', 0, 1.3333],
        22012500: ['None', 0, 2],
        22012600: ['Pyro', 0, 2.6667],
        22012700: ['Hydro', 0, 2.6667],
        22012800: ['Dendro', 0, 2.6667],
        22012900: ['Electro', 0, 2.6667],
        22013000: ['Anemo', 0, 2.6667],
        22013090: ['Cryo', 0, 2.6667],
        22013200: ['Geo', 0, 2.6667],
        22013300: ['None', 2.5, 0],
        22013309: ['None', 1, 1],
        22013400: ['Pyro', 1.3333, 0],
        22013500: ['Hydro', 1.3333, 0],
        22013600: ['Dendro', 1.3333, 0],
        22013700: ['Electro', 1.3333, 0],
        22013800: ['Anemo', 1.3333, 0],
        22013900: ['Cryo', 1.3333, 0],
        22014000: ['Geo', 1.3333, 0],
    }
    
    hpdrops_parsed = []
    hpdrops = in_dict.get('HpDrops')
    for hpdrop in hpdrops:
        if not hpdrop.get('DropId'):
            continue
        
        hpdrops_parsed.append([hpdrop.get('DropId'), hpdrop.get('HpPercent')])
        
    hpdrops_parsed.append([in_dict.get('KillDropId'), 0])
    
    out = '''{{Energy Drops
|type  = '''
    i = 1

    for hpdrop in hpdrops_parsed:
        particles = particle_ids.get(hpdrop[0])
        
        if i == 1:
            try:
                out = out + particles[0]
            except TypeError:
                out = ''
                break
                

        out = out + f'\n|hp{i}   = {hpdrop[1]}'
        
        if particles[1]:
            out = out + f'\n|o{i}    = {particles[1]}'
            
        if particles[2]:
            out = out + f'\n|p{i}    = {particles[2]}'
            
        i = i + 1
    
    if out:
        out = out + '\n}}'
    
    return out


curve_dict = {
    'GROW_CURVE_ATTACK': 1,
    'GROW_CURVE_HP': 1,
    'GROW_CURVE_ATTACK_2': 2,
    'GROW_CURVE_HP_2': 2,
    'GROW_CURVE_ACTIVITY_HP_1': 'activity1',
    'GROW_CURVE_ACTIVITY_ATTACK_1': 'activity1',
}


def parse_enemy_stats(in_dict: dict):
    hp_curve, atk_curve, _ = in_dict.get('PropGrowCurves')
    hp = Decimal(str(in_dict.get('HpBase')))
    atk = Decimal(str(in_dict.get('AttackBase') or 0))
    
    hp_curve = curve_dict[hp_curve.get('GrowCurve')]
    atk_curve = curve_dict[atk_curve.get('GrowCurve')]
    
    out = f'''|hp_ratio     = {hp / Decimal('13.584')}
|hp_type      = {hp_curve}
|atk_ratio    = {atk / Decimal('12.56')}
|atk_type     = {atk_curve}'''

    # res section
    res_dict = {
        'pyro_res   ': Decimal(str(in_dict.get('FireSubHurt'))) * Decimal('100'),
        'dendro_res ': Decimal(str(in_dict.get('GrassSubHurt'))) * Decimal('100'),
        'hydro_res  ': Decimal(str(in_dict.get('WaterSubHurt'))) * Decimal('100'),
        'electro_res': Decimal(str(in_dict.get('ElecSubHurt'))) * Decimal('100'),
        'anemo_res  ': Decimal(str(in_dict.get('WindSubHurt'))) * Decimal('100'),
        'cryo_res   ': Decimal(str(in_dict.get('IceSubHurt'))) * Decimal('100'),
        'geo_res    ': Decimal(str(in_dict.get('RockSubHurt'))) * Decimal('100'),
        'phys_res   ': Decimal(str(in_dict.get('PhysicalSubHurt'))) * Decimal('100'),
    }
    
    res_str = ''
    for key, value in res_dict.items():
        if value == 10:
            continue
        else:
            if value == int(value):
                value = int(value)
            res_str = res_str + f'|{key} = {value}%\n'
    
    if res_str:
        out = f'{res_str}\n{out}'

    return out


def parse_enemy_stats_2(in_dict: dict):
    name = in_dict.get('DescribeName')
    
    hp_curve, atk_curve, _ = in_dict.get('PropGrowCurves')
    hp = in_dict.get('HpBase')
    
    hp_curve = curve_dict[hp_curve.get('GrowCurve')]
    
    out = f'''|-
| {{{{Enemy|{name}|20}}}} || {hp} || Type {hp_curve} || {Decimal(str(hp)) / Decimal('13.584')}'''

    return out


def parse_enemy_stats_3(in_dict: dict):
    name = in_dict.get('DescribeName')
    
    hp_curve, atk_curve, _ = in_dict.get('PropGrowCurves')
    atk = in_dict.get('AttackBase') or 0
    
    atk_curve = curve_dict[atk_curve.get('GrowCurve')]
    
    out = f'''|-
| {{{{Enemy|{name}|20}}}} || {atk} || Type {atk_curve} || {Decimal(str(atk)) / Decimal('12.56')}'''

    return out


def find_similar_file(directory, target_name, max_distance = 3):
    closest_file = None
    min_distance = max_distance + 1  # Start with a distance larger than max_distance
    
    for filename in os.listdir(directory):
        if filename.endswith('.json'):
            # Calculate the Levenshtein distance between the target name and the current filename
            distance = Levenshtein.distance(target_name, filename[:-5])
            
            # Check if the distance is within the allowed range
            if distance <= max_distance and distance < min_distance:
                min_distance = distance
                closest_file = filename

    if closest_file:
        file_path = os.path.join(directory, closest_file)
        with open(file_path, 'r') as file:
            data = json.load(file)
        return data, closest_file
    
    return None, None


def parse_enemy_stats_weight(in_dict: dict):
    name = in_dict.get('DescribeName')
    internal_name = in_dict.get('MonsterName')
    
    config_hash = in_dict.get('CombatConfigHash')
    config_startswith = hex(config_hash)[8:16]
    
    config, _ = find_similar_file(f'{BIN_PATH}/Monster', config_startswith)
    
    if not config:
        config, _ = find_similar_file(f'{BIN_PATH}/Monster', f'ConfigMonster_{internal_name}')
    
    weight = None
    if config:
        weight = config['combat']['property']['weight']
    
    if weight:
        out = f'''|-
| {{{{Enemy|{name}|20}}}} || {int(weight)}'''
    else:
        out = f'''|-
| {{{{Enemy|{name}|20}}}} || Not Found: {config_startswith}, {internal_name}'''

    return out


def parse_enemy_stats_enduretype(in_dict: dict):
    enduretype_dict = {
        'Monster_Minion': 'Minion',
        'Monster_Slime': 'Slime',
        'Monster_Boss_Other': 'Boss',
        'Monster_Boss_Humanoid': 'Humanoid Boss',
        'Monster_Demiboss_Humanoid': 'Humanoid Demiboss',
        'Monster_Grunt_Humanoid': 'Humanoid Grunt',
        'Monster_Grunt_Other': 'Other Grunt',
    }
    
    name = in_dict.get('DescribeName')
    internal_name = in_dict.get('MonsterName')
    
    config_hash = in_dict.get('CombatConfigHash')
    config_startswith = hex(config_hash)[8:16]
    
    config, _ = find_similar_file(f'{BIN_PATH}/Monster', config_startswith)
    
    if not config:
        config, _ = find_similar_file(f'{BIN_PATH}/Monster', f'ConfigMonster_{internal_name}')
    
    et = None
    if config:
        et = enduretype_dict[config['combat']['property']['endureType']]
    
    if et:
        out = f'''|-
| {{{{Enemy|{name}|20}}}} || {et}'''
    else:
        out = f'''|-
| {{{{Enemy|{name}|20}}}} || Not Found: {config_startswith}, {internal_name}'''

    return out


def parse_new_enemies():    
    if not os.path.exists(f'{OUTPUT_PATH}/Enemies'):
            os.makedirs(f'{OUTPUT_PATH}/Enemies')
    
    with open(f'{EXCEL_PATH}/MonsterExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        monsterexcel = json.load(file)
        
    with open(f'{EXCEL_PATH_OLD}/MonsterExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        monsterexcel_old = json.load(file)
        
    with open(f'{EXCEL_PATH}/MonsterDescribeExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        describeexcel = {item['Id']: item for item in json.load(file)}
        
    with open(f'{EXCEL_PATH}/AnimalCodexExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        codexexcel = {item['Id']: item for item in json.load(file)}
        
    # build list of old enemies
    old_ids = []
    for item in monsterexcel_old:
        mons_id = item.get('Id')
        if mons_id:
            old_ids.append(mons_id)
        
    for item in monsterexcel:
        mons_id = item.get('Id')
        if mons_id in old_ids:
            # print(f'Skipping {mons_id}.')
            continue
        
        name = item.get('DescribeName')
        if not name or isinstance(name, int):
            continue
        
        print(f'====={name}=====')
        
        particles = parse_enemy_particles(item)
        
        stats = parse_enemy_stats(item)
        
        # icons
        describe_id = item.get('DescribeId')
        icon_filename = describeexcel.get(describe_id).get('Icon')
        
        out_name = f'{name} Icon.png'
        out_name_clean = out_name.replace(':', '')
        
        if out_name != out_name_clean:
            file_redirect(out_name, out_name_clean)
        
        copy_file(f'{IMAGE_PATH}/{icon_filename}.png', f'{OUTPUT_PATH}/Images/Enemy Icons/{out_name_clean}')
        
        # codex
        desc = ''
        family = ''
        if mons_id in codexexcel:
            codex = codexexcel[mons_id]
            desc = f'''
==Descriptions==
{{{{Description|{codex.get('DescTextMapHash')}|[[Archive]]}}}}'''

            if codex.get('SubType') == 'CODEX_SUBTYPE_ABYSS':
                family = 'The Abyss'
            elif codex.get('SubType') == 'CODEX_SUBTYPE_HILICHURL':
                family = 'Hilichurls'
            elif codex.get('SubType') == 'CODEX_SUBTYPE_FATUI':
                family = 'Fatui'
            elif codex.get('SubType') == 'CODEX_SUBTYPE_AUTOMATRON':
                family = 'Automatons'
            elif codex.get('SubType') == 'CODEX_SUBTYPE_HUMAN':
                family = 'Other Human Factions'
            else:
                family = 'Elemental Lifeforms'      

        # tier
        if item.get('SecurityLevel') == 'ELITE':
            tier = ['Elite Enemies', 'Elite']
        elif item.get('SecurityLevel') == 'BOSS':
            tier = ['Normal Bosses', 'Bosses']
        else:
            tier = ['Common Enemies', 'Common']
            
        # OL
        ol = gen_ol(name)
        
        file_write_2 = f"""<%-- [PAGE_INFO]
    comment = #Please do not remove this struct. It's record contains some important information of edit. This struct will be removed automatically after you push edits.#
    pageTitle = #{name}#
    pageID = ##
    revisionID = ##
    contentModel = ##
    contentFormat = ##
[END_PAGE_INFO] --%>

{{{{Enemy Infobox
|title     = 
|dmgtype   = unknown
|image     = Enemy {name.replace(':', '')}.png
|type      = {tier[0]}
|family    = {family}
|group     = 
|weakpoint = 
}}}}
{{{{Enemy Intro}}}}

==Drops==
===Energy===
{particles}

==Stats==
{{{{Enemy Stats
{stats}
}}}}

==Abilities==
{{{{Under Construction}}}}<!--
{{{{Enemy Attacks
|name_1      = 
|desc_1      = 
}}}}-->
{desc}

==Gallery==
<gallery>
{out_name_clean}|Icon
</gallery>

==Other Languages==
{ol}

==Change History==
{{{{Change History|{getattr(args, 'ver', '')}}}}}

==Navigation==
{{{{Enemy Navbox|{tier[1]}}}}}"""
            
        file_write_path_2 = f'{OUTPUT_PATH}/Enemies/{name.replace(":", "").replace("?", r"%3F")}.wikitext'
        write_file(file_write_path_2, file_write_2)    
    

def parse_new_enemies_2():
    file_write = '<!-------------- HP --------------->'
    file_write_path = f'{OUTPUT_PATH}/New_Enemies_Output.wikitext'
    
    with open(f'{EXCEL_PATH}/MonsterExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        monsterexcel = json.load(file)
        
    with open(f'{EXCEL_PATH_OLD}/MonsterExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        monsterexcel_old = json.load(file)
        
    # build list of old enemies
    old_ids = []
    old_names = []
    for item in monsterexcel_old:
        mons_id = item.get('Id')
        name = item.get('DescribeName')
        if mons_id:
            old_ids.append(mons_id)
        if name:
            old_names.append(name)
        
    for item in monsterexcel:
        mons_id = item.get('Id')
        
        name = item.get('DescribeName')
        if not name:
            continue
        
        if mons_id in old_ids or name in old_names:
            continue
        
        hp = parse_enemy_stats_2(item)
        file_write = file_write + '\n' + hp
        
    file_write = file_write + '\n\n<!-------------- ATK --------------->'
    
    for item in monsterexcel:
        mons_id = item.get('Id')
        
        name = item.get('DescribeName')
        if not name:
            continue
        
        if mons_id in old_ids or name in old_names:
            continue
        
        atk = parse_enemy_stats_3(item)
        file_write = file_write + '\n' + atk
        
    """file_write = file_write + '\n\n<!-------------- Weight --------------->'
    
    for item in monsterexcel:
        mons_id = item.get('Id')
        
        name = item.get('DescribeName')
        if not name:
            continue
        
        if mons_id in old_ids or name in old_names:
            continue
        
        weight = parse_enemy_stats_weight(item)
        
        file_write = file_write + '\n' + weight
        
    file_write = file_write + '\n\n<!-------------- Endure Type --------------->'
    
    for item in monsterexcel:
        mons_id = item.get('Id')
        
        name = item.get('DescribeName')
        if not name:
            continue
        
        if mons_id in old_ids or name in old_names:
            continue
        
        et = parse_enemy_stats_enduretype(item)
        
        file_write = file_write + '\n' + et"""
        
    
        
        
    write_file(file_write_path, file_write)
    

def parse_fishing_points():
    '''<%-- [PAGE_INFO]
    comment = #Please do not remove this struct. It's record contains some important information of edit. This struct will be removed automatically after you push edits.#
    pageTitle = #Fishing Point/Mont Esus East#
    pageID = #261067#
    revisionID = #1458412#
    contentModel = #wikitext#
    contentFormat = #text/x-wiki#
[END_PAGE_INFO] --%>

{{Fishing Point
|title         = Mont Esus East
|id            = 5010
|subarea       = Mont Esus East
|area          = Liffey Region
|region        = Fontaine
|description   = One of the fishing points registered with the Fontaine Fishing Association. Located on the shoals near Mont Esus, it has a rich variety of fish. Looking east from here, one can see the ruins of the Fontaine Research Institute's Central Laboratory...
|day           = Streaming Axe Marlin; Blazing Heartfeather Bass; Maintenance Mek: Initial Configuration; Ornamental Streaming Axe Marlin; Ornamental Blazing Heartfeather Bass; Ornamental Maintenance Mek: Initial Configuration
|night         = Streaming Axe Marlin; Maintenance Mek: Initial Configuration; Maintenance Mek: Situation Controller; Ornamental Streaming Axe Marlin; Ornamental Maintenance Mek: Initial Configuration; Ornamental Maintenance Mek: Situation Controller
|display limit = 5
|total         = 13
}}'''
    
    with open(f'{EXCEL_PATH}/FishPoolExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        poolexcel = {item['Id']: item for item in json.load(file)}
        
    with open(f'{EXCEL_PATH_OLD}/FishPoolExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        poolexcel_old = {item['Id']: item for item in json.load(file)}
        
    with open(f'{EXCEL_PATH_OLD}/../Testing/fishstock.json', 'r', encoding = 'utf-8') as file:
        fishstock = {item['Id']: item for item in json.load(file)}
    
    for id, item in poolexcel.items():
        if id in list(poolexcel_old.keys()):
            print(f'Skipping {id}.')
            continue
        
        title = item.get('PoolNameTextMapHash')
        

def parse_hunting_v2():
    with open(f'{EXCEL_PATH}/HuntingV2MonsterBundleExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        bundleexcel = {item['Id']: item for item in json.load(file)}
    
    with open(f'{EXCEL_PATH}/HuntingV2RegionExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        regionexcel = {item['Id']: item for item in json.load(file)}
        
    with open(f'{EXCEL_PATH}/MonsterExcelConfigData.json', 'r', encoding = 'utf-8') as file:
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

    file_write_path = f'{OUTPUT_PATH}/Bounties_V2_Output.wikitext'
    
    write_file(file_write_path, file_write)
    

def parse_cooking_qte():
    with open(f'{EXCEL_PATH}/CookRecipeExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        recipeexcel = {item['Id']: item for item in json.load(file)}
    
    out = {}
    
    for key, recipe in recipeexcel.items():
        name = recipe.get('NameTextMapHash')
        qteparams = recipe.get('QteParam').split(',')
        out[name] = {}
        out[name]['center'] = float(qteparams[0])
        out[name]['width'] = float(qteparams[1])
        
    file_write_path = f'{OUTPUT_PATH}/Recipe_Output.lua'
    
    write_file(file_write_path, f'return {python_dict_to_lua_table(out)}')
    

def clamp(n, min_value, max_value):
    return max(min(n, max_value), min_value)


def cooking_qte_image_gen(center, length):
    BG_PATH = 'Cook.webp'
    
    SIZE = 1240
    SCALE = 8  # Scale factor for anti-aliasing
    SCALED_SIZE = SIZE * SCALE
    THICKNESS = int(1 * SCALED_SIZE * 0.5) 
    INNER_THICKNESS = int((1 - 0.04066555965) * SCALED_SIZE * 0.5)
    
    Q1 = clamp(78 * (center - length / 2), 0, 78)
    Q2 = clamp(78 * (center - length / 8), 0, 78)
    Q3 = clamp(78 * (center + length / 8), 0, 78)
    Q4 = clamp(78 * (center + length / 2), 0, 78)
    
    TRANSPARENT = (0, 0, 0, 0)
    COLOR1 = (236, 233, 179, 255)  # #ECE9B3
    COLOR2 = (255, 192, 64, 255)   # #FFC040
    
    base_image = Image.new('RGBA', (SCALED_SIZE, SCALED_SIZE))
    draw = ImageDraw.Draw(base_image)
    
    # Draw pie chart sections
    draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231, 231 + Q1, fill=TRANSPARENT)
    draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231 + Q1, 231 + Q2, fill=COLOR1)
    draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231 + Q2, 231 + Q3, fill=COLOR2)
    draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231 + Q3, 231 + Q4, fill=COLOR1)
    draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231 + Q4, 309, fill=TRANSPARENT)
    
    # Cut out center
    mask = Image.new('L', (SCALED_SIZE, SCALED_SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse([SCALED_SIZE//2 - THICKNESS, SCALED_SIZE//2 - THICKNESS, SCALED_SIZE//2 + THICKNESS, SCALED_SIZE//2 + THICKNESS], fill=255)
    mask_draw.ellipse([SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS], fill=0)
    base_image.putalpha(mask)
    
    # Mask to yellow section only
    mask2 = Image.new('L', (SCALED_SIZE, SCALED_SIZE), 0)
    mask2_draw = ImageDraw.Draw(mask2)
    mask2_draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231 + Q1, 231 + Q4, fill=255)
    mask2_draw.ellipse([SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS], fill=0)
    base_image.putalpha(mask2)
    
    # Crop
    black_mask = Image.new('L', (SCALED_SIZE, SCALED_SIZE), 0)
    black_mask_draw = ImageDraw.Draw(black_mask)
    black_mask_draw.pieslice([0, 0, SCALED_SIZE, SCALED_SIZE], 231, 309, fill=255)
    black_mask_draw.ellipse([SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 - INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS, SCALED_SIZE//2 + INNER_THICKNESS], fill=0)
    
    bbox = black_mask.getbbox()

    bar_final = base_image.crop(bbox)
    
    # Downscale (antialiasing)
    cropped_size = [int(size / SCALE) for size in bar_final.size]
    bar_final = bar_final.resize(cropped_size, Image.LANCZOS)
    
    # Add background
    background = Image.open(BG_PATH).convert("RGBA")
    
    canvas = Image.new('RGBA', background.size, (0, 0, 0, 0))
    bar_x = (canvas.width - bar_final.width) // 2
    canvas.paste(bar_final, (bar_x, 43), bar_final)
    
    final_image = Image.alpha_composite(background, canvas)
    
    # Save
    filename = f'Manual Cooking C-{int(center * 100)} W-{int(length * 100)}.png'
    try:
        final_image.save(f'{OUTPUT_PATH}/Cooking_QTE/{filename}')
        print(f'Successfully saved {filename}')
    except Exception as e:
        print(f'Error saving {filename}: {e}')


def cooking_qte_2():
    if not os.path.exists(f'{OUTPUT_PATH}/Cooking_QTE'):
        os.makedirs(f'{OUTPUT_PATH}/Cooking_QTE')
    
    for center in [0.3, 0.38, 0.4, 0.45, 0.48, 0.5, 0.52, 0.55, 0.6, 0.63, 0.65, 0.7, 0.72, 0.77, 0.8, 0.85]:
        for length in [0.17, 0.22, 0.27, 0.35, 0.4]:
            cooking_qte_image_gen(center, length)
            

def redirects_from_str():
    redirects = r"""Bronzelock%%%Ruin Drake: Earthguard
Ichcahuipilli's Aegis%%%Foliar-Swift Wayob Manifestation
Atlatl's Blessing%%%Rock-Cavernous Wayob Manifestation
Ciuhacoatl of Chimeric Bone%%%Yumkasaurus Warrior: Flowing Skyfire
Tlatzacuilotl%%%Tepetlisaurus Warrior: Rockbreaker Blade
Chimalli's Shade%%%Flow-Inverted Wayob Manifestation
Potapo's Solidarity%%%Biting-Cold Wayob Manifestation
Sappho Amidst the Waves%%%Koholasaurus Warrior: Waveshuttler
Tupayo's Aid%%%Burning-Aflame Wayob Manifestation
Spirit of the Fallen Dawnstar%%%Iktomisaurus
Balachko%%%Fatui Pyro Agent"""

    for line in redirects.split("\n"):
        pagename, target = line.split(r"%%%")
        
        main_redirect(target, pagename)
        
    
#########################################################################


if args.blessingscan:
    parse_blessing_scan()

if args.tcgicon:
    parse_blessing_scan()

if args.newenemies:
    OLGen.load_data()
    parse_new_enemies()
    parse_new_enemies_2()
    
if args.fishingpoints:
    parse_fishing_points()
    
if args.huntingv2:
    parse_hunting_v2()
    
if args.cookingqte:
    parse_cooking_qte()
    
if args.cookingqte2:
    cooking_qte_2()
    
if args.capkeys:
    capitalize_keys_in_json_files()
    
if args.redirectfromstr:
    redirects_from_str()