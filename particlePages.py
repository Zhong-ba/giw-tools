"""Conservative Skill notes and Energy/Data rows from reviewed particle event patterns."""
from dataclasses import dataclass
import math

from advancedProperties import number
from combatPages import insert_rows
import toolLog as report
from particleGeneration import particle_distribution
from travelerKits import TRAVELER_IDS


ENERGY = 'Energy/Data'
EMPTY_CONDITIONS = {'predicates': [], 'branches': []}


@dataclass(frozen=True)
class Source:
    ability: str
    modifier: str
    duration: float | None = 0.3
    state: tuple[str, int] | None = None
    trigger_state: tuple[str, str] | None = None
    hit_event: str = 'onAttackLanded'
    hit_target: tuple[str, bool] = ('Target', False)
    apply_target: str | None = None
    unique_handler: bool = False
    particle_target: str | None = None
    born: str = 'ConfigBornByTarget'
    position_key: str | None = None
    attack_type: str = 'Range'
    root_action: str = 'AttachModifier'
    excluded_hit_tag: str | None = None


@dataclass(frozen=True)
class Skill:
    element: str
    spawn: str
    layout: str
    cases: tuple[tuple[Source, ...], ...]
    hit: str = ''
    trigger: str = ''
    cooldown: float | None = None
    hits: tuple[int, int] | None = None


# Only semantics are reviewed here; particle quantities always come from the dataset.
# Other characters and changed event structures remain review-only, even when their numbers look plausible.
REVIEWED = {
    10000003: Skill('Anemo', 'Character', 'both', ((
        Source('Avatar_Qin_VortexSmash', 'Ball'),
        Source('Avatar_Qin_VortexSmash', 'Ball_Extra', 1),
    ),)),
    10000002: Skill('Cryo', 'Character', 'press', ((
        Source('Avatar_Ayaka_Icespine_Strike_New', 'DropBall_Base', root_action='ApplyModifier'),
    ),)),
    10000016: Skill('Pyro', 'Character', 'press', ((
        Source('Avatar_Diluc_Fire_Blade', 'Ball'),
        Source('Avatar_Diluc_Fire_Blade', 'Ball_Extra'),
    ),), trigger='On Hit'),
    10000022: Skill('Anemo', 'Enemy', 'press_hold', (
        (Source('Venti_WindBlade_FX_Land', 'WindBladeLand_ElementBall_Base', None),),
        (Source('Venti_WindBlade_FX', 'WindBladeElementBall_Base', None),),
    )),
    10000032: Skill('Pyro', 'Character', 'press_hold', (
        (Source('Avatar_Bennett_ElementalArt_Handler', 'Ball1',
                trigger_state=('_ABILITY_Bennett_ElementalArt_Level', 'NoneOrEqual'), unique_handler=True),),
        (Source('Avatar_Bennett_ElementalArt_Handler', 'Ball2', 1.5,
                trigger_state=('_ABILITY_Bennett_ElementalArt_Level', 'MoreThan'), unique_handler=True),),
    )),
    10000039: Skill('Cryo', 'Enemy', 'both', ((
        Source('Avatar_Diona_ElementalArt_Bullet_Material', 'Ball', 1, apply_target='OriginOwner',
               born='ConfigBornByGlobalValue', position_key='_ABILITY_Diona_GenerateElemBall_CustomPos'),
    ),), hit='an Icy Paw', trigger='Per Icy Paw', hits=(2, 5)),
    10000036: Skill('Cryo', 'Character', 'press', ((
        Source('Avatar_Chongyun_ElementalArt_Damage', 'Ball_Base', 0.2,
               attack_type='Melee', root_action='ApplyModifier'),
    ),)),
    10000047: Skill('Anemo', 'Character', 'press_hold', (
        (Source('Avatar_Kazuha_ElementalArt_Check', 'Avatar_Kazuha_ElementalArt_DropBall', 0.2,
                state=('_ABILITY_Kazuha_ElementalArt_ClickOrHold_Mark', 1), born='ConfigBornBySelf'),),
        (Source('Avatar_Kazuha_ElementalArt_Check', 'Avatar_Kazuha_ElementalArt_DropBall', 0.2,
                state=('_ABILITY_Kazuha_ElementalArt_ClickOrHold_Mark', 2), born='ConfigBornBySelf'),),
    )),
    10000073: Skill('Dendro', 'Character', 'both', ((
        Source('Avatar_Nahida_ElementalArt', 'Avatar_Nahida_ElementalArt_DropBall', 7,
               hit_event='onHittingOther', hit_target=('Target', True), particle_target='CurLocalAvatar'),
    ),), hit='Tri-Karma Purification', trigger='On Tri-Karma Purification', cooldown=7),
    10000050: Skill('Pyro', 'Character', 'press', ((
        Source('Avatar_Tohma_ElementalArt_Strike', 'Ball', hit_event='onHittingOther',
               hit_target=('Other', False), unique_handler=True),
        Source('Avatar_Tohma_ElementalArt_Strike', 'Ball_Extra', hit_event='onHittingOther',
               hit_target=('Other', False), unique_handler=True),
    ),)),
    10000055: Skill('Geo', 'Character', 'press', ((
        Source('Avatar_Gorou_ElementalArt_SkillHoldCharge', 'Gorou_ElementalArt_BloomElemBall', 0.2,
               born='ConfigBornBySelf'),
    ),)),
    10000057: Skill('Geo', 'Character', 'press', ((
        Source('Avatar_Itto_ElementalArt', 'Avatar_Itto_ElementalArt_DropBall', 0.2,
               hit_event='onHittingOther', born='ConfigBornBySelf'),
    ),)),
    10000069: Skill('Dendro', 'Character', 'press', ((
        Source('Avatar_Tighnari_ElementalArt', 'Ball', hit_target=('Target', True), born='ConfigBornBySelf'),
    ),)),
    10000081: Skill('Dendro', 'Character', 'press', ((
        Source('Avatar_Kaveh_ElementalArt', 'Avatar_Kaveh_ElementalArt_ElementalBall', 0.2,
               hit_event='onHittingOther', hit_target=('Other', False)),
    ),)),
    10000087: Skill('Hydro', 'Character', 'press', ((
        Source('Avatar_Neuvillette_ElementalArt', 'Avatar_Neuvillette_ElementalArt_DropBall',
               hit_event='onHittingOther', hit_target=('Other', False), born='ConfigBornBySelf'),
    ),), trigger='On Skill DMG'),
    10000091: Skill('Geo', 'Character', 'both', ((
        Source('Avatar_Navia_ElementalArt', 'Navia_Rock_ElemBall', 0.2,
               hit_target=('Target', True), unique_handler=True),
    ),), hit='Rosula Shardshot', trigger='On Rosula Shardshot'),
}

TRAVELER_SKILLS = {
    503: Skill('Hydro', 'Character', 'both', ((
        Source('Avatar_PlayerBoy_ElementalArt_Water_ElemBall', 'PlayerBoy_Water_Elemball_Drop',
               hit_event='onHittingOther', unique_handler=True, born='ConfigBornBySelf', attack_type='Default'),
    ),), hit='Torrent Surge', trigger='On Torrent Surge'),
    505: Skill('Cryo', 'Character', 'press', ((
        Source('Avatar_Player_ElementalArt_Ice', 'Player_Ice_ElementalArt_ElemBall_Initial',
               hit_target=('Target', True), unique_handler=True, root_action='ApplyModifier',
               excluded_hit_tag='Player_Ice_Icicle'),
    ),)),
    508: Skill('Dendro', 'Character', 'press', ((
        Source('Avatar_PlayerBoy_ElementalArt_Grass', 'PlayerBoy_Grass_ElemBall',
               unique_handler=True, root_action='ApplyModifier'),
    ),)),
}
REVIEWED_DEPOTS = {(character, depot + (200 if character == 10000007 else 0)): rule
                   for character in TRAVELER_IDS for depot, rule in TRAVELER_SKILLS.items()}


def _conditions(source: Source) -> dict:
    if source.state is None:
        return EMPTY_CONDITIONS
    key, value = source.state
    return {'predicates': [{'$type': 'GenerateElemBall', 'predicates': [
        {'$type': 'ByTargetGlobalValue', 'target': 'Target', 'key': key, 'value': value},
    ]}], 'branches': []}


def _validate_hit(conditions: dict, source: Source) -> None:
    wrappers = conditions.get('predicates', [])
    branches = ['successActions', 'failActions'] if source.excluded_hit_tag else ['successActions']
    if conditions.get('branches') != branches or len(wrappers) != (2 if source.trigger_state or source.excluded_hit_tag else 1):
        raise ValueError('Hit-trigger branches differ from the reviewed pattern.')
    wrapper = wrappers[0]
    if (wrapper.get('$type') != 'Predicated' or wrapper.get('target') != source.hit_target[0]
            or wrapper.get('value', -1) != -1 or wrapper.get('setTarget', False) != source.hit_target[1]
            or set(wrapper) - {'$type', 'target', 'value', 'setTarget', 'doOffStage', 'targetPredicates'}):
        raise ValueError('Hit-trigger predicate wrapper is not reviewed.')
    required = {'ByAttackTags', 'ByEntityTypes', '_ANIMAL_ENTITY_TYPE'}
    if source.trigger_state:
        key, comparison = source.trigger_state
        if wrappers[1] != {'$type': 'ApplyModifier', 'predicates': [
                {'$type': 'ByTargetGlobalValue', 'target': 'Target', 'key': key, 'compareType': comparison}]}:
            raise ValueError('Press/hold state restriction differs from the reviewed pattern.')
    if source.excluded_hit_tag and wrappers[1] != {
            '$type': 'Predicated', 'doOffStage': True, 'target': 'Target', 'value': -1, 'setTarget': True,
            'targetPredicates': [{'$type': 'ByAttackTags', 'attackTags': [source.excluded_hit_tag], 'target': 'Target'}]}:
        raise ValueError('Excluded hit type differs from the reviewed pattern.')
    found = set()
    for predicate in wrapper.get('targetPredicates', []):
        kind = predicate.get('$type')
        if predicate.get('target') != 'Target':
            raise ValueError('Hit-trigger predicate target is not reviewed.')
        if kind == 'ByAttackTags' and predicate == {
                '$type': kind, 'target': 'Target', 'attackTags': ['Elemental_Art']}:
            found.add(kind)
        elif kind == 'ByEntityTypes' and predicate == {
                '$type': kind, 'target': 'Target', 'entityTypes': ['Monster'], 'isAuthority': -1}:
            found.add(kind)
        elif kind == 'ByAttackType' and predicate == {
                '$type': kind, 'target': 'Target', 'attackType': source.attack_type}:
            continue
        elif kind == 'ByTargetGlobalValue':
            key = predicate.get('key')
            comparison = 'NoneOrEqual' if key == '_ANIMAL_ENTITY_TYPE' else None
            expected = {'$type': kind, 'target': 'Target', 'key': key, 'compareType': comparison}
            if comparison is None or predicate != expected:
                raise ValueError('Hit-trigger state restriction is not reviewed.')
            found.add(key)
        else:
            raise ValueError(f'Hit-trigger predicate {kind} is not reviewed.')
    if found != required:
        raise ValueError('A reviewed hit-trigger restriction is missing.')


def _validate_source(event: dict, source: Source) -> None:
    if event['warnings'] or event.get('talent_additions'):
        raise ValueError('Generation has warnings or a talent-added ability with unresolved activation.')
    if event['event'] != 'onAdded' or event['conditions'] != _conditions(source):
        raise ValueError('Generation event or state restrictions differ from the reviewed pattern.')
    expected_gate = {'stacking': 'Unique'}
    if source.duration is not None:
        expected_gate['duration'] = source.duration
    gate = {key: float(number(value)) if key == 'duration' else value
            for key, value in event['modifier_gate'].items()}
    if gate != expected_gate:
        raise ValueError('Generation modifier gate differs from the reviewed pattern.')
    triggers = event['triggers']
    if len(triggers) != 1:
        raise ValueError('Generation does not have one reviewed local hit trigger.')
    trigger = triggers[0]
    if (trigger.get('event') != source.hit_event
            or trigger.get('action') not in ('ApplyModifier', 'AttachModifier')
            or trigger.get('target') != source.apply_target
            or trigger.get('caller_gate') != ({'stacking': 'Unique'} if source.unique_handler else {})):
        raise ValueError('Generation trigger differs from the reviewed hit pattern.')
    if any(action.get('target') != source.particle_target
           or (action.get('born') or {}).get('$type') != source.born
           or (action.get('born') or {}).get('positionKey') != source.position_key for action in event['actions']):
        raise ValueError('Particle spawn configuration differs from the reviewed pattern.')
    _validate_hit(trigger['conditions'], source)
    roots = trigger['callers']
    if len(roots) != 1:
        raise ValueError('Generation handler activation is not reviewed.')
    root = roots[0]
    if (root.get('caller_modifier') != '' or root.get('event') != 'onAdded'
            or root.get('action') != source.root_action or root.get('target') is not None
            or root.get('conditions') != EMPTY_CONDITIONS or root.get('caller_gate') != {}
            or root.get('callers') != []):
        raise ValueError('Generation handler is not unconditionally attached by the reviewed ability.')


def _amount(events: list[dict]) -> float:
    if len(events) > 1:
        callers = [{key: value for key, value in event['triggers'][0].items() if key != 'path'} for event in events]
        if any(caller != callers[0] for caller in callers[1:]):
            raise ValueError('Particle components do not share the same triggering action list.')
    for event in events:
        if event['expected_particles'] is None:
            raise ValueError('Particle quantity is unresolved.')
    distribution = particle_distribution(events)
    amount = float(number(sum(count * probability for count, probability in distribution.items())))
    if amount <= 0 or not math.isclose(amount, sum(event['expected_particles'] for event in events), abs_tol=1e-6):
        raise ValueError('No supported positive particle quantity; zero generation is not inferred.')
    return amount


def skill_particles(report: dict) -> dict:
    """Render only reviewed, completely matched event sets; otherwise return an explicit review status."""
    character_id = report['character_id']
    depot_rule = REVIEWED_DEPOTS.get((character_id, report.get('skill_depot')))
    rule = depot_rule or REVIEWED.get(character_id)
    if rule is None:
        reason = ('No recognized generation; this does not prove zero particles.' if not report['events'] else
                  'This character has no reviewed particle-to-Skill mapping.')
        return {'status': 'review_required', 'reason': reason, 'notes': '', 'energy_cells': None}
    try:
        if depot_rule is None and report['skill_depot'] != (character_id - 10000000) * 100 + 1:
            raise ValueError('This skill depot is not reviewed.')
        events = report['events']
        used, amounts = set(), []
        for case in rule.cases:
            selected = []
            for source in case:
                matches = [(index, event) for index, event in enumerate(events)
                           if event['ability'] == source.ability and event['modifier'] == source.modifier
                           and event['conditions'] == _conditions(source)]
                if len(matches) != 1 or matches[0][0] in used:
                    raise ValueError(f'Missing or ambiguous generation source: {source.ability}/{source.modifier}.')
                index, event = matches[0]
                _validate_source(event, source)
                if event['element'] != rule.element:
                    raise ValueError('Generated element differs from the reviewed Skill.')
                used.add(index)
                selected.append(event)
            amounts.append(_amount(selected))
        if len(used) != len(events):
            raise ValueError('Additional generation branches need review; existing wiki rows are preserved.')
    except ValueError as error:
        return {'status': 'review_required', 'reason': str(error), 'notes': '', 'energy_cells': None}

    values = [number(amount) for amount in amounts]
    arguments = f'{rule.hit}|{values[0]}' if rule.hit else '|'.join(values)
    notes = f'* {{{{Talent Note|particles|{arguments}}}}}\n'
    if rule.cooldown is not None:
        notes += f"** Particles can be generated once every '''{number(rule.cooldown)}'''s.\n"
    if rule.hits:
        press, hold = (number(amounts[0] * hits) for hits in rule.hits)
        notes += f"** Average totals with all paws hitting: '''{press}''' on press and '''{hold}''' on hold.\n"
    qualifiers = [rule.trigger] if rule.trigger else []
    if rule.cooldown is not None:
        qualifiers.append(f'{number(rule.cooldown)}s CD')
    suffix = f' <small>({"; ".join(qualifiers)})</small>' if qualifiers else ''
    if rule.layout == 'both':
        particles = f'colspan="2" | {values[0]}{suffix}'
    elif rule.layout == 'press_hold':
        particles = f'{values[0]} || {values[1]}'
    else:
        particles = f'{values[0]}{suffix} || &mdash;'
    return {
        'status': 'supported', 'reason': 'All generation events match a reviewed Skill pattern.',
        'notes': notes, 'amounts': amounts,
        'energy_cells': f'{particles} || {{{{{rule.element}}}}} || {rule.spawn}',
    }


def energy_pages(name: str, output: dict, fetch=None, *, update_existing: bool = False) -> tuple[dict[str, str], list[str]]:
    """Update only the selected character's Skill row in the current Energy/Data revision."""
    if output['status'] != 'supported':
        report.info(f'{ENERGY}: skipped; {output["reason"]}')
        return {}, [f'{ENERGY}: skipped; {output["reason"]}']
    if fetch is None:
        from wikiVersion import page_texts as fetch
    report.stage('Fetching current Energy data page')
    texts = fetch([ENERGY])
    if ENERGY not in texts:
        report.warning(f'{ENERGY}: could not fetch the current revision')
        return {}, [f'{ENERGY}: could not fetch the current revision']
    row = f'| {{{{Character|{name}|20|nobr=1}}}}\n| {output["energy_cells"]}'
    # Energy/Data keeps Traveler variants before the alphabetical character list.
    def order(character):
        return (not character.startswith('Traveler ('), character.casefold())

    updated, outcome = insert_rows(texts[ENERGY], 'Elemental Skills', name, lambda _: [row],
                                   update_existing, sort_key=order)
    pages = {ENERGY: updated} if updated != texts[ENERGY] else {}
    if not pages and outcome.startswith('updated '):
        outcome = 'unchanged'
    report.info(f'{ENERGY} > Elemental Skills: {outcome}')
    return pages, [f'{ENERGY} > Elemental Skills: {outcome}']
