"""Adds a character's rows to the community combat data pages, starting from each page's current revision.

Rows come from the same hits as {{Advanced Properties}} (advancedProperties.combat_data). Each table keeps its
alphabetical order. Existing character rows are preserved unless updating them is explicitly requested.
"""
import re
from types import SimpleNamespace

from advancedProperties import combat_data, icd_sequence, number

GAUGE = 'Elemental Gauge Theory/Character Data'
ICD = 'Internal Cooldown/Data'
AOE = 'Area of Effect'
HITLAG = 'Hitlag/Data'
TARGETING = 'Targeting/Data'
PAGES = (GAUGE, ICD, AOE, HITLAG, TARGETING)
ELEMENTS = {'Fire': 'Pyro', 'Water': 'Hydro', 'Electric': 'Electro', 'Ice': 'Cryo', 'Grass': 'Dendro', 'Wind': 'Anemo',
            'Rock': 'Geo'}
WEAPONS = {'WEAPON_SWORD_ONE_HAND': 'Sword', 'WEAPON_CLAYMORE': 'Claymore', 'WEAPON_POLE': 'Polearm', 'WEAPON_BOW': 'Bow',
           'WEAPON_CATALYST': 'Catalyst'}
PLUNGES = {'Plunge': 'Plunging Collision', 'Plunging Attack Collision': 'Plunging Collision', 'Low Plunge': 'Plunging',
           'High Plunge': 'Plunging'}
NO_ICD = 'colspan="2" | <small>(No ICD)</small>'
# Lunar and Stellar reaction hits (MoonOvergrow, StarSuperconductor, StarSwirl...) have no hitbox or hitlag of their own.
REACTION_TAGS = ('Moon', 'Star')
LETTER = re.compile(r' [A-Z]\d*$')
LOCK_SHAPE = re.compile(r'Circle(?:LockEnemy)?R([\d.]+)(?:H([\d.]+))?(HC)?')
CHARACTER = re.compile(r'\{\{\s*Character\s*\|\s*([^|}]+?)\s*[|}]')
ICD_SECTIONS = {'normal': 'Character Normal Attack', 'charged': 'Character Charged Attacks', 'E': 'Character Elemental Skills',
                'Q': 'Character Elemental Burst', 'P': 'Other Abilities', 'C': 'Other Abilities'}
AOE_SECTIONS = {'E': 'Elemental Skills', 'Q': 'Elemental Bursts', 'P': 'Other Notable Abilities', 'C': 'Other Notable Abilities'}


def attack_kind(title: str) -> str:
    """normal, charged, plunge, or other, from an Advanced Properties row title."""
    base = LETTER.sub('', title)
    if base in PLUNGES or re.search(r'\bPlung', base):
        return 'plunge'
    if re.fullmatch(r'(Normal Attack )?\d+-Hit', base):
        return 'normal'
    if re.match(r'(Charged Attack|Aimed Shot|Fully-Charged Aimed Shot)\b', base):
        return 'charged'
    return 'other'


def short_label(title: str) -> str:
    """How the gauge, ICD, and AoE pages name a hit inside a talent: Normal/Charged/Plunging for basic attacks."""
    kind = attack_kind(title)
    if kind == 'normal':
        return 'Normal'
    if kind == 'plunge':
        base = LETTER.sub('', title)
        if base in PLUNGES:
            return PLUNGES[base]
        if 'Collision' in base:
            return 'Plunging Collision'
        return 'Plunging' if re.fullmatch(r'(Low/High |Low |High )?Plunge( \d+-Hit)?', base) else title
    if kind == 'charged' and title.startswith('Charged Attack'):
        return title.removeprefix('Charged Attack').strip() or 'Charged'
    return title


def merge(entries: list[tuple[str, str]]) -> list[tuple[list[str], str]]:
    """Groups (title, value) entries by value like the wiki, which writes hits that read the same as one row."""
    groups = {}
    for title, value in entries:
        groups.setdefault(value, []).append(title)
    return [(titles, value) for value, titles in groups.items()]


def row_labels(titles: list[str], label, skip: str, reactions: set = frozenset()) -> list[tuple[str, list[str]]]:
    """[(label, letters)] for the hits of one row, without labels that only repeat the talent's name."""
    labels = {}
    for title in titles:
        base = LETTER.sub('', title)
        text = label(base)
        # Reaction hits are often titled after their constellation: "<name> Lunar-Bloom" reads as "Lunar-Bloom".
        if text and title in reactions and text.startswith(f'{skip} '):
            text = text[len(skip) + 1:]
        if text and text != skip:
            labels.setdefault(text, []).append(title[len(base):].strip())
    return [(text, [letter for letter in letters if letter]) for text, letters in labels.items()]


def sequence_text(sequence: list[int]) -> str:
    """The Gauge Sequence cell of the ICD Types table."""
    if not sequence:
        return '?'
    if sequence[0] == 1 and not any(sequence[1:]):
        return "Only the 1st is '''''1''''', others are 0"
    for period in range(1, len(sequence) // 2 + 1):
        if all(item == sequence[index % period] for index, item in enumerate(sequence)):
            return f"'''''{' '.join(map(str, sequence[:period]))}''''' as the repetend"
    return f"'''''{' '.join(map(str, sequence))}'''''"


def _hits(data: SimpleNamespace) -> list[SimpleNamespace]:
    hits = []
    for talent, (_, name, rows) in data.skills.items():
        hits += [SimpleNamespace(talent=talent, name=name, row=row) for row in rows]
    for talent, talents in (('P', data.passives), ('C', data.constellations)):
        for name, rows in talents.values():
            hits += [SimpleNamespace(talent=talent, name=name, row=row) for row in rows]
    for hit in hits:
        hit.title = hit.row['title']
        hit.kind = attack_kind(hit.title)
        hit.combat = dict(hit.row.get('combat') or ())
        hit.element = ELEMENTS.get(hit.combat.get('element', ''), '')
        hit.reaction = str(hit.row.get('attack_tag', '')).startswith(REACTION_TAGS)
    return [hit for hit in hits if '(Hit Weak Spot)' not in hit.title]


def _talent(hit, gauge: bool = False, text: str | None = None) -> str:
    if hit.talent == 'C':
        return f'{{{{Constellation|{hit.name}|level=1|nobr=1|20}}}}' if gauge else f'{{{{Constellation|{hit.name}|20|nobr=1|level=1}}}}'
    if text:
        return f'{{{{Talent|{hit.name}|20|nobr=1|text={text}}}}}'
    return f'{{{{Talent|{hit.name}|type=1|nobr=1|20}}}}' if gauge else f'{{{{Talent|{hit.name}|20|nobr=1|type=1}}}}'


def talent_cells(hits: list, value, template, label=short_label, always_label=False) -> list[str]:
    """Row cells after the character cell: one per talent and distinct value, labelled with the hits it covers when
    the talent needs more than one row, the row holds only Lunar/Stellar reaction hits, or always_label (a bool or a
    predicate on the talent's first hit) holds."""
    by_talent = {}
    for hit in hits:
        cell = value(hit)
        if cell is not None:
            by_talent.setdefault((hit.talent, hit.name), []).append((hit, cell))
    cells = []
    for entries in by_talent.values():
        merged = merge([(hit.title, cell) for hit, cell in entries])
        reactions = {hit.title for hit, _ in entries if getattr(hit, 'reaction', False)}
        rows = [(row_labels(titles, label, entries[0][0].name, reactions), cell) for titles, cell in merged]
        plain = [tuple(text for text, _ in labels) for labels, _ in rows]
        force = always_label(entries[0][0]) if callable(always_label) else always_label
        for (labels, cell), key, (titles, _) in zip(rows, plain, merged):
            # Rows that would read the same keep their letters, compactly: Skill A/B/C.
            lettered = plain.count(key) > 1
            texts = [f'{text} {"/".join(letters)}' if lettered and letters else text for text, letters in labels]
            shown = force or len(merged) > 1 or reactions.issuperset(titles)
            suffix = f' ({"/".join(texts)})' if texts and shown else ''
            cells.append(f'{template(entries[0][0])}{suffix} || {cell}')
    return cells


def character_rows(name: str, cells: list[str], style: str) -> list[str]:
    """Table rows for one character: the character cell spans all of their rows."""
    span = f'rowspan="{len(cells)}" ' if len(cells) > 1 else ''
    if style == 'small':
        first = f'| {span}| {{{{Character|{name}|20|nobr=1}}}} || ' if span else f'| {{{{Character|{name}|20|nobr=1}}}} || '
    else:
        align = 'text-align:center;' if style == 'gauge' else 'text-align:center'
        first = f'| {span}style="{align}" | {{{{Character|{name}|50}}}} || '
    return [first + cells[0], *(f'| {cell}' for cell in cells[1:])]


def _table(text: str, heading: str) -> tuple[int, int] | None:
    """(start, end) offsets of the lines between {| and |} of the first table under a heading."""
    match = re.search(rf'^(=+)[ \t]*{re.escape(heading)}[ \t]*\1[ \t]*$', text, re.M)
    if not match:
        return None
    following = re.compile(r'^=+[^=\n].*?=+[ \t]*$', re.M).search(text, match.end())
    limit = following.start() if following else len(text)
    start = text.find('\n{|', match.end(), limit)
    end = text.find('\n|}', start + 1, limit) if start >= 0 else -1
    return (start + 1, end + 1) if end >= 0 else None


def insert_rows(text: str, heading: str, name: str, build, update_existing: bool = False) -> tuple[str, str]:
    """Inserts a character's rows into the table under a heading, before the first character that sorts after them.
    build(table lines) returns the rows, or nothing to skip. Opt-in updates replace the character's existing block.
    Returns (text, outcome)."""
    span = _table(text, heading)
    if span is None:
        return text, f'no "{heading}" table'
    lines = text[span[0]:span[1]].rstrip('\n').split('\n')
    starts = [index for index, line in enumerate(lines) if line.strip() == '|-']
    names = {}
    for index in starts:
        found = CHARACTER.search(lines[index + 1]) if index + 1 < len(lines) else None
        if found:
            names[index] = found.group(1)
    matches = [index for index, existing in names.items() if existing.casefold() == name.casefold()]
    if matches and not update_existing:
        return text, 'already listed'
    if matches:
        for index in reversed(matches):
            end = next((other for other in starts if other > index and (
                other in names or other + 1 < len(lines) and
                re.search(r'\|\s*(?:Most|All) [^|]*Characters\s*\|\|', lines[other + 1])
            )), len(lines))
            del lines[index:end]
        names = {}
        for index, line in enumerate(lines[:-1]):
            if line.strip() == '|-':
                found = CHARACTER.search(lines[index + 1])
                if found:
                    names[index] = found.group(1)
    rows = build(lines)
    if not rows:
        if matches:
            return text[:span[0]] + '\n'.join(lines) + '\n' + text[span[1]:], 'removed existing rows; nothing to add'
        return text, 'nothing to add'
    position = next((index for index, existing in names.items() if existing.casefold() > name.casefold()), len(lines))
    block = [line for row in rows for line in ('|-', row)]
    lines[position:position] = block
    action = 'updated' if matches else 'added'
    return text[:span[0]] + '\n'.join(lines) + '\n' + text[span[1]:], f'{action} {len(rows)} row{"s" * (len(rows) != 1)}'


def _apply(text: str, title: str, name: str, sections: dict, log: list, update_existing: bool = False) -> str:
    for heading, build in sections.items():
        text, outcome = insert_rows(text, heading, name, build, update_existing)
        log.append(f'{title} > {heading}: {outcome}')
    return text


def gauge_page(text: str, name: str, data: SimpleNamespace, hits: list, log: list, update_existing: bool = False) -> str:
    # Only hits whose attackInfo has an elementType; infused physical attacks are covered by the page's note.
    hits = [hit for hit in hits if hit.element]
    sections = {}
    for element in dict.fromkeys(hit.element for hit in hits):
        chosen = [hit for hit in hits if hit.element == element]

        def build(_, chosen=chosen):
            cells = talent_cells(chosen, lambda hit: hit.row['gu'].replace('<br>', ' ') if hit.row['gu'] != '&mdash;' else None,
                                 lambda hit: _talent(hit, gauge=True), always_label=lambda hit: hit.talent == 'NA')
            return character_rows(name, cells, 'gauge') if cells else None
        sections[element] = build
    return _apply(text, GAUGE, name, sections, log, update_existing)


def _icd_types(text: str) -> dict[tuple[str, str], str]:
    """{(reset, gauge sequence): name} of the ICD Types table."""
    span = _table(text, 'ICD Types')
    types = {}
    for line in text[span[0]:span[1]].split('\n') if span else []:
        cells = [cell.strip() for cell in line.lstrip('|').split('||')]
        if line.startswith('|') and not line.startswith(('|-', '|}')) and len(cells) == 3:
            types.setdefault((cells[1], re.sub(r'<sup>.*?</sup>', '', cells[2]).strip()), cells[0])
    return types


def icd_page(text: str, name: str, data: SimpleNamespace, hits: list, log: list, update_existing: bool = False) -> str:
    existing = _icd_types(text)
    names = set(existing.values())
    tokens = [re.escape(token) for token in {re.sub(r'New$', '', internal) for internal in data.names} if token]
    own = re.compile(rf'(?<![A-Za-z])(?:{"|".join(tokens)})(?![a-z])', re.I) if tokens else None
    chosen = [hit for hit in hits if hit.element and hit.kind != 'plunge']
    own_groups = list(dict.fromkeys(hit.combat.get('group') for hit in chosen if hit.row['icdtag'] != 'none'
                                    and hit.combat.get('group') != 'default' and own and own.search(hit.combat.get('group', ''))))
    type_names, new_types = {'default': 'Default'}, []
    for hit in chosen:
        group = hit.combat.get('group', 'default')
        if hit.row['icdtag'] == 'none' or group in type_names:
            continue
        settings = data.attenuation.get(group)
        if settings is None:
            type_names[group] = '?'
            log.append(f'{ICD}: ICD group {group} is not in AttackAttenuationExcelConfigData; fill in its ICD Type.')
            continue
        key = (number(settings.get('ResetCycle', 0)), sequence_text(icd_sequence(settings)))
        if group in own_groups:
            type_name = name if len(own_groups) == 1 else f'{name} {hit.row["icdtag"]}'
        else:
            type_name = existing.get(key) or group.replace('_', ' ')
        type_names[group] = type_name
        if type_name not in names:
            names.add(type_name)
            new_types.append(f'| {type_name} || {key[0]} || {key[1]}')
    if new_types:
        span = _table(text, 'ICD Types')
        if span:
            text = text[:span[1]] + ''.join(f'|-\n{row}\n' for row in new_types) + text[span[1]:]
            log.append(f'{ICD} > ICD Types: added {", ".join(row.split(" || ")[0][2:] for row in new_types)}')

    normal_attack = next((skill_name for talent, (_, skill_name, _) in data.skills.items() if talent == 'NA'), name)

    def section(hit):
        if hit.kind in ('normal', 'charged'):
            return ICD_SECTIONS[hit.kind]
        if hit.talent == 'NA':
            return ICD_SECTIONS['charged' if str(hit.row.get('attack_tag', '')).startswith('Extra') else 'normal']
        return ICD_SECTIONS[hit.talent]

    def value(hit):
        if hit.row['icdtag'] == 'none':
            return NO_ICD
        type_name = type_names.get(hit.combat.get('group', 'default'), '?')
        # Plain Normal Attacks with the default ICD are the "Most Melee/Catalyst Characters" rows.
        if section(hit) == ICD_SECTIONS['normal'] and hit.row['icdtag'] == 'Normal Attack' and type_name == 'Default':
            return None
        return f'{hit.row["icdtag"]} || {type_name}'

    sections = {}
    for heading in dict.fromkeys(ICD_SECTIONS.values()):
        members = [SimpleNamespace(**dict(vars(hit), talent='NA', name=normal_attack)) if heading in
                   (ICD_SECTIONS['normal'], ICD_SECTIONS['charged']) else hit for hit in chosen if section(hit) == heading]
        if not members:
            continue
        charged = heading == ICD_SECTIONS['charged']

        def build(lines, members=members, charged=charged):
            if charged:
                weapon = WEAPONS.get(data.weapon)
                defaults = set()
                for line in lines:
                    cells = [cell.strip() for cell in line.lstrip('|').split('||')]
                    if len(cells) >= 3 and re.match(r'(Most|All)\b', cells[0]) and weapon and re.search(rf'\b{weapon}\b', cells[0]):
                        defaults.add(' || '.join(cells[2:]))
                exceptions = [hit for hit in members if hit.reaction or value(hit) not in defaults]
                cells = talent_cells(exceptions, value, lambda hit: _talent(hit, text='Charged Attack'),
                                     label=lambda title: '' if short_label(title) == 'Charged' else short_label(title),
                                     always_label=True)
            else:
                cells = talent_cells(members, value, _talent)
            return character_rows(name, cells, 'small') if cells else None
        sections[heading] = build
    return _apply(text, ICD, name, sections, log, update_existing)


def aoe_page(text: str, name: str, hits: list, log: list, update_existing: bool = False) -> str:
    sections = {}
    for talent, heading in AOE_SECTIONS.items():
        chosen = [hit for hit in hits if hit.talent == talent and hit.kind == 'other' and not hit.reaction
                  and hit.combat.get('aoe')]
        if chosen:
            sections.setdefault(heading, []).extend(chosen)
    builds = {heading: (lambda _, chosen=chosen: character_rows(
        name, talent_cells(chosen, lambda hit: ' || '.join(hit.combat['aoe']), _talent, label=lambda title: title), 'small'))
        for heading, chosen in sections.items()}
    return _apply(text, AOE, name, builds, log, update_existing)


def hitlag_defaults(lines: list[str]) -> list[tuple[str, tuple]]:
    """(attack, values) rows of the table's "Most ... Characters" block."""
    defaults, in_default = [], False
    for index, line in enumerate(lines):
        if line.strip() == '|-' or not line.startswith('|') or line.startswith('|}'):
            continue
        cells = [cell.strip() for cell in line.split('||')]
        if index and lines[index - 1].strip() == '|-' and CHARACTER.search(line):
            in_default = False
        elif re.search(r'\|\s*(Most|All) [^|]*Characters\s*$', cells[0]):
            in_default = True
        if in_default and len(cells) >= 4:
            defaults.append((cells[-4].lstrip('| ').strip(), tuple(cells[-3:])))
    return defaults


def _hit_number(title: str) -> str:
    match = re.search(r'(\d+)-Hit(?: ([A-Z]\d*))?$', title)
    return f'{match.group(1)}{match.group(2) or ""}' if match else title


def hitlag_page(text: str, name: str, data: SimpleNamespace, hits: list, log: list, update_existing: bool = False) -> str:
    weapon = WEAPONS.get(data.weapon)
    chosen = [hit for hit in hits if hit.talent == 'NA' and hit.kind != 'plunge' and not hit.reaction]
    if not weapon or not chosen:
        log.append(f'{HITLAG}: nothing to add')
        return text

    def values(hit):
        time, extendable, scale = hit.combat.get('hitlag', ('0', False, ''))
        return time, f'{{{{check|{"yes" if extendable else "no"}}}}}', scale or '0.01'

    def build(lines):
        defaults = hitlag_defaults(lines)

        def is_default(hit):
            for attack, default in defaults:
                if default != values(hit):
                    continue
                if attack == 'All Attacks' or hit.kind == 'charged' and attack == LETTER.sub('', hit.title):
                    return True
                if hit.kind == 'normal' and (attack == 'Normal Attack' or attack.startswith('Normal Attack ') and
                                             re.sub(r'[A-Z]$', '', _hit_number(hit.title)) in re.split(r',\s*', attack[14:])):
                    return True
            return False

        groups = {}
        for hit in chosen:
            if not is_default(hit):
                groups.setdefault((hit.kind if hit.kind in ('normal', 'charged') else hit.title, values(hit)), []).append(hit)
        cells = []
        for (kind, value), members in groups.items():
            # A hit's letter goes when every lettered part of that hit shares the row (3A, 3B -> 3).
            titles = [LETTER.sub('', hit.title) if all(other in members for other in chosen
                                                         if LETTER.sub('', other.title) == LETTER.sub('', hit.title))
                      else hit.title for hit in members]
            if kind == 'normal':
                attack = 'Normal Attack ' + ', '.join(dict.fromkeys(_hit_number(title) for title in titles))
            else:
                attack = ', '.join(dict.fromkeys(titles))
            cells.append(f'{attack} || {" || ".join(value)}')
        return character_rows(name, cells, 'center') if cells else None

    return _apply(text, HITLAG, name, {f'{weapon} Characters': build}, log, update_existing)


def targeting_page(text: str, name: str, data: SimpleNamespace, log: list, update_existing: bool = False) -> str:
    weapon = WEAPONS.get(data.weapon)
    skills = []
    for talent in ('E', 'Q'):
        match = LOCK_SHAPE.fullmatch(data.lock_shapes.get(talent, ''))
        if match:
            skills.append((data.skills[talent][1], match))
    if not weapon or not skills:
        log.append(f'{TARGETING}: nothing to add')
        return text

    def build(lines):
        header = next((line for line in lines if line.startswith('!')), '')
        columns = [cell.strip().lower() for cell in header.lstrip('!').split('!!')][2:]
        cells = []
        for skill_name, match in skills:
            radius, height, highest = match.groups()
            known = {'shape': 'Cylinder', 'radius': number(radius), 'height': number(height) if height else '?',
                     'priority': 'Highest Targeting Score' if highest else '?', 'center': 'Self'}
            row = [next((value for key, value in known.items() if key in column), '&mdash;') for column in columns]
            cells.append(f'{{{{Talent|{skill_name}|20|nobr=1|type=1}}}} || {" || ".join(row)}')
        return character_rows(name, cells, 'center')

    return _apply(text, TARGETING, name, {f'{weapon} Characters': build}, log, update_existing)


def update_pages(name: str, data: SimpleNamespace, texts: dict[str, str], update_existing: bool = False) -> tuple[dict[str, str], list[str]]:
    """({page title: updated wikitext}, log) for changed pages. Existing character rows are kept unless opted in."""
    hits = _hits(data)
    builders = {
        GAUGE: lambda text, log: gauge_page(text, name, data, hits, log, update_existing),
        ICD: lambda text, log: icd_page(text, name, data, hits, log, update_existing),
        AOE: lambda text, log: aoe_page(text, name, hits, log, update_existing),
        HITLAG: lambda text, log: hitlag_page(text, name, data, hits, log, update_existing),
        TARGETING: lambda text, log: targeting_page(text, name, data, log, update_existing),
    }
    pages, log = {}, []
    for title, builder in builders.items():
        if title not in texts:
            log.append(f'{title}: could not fetch the current revision')
            continue
        updated = builder(texts[title], log)
        if updated != texts[title]:
            pages[title] = updated
    return pages, log


def combat_pages(character_id: int, skill_depot: int | None, name: str, fetch=None, *, update_existing: bool = False) -> tuple[dict[str, str], list[str]]:
    """Fetches the current combat data pages and adds the character to them. See update_pages."""
    if fetch is None:
        from wikiVersion import page_texts as fetch
    data = combat_data(character_id, skill_depot)
    return update_pages(name, data, fetch(PAGES), update_existing)
