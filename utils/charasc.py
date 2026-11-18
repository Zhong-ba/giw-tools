import json

from getConfig import CONFIG
import toolLog as report
from utils.files import write_file

ASCENSION_TITLE = 'Module:Character Ascensions and Stats/data'
TALENT_TITLE = 'Module:Talent Upgrade/data'

GEM_SUFFIXES = (' Sliver', ' Fragment', ' Chunk', ' Gemstone')
BOOK_PREFIXES = ('Teachings of ', 'Guide to ', 'Philosophies of ')
CROWN = 'Crown of Insight'
BASE_PROPS = {'FIGHT_PROP_BASE_HP', 'FIGHT_PROP_BASE_ATTACK', 'FIGHT_PROP_BASE_DEFENSE'}
SPEC_NAMES = {
    'FIGHT_PROP_HP_PERCENT': 'HP',
    'FIGHT_PROP_ATTACK_PERCENT': 'ATK',
    'FIGHT_PROP_DEFENSE_PERCENT': 'DEF',
    'FIGHT_PROP_CRITICAL': 'CRIT Rate',
    'FIGHT_PROP_CRITICAL_HURT': 'CRIT DMG',
    'FIGHT_PROP_CHARGE_EFFICIENCY': 'Energy Recharge',
    'FIGHT_PROP_HEAL_ADD': 'Healing Bonus',
    'FIGHT_PROP_ELEMENT_MASTERY': 'Elemental Mastery',
    'FIGHT_PROP_PHYSICAL_ADD_HURT': 'Physical DMG Bonus',
    'FIGHT_PROP_FIRE_ADD_HURT': 'Pyro DMG Bonus',
    'FIGHT_PROP_WATER_ADD_HURT': 'Hydro DMG Bonus',
    'FIGHT_PROP_GRASS_ADD_HURT': 'Dendro DMG Bonus',
    'FIGHT_PROP_ELEC_ADD_HURT': 'Electro DMG Bonus',
    'FIGHT_PROP_WIND_ADD_HURT': 'Anemo DMG Bonus',
    'FIGHT_PROP_ICE_ADD_HURT': 'Cryo DMG Bonus',
    'FIGHT_PROP_ROCK_ADD_HURT': 'Geo DMG Bonus',
}
# Flat stats; every other specialty is a percentage.
FLAT_SPECS = {'FIGHT_PROP_ELEMENT_MASTERY'}
# The Traveler's talents follow the region of its element, in the wiki's order.
TRAVELER_REGIONS = {
    'Wind': 'Mondstadt', 'Rock': 'Liyue', 'Electric': 'Inazuma', 'Grass': 'Sumeru',
    'Water': 'Fontaine', 'Fire': 'Natlan', 'Ice': 'Snezhnaya',
}
DEFAULT_BOSS_COSTS = [1, 1, 2, 2]
TEST_CHARACTER = '''\t['Test Character'] = {
\t\t['quality'] = 4,
\t\t['gem'] = 'Brilliant Diamond',
\t\t['boss'] = nil,
\t\t['local'] = 'Windwheel Aster',
\t\t['common'] = { 'Damaged Mask', 'Stained Mask', 'Ominous Mask' },
\t\t['spec'] = nil,
\t\t['spec_base'] = nil,
\t\t['base_hp'] = nil,
\t\t['asc_hp'] = nil,
\t\t['base_atk'] = nil,
\t\t['asc_atk'] = nil,
\t\t['base_def'] = nil,
\t\t['asc_def'] = nil
\t},
'''


def _load(name):
    with open(f'{CONFIG.EXCEL_PATH}/{name}.json', 'r', encoding = 'utf-8') as file:
        return json.load(file)


def _costs(row):
    return {item['Id']: item.get('Count', 0) for item in row.get('CostItems', []) if item.get('Id')}


def _unique(items):
    return list(dict.fromkeys(items))


def _boss(levels):
    '''The item every one of levels costs, which is only ever the boss material.'''
    shared = set.intersection(*(set(level) for level in levels)) if levels else set()
    return next(iter(shared), None) if len(shared) == 1 else None


def _strip(name, affixes, prefix = False):
    for affix in affixes:
        if prefix and name.startswith(affix):
            return name[len(affix):]
        if not prefix and name.endswith(affix):
            return name[:-len(affix)]
    return None


def playable_characters(avatars = None):
    '''Playable characters by name, skipping trial and template variants and avatars without ascension costs.'''
    avatars = avatars if avatars is not None else _load('AvatarExcelConfigData')
    promotes = {}
    for row in _load('AvatarPromoteExcelConfigData'):
        promotes.setdefault(row['AvatarPromoteId'], []).append(row)
    out = {}
    for avatar in avatars:
        name = avatar.get('NameTextMapHash')
        rows = sorted(promotes.get(avatar.get('AvatarPromoteId'), []), key = lambda row: row.get('PromoteLevel', 0))
        if (avatar.get('UseType') != 'AVATAR_FORMAL' or not name or name in out
                or avatar.get('FeatureTagGroupID', avatar['Id']) != avatar['Id'] or not any(map(_costs, rows))):
            continue
        out[name] = (avatar, rows)
    return dict(sorted(out.items(), key = lambda item: item[0].casefold()))


def ascension_data(characters = None):
    characters = characters if characters is not None else playable_characters()
    exchange = {item.get('NameTextMapHash') for item in _load('MaterialExcelConfigData')
                if item.get('MaterialType') == 'MATERIAL_EXCHANGE'}
    out = {}
    for name, (avatar, rows) in report.track(list(characters.items()), 'Building character ascension and stat data'):
        levels = [list(_costs(row)) for row in rows if _costs(row)]
        # The gem family comes from the Sliver; other names such as Transoceanic Chunk can share its suffixes.
        gem = next((_strip(item, (' Sliver',)) for level in levels for item in level if item.endswith(' Sliver')), None)
        gems = {f'{gem}{suffix}' for suffix in GEM_SUFFIXES} if gem else set()
        local = next((item for level in levels for item in level if item in exchange), None)
        rest = [[item for item in level if item not in gems and item != local] for level in levels]
        boss = _boss(rest[1:])
        props = {prop['PropType']: prop.get('Value', 0) for prop in rows[-1].get('AddProps', [])}
        first = {prop['PropType']: prop.get('Value', 0) for row in rows if row.get('PromoteLevel') == 2
                 for prop in row.get('AddProps', [])}
        spec = next((prop for prop in props if prop not in BASE_PROPS), None)
        curve = next((grow['GrowCurve'] for grow in avatar.get('PropGrowCurves', [])
                      if grow.get('Type') == 'FIGHT_PROP_BASE_HP'), '')
        spec_base = first.get(spec)
        if spec_base is not None:
            spec_base = round(spec_base, 2) if spec in FLAT_SPECS else round(spec_base * 100, 2)
        out[name] = {
            'quality': 5 if curve.endswith('S5') else 4,
            'gem': gem,
            'boss': boss or 'None',
            'local': local,
            'common': _unique(item for level in rest for item in level if item != boss),
            'spec': SPEC_NAMES.get(spec, spec),
            'spec_base': spec_base,
            'spec_flat': spec in FLAT_SPECS,
            'base_hp': avatar.get('HpBase'),
            'asc_hp': props.get('FIGHT_PROP_BASE_HP'),
            'base_atk': avatar.get('AttackBase'),
            'asc_atk': props.get('FIGHT_PROP_BASE_ATTACK'),
            'base_def': avatar.get('DefenseBase'),
            'asc_def': props.get('FIGHT_PROP_BASE_DEFENSE'),
            'base_em': avatar.get('ElementMastery'),
        }
    return out


def _talent_materials(group, proud):
    levels = [_costs(row) for row in sorted(proud.get(group, []), key = lambda row: row.get('Level', 0))]
    levels = [level for level in levels if level]
    books = _unique(book for level in levels for item in level
                    if (book := _strip(item, BOOK_PREFIXES, prefix = True)))
    rest = [{item: count for item, count in level.items()
             if item != CROWN and not _strip(item, BOOK_PREFIXES, prefix = True)} for level in levels]
    # Each level needs far more of its common material than of the weekly boss material.
    common = [max(level, key = level.get) for level in rest if level]
    upper = [level for level in rest if len(level) > 1]
    boss = _boss([[item for item in level if item not in common] for level in upper])
    entry = {
        'books': books[0] if len(books) == 1 else books,
        'boss': boss,
        'common': _unique(common),
    }
    counts = [level[boss] for level in upper] if boss else []
    if counts and counts != DEFAULT_BOSS_COSTS and len(set(counts)) == 1:
        entry['bossCost'] = counts[0]
    return entry


def talent_data(characters = None):
    characters = characters if characters is not None else playable_characters()
    depots = {row['Id']: row for row in _load('AvatarSkillDepotExcelConfigData')}
    skills = {row['Id']: row for row in _load('AvatarSkillExcelConfigData')}
    proud = {}
    for row in _load('ProudSkillExcelConfigData'):
        proud.setdefault(row.get('ProudSkillGroupId'), []).append(row)

    def skill_group(depot):
        ids = [skill for skill in depot.get('Skills', []) if skill]
        # The Elemental Skill; the Traveler's Normal Attack can use another region's materials.
        return skills.get(ids[1] if len(ids) > 1 else ids[0] if ids else None, {}).get('ProudSkillGroupId')

    out, regions = {}, {}
    for name, (avatar, _) in report.track(list(characters.items()), 'Building talent material data'):
        candidates = avatar.get('CandSkillDepotIds') or []
        if candidates:
            for depot in map(depots.get, candidates):
                element = skills.get((depot or {}).get('EnergySkill'), {}).get('CostElemType')
                if element in TRAVELER_REGIONS and TRAVELER_REGIONS[element] not in regions and skill_group(depot):
                    regions[TRAVELER_REGIONS[element]] = _talent_materials(skill_group(depot), proud)
            continue
        group = skill_group(depots.get(avatar.get('SkillDepotId'), {}))
        if group in proud:
            out[name] = _talent_materials(group, proud)
    return out, {region: regions[region] for region in TRAVELER_REGIONS.values() if region in regions}


def lua_string(value):
    if value is None:
        return 'nil'
    if "'" in value and '"' not in value:
        return f'"{value}"'
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


def _number(value):
    if value is None:
        return 'nil'
    return str(int(value)) if isinstance(value, int) else repr(float(value))


def _header(title):
    return f'''--[=[<%-- [PAGE_INFO]
    pageTitle = #{title}#
[END_PAGE_INFO] --%>--]=]

'''


def ascension_lua(data = None):
    data = data if data is not None else ascension_data()
    entries = []
    for name, entry in data.items():
        spec_base = entry['spec_base']
        if spec_base is not None and entry['spec_flat'] and float(spec_base).is_integer():
            spec_base = int(spec_base)
        lines = [
            f"['quality'] = {entry['quality']}",
            f"['gem'] = {lua_string(entry['gem'])}",
            f"['boss'] = {lua_string(entry['boss'])}",
            f"['local'] = {lua_string(entry['local'])}",
            f"['common'] = {{ {', '.join(map(lua_string, entry['common']))} }}",
            f"['spec'] = {lua_string(entry['spec'])}",
            f"['spec_base'] = {_number(spec_base)}",
            *(f"['{stat}'] = {_number(entry[stat])}"
              for stat in ('base_hp', 'asc_hp', 'base_atk', 'asc_atk', 'base_def', 'asc_def')),
        ]
        body = ',\n\t\t'.join(lines)
        if entry['base_em'] is not None:
            body += f",\n\t\t--special EM base\n\t\t['base_em'] = {_number(entry['base_em'])}"
        entries.append(f"\t[{lua_string(name)}] = {{\n\t\t{body}\n\t}}")
    return f'{_header(ASCENSION_TITLE)}return {{\n{TEST_CHARACTER}' + ',\n'.join(entries) + '\n}\n'


def _talent_entry(name, entry):
    books = entry['books']
    books = f"{{{', '.join(map(lua_string, books))}}}" if isinstance(books, list) else lua_string(books)
    lines = [f'books  = {books}', f"boss   = {lua_string(entry['boss'])}"]
    if 'bossCost' in entry:
        lines.append(f"bossCost = {entry['bossCost']}")
    lines.append(f"common = {{{', '.join(map(lua_string, entry['common']))}}}")
    return f"\t[{lua_string(name)}] = {{\n\t\t" + ',\n\t\t'.join(lines) + '\n\t}'


def talent_lua(data = None):
    characters, regions = data if data is not None else talent_data()
    entries = [_talent_entry(name, entry) for name, entry in characters.items()]
    if regions:
        entries.append('\t--Traveler Variants\n' + _talent_entry(*next(iter(regions.items()))))
        entries += [_talent_entry(name, entry) for name, entry in list(regions.items())[1:]]
    return f'{_header(TALENT_TITLE)}return {{\n' + ',\n'.join(entries) + '\n}\n'


def write_character_data(directory = None):
    '''Writes both modules and returns how many characters each lists.'''
    directory = directory or CONFIG.OUTPUT_PATH
    report.stage('Loading playable characters and ascension materials')
    characters = playable_characters()
    ascension = ascension_data(characters)
    talents = talent_data(characters)
    report.stage('Writing character data modules', 2)
    write_file(f'{directory}/Character_Ascensions_and_Stats_data.lua', ascension_lua(ascension), overwrite = True)
    report.advance(1)
    write_file(f'{directory}/Talent_Upgrade_data.lua', talent_lua(talents), overwrite = True)
    report.advance(2)
    return len(ascension), len(talents[0]) + len(talents[1])
