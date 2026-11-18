"""Experimental, read-only particle-generation evidence extraction from character abilities.

Counts are per triggering event, not per cast. Conditions and modifier lifetimes
are evidence, not automatically proven gameplay restrictions or effective cooldowns.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

from advancedProperties import number


PARTICLE_ELEMENTS = {2017: 'Pyro', 2018: 'Hydro', 2019: 'Dendro', 2020: 'Electro',
                     2021: 'Anemo', 2022: 'Cryo', 2023: 'Geo'}
PREDICATE_KEYS = ('predicates', 'targetPredicates', 'predicate', 'predicateType')


def _walk(node, path=(), parents=()):
    if isinstance(node, dict):
        yield path, node, parents
        for key, value in node.items():
            yield from _walk(value, (*path, key), (*parents, node))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, (*path, str(index)), parents)


def _numeric(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(number(value))
    return None


def _resolve(value, specials):
    return _numeric(specials.get(value)) if isinstance(value, str) else _numeric(value)


def _conditions(path, parents):
    conditions = []
    for parent in parents:
        if parent.get('$type') == 'Predicated':
            conditions.append({key: value for key, value in parent.items()
                               if key not in ('successActions', 'failActions', 'failureActions')})
        elif any(parent.get(key) for key in PREDICATE_KEYS):
            conditions.append({key: value for key, value in parent.items()
                               if key in (*PREDICATE_KEYS, '$type', 'target')})
    # Keep branch identity: success and failure do not happen together.
    branches = [part for part in path if part in ('successActions', 'failActions', 'failureActions')]
    return {'predicates': conditions, 'branches': branches}


def _branch(parent, node):
    return next((key for key in ('successActions', 'failActions', 'failureActions')
                 if any(candidate is node for _, candidate, _ in _walk(parent.get(key)))), None)


def _location(path):
    if 'modifiers' in path:
        index = path.index('modifiers')
        return (path[index + 1] if len(path) > index + 1 else '',
                path[index + 2] if len(path) > index + 2 else '')
    return '', path[0] if path else ''


def _ability_records(files):
    records = []
    for file in files:
        data = json.loads(file.read_text(encoding='utf-8-sig'))
        for path, node, _ in _walk(data):
            if isinstance(node.get('abilityName'), str) and '$type' not in node:
                # Gadget references to an ability are not an ability definition.
                if any(key in node for key in ('modifiers', 'abilitySpecials', 'onAdded', 'abilityMixins')):
                    records.append((file, path, node))
    return records


def analyze_files(files: list[Path]) -> dict:
    """Extract conditional per-event generation and reverse modifier references.

    An empty result means no recognized generation was found, not proven zero.
    Unknown expressions or action wrappers make the count unresolved.
    """
    records = _ability_records(files)
    definitions = defaultdict(list)
    for file, path, ability in records:
        definitions[ability['abilityName']].append((file, path, ability))
    events = []
    warnings = [
        'Prototype: counts are conditional per event; skill labels, per-cast totals, effective cooldowns and spawn '
        'locations are not inferred.',
        'File discovery follows character names; shared or indirectly referenced files may be missing.',
        'Ability-default specials are used; talent overrides, ability activation and modifier eligibility are not '
        'fully evaluated. guaranteed_particles is only a lower bound conditional on this event executing.',
    ]
    for file, root, ability in records:
        ability_name = ability['abilityName']
        specials = ability.get('abilitySpecials') or {}
        modifiers = ability.get('modifiers') or {}
        references = defaultdict(list)
        groups = {}
        random_paths = {id(node): path for path, node, _ in _walk(ability) if node.get('$type') == 'Randomed'}
        for path, node, parents in _walk(ability):
            kind = node.get('$type')
            modifier, event = _location(path)
            if kind in ('ApplyModifier', 'AttachModifier') and node.get('modifierName'):
                caller = modifiers.get(modifier, {})
                references[node['modifierName']].append({
                    'caller_modifier': modifier, 'event': event, 'action': kind,
                    'caller_gate': {key: caller[key] for key in ('duration', 'stacking', 'isUnique') if key in caller},
                    'target': node.get('target'), 'conditions': _conditions(path, (*parents, node)),
                    'path': '/'.join(path), 'action_list': '/'.join(path[:-1]),
                })
            if kind != 'GenerateElemBall':
                continue
            issues = []
            element = PARTICLE_ELEMENTS.get(node.get('configID'))
            energy = _resolve(node.get('baseEnergy'), specials)
            ratio = _resolve(node.get('ratio'), specials)
            if element is None:
                issues.append('Unrecognized particle configID; particle/orb conversion is unresolved.')
            if energy is None or energy < 0 or energy % 3:
                issues.append('baseEnergy is not a recognized nonnegative multiple of 3.')
            if ratio is None or ratio < 0:
                issues.append('Missing, negative or unresolved generation ratio.')
            if isinstance(node.get('ratio'), str):
                special = node['ratio']
                if any(other.get('overrideMapKey') == special for _, other, _ in _walk(ability)):
                    issues.append(f'Ratio special {special} is written at runtime.')
            chance = 1.0
            random_path = []
            for parent in parents:
                if parent.get('$type') == 'Randomed':
                    probability = _resolve(parent.get('chance'), specials)
                    if isinstance(parent.get('chance'), str) and any(
                            other.get('overrideMapKey') == parent['chance'] for _, other, _ in _walk(ability)):
                        issues.append('Random probability special is written at runtime.')
                    branch = _branch(parent, node)
                    if probability is None or not 0 <= probability <= 1 or branch is None:
                        issues.append('Unresolved random probability or branch.')
                    else:
                        chance *= probability if branch == 'successActions' else 1 - probability
                        random_path.append({
                            'path': '/'.join((*root, *random_paths[id(parent)])),
                            'probability': probability, 'branch': branch,
                        })
                elif parent.get('$type') not in (None, 'Predicated'):
                    issues.append(f"Unsupported enclosing action {parent['$type']}.")
            conditions = _conditions(path, (*parents, node))
            # Random branches contribute to the same expectation; predicate branches remain separate.
            predicate_branches = []
            for parent in parents:
                if parent.get('$type') == 'Predicated':
                    predicate_branches.append(_branch(parent, node))
            conditions['branches'] = predicate_branches
            key = (modifier, event, element, json.dumps(conditions, sort_keys=True))
            if key not in groups:
                groups[key] = {
                    'file': str(file), 'ability': ability_name, 'modifier': modifier, 'event': event,
                    'element': element, 'conditions': conditions, 'expected_particles': 0.0,
                    'guaranteed_particles': 0.0, 'actions': [], 'warnings': [],
                }
            group = groups[key]
            count = energy / 3 * ratio if not issues else None
            group['actions'].append({
                'path': '/'.join((*root, *path)), 'base_energy': node.get('baseEnergy'),
                'ratio': node.get('ratio'), 'chance': float(number(chance)) if not issues else None,
                'particles_on_success': count, 'born': node.get('born'), 'target': node.get('target'),
                'random_path': random_path, 'warnings': issues,
            })
            if issues:
                group['expected_particles'] = group['guaranteed_particles'] = None
            elif group['expected_particles'] is not None:
                group['expected_particles'] += count * chance
                if chance == 1:
                    group['guaranteed_particles'] += count
            group['warnings'].extend(issues)

        def trace(modifier, seen=()):
            if modifier in seen:
                return [{'modifier': modifier, 'cycle': True}]
            if len(seen) >= 12:
                return [{'modifier': modifier, 'truncated': True}]
            result = []
            for reference in references.get(modifier, []):
                caller = reference['caller_modifier']
                result.append({**reference, 'callers': trace(caller, (*seen, modifier)) if caller else []})
            return result

        for group in groups.values():
            modifier = group['modifier']
            config = modifiers.get(modifier, {})
            group['modifier_gate'] = {key: config[key] for key in ('duration', 'stacking', 'isUnique') if key in config}
            group['triggers'] = trace(modifier) if modifier else []
            if modifier and not group['triggers']:
                group['warnings'].append('No local ApplyModifier/AttachModifier caller found; reachability is unresolved.')
            if len(definitions[ability_name]) > 1:
                group['warnings'].append('Multiple definitions of this ability exist; variants are not merged.')
            for key in ('expected_particles', 'guaranteed_particles'):
                if group[key] is not None:
                    group[key] = float(number(group[key]))
            group['warnings'] = list(dict.fromkeys(group['warnings']))
            events.append(group)
    if not events:
        warnings.append('No recognized GenerateElemBall actions found. This does not establish zero generation.')
    return {'events': events, 'warnings': warnings}


def particle_distribution(events: list[dict]) -> dict[int, float]:
    """Resolve correlated Randomed branches into the adjacent integer outcomes Energy/Data can represent."""
    items, contexts = [], {}
    for event in events:
        for action in event['actions']:
            count, chance = action['particles_on_success'], action['chance']
            if (count is None or chance is None or not math.isfinite(count) or not math.isfinite(chance)
                    or count < 0 or count != int(count) or not 0 <= chance <= 1):
                raise ValueError('Particle outcome distribution is unresolved.')
            decisions, probability, ancestry = [], 1.0, ()
            for decision in action.get('random_path', []):
                value, branch = decision['probability'], decision['branch']
                if not math.isfinite(value) or not 0 <= value <= 1 or branch not in (
                        'successActions', 'failActions', 'failureActions'):
                    raise ValueError('Random branch probability is unresolved.')
                key = (event['file'], event['ability'], decision['path'])
                if key in {parent for parent, _ in ancestry}:
                    raise ValueError('Random branch ancestry contains a cycle.')
                context = (ancestry, value)
                if key in contexts and contexts[key] != context:
                    raise ValueError('Random branch ancestry or probability is inconsistent.')
                contexts[key] = context
                success = branch == 'successActions'
                decisions.append((key, value, success))
                ancestry = (*ancestry, (key, success))
                probability *= value if success else 1 - value
            if not math.isclose(chance, probability, rel_tol=0, abs_tol=1e-6):
                raise ValueError('Random branch provenance is missing or inconsistent.')
            items.append((int(count), decisions))

    def adjacent(outcomes):
        if len(outcomes) > 2 or max(outcomes) - min(outcomes) > 1:
            raise ValueError('Particle outcomes are not a guaranteed integer count plus at most one extra particle.')
        return outcomes

    def outcomes(items):
        base = sum(count for count, path in items if not path)
        groups = {}
        for count, path in items:
            if path:
                key, chance, success = path[0]
                group = groups.setdefault(key, (chance, [], []))
                group[1 if success else 2].append((count, path[1:]))
        distribution = {base: 1.0}
        for chance, success, failure in groups.values():
            choices = defaultdict(float)
            for probability, branch in ((chance, success), (1 - chance, failure)):
                if probability:
                    for count, weight in outcomes(branch).items():
                        choices[count] += probability * weight
            adjacent(choices)
            combined = defaultdict(float)
            for count, weight in distribution.items():
                for extra, probability in choices.items():
                    combined[count + extra] += weight * probability
            distribution = adjacent(combined)
        return dict(distribution)

    return outcomes(items)


def particle_generation(character_id: int, skill_depot: int | None = None) -> dict:
    """Read the selected character's files using the same discovery as Advanced Properties."""
    from advancedProperties import _character

    character = _character(character_id, skill_depot)
    if not character.files:
        raise FileNotFoundError(f'No character BinOutput files found for {character_id}.')
    report = analyze_files(character.files)
    additions = defaultdict(list)
    for file in character.talent_files:
        if file.stem.casefold() not in {f'configtalent_{name}'.casefold() for name in character.names}:
            continue
        data = json.loads(file.read_text(encoding='utf-8-sig'))
        for path, node, _ in _walk(data):
            if node.get('$type') == 'AddAbility':
                additions[node.get('abilityName')].append({'file': str(file), 'open_config': path[0], 'path': '/'.join(path)})
    for event in report['events']:
        event['talent_additions'] = additions.get(event['ability'], [])
        if event['talent_additions']:
            event['warnings'].append('This ability is added by a talent configuration; baseline activation is not assumed.')
    from travelerKits import TRAVELER_IDS, element_for
    name = character.avatar['NameTextMapHash']
    if character_id in TRAVELER_IDS:
        skills = json.loads((character.excel / 'AvatarSkillExcelConfigData.json').read_text(encoding='utf-8'))
        name = f'Traveler ({element_for(character.depot, skills)})'
    return {
        'character_id': character_id, 'character': name,
        'skill_depot': character.depot['Id'], 'files_scanned': len(character.files),
        **report,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--id', type=int, nargs='+', help='Character IDs to inspect.')
    selection.add_argument('--audit', action='store_true', help='Audit coverage of all formal characters and skill depots.')
    parser.add_argument('--skilldepot', type=int, help='Skill depot for a selectable-element character.')
    parser.add_argument('--output', type=Path, help='Save UTF-8 JSON to this file instead of printing it.')
    args = parser.parse_args()
    if args.audit:
        if args.skilldepot is not None:
            parser.error('--skilldepot cannot be combined with --audit; every candidate depot is audited.')
        from particleAudit import audit_coverage
        report = audit_coverage()
        failed = bool(report['summary']['error'])
    else:
        from getConfig import CONFIG
        from travelerKits import TRAVELER_IDS, select_depots
        excel = Path(CONFIG.EXCEL_PATH)
        avatars = json.loads((excel / 'AvatarExcelConfigData.json').read_text(encoding='utf-8'))
        depots = json.loads((excel / 'AvatarSkillDepotExcelConfigData.json').read_text(encoding='utf-8'))
        skills = json.loads((excel / 'AvatarSkillExcelConfigData.json').read_text(encoding='utf-8'))
        report = []
        for character_id in args.id:
            if character_id in TRAVELER_IDS:
                avatar = next((row for row in avatars if row['Id'] == character_id), None)
                if avatar is None:
                    parser.error(f'Character {character_id} is not in the dataset.')
                try:
                    selected = select_depots(avatar, depots, skills, args.skilldepot)
                except ValueError as error:
                    parser.error(str(error))
                report.extend(particle_generation(character_id, depot['Id']) for depot in selected)
            else:
                report.append(particle_generation(character_id, args.skilldepot))
        failed = False
    content = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(content, encoding='utf-8')
    else:
        print(content)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
