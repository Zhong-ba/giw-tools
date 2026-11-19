"""Extract reviewable enemy AI tables from supported ConfigMonster layouts."""

import hashlib
import json
import math
import re
import sys
from pathlib import Path

import toolLog as report


LABELS = {
    (24010101, '201', 'Smash'): 'Punch and Jump Combo',
    (25080101, '301', 'RushAtk'): 'Iai: Thrust',
    (20060501, '201', 'ElectricBullet'): 'Thunderstrike',
    (20060501, '301', 'FlyHor'): 'Blitz Bump',
}
NON_COMBAT = {'OnAlert', 'OnNerve', 'None'}
UNKNOWN = '?'
NA = None
RESULT_FILE = 'Enemy AI Logic.json'
EDITS_FILE = 'Enemy AI Edits.json'
COLUMNS = ('Range Req. (m)', 'Angle Req. (°)', 'Priority', 'CD (s)', 'Shared CD (s)',
           'Global CD Group', 'Global CD (s)', 'Action Interval (s)')
ATTACK_ELEMENTS = {'Fire': 'Pyro', 'Water': 'Hydro', 'Wind': 'Anemo', 'Electric': 'Electro',
                   'Grass': 'Dendro', 'Ice': 'Cryo', 'Rock': 'Geo',
                   'None': 'Physical', 'Physical': 'Physical'}


def _read(path):
    with path.open(encoding='utf-8-sig') as file:
        return json.load(file)


def _number(value):
    if type(value) in (float, int) and math.isfinite(value) and value >= 0:
        return value
    return None


def _value(value):
    return UNKNOWN if value is None else f'{value:.10g}'


def _span(low, high):
    if low is None or high is None or high < low:
        return UNKNOWN
    return _value(low) if low == high else f'{_value(low)}–{_value(high)}'


def _cell(value):
    return ''.join({'&': '&amp;', '<': '&lt;', '>': '&gt;', '|': '&#124;',
                    '[': '&#91;', ']': '&#93;', '{': '&#123;', '}': '&#125;',
                    "'": '&#39;', '~': '&#126;', '–': '&ndash;', '°': '&deg;',
                    '\r': ' ', '\n': ' '}.get(char, char) for char in value)


def snapshot(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def validate_edits(text):
    data = json.loads(text)
    if not isinstance(data, dict) or set(data) != {'names', 'removed'}:
        raise ValueError('Invalid Enemy AI edits.')
    names, removed = data['names'], data['removed']
    if (not isinstance(names, dict) or not isinstance(removed, list)
            or any(not isinstance(key, str) or not re.fullmatch(r'[0-9]+:[0-9]+', key)
                   for key in [*names, *removed])
            or any(not isinstance(name, str) or len(name) > 200 for name in names.values())):
        raise ValueError('Invalid Enemy AI edits.')


def _skill_values(skill):
    # Prepared Gura retains these raw keys. Its remapped `cd` and `castCondition`
    # are not the base cooldown and selection gate used by the wiki tables.
    gate = skill.get('PBKCKJFILBL')
    if not isinstance(gate, dict) or 'MAGBAFADLAM' not in gate:
        return None
    maximum = _number(gate.get('JHDKBGNBIFI'))
    minimum = _number(gate.get('NGHGGFANFMO', 0))
    angle = gate.get('JHJBNCLANGO')
    cooldown = _number(skill.get('CIAJDMHGJFG'))
    spread = _number(skill.get('cdUpperRange', 0))
    return (
        _span(minimum, maximum),
        NA if angle == -1 else _span(0, _number(angle)),
        _value(_number(skill.get('priority'))),
        _span(cooldown, cooldown + spread) if cooldown is not None and spread is not None else UNKNOWN,
    )


def _local_groups(ai):
    groups = {}
    configs = ai.get('skillGroupCDConfigs')
    if isinstance(configs, list):
        for config in configs:
            if isinstance(config, dict) and type(config.get('skillGroupCDID')) is int:
                groups[config['skillGroupCDID']] = _number(config.get('skillGroupCDTime'))
    return groups


def _global_groups(root):
    path = root / 'Common' / 'ConfigGlobalCombat.json'
    try:
        data = _read(path)
    except (OSError, ValueError) as error:
        return {}, f'{path.name}: {error}'
    settings = data.get('DNAKKNAKBDC') if isinstance(data, dict) else None
    groups = settings.get('HNDPLEPIEND') if isinstance(settings, dict) else None
    if not isinstance(groups, dict):
        return {}, f'{path.name}: unsupported global cooldown layout.'
    return {key: _number(entry.get('minInterval')) for key, entry in groups.items()
            if isinstance(entry, dict)}, None


def extract_rows(monster_id, data, global_groups):
    ai = data.get('aibeta') if isinstance(data, dict) else None
    skills = ai.get('skills') if isinstance(ai, dict) else None
    if not isinstance(skills, dict) or not skills:
        return None, ['No readable aibeta.skills table.']

    warnings = []
    rows = []
    locals_ = _local_groups(ai)
    interval = _value(_number(ai.get('skillGCD')))
    if interval == UNKNOWN:
        warnings.append('Action interval is missing or unresolved; not assumed to be zero.')
    omitted = []
    has_supported_row = False
    for skill_id, skill in skills.items():
        if not skill_id.isascii() or not skill_id.isdecimal() or not isinstance(skill, dict):
            warnings.append(f'Skill {skill_id}: malformed record; omitted.')
            continue
        skill_type = skill.get('skillType')
        if isinstance(skill_type, str) and skill_type in NON_COMBAT:
            omitted.append(skill_id)
            continue
        values = _skill_values(skill)
        if values is None:
            values = (UNKNOWN,) * 4
            warnings.append(f'Skill {skill_id}: unsupported selection or cooldown fields.')
        else:
            has_supported_row = True
            for label, value in zip(('range', 'angle', 'priority', 'cooldown'), values):
                if value == UNKNOWN:
                    warnings.append(f'Skill {skill_id}: {label} could not be decoded.')

        internal_name = skill.get('name')
        internal_name = internal_name if isinstance(internal_name, str) else ''
        name = LABELS.get((monster_id, skill_id, internal_name), internal_name or 'Unnamed skill')
        local_id = skill.get('skillGroupCDID')
        shared = NA
        if type(local_id) is int and local_id >= 0:
            shared = _value(locals_.get(local_id))
            if shared == UNKNOWN:
                warnings.append(f'Skill {skill_id}: local cooldown group {local_id} is unresolved.')
        elif local_id != -1 and ai.get('skillGroupCDConfigs'):
            shared = UNKNOWN
            warnings.append(f'Skill {skill_id}: local cooldown group is missing or unresolved.')

        global_id = skill.get('publicCDGroup')
        global_name = global_cd = NA
        if isinstance(global_id, str) and global_id:
            global_name = global_id
            global_cd = _value(global_groups.get(global_id))
            if global_cd == UNKNOWN:
                warnings.append(f'Skill {skill_id}: global cooldown group {global_id} is unresolved.')
        states = skill.get('stateIDs')
        rows.append({'id': skill_id, 'name': name, 'internal': internal_name,
                     'states': [state for state in states if isinstance(state, str)] if isinstance(states, list) else [],
                     'cells': [*values, shared, global_name, global_cd, interval]})

    if omitted:
        warnings.append(f'Excluded non-combat records: {", ".join(omitted)}.')
    if not has_supported_row:
        return None, ['No skills with a supported selection layout.', *warnings]
    return rows, warnings


def draft(monster_id, data, global_groups):
    rows, warnings = extract_rows(monster_id, data, global_groups)
    return (render_wikitext(rows) if rows else None), warnings


def render_wikitext(rows):
    lines = [
        '===AI Logic===',
        '<!-- Review draft: ? means unresolved. Check internal labels, conditions, and row selection. -->',
        '{| class="wikitable"',
        '! ' + ' !! '.join(map(_cell, ('Ability', *COLUMNS))),
    ]
    for row in rows:
        cells = [row['name'], *row['cells']]
        lines.extend(('|-', '| ' + ' || '.join('&mdash;' if cell is None else _cell(cell) for cell in cells)))
    return '\n'.join([*lines, '|}', ''])


def write_ai_drafts(output: Path, bin_root: Path, enemy_ids: list[int], *, structured=False,
                    repo_root: Path | None = None) -> int:
    monster_dir = bin_root / 'Monster'
    if not monster_dir.is_dir():
        raise FileNotFoundError(f'Monster config folder not found: {monster_dir}')

    output.mkdir(parents=True, exist_ok=True)
    configs: dict[int, list[Path]] = {monster_id: [] for monster_id in enemy_ids}
    for path in sorted(monster_dir.glob('*.json')):
        match = re.search(r'(?:^|_)([0-9]+)$', path.stem)
        if match and (monster_id := int(match[1])) in configs:
            configs[monster_id].append(path)
    global_groups, global_error = _global_groups(bin_root)
    diagnostics = [
        'Enemy AI Logic - review diagnostics',
        'Drafts are excerpts, not full wiki pages. Review labels, skill selection and runtime behavior.',
        'Initial cooldown, phase/state requirements, and interval trigger/ignore flags are not generated.',
        'A dash means no decoded requirement/group; ? means unresolved. Compare against the intended game variant.',
    ]
    if global_error:
        diagnostics.append(global_error)
    results = []
    resolve = structured or repo_root is not None
    if resolve:
        from webui.references import _index, gadget_rows
        index, index_warnings = _index(bin_root.resolve(), 'Ability')
        diagnostics.extend(index_warnings)
        gadgets = {}
        gadget_index = {}
        if repo_root is not None:
            try:
                for item in gadget_rows({'RepoPath': str(repo_root)}, diagnostics):
                    name = item.get('JsonName')
                    if isinstance(name, str) and name:
                        gadgets.setdefault(item['Id'], set()).add(name)
            except (OSError, ValueError, KeyError) as error:
                diagnostics.append(f'Could not read gadget IDs: {error}')
            if gadgets:
                gadget_index, gadget_warnings = _index(bin_root.resolve(), 'Gadget', gadget=True)
                diagnostics.extend(gadget_warnings)
    count = 0
    for monster_id, paths in report.track(configs.items(), 'Extracting Enemy AI Logic'):
        source = None
        rows = None
        if not paths:
            warnings = ['No exact ID-specific ConfigMonster file; no name or variant fallback.']
        elif len(paths) > 1:
            warnings = [f'Ambiguous exact ID matches: {", ".join(path.name for path in paths)}.']
        else:
            source = paths[0]
            try:
                text = source.read_text(encoding='utf-8-sig')
                data = json.loads(text)
                rows, warnings = extract_rows(monster_id, data, global_groups)
            except (OSError, ValueError) as error:
                warnings = [f'Could not read config: {error}']
            else:
                if resolve and rows:
                    attach_references(rows, data, bin_root.resolve(), source.resolve(), index, warnings,
                                      gadgets, gadget_index, snapshot(text))
        diagnostics.extend(('', f'{monster_id}' + (f' - Monster/{source.name}' if source else '')))
        diagnostics.extend(warnings or ['No extraction warnings.'])
        if not structured and rows:
            for row in rows:
                for ref in row.get('references', ()):
                    if ref['attackInfo']:
                        records = '; '.join(' · '.join(filter(None, (
                            hit['element'], hit['percent'] or '?', hit.get('condition'),
                        ))) for hit in ref['attacks'])
                        diagnostics.append(f'Skill {row["id"]} [{ref["confidence"]}] '
                                           f'{ref["path"]} / {ref["focus"]}: {records}')
                        diagnostics.extend(f'  {step}' for step in ref.get('evidence', ()))
        if structured:
            results.append({'id': monster_id, 'source': f'Monster/{source.name}' if source else None,
                            'rows': rows or [], 'warnings': warnings})
        if rows:
            if not structured:
                (output / f'{monster_id} - AI Logic.wikitext.txt').write_text(render_wikitext(rows), encoding='utf-8')
            count += 1
        else:
            report.warning(f'Monster {monster_id}: {warnings[0]}')
    (output / 'AI Logic Diagnostics.txt').write_text('\n'.join(diagnostics) + '\n', encoding='utf-8')
    if structured:
        marker = bin_root.parent / '.prepared.json'
        revision = _read(marker) if marker.is_file() else None
        (output / RESULT_FILE).write_text(json.dumps({'columns': COLUMNS, 'monsters': results,
                                                      'revision': revision}, ensure_ascii=False), encoding='utf-8')
        (output / EDITS_FILE).write_text('{"names":{},"removed":[]}\n', encoding='utf-8')
    return count


def _object(value):
    return value if isinstance(value, dict) else {}


def _objects(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _attack_summaries(node, condition=None):
    if isinstance(node, list):
        for item in node:
            yield from _attack_summaries(item, condition)
    if not isinstance(node, dict):
        return
    predicates = _objects(node.get('predicates'))
    local = None
    if predicates:
        pred = predicates[0]
        key = pred.get('key')
        if len(predicates) == 1 and pred.get('$type') == 'ByTargetGlobalValue' and isinstance(key, str):
            if pred.get('compareType') == 'NoneOrEqual' and 'value' not in pred:
                local = f'{key}: NoneOrEqual'
            elif pred.get('compareType') in (None, 'Equal') and type(pred.get('value')) in (int, float):
                local = f'{key} = {pred["value"]}'
        local = local or 'Conditional'
    active = ' / '.join(filter(None, (condition, local))) or None
    if info := _object(node.get('attackInfo')):
        prop = _object(info.get('attackProperty'))
        element = prop.get('elementType')
        multiplier = prop.get('damagePercentage')
        percent = (multiplier * 100.0 if type(multiplier) in (float, int)
                   and abs(multiplier) < sys.float_info.max / 100 else None)
        yield {'element': ATTACK_ELEMENTS.get(element, element) if isinstance(element, str) and element else 'Physical',
               'percent': f'{percent:.7g}%' if percent is not None else None,
               **({'condition': active} if active else {})}
    for key, child in node.items():
        if key not in ('attackInfo', 'predicates'):
            inherited = (' / '.join(filter(None, (condition, 'If condition fails')))
                         if key == 'failActions' and local else active)
            yield from _attack_summaries(child, inherited)


def attach_references(rows, data, root, source, index, warnings, gadgets, gadget_index, source_digest):
    from webui.references import _definitions, _gadget_targets

    slots = {}
    for item in _objects(data.get('abilities')):
        name, slot = item.get('abilityName'), item.get('abilityID')
        if isinstance(name, str) and name:
            slots.setdefault(name, set()).update([slot] if isinstance(slot, str) and slot else [])
    events = _object(_object(data.get('combat')).get('animEvents'))
    attack_events = {name for name, event in events.items() if any(_attack_summaries(event))}
    digests = {source: source_digest}
    documents = {}
    definitions = {}

    def document(path):
        if path not in documents:
            text = path.read_text(encoding='utf-8-sig')
            documents[path] = json.loads(text)
            digests[path] = snapshot(text)
        return documents[path]

    def ability_at(path, name):
        if path not in definitions:
            entries = {}
            for label, body in _definitions(document(path)):
                entries[label] = None if label in entries else body
            definitions[path] = entries
        return definitions[path].get(name)

    # Named modifier maps can retain scrambled container keys in prepared BinOutput.
    def modifier_at(body, name):
        entries = [(key, value[name]) for key, value in body.items()
                   if isinstance(value, dict) and isinstance(value.get(name), dict)]
        return entries[0] if len(entries) == 1 else (None, None)

    confidence_order = {'direct': 0, 'traced': 1, 'candidate': 2}

    def add(refs, path, kind, focus, confidence, node, evidence=(), pointer=None, section=None):
        if not path.resolve().is_relative_to(root):
            return
        attacks = list(_attack_summaries(node))
        key = path, focus, tuple(pointer or ()), tuple(section or ())
        prev = refs.get(key)
        if prev is not None and confidence_order[prev['confidence']] <= confidence_order[confidence]:
            if prev['confidence'] == confidence:
                prev['evidence'] = list(dict.fromkeys([*prev.get('evidence', ()), *evidence]))
            return
        refs[key] = {'path': path.relative_to(root).as_posix(), 'snapshot': digests[path],
                     'kind': kind, 'focus': focus, 'confidence': confidence, 'attackInfo': bool(attacks),
                     **({'evidence': list(evidence)} if evidence else {}),
                     **({'attacks': attacks} if attacks else {}),
                     **({'pointer': pointer} if pointer else {}),
                     **({'section': section} if section else {})}

    def spawned(refs, actions, confidence, evidence, warn):
        spawns = {}
        for i, action in enumerate(actions if isinstance(actions, list) else ()):
            action = _object(action)
            kind = action.get('$type')
            field = 'bulletID' if kind == 'TriggerBullet' else 'gadgetID' if kind == 'CreateGadget' else None
            if field and type(gadget_id := action.get(field)) is int and gadget_id > 0:
                spawns.setdefault(gadget_id, []).append(f'{action["$type"]}[{i}].{field}')
        for gadget_id, actions in spawns.items():
            names = gadgets.get(gadget_id, ())
            if len(names) != 1:
                warn(f'No unique Gadget Excel name for spawned object {gadget_id}.')
                continue
            name, = names
            targets = _gadget_targets(root, gadget_index, name)
            if len(targets) != 1:
                warn(f'No unique Gadget config for {name} ({gadget_id}).')
                continue
            path, entry = next(iter(targets.items()))
            if not path.resolve().is_relative_to(root):
                warn(f'Gadget config for {name} is outside BinOutput.')
                continue
            gadget = _object(document(path))
            if entry is not None:
                gadget = _object(gadget.get(entry))
            chain = (*evidence, f'{len(actions)} configured spawn action(s): {", ".join(actions)} '
                     f'→ Gadget Excel {gadget_id}: {name} → {path.name}')
            event_path = ([entry] if entry is not None else []) + ['combat', 'animEvents']
            gadget_events = _object(gadget.get('combat')).get('animEvents')
            if any(_attack_summaries(gadget_events)):
                add(refs, path, 'Spawned gadget events', name, confidence, gadget_events, chain, event_path)
            for item in _objects(gadget.get('abilities')):
                ability = item.get('abilityName')
                if not isinstance(ability, str):
                    continue
                paths = index.get(ability, ())
                if len(paths) != 1 or (body := ability_at(next(iter(paths)), ability)) is None:
                    warn(f'No unique Ability definition for {name} → {ability}.')
                    continue
                if any(_attack_summaries(body)):
                    add(refs, next(iter(paths)), 'Spawned gadget ability', ability, confidence, body,
                        (*chain, f'Gadget abilities → {ability}'))

    for row in rows:
        states = set(row['states'])
        identifiers = {row['internal'], *states} - {''}
        registered_name_pattern = re.compile(
            r'(?:^|_)(?:' + '|'.join(re.escape(name) for name in sorted(identifiers)) + r')\d*(?:_|$)',
            re.IGNORECASE,
        ) if identifiers else None
        refs = {}

        def warn(text):
            message = f'Skill {row["id"]}: {text}'
            if message not in warnings:
                warnings.append(message)

        event_links = {state: f'AI state {state} → combat.animEvents.{state}' for state in states if state in events}
        state_names = {state: f'AI state {state}' for state in sorted(states)}
        for layer, config in _object(data.get('stateLayers')).items():
            for state in sorted(states):
                animators = _object(_object(_object(_object(config).get('stateIDs')).get(state)).get('animatorStates'))
                for animator in animators:
                    state_names.setdefault(animator, f'AI state {state} → {layer}.animatorStates.{animator}')
                for animator in animators.keys() & events.keys():
                    event_links.setdefault(animator, f'AI state {state} → {layer}.animatorStates.{animator} '
                                                    f'→ combat.animEvents.{animator}')
        for event, evidence in sorted(event_links.items()):
            add(refs, source, 'Monster animation event', event, 'direct', events[event], (evidence,),
                ['combat', 'animEvents', event])
        for state, evidence in state_names.items():
            if state.endswith('_Attack'):
                base = state.removesuffix('_Attack')
                aliases = (base, f'{base}_Boost')
            elif state in ('Stamp', 'Swipe', 'Whirl'):
                aliases = (f'{state}Atk',)
            else:
                continue
            for event in aliases:
                if event in attack_events and event not in event_links:
                    add(refs, source, 'Monster animation event candidate', event, 'candidate', events[event],
                        (f'{evidence} → combat.animEvents.{event} (name match; animation invocation not verified).',),
                        ['combat', 'animEvents', event])

        for ability, ids in slots.items():
            exact = ability in identifiers or bool(ids & identifiers)
            related = exact or any(slot.startswith(name + '_') for slot in ids for name in identifiers) or (
                registered_name_pattern is not None and registered_name_pattern.search(ability) is not None)
            paths = sorted(index.get(ability, ()))
            if not paths and exact:
                warn(f'No Ability JSON definition for {ability}.')
            if len(paths) != 1 and not related:
                continue
            for path in paths:
                try:
                    body = ability_at(path, ability)
                    if body is None:
                        if related:
                            warn(f'Ambiguous or missing definition {ability} in {path.name}.')
                        continue
                    if related:
                        kind = 'Ability ID match' if exact and len(paths) == 1 else 'Related Ability candidate'
                        chain = (f'{kind}: {ability}; animation invocation not verified.',)
                        add(refs, path, kind, ability, 'candidate', body, chain)
                        if len(paths) == 1:
                            spawned(refs, body.get('onAbilityStart'), 'candidate', chain, warn)
                    if len(paths) != 1:
                        continue
                    for mixin in _objects(body.get('abilityMixins')):
                        if mixin.get('$type') != 'AttachToStateIDMixin':
                            continue
                        mixin_states = mixin.get('stateIDs')
                        matched = [state for state in sorted(states)
                                   if isinstance(mixin_states, list) and state in mixin_states]
                        name = mixin.get('modifierName')
                        if not matched or not isinstance(name, str):
                            continue
                        container, modifier = modifier_at(body, name)
                        if modifier is None:
                            warn(f'No unique local modifier {name} in {ability}.')
                            continue
                        chain = (f'AI state {", ".join(matched)} → {ability}.abilityMixins (AttachToStateIDMixin) '
                                 f'→ {container}.{name}.onAdded',)
                        if any(_attack_summaries(modifier.get('onAdded'))):
                            add(refs, path, 'State-bound modifier', ability, 'traced', modifier.get('onAdded'), chain,
                                section=[container, name, 'onAdded'])
                        spawned(refs, modifier.get('onAdded'), 'traced', chain, warn)
                except (OSError, ValueError) as error:
                    warn(f'Could not inspect {path.name}: {error}')
        if not any(ref['confidence'] != 'candidate' or ref['kind'] == 'Ability ID match' for ref in refs.values()):
            add(refs, source, 'Monster skill record', f'aibeta.skills.{row["id"]}', 'direct', None,
                pointer=['aibeta', 'skills', row['id']])
        if not any(ref['attackInfo'] and ref.get('pointer', [])[:2] == ['combat', 'animEvents']
                   and ref['path'] == source.relative_to(root).as_posix() for ref in refs.values()):
            add(refs, source, 'Monster source file', source.name, 'direct', None)
        row['references'] = sorted(refs.values(), key=lambda ref: (
            not ref['attackInfo'], confidence_order[ref['confidence']],
            ref['kind'] == 'Related Ability candidate',
        ))
