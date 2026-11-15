from decimal import Decimal
import os
import json
import Levenshtein # type: ignore

from getConfig import CONFIG
from utils.files import write_file, copy_file
from utils.monsterConfig import monster_property
from utils.redirect import file_redirect
from utils.pageinfo import pageinfo
from enemyList import added_monsters, has_name, monster_set

PARTICLE_IDS = {
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
key_remap = {
    "HpDrops": "HpDrops",
    "DropId": "DropId",
    "HpPercent": "HpPercent",
    "KillDropId": "KillDropId",
}
key_remap_updated = False


def parse_enemy_particles(in_dict: dict):
    hpdrops_parsed = []
    hpdrops = in_dict.get(key_remap['HpDrops'])
    
    for hpdrop in hpdrops:
        if not hpdrop.get(key_remap['DropId']):
            continue
        
        hpdrops_parsed.append([hpdrop.get(key_remap['DropId']), hpdrop.get(key_remap['HpPercent'])])
        
    hpdrops_parsed.append([in_dict.get(key_remap['KillDropId']), 0])
    
    out = '''{{Energy Drops
|type  = '''
    i = 1

    for hpdrop in hpdrops_parsed:
        particles = PARTICLE_IDS.get(hpdrop[0])
        if not particles:
            continue
        
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
    'GROW_CURVE_HP_LITTLEMONSTER': 'wildlife',
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
    candidate_files = []
    
    for filename in os.listdir(directory):
        if filename.endswith('.json'):
            # Calculate the Levenshtein distance between the target name and the current filename
            distance = Levenshtein.distance(target_name, filename[:-5])
            
            # Check if the distance is within the allowed range
            if distance <= max_distance:
                candidate_files.append((distance, filename))

    for _, candidate_file in sorted(candidate_files, key = lambda item: item[0]):
        file_path = os.path.join(directory, candidate_file)
        try:
            with open(file_path, 'r', encoding = 'utf-8') as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        return data, candidate_file
    
    return None, None


def find_monster_config_by_id(directory, monster_id):
    if monster_id is None:
        return None, None

    monster_id_str = str(monster_id)

    for filename in os.listdir(directory):
        if not filename.endswith('.json'):
            continue

        if filename == f'{monster_id_str}.json' or filename.endswith(f'_{monster_id_str}.json'):
            file_path = os.path.join(directory, filename)
            try:
                with open(file_path, 'r', encoding = 'utf-8') as file:
                    data = json.load(file)
            except (OSError, json.JSONDecodeError):
                return None, None

            return data, filename

    return None, None


def find_monster_config_by_name(directory, internal_name):
    # Sources with readable file names store configs as <MonsterName>.json.
    if not internal_name:
        return None, None
    filename = f'{internal_name}.json'
    try:
        with open(os.path.join(directory, filename), 'r', encoding = 'utf-8') as file:
            return json.load(file), filename
    except (OSError, json.JSONDecodeError):
        return None, None


def resolve_monster_config(directory, monster_id, config_startswith, internal_name):
    candidates = [
        find_monster_config_by_id(directory, monster_id),
        find_monster_config_by_name(directory, internal_name),
        find_similar_file(directory, config_startswith),
        find_similar_file(directory, f'ConfigMonster_{internal_name}'),
    ]

    first_found_config = None
    first_found_name = None

    for config, config_name in candidates:
        if not config:
            continue

        if first_found_config is None:
            first_found_config = config
            first_found_name = config_name

        if get_monster_config_property(config):
            return config, config_name

    return first_found_config, first_found_name


def get_monster_config_property(config: dict | None):
    return monster_property(config)


def parse_enemy_stats_weight(in_dict: dict):
    name = in_dict.get('DescribeName')
    internal_name = in_dict.get('MonsterName')
    monster_id = in_dict.get('Id')
    
    config_hash = in_dict.get('CombatConfigHash')
    config_startswith = hex(int(config_hash))[8:16]
    
    config, config_name = resolve_monster_config(
        f'{CONFIG.BIN_PATH}/Monster',
        monster_id,
        config_startswith,
        internal_name,
    )
    
    property_dict = get_monster_config_property(config)
    weight = None
    if property_dict:
        weight = property_dict.get('weight')
        if not weight:
            weight = property_dict.get('bonusRange')
    
    if weight:
        out = f'''|-
| {{{{Enemy|{name}|20}}}} || {int(weight)}'''
    elif config_name:
        out = f'''|-
| {{{{Enemy|{name}|20}}}} || Unsupported Config: {config_name[:-5]}'''
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
    monster_id = in_dict.get('Id')
    
    config_hash = in_dict.get('CombatConfigHash')
    config_startswith = hex(int(config_hash))[8:16]
    
    config, config_name = resolve_monster_config(
        f'{CONFIG.BIN_PATH}/Monster',
        monster_id,
        config_startswith,
        internal_name,
    )
    
    property_dict = get_monster_config_property(config)
    et = None
    if property_dict:
        et = enduretype_dict.get(property_dict.get('endureType'))
    
    if et:
        out = f'''|-
| {{{{Enemy|{name}|20}}}} || {et}'''
    elif config_name:
        out = f'''|-
| {{{{Enemy|{name}|20}}}} || Unsupported Config: {config_name[:-5]}'''
    else:
        out = f'''|-
| {{{{Enemy|{name}|20}}}} || Not Found: {config_startswith}, {internal_name}'''

    return out


def update_key_remap(in_dict: dict):
    global key_remap
    global key_remap_updated
    target_values = {
        "HpPercent": 60,
        "DropId": 22010010,
    }
    top_level_target_values = {
        "KillDropId": 22010010,
    }

    for current_key, current_value in in_dict.items():
        for target_name, target_value in top_level_target_values.items():
            if current_value == target_value:
                key_remap[target_name] = current_key
                key_remap_updated = True
    
    for top_key, items, in in_dict.items():
        if not isinstance(items, list):
            continue
        
        for item in items:
            if not isinstance(item, dict):
                continue
            
            for target_name, target_value in target_values.items():
                for current_key, current_value in item.items():
                    if current_value == target_value:
                        key_remap[target_name] = current_key
                        
                        key_remap["HpDrops"] = top_key
                        
                        key_remap_updated = True
                        break


def old_monsters(rows=None):
    """(ids, names) of the monsters in the build being compared against.

    rows are raw ExcelBinOutput rows of that build, whose names are resolved with the current describe table;
    without them, RepoPathOld's mapped table is read."""
    if rows is None:
        if CONFIG.EXCEL_PATH_OLD is None:
            raise FileNotFoundError('RepoPathOld is not configured; choose an older revision to compare against.')
        with open(f'{CONFIG.EXCEL_PATH_OLD}/MonsterExcelConfigData.json', 'r', encoding = 'utf-8') as file:
            return monster_set(json.load(file))
    with open(f'{CONFIG.EXCEL_PATH}/MonsterDescribeExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        describe_names = {item['Id']: item.get('NameTextMapHash') for item in json.load(file)}
    return monster_set(rows, describe_names)


def load_monsters():
    with open(f'{CONFIG.EXCEL_PATH}/MonsterExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        monsterexcel = json.load(file)
    # update key remap
    if not key_remap_updated:
        update_key_remap(monsterexcel[0])
    return monsterexcel


def write_enemy_pages(args, gen_ol, rows, icons = True):
    if not os.path.exists(f'{CONFIG.OUTPUT_PATH}/Enemies'):
        os.makedirs(f'{CONFIG.OUTPUT_PATH}/Enemies')
        
    with open(f'{CONFIG.EXCEL_PATH}/MonsterDescribeExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        describeexcel = {item['Id']: item for item in json.load(file)}
        
    with open(f'{CONFIG.EXCEL_PATH}/AnimalCodexExcelConfigData.json', 'r', encoding = 'utf-8') as file:
        codexexcel = {item['Id']: item for item in json.load(file)}
        
    for item in rows:
        mons_id = item.get('Id')
        name = item.get('DescribeName')
        
        print(f'====={mons_id}: {name}=====')
        
        particles = parse_enemy_particles(item)
        
        stats = parse_enemy_stats(item)
        
        # icons
        out_name = f'{name} Icon.png'
        out_name_clean = out_name.replace(':', '')
        
        if icons:
            describe_id = item.get('DescribeId')
            icon_filename = describeexcel.get(describe_id).get('Icon')
            
            if out_name != out_name_clean:
                file_redirect(out_name, out_name_clean)
            
            copy_file(f'{CONFIG.IMAGE_PATH}/{icon_filename}.png', f'{CONFIG.OUTPUT_PATH}/Images/Enemy Icons/{out_name_clean}')
        
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
        
        file_write_2 = f"""{pageinfo(name)}
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
}}}}-->{desc}

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
            
        file_write_path_2 = f'{CONFIG.OUTPUT_PATH}/Enemies/{name.replace(":", "").replace("?", r"%3F")}.wikitext'
        write_file(file_write_path_2, file_write_2)


def write_enemy_stats(rows, filename = 'New_Enemies_Output.wikitext'):
    file_write = ['<!-------------- HP --------------->']
    file_write_path = f'{CONFIG.OUTPUT_PATH}/{filename}'

    sections = (
        ('HP', parse_enemy_stats_2),
        ('ATK', parse_enemy_stats_3),
        ('Weight', parse_enemy_stats_weight),
        ('Endure Type', parse_enemy_stats_enduretype),
    )
    for index, (title, render_stats) in enumerate(sections):
        if index:
            file_write.append(f'\n\n<!-------------- {title} --------------->')
        for item in rows:
            file_write.append('\n' + render_stats(item))

    write_file(file_write_path, ''.join(file_write))


def parse_new_enemies(args, gen_ol, old = None, icons = True, new_names_only = False):
    monsterexcel = load_monsters()
    rows = added_monsters(monsterexcel, old or old_monsters(), new_names_only = new_names_only)
    write_enemy_pages(args, gen_ol, rows, icons)
    

def parse_new_enemies_2(old = None):
    monsterexcel = load_monsters()
    old_ids, old_names = old or old_monsters()
    new_enemies = [
        item for item in monsterexcel
        if item.get('DescribeName')
        and item.get('Id') not in old_ids
        and item.get('DescribeName') not in old_names
    ]
    write_enemy_stats(new_enemies)


def parse_enemies(args, gen_ol, ids, icons = True, stats_file = 'New_Enemies_Output.wikitext'):
    """Pages and stat tables for the given monster IDs; IDs sharing a name get one page (the first ID's)."""
    wanted = set(ids)
    rows = [item for item in load_monsters() if item.get('Id') in wanted and has_name(item)]
    missing = sorted(wanted - {item['Id'] for item in rows})
    if missing:
        raise ValueError(f'Not named enemies in the active dataset: {", ".join(map(str, missing))}.')
    pages, names = [], set()
    for item in rows:
        if item['DescribeName'] not in names:
            names.add(item['DescribeName'])
            pages.append(item)
    write_enemy_pages(args, gen_ol, pages, icons)
    write_enemy_stats(rows, stats_file)
    return len(pages)
