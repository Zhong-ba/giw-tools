"""Builds a character's {{Advanced Properties}} templates from the attacks in BinOutput.

Attacks are named after the Attribute Scaling row they use: the attack's ability special is linked to a talent
parameter by ConfigTalent_<Name>.json, and the talent's ParamDescList names that parameter.
"""
import collections
import json
import re
import struct
from pathlib import Path
from types import SimpleNamespace

WEAPONS_WITHOUT_ELEMENT_GU = {'WEAPON_BOW'}
# Common impulse types (Interruption Resistance/Stagger#Impulse Type); overrides equal to one are written as its level.
IMPULSE_PRESETS = {
    ('Mute', 0, 0): '0', ('Shake', 0, 0): '1', ('Light', 200, 0): '2', ('Heavy', 200, 0): '3', ('Heavy', 800, 0): '4',
    ('Air', 480, 600): '5', ('Air', 655, 800): '6', ('Air', 0, 800): '7', ('Air', 795, 900): '8', ('Air', 1200, 600): '9',
}
DEFAULT_POISE = 30
# Bow plunges come from shared abilities, so they are absent from the character's files.
BOW_PLUNGES = (
    ('Plunging Attack Collision', '10', '2'),
    ('Low Plunge', '50', '2'),
    ('High Plunge', '100', '3'),
)
PLUNGE_TITLES = [title for title, _, _ in BOW_PLUNGES]
WEAK_SPOT_POISE = 3
WEAK_SPOT_IMPULSE = '5'
TALENT_KEYS = ('NA', 'E', 'Q')
ICD_BASES = (
    ('normal', 'Normal Attack'), ('extra', 'Charged Attack'), ('falling', 'Plunging Attack'), ('plunge', 'Plunging Attack'),
    ('burst', 'Elemental Burst'), ('art', 'Elemental Skill'), ('eart', 'Elemental Skill'), ('elea', 'Elemental Skill'),
    ('skill', 'Elemental Skill'),
)
ATTACK_TAG_ICD = {'NormalAttack': 'Normal Attack', 'ExtraAttack': 'Charged Attack', 'FallingAttack': 'Plunging Attack',
                  'Elemental_Art': 'Elemental Skill', 'Elemental_Burst': 'Elemental Burst'}
LAYOUT = re.compile(r'#?\{LAYOUT_MOBILE#[^}]*\}\{LAYOUT_PC#([^}]*)\}\{LAYOUT_PS#[^}]*\}')
LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
# Reaction attacks are named like the hit they come from, e.g. Normal Attack 1-Hit Lunar-Bloom.
REACTION_ATTACKS = (('MoonOvergrow', 'Lunar-Bloom'), ('MoonShock', 'Lunar-Charged'), ('MoonCrystallize', 'Lunar-Crystallize'),
                    ('StarSuperconductor', 'Stellar-Conduct'))


def number(value) -> str:
    """Shortest decimal that round-trips the float32 value; longer tails are extraction noise."""
    value = struct.unpack('f', struct.pack('f', float(value)))[0]
    for digits in range(8):
        rounded = round(value, digits)
        if struct.unpack('f', struct.pack('f', rounded))[0] == value:
            return f'{rounded:.{digits}f}'.rstrip('0').rstrip('.') if digits else str(int(rounded))
    return repr(value)


def _load(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def _walk(node, path, ability, attacks, events):
    if isinstance(node, dict):
        if isinstance(node.get('abilityName'), str):
            ability = node['abilityName']
        if node.get('$type') == 'ModifyDamageMixin' and isinstance(node.get('damagePercentage'), str):
            for event in node.get('animEventNames') or []:
                events[event].append(node['damagePercentage'])
            for tag in node.get('attackTags') or []:
                events[('tag', tag)].append(node['damagePercentage'])
        for key, value in node.items():
            if key.lower() == 'attackinfo' and isinstance(value, dict):
                attacks.append((ability, path + [key], value))
            _walk(value, path + [key], ability, attacks, events)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk(value, path + [str(index)], ability, attacks, events)


def character_files(bin_path: Path, name: str) -> list[Path]:
    """The character's avatar config plus every ability and skill gadget file that names the character."""
    pattern = re.compile(rf'(?<![A-Za-z])(?i:{re.escape(name)})(?![a-z])')
    files = [path for path in (bin_path / 'Avatar').glob('ConfigAvatar_*.json')
             if path.stem.lower() == f'configavatar_{name}'.lower()]
    for folder in (bin_path / 'Ability' / 'Temp' / 'AvatarAbilities', bin_path / 'Ability' / 'Temp' / 'AvatarAniEventAbilities',
                   bin_path / 'Gadget'):
        if folder.is_dir():
            files += sorted(path for path in folder.glob('*.json')
                            if pattern.search(path.stem) and (folder.name != 'Gadget' or path.stem.startswith('ConfigGadget_SkillObj_')))
    return files


def talent_links(config: dict, open_config: str) -> dict[str, int]:
    """{ability special: talent parameter number} for one talent level config. Scrambled keys are matched by shape."""
    links = {}
    for entry in config.get(open_config) or []:
        if not isinstance(entry, dict):
            continue
        special, delta = entry.get('paramSpecial'), entry.get('paramDelta')
        if not (isinstance(special, str) and isinstance(delta, str)):
            values = [value for key, value in entry.items() if key != '$type' and isinstance(value, str)]
            delta = next((value for value in values if re.fullmatch(r'%\d+', value)), None)
            special = next((value for value in values if value != delta and not value.startswith('Avatar_')), None)
        if special and delta and re.fullmatch(r'%\d+', delta):
            links[special] = int(delta[1:])
    return links


def icd_type(group: dict | None) -> str:
    if not group:
        return ''
    reset = number(group.get('ResetCycle', 0))
    # The hit pattern is the remaining 0/1 sequence; its field name is scrambled.
    sequence = next((value for key, value in group.items() if key not in ('DamageSequence', 'DurabilitySequence')
                     and isinstance(value, list) and value and all(item in (0, 1) for item in value)), [])
    hits = sequence.index(1, 1) if 1 in sequence[1:] else None
    if hits and all(item == (1 if index % hits == 0 else 0) for index, item in enumerate(sequence)):
        return f'{reset}s/{hits} Hits'
    if sequence and sequence[0] == 1 and not any(sequence[1:]):
        return f'{reset}s'
    if sequence:
        hits = ', '.join(ordinal(index + 1) for index, item in enumerate(sequence) if item)
        return f'{reset}s: <small>{hits} Hits Apply Element</small>'
    return f'{reset}s<!-- hit sequence: -->'


def ordinal(value: int) -> str:
    suffix = 'th' if 10 <= value % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(value % 10, 'th')
    return f'{value}{suffix}'


def impulse(pattern: dict) -> str:
    override = pattern.get('overrideHitImpulse')
    if not override and pattern.get('hitLevel'):
        override = pattern
    if override:
        level = override.get('hitLevel', 'Mute')
        x, y = float(override.get('hitImpulseX', 0)), float(override.get('hitImpulseY', 0))
        return IMPULSE_PRESETS.get((level, x, y), f'{level}, {number(x)}, {number(y)}')
    kind = pattern.get('hitImpulseType') or ''
    return kind[2:] if kind.startswith('LV') else kind or '0'


def title(talent: str, label: str) -> str:
    base = re.sub(r'\s*DMG$', '', LAYOUT.sub(r'\1', label)).strip()
    if talent == 'NA':
        if re.fullmatch(r'\d+-Hit', base):
            base = f'Normal Attack {base}'
        elif base == 'Plunge':
            base = 'Plunging Attack Collision'
    return base


def label_parts(form: str) -> tuple[list[int], list[int], bool]:
    """(param numbers, hits per param, whether the params are separate hits) for a ParamDescList value.

    "{param1}+{param2}" is two hits and "{param1}×2" is one value dealt twice, but "{param1} ATK+{param2} DEF" is a
    single hit that scales off two stats."""
    refs = list(re.finditer(r'\{param(\d+):[^}]*\}(?:\s*[×*]\s*(\d+))?([^+/{]*)', form))
    params = [int(ref.group(1)) for ref in refs]
    repeats = [int(ref.group(2) or 1) for ref in refs]
    stats = {ref.group(3).strip().removesuffix('%') for ref in refs}
    return params, repeats, len(refs) > 1 and len(stats) == 1 or any(count > 1 for count in repeats)


def _name_hits(rows: list[dict]) -> list[dict]:
    """Titles each row after its scaling label, numbering the hits of multi-hit labels like the wiki does:
    letters for repeated values and numbered hits (3-Hit A), N-Hit for the parts of a named attack."""
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row['label']].append(row)
    result = []
    for (talent, _, label), group in groups.items():
        repeats, separate = group[0]['parts']
        base = title(talent, label)
        if not separate:
            result += [dict(row, title=base) for row in group]
            continue
        hits = []
        for index, repeat in enumerate(repeats):
            matched = [row for row in group if row['ref'] == index]
            hits += matched * repeat if len(matched) == 1 else matched
        if base == 'Low/High Plunge' and len(hits) == 2:
            result += [dict(row, title=name) for row, name in zip(hits, ('Low Plunge', 'High Plunge'))]
            continue
        letters = any(count > 1 for count in repeats) or re.search(r'(\d+-Hit|Charged Attack)$', base)
        if len(hits) == 1:
            result.append(dict(hits[0], title=base))
            continue
        result += [dict(row, title=f'{base} {LETTERS[index]}' if letters else f'{base} {index + 1}-Hit')
                   for index, row in enumerate(hits)]
    return result


def icd_base(tag: str, attack_tag: str) -> str:
    words = [word.lower() for word in re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?![a-z])', tag)]
    for word, base in ICD_BASES:
        if word in words:
            return base
    for prefix, base in ATTACK_TAG_ICD.items():
        if attack_tag.startswith(prefix):
            return base
    return ' '.join(re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+', tag)) or tag


def format_template(rows: list[dict]) -> str:
    lines = ['{{Advanced Properties']
    for index, row in enumerate(rows, 1):
        suffix = '' if index == 1 else str(index)
        if index > 1:
            lines.append('')
        for key in ('title', 'gu', 'icdtag', 'icdtype', 'poise', 'impulse', 'blunt'):
            value = row.get(key)
            if value:
                lines.append(f'|{f"{key}{suffix}".ljust(len("impulse") + len(suffix) + 1)}= {value}')
    return '\n'.join(lines + ['}}'])


def _character(character_id: int, skill_depot: int | None) -> SimpleNamespace:
    """Loads the excel rows, talent config files, and BinOutput files shared by every Advanced Properties page."""
    from getConfig import CONFIG

    excel = Path(CONFIG.EXCEL_PATH)
    bin_path = Path(CONFIG.BIN_PATH)
    avatar = next((item for item in _load(excel / 'AvatarExcelConfigData.json') if item.get('Id') == character_id), None)
    if avatar is None:
        raise ValueError(f'Character {character_id} is not in the dataset.')
    if skill_depot is None and avatar.get('CandSkillDepotIds'):
        raise ValueError('Choose a skill depot for characters with selectable elements, such as the Traveler.')
    name = avatar.get('IconName', '').removeprefix('UI_AvatarIcon_')
    depot = next((item for item in _load(excel / 'AvatarSkillDepotExcelConfigData.json')
                  if item.get('Id') == (skill_depot or avatar.get('SkillDepotId'))), None)
    if not name or depot is None:
        raise ValueError(f'Character {character_id} has no skill data.')
    skills = depot.get('Skills') or []
    if len(skills) < 2 or not depot.get('EnergySkill'):
        raise ValueError(f'Skill depot {depot.get("Id")} has no Normal Attack, Skill, and Burst.')
    skill_ids = dict(zip(TALENT_KEYS, (skills[0], skills[1], depot['EnergySkill'])))
    groups = {item['Id']: item.get('ProudSkillGroupId') for item in _load(excel / 'AvatarSkillExcelConfigData.json') if 'Id' in item}
    proud = {(item.get('ProudSkillGroupId'), item.get('Level')): item for item in _load(excel / 'ProudSkillExcelConfigData.json')}
    attenuation = {item.get('Group'): item for item in _load(excel / 'AttackAttenuationExcelConfigData.json')}

    talent_dir = bin_path / 'Talent' / 'AvatarTalents'
    talent_files = sorted(talent_dir.glob('ConfigTalent_*.json')) if talent_dir.is_dir() else []
    if not talent_files:
        raise FileNotFoundError('No talent configs in BinOutput/Talent/AvatarTalents. Run quickSetup.bat again to download them.')
    # Most characters keep every talent in ConfigTalent_<Name>; the Traveler's are split across element files.
    talent_files.sort(key=lambda path: path.stem.lower() != f'configtalent_{name}'.lower())
    skill_configs = {proud.get((groups.get(skill_id), 1), {}).get('OpenConfig') for skill_id in skill_ids.values()} - {None, ''}
    names = {name} | {re.sub(r'_SkillUpgrade_\d+$', '', config) for config in skill_configs}
    files = list(dict.fromkeys(path for file_name in sorted(names) for path in character_files(bin_path, file_name)))
    return SimpleNamespace(excel=excel, avatar=avatar, depot=depot, skill_ids=skill_ids, groups=groups, proud=proud,
                           attenuation=attenuation, talent_files=talent_files, skill_configs=skill_configs, files=files,
                           bow=avatar.get('WeaponType') in WEAPONS_WITHOUT_ELEMENT_GU)


def _talent_config(character: SimpleNamespace, open_configs: set[str]) -> dict:
    config = {}
    for path in character.talent_files:
        if open_configs <= config.keys():
            break
        data = _load(path)
        config.update({key: data[key] for key in open_configs & data.keys()})
    return config


def _skill_labels(character: SimpleNamespace, talent_config: dict) -> dict[str, list]:
    """{special: [(talent, row order, label, param index within the label, label parts)]}"""
    labels = collections.defaultdict(list)
    for talent, skill_id in character.skill_ids.items():
        level_one = character.proud.get((character.groups.get(skill_id), 1))
        if not level_one:
            continue
        rows = []
        for order, description in enumerate(level_one.get('ParamDescList') or []):
            if isinstance(description, str) and '|' in description:
                label, form = description.split('|', 1)
                params, repeats, separate = label_parts(form)
                parts = (tuple(repeats), separate)
                rows += [(n, (talent, order, label, index, parts)) for index, n in enumerate(params)]
        for special, n in talent_links(talent_config, level_one.get('OpenConfig', '')).items():
            labels[special] += [label for param, label in rows if param == n]
    return labels


def _find_labels(info: dict, path: list, events: dict, labels: dict) -> list:
    """Scaling labels of an attack: from its damage special, the mixins of its animation event or attack tag, or any
    special it names."""
    damage = (info.get('attackProperty') or {}).get('damagePercentage')
    candidates = (
        damage if isinstance(damage, list) else [damage] if isinstance(damage, str) else [],
        [special for event in path if event in events for special in events[event]],
        events.get(('tag', str(info.get('attackTag') or '')), []),
        list(_strings(info)),
    )
    for keys in candidates:
        found = sorted({label for key in keys if isinstance(key, str) for label in labels.get(key.lstrip('%'), [])},
                       key=lambda label: label[:4])
        if found:
            return found
    return []


def _attack_properties(info: dict, bow: bool, attenuation: dict) -> dict:
    prop = info.get('attackProperty') or {}
    attack_tag = str(info.get('attackTag') or '')
    element = prop.get('elementType')
    physical = element in (None, '', 'None', 'Physical')
    if bow and physical and attack_tag.startswith(('NormalAttack', 'ExtraAttack', 'FallingAttack')):
        gu = '&mdash;'
    else:
        gu = f'{number((prop.get("elementDurability") or 0) / 25)}U'
    tag = info.get('attenuationTag') or ''
    tag = tag[0] if isinstance(tag, list) and tag else tag if isinstance(tag, str) else ''
    return {
        'gu': gu, 'tag': tag, 'attack_tag': attack_tag,
        'icdtype': icd_type(attenuation.get(info.get('attenuationGroup') or 'default')) if tag else '',
        'poise': number(prop.get('enBreak', DEFAULT_POISE)), 'impulse': impulse(info.get('hitPattern') or {}),
        'blunt': '1' if prop.get('strikeType') == 'Blunt' else '',
    }


def advanced_properties(character_id: int, skill_depot: int | None = None) -> dict[int, str]:
    """Returns {talent skill id: {{Advanced Properties}} template} for the Normal Attack, Skill, and Burst."""
    character = _character(character_id, skill_depot)
    labels = _skill_labels(character, _talent_config(character, character.skill_configs))

    attacks, events = [], collections.defaultdict(list)
    for path in character.files:
        _walk(_load(path), [], None, attacks, events)

    pages = {talent: [] for talent in TALENT_KEYS}
    seen = set()
    for appearance, (_, path, info) in enumerate(attacks):
        found = _find_labels(info, path, events, labels)
        if not found:
            continue
        talent, order, label, ref, parts = found[0]
        row = {'label': (talent, order, label), 'ref': ref, 'parts': parts, 'order': (order, ref, appearance),
               **_attack_properties(info, character.bow, character.attenuation)}
        key = (talent, order, ref, row['gu'], row['tag'], row['icdtype'], row['poise'], row['impulse'], row['blunt'])
        if key not in seen:
            seen.add(key)
            pages[talent].append(row)

    templates = {}
    for talent, rows in pages.items():
        rows.sort(key=lambda row: row['order'])
        rows = _name_hits(rows)
        if talent == 'NA' and character.bow:
            rows = _bow_rows(rows)
        _letter_duplicates(rows)
        _name_icd_tags(rows)
        rows = _group_icd(rows)
        if rows:
            templates[character.skill_ids[talent]] = format_template(rows)
    return templates


def _gate_params(node: dict) -> set[str]:
    """Talent params a node's predicates require; params under ByNot are the opposite condition and are skipped."""
    found = set()

    def scan(value):
        if isinstance(value, dict):
            if value.get('$type') == 'ByNot':
                return
            if value.get('$type') == 'ByUnlockTalentParam' and isinstance(value.get('talentParam'), str):
                found.add(value['talentParam'])
            for item in value.values():
                scan(item)
        elif isinstance(value, list):
            for item in value:
                scan(item)

    for key in ('predicates', 'targetPredicates', 'predicatesForeach'):
        scan(node.get(key))
    return found


def _link_strings(node: dict, crit: bool = False) -> set[str]:
    """Specials a damage source scales with. Crit bonuses (unless crit is set), and damageExtra next to a
    damagePercentage, only buff an existing hit, so they do not make the hit the talent's own."""
    if isinstance(node.get('attackProperty'), dict):
        node = dict(node, attackProperty=_link_strings_source(node['attackProperty'], crit))
    else:
        node = _link_strings_source(node, crit)
    return {value.lstrip('%') for value in _strings(node)}


def _link_strings_source(source: dict, crit: bool = False) -> dict:
    extra_is_buff = source.get('damagePercentage') or source.get('$type') == 'ModifyDamageMixin'
    return {key: value for key, value in source.items()
            if (crit or not key.startswith('bonusCritical')) and not (extra_is_buff and key == 'damageExtra')}


def _has_attack(node) -> bool:
    if isinstance(node, dict):
        return any(key.lower() == 'attackinfo' or _has_attack(value) for key, value in node.items())
    return isinstance(node, list) and any(_has_attack(value) for value in node)


def _scan(node, path: list, ability: str | None, gates: frozenset, found: SimpleNamespace, variant: bool = False) -> None:
    """Collects attacks with the talent params gating them, plus the modifier applications, gadget spawns, and
    damage mixins that link attacks to talents indirectly. Attacks in a gated branch whose other branch also attacks
    are variants of an existing hit rather than new hits."""
    if isinstance(node, dict):
        if isinstance(node.get('abilityName'), str):
            ability = node['abilityName']
        own = _gate_params(node)
        here = gates | own
        branches = bool(own) and _has_attack(node.get('failActions'))
        kind = str(node.get('$type') or '')
        if kind == 'ModifyDamageMixin':
            found.mixins.append((ability, node))
        if not kind.startswith('Remove'):
            for key in ('modifierName', 'modifierNames'):
                modifiers = node.get(key)
                for modifier in modifiers if isinstance(modifiers, list) else [modifiers]:
                    if isinstance(modifier, str):
                        found.applied[(ability, modifier)].append(here)
        if kind == 'CreateGadget' and isinstance(node.get('gadgetID'), int) and here:
            found.gadgets.append((ability, node['gadgetID'], here))
        for key, value in node.items():
            inner = gates if key == 'failActions' else here
            inner_variant = variant or branches and key == 'successActions'
            if key.lower() == 'attackinfo' and isinstance(value, dict):
                found.attacks.append((ability, inner, path + [key], value, variant))
            _scan(value, path + [key], ability, inner, found, inner_variant)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _scan(value, path + [str(index)], ability, gates, found, variant)


def _gadget_abilities(character: SimpleNamespace, gadget_ids: set[int]) -> dict[int, set[str]]:
    json_names = {item.get('Id'): item.get('JsonName') for item in _load(character.excel / 'GadgetExcelConfigData.json')
                  if item.get('Id') in gadget_ids}
    configs = {}
    for path in character.files:
        if path.parent.name == 'Gadget':
            configs.update(_load(path))
    return {gadget: {entry.get('abilityName') for entry in (configs.get(json_names.get(gadget)) or {}).get('abilities') or []
                     if isinstance(entry, dict)} for gadget in gadget_ids}


def _talent_rows(entries: list, scan: SimpleNamespace, gadgets: dict, character: SimpleNamespace, name: str,
                 later_params: set[str], sibling_titles: dict, events: dict, labels: dict) -> list[dict]:
    """Attacks a passive or constellation adds: those in abilities it adds, behind its talent param gates (directly,
    through gated modifiers, or in gated gadgets), or scaled by the specials it sets. Hits that use a Normal Attack,
    Skill, or Burst scaling row stay on those pages unless the talent scales them or gates them as an extra hit, and
    hits that need several talents belong to the one unlocked last."""
    entries = [entry for entry in entries if isinstance(entry, dict)]
    added = {entry.get('abilityName') for entry in entries if entry.get('$type') == 'AddAbility'} - {None}
    unlocked = {(entry.get('abilityName'), entry.get('talentParam')) for entry in entries
                if entry.get('$type') == 'UnlockTalentParam'}
    specials = {(entry.get('abilityName'), entry.get('paramSpecial')) for entry in entries
                if entry.get('$type') == 'ModifyAbility' and isinstance(entry.get('paramSpecial'), str)}
    own_specials = {special for _, special in specials}
    params = {param for _, param in unlocked}
    spawned = set().union(*(gadgets.get(gadget, set()) for ability, gadget, gates in scan.gadgets
                            if any((ability, param) in unlocked for param in gates) and not gates & later_params))
    mixin_events, mixin_tags = set(), set()
    for ability, mixin in scan.mixins:
        if any((ability, value) in specials for value in _link_strings(mixin)):
            mixin_events.update(mixin.get('animEventNames') or [])
            mixin_tags.update(mixin.get('attackTags') or [])

    rows, seen = [], set()
    for ability, gates, path, info, variant in scan.attacks:
        strings = _link_strings(info)
        # Crit bonuses don't link a hit to a talent, but do mark a hit in a linked ability as the talent's own.
        all_strings = _link_strings(info, crit=True)
        attack_tag = str(info.get('attackTag') or '')
        scaled = any((ability, special) in specials for special in strings)
        gated = any((ability, param) in unlocked for param in gates) and not gates & later_params
        if not (ability in added or gated or scaled
                or ability in spawned and (not gates or gates & params)
                or mixin_events & set(path) or attack_tag in mixin_tags):
            continue
        found = [] if all_strings & own_specials else _find_labels(info, path, events, labels)
        # A variant with an ICD tag named after the talent is a separate hit (Jahoda C1), not a tweaked one.
        variant = variant and info.get('attenuationTag') not in params
        if found and not (gated and not variant):
            continue
        row = _attack_properties(info, character.bow, character.attenuation)
        key = tuple(value for field, value in row.items() if field != 'attack_tag')
        if key in seen:
            continue
        seen.add(key)
        reaction = next((suffix for prefix, suffix in REACTION_ATTACKS if attack_tag.startswith(prefix)), None)
        if found:
            base = title(found[0][0], found[0][2])
        elif reaction and ability in sibling_titles:
            base = sibling_titles[ability]
        else:
            base = name
        rows.append(dict(row, title=f'{base} {reaction}' if reaction else base))
    return rows


def talent_advanced_properties(character_id: int, skill_depot: int | None = None) -> tuple[dict[int, str], dict[int, str]]:
    """Returns ({passive proud skill group id: template}, {constellation talent id: template}) for the passives and
    constellations that deal damage. Rows are titled after the scaling row they reuse, or else the talent's name."""
    character = _character(character_id, skill_depot)
    passives = {}
    for opens in ('InherentProudSkillOpens', 'SpecialProudSkillOpens'):
        for item in character.depot.get(opens) or []:
            level_one = character.proud.get((item.get('ProudSkillGroupId'), 1)) if isinstance(item, dict) else None
            if level_one and level_one.get('OpenConfig'):
                passives[item['ProudSkillGroupId']] = (level_one['OpenConfig'], level_one.get('NameTextMapHash'))
    constellation_ids = set(character.depot.get('Talents') or [])
    constellations = {item['TalentId']: (item['OpenConfig'], item.get('NameTextMapHash'))
                      for item in _load(character.excel / 'AvatarTalentExcelConfigData.json')
                      if item.get('TalentId') in constellation_ids and item.get('OpenConfig')}
    talent_config = _talent_config(character, character.skill_configs | {config for config, _ in
                                                                           [*passives.values(), *constellations.values()]})
    labels = _skill_labels(character, talent_config)

    scan = SimpleNamespace(attacks=[], mixins=[], applied=collections.defaultdict(list), gadgets=[])
    for path in character.files:
        _scan(_load(path), [], None, frozenset(), scan)
    # A modifier's attacks are gated only when every application of the modifier is.
    for index, (ability, gates, path, info, variant) in enumerate(scan.attacks):
        for position, key in enumerate(path[:-1]):
            if key == 'modifiers' and scan.applied.get((ability, path[position + 1])):
                gates |= frozenset.intersection(*scan.applied[(ability, path[position + 1])])
        scan.attacks[index] = (ability, gates, path, info, variant)
    events = collections.defaultdict(list)
    for _, mixin in scan.mixins:
        if isinstance(mixin.get('damagePercentage'), str):
            for event in mixin.get('animEventNames') or []:
                events[event].append(mixin['damagePercentage'])
            for tag in mixin.get('attackTags') or []:
                events[('tag', tag)].append(mixin['damagePercentage'])
    sibling_titles = {}
    for ability, _, path, info, _ in scan.attacks:
        found = _find_labels(info, path, events, labels)
        if found and ability not in sibling_titles:
            sibling_titles[ability] = title(found[0][0], found[0][2])
    gadgets = _gadget_abilities(character, {gadget for _, gadget, _ in scan.gadgets}) if scan.gadgets else {}

    # Passives unlock before constellations, so later talents come later in this order.
    unlock_order = [(kind, talent_id, open_config, name) for kind, talents in enumerate((passives, constellations))
                    for talent_id, (open_config, name) in talents.items()]
    talent_params = [{entry.get('talentParam') for entry in talent_config.get(open_config) or []
                      if isinstance(entry, dict) and entry.get('$type') == 'UnlockTalentParam'} - {None}
                     for _, _, open_config, _ in unlock_order]
    templates = ({}, {})
    for index, (kind, talent_id, open_config, name) in enumerate(unlock_order):
        later_params = set().union(*talent_params[index + 1:]) - talent_params[index]
        rows = _talent_rows(talent_config.get(open_config) or [], scan, gadgets, character, str(name or open_config),
                            later_params, sibling_titles, events, labels)
        _letter_duplicates(rows)
        _name_icd_tags(rows)
        rows = _group_icd(rows)
        if rows:
            templates[kind][talent_id] = format_template(rows)
    return templates


def _bow_rows(rows: list[dict]) -> list[dict]:
    """Adds the weak spot hits of aimed shots and the shared bow plunges, as the wiki lists them."""
    result = []
    for row in rows:
        result.append(row)
        if row['title'] in ('Aimed Shot', 'Fully-Charged Aimed Shot'):
            if row['gu'] != '&mdash;':
                row['gu'] = f'{row["gu"]}<br><small>(w/ [[Dropoff]])</small>'
            weak = dict(row, title=f'{row["title"]} (Hit Weak Spot)', poise=number(float(row['poise']) * WEAK_SPOT_POISE),
                        impulse=WEAK_SPOT_IMPULSE, gu=row['gu'].replace('[[Dropoff]]', 'Dropoff'))
            result.append(weak)
    present = {row['title'] for row in result}
    result = [row for row in result if row['title'] not in PLUNGE_TITLES]
    for plunge, poise, level in BOW_PLUNGES:
        if plunge in present:
            result += [row for row in rows if row['title'] == plunge]
        else:
            result.append({'title': plunge, 'gu': '&mdash;', 'tag': '', 'icdtype': '', 'poise': poise,
                           'impulse': level, 'blunt': '', 'attack_tag': 'FallingAttack'})
    return result


def _letter_duplicates(rows: list[dict]) -> None:
    """Hits that share a scaling row but differ in properties get letters, as on the wiki (3-Hit A, 3-Hit B)."""
    counts = collections.Counter(row['title'] for row in rows)
    used = collections.Counter()
    for row in rows:
        if counts[row['title']] > 1:
            name = row['title']
            used[name] += 1
            row['title'] = f'{name} {LETTERS[used[name] - 1]}' if not re.search(r' [A-Z]$', name) else f'{name}{used[name]}'


def _name_icd_tags(rows: list[dict]) -> None:
    """Readable ICD tags; different tags that would read the same are lettered so shared ICD stays visible."""
    bases = collections.defaultdict(list)
    for row in rows:
        if row['tag']:
            base = icd_base(row['tag'], row['attack_tag'])
            if row['tag'] not in bases[base]:
                bases[base].append(row['tag'])
    for row in rows:
        if not row['tag']:
            row['icdtag'] = 'none'
            continue
        base = icd_base(row['tag'], row['attack_tag'])
        tags = bases[base]
        row['icdtag'] = f'{base} {LETTERS[tags.index(row["tag"])]}' if len(tags) > 1 else base


def _group_icd(rows: list[dict]) -> list[dict]:
    """Moves rows that share an ICD tag and type next to the first of them; the template merges adjacent equal cells."""
    groups = {}
    for index, row in enumerate(rows):
        key = (row['icdtag'], row['icdtype']) if row['icdtag'] != 'none' else index
        groups.setdefault(key, []).append(row)
    return [row for group in groups.values() for row in group]
