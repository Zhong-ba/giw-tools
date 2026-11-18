"""Read-only coverage audit of every canonical formal avatar and selectable skill depot."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

from particleGeneration import _numeric, _walk, particle_generation
from particlePages import EMPTY_CONDITIONS, REVIEWED, REVIEWED_DEPOTS, _amount, skill_particles


def _blockers(report: dict, output: dict) -> tuple[list[str], list[str]]:
    if output['status'] == 'supported':
        return [], []
    events = report['events']
    if not events:
        return ['no_generation_not_proven_zero'], []
    blockers, candidates = set(), []
    if report['character_id'] in REVIEWED or (report['character_id'], report.get('skill_depot')) in REVIEWED_DEPOTS:
        blockers.add('reviewed_pattern_changed')
    for event in events:
        if event['expected_particles'] is None:
            blockers.add('unresolved_quantity')
        if event.get('talent_additions'):
            blockers.add('talent_activation')
        if any('Multiple definitions' in warning for warning in event['warnings']):
            blockers.add('duplicate_definitions')
        if event['conditions'] != EMPTY_CONDITIONS:
            blockers.add('conditional_generation')
        triggers = event['triggers']
        if not triggers:
            blockers.add('trigger_reachability')
        if len(triggers) > 1:
            blockers.add('multiple_trigger_paths')
        for _, node, _ in _walk(triggers):
            if node.get('cycle') or node.get('truncated'):
                blockers.add('trigger_reachability')
            if 'caller_modifier' in node:
                if node['caller_modifier'] and not node['callers']:
                    blockers.add('trigger_reachability')
                if node.get('caller_gate', {}).get('duration') is not None:
                    blockers.add('effective_cooldown')
                if any(branch != 'successActions' for branch in node['conditions']['branches']):
                    blockers.add('conditional_trigger')
            if node.get('$type') == 'ByTargetGlobalValue' and node.get('key') != '_ANIMAL_ENTITY_TYPE':
                blockers.add('conditional_trigger')
            if node.get('$type', '').startswith('By') and node['$type'] not in (
                    'ByAttackTags', 'ByEntityTypes', 'ByTargetGlobalValue', 'ByAttackType'):
                blockers.add('conditional_trigger')
        raw_duration = event.get('modifier_gate', {}).get('duration')
        duration = _numeric(raw_duration)
        if raw_duration is not None and (duration is None or duration > 1):
            blockers.add('effective_cooldown')
        if any((action.get('born') or {}).get('$type') == 'ConfigBornByGlobalValue' for action in event['actions']):
            blockers.add('spawn_resolution')
        try:
            _amount([event])
        except ValueError:
            blockers.add('outcome_distribution')
    if len(events) == 1:
        candidates.append('single_generation_event')
    elif all(event['conditions'] == EMPTY_CONDITIONS for event in events):
        if len({(event['file'], event['ability']) for event in events}) == 1:
            try:
                if all(len(event['triggers']) == 1 for event in events):
                    _amount(events)
                    candidates.append('co_trigger_components')
            except ValueError:
                blockers.add('multiple_generation_sources')
        if not candidates:
            blockers.add('multiple_generation_sources')
    blockers.add('unreviewed_skill_semantics')
    priority = (
        'reviewed_pattern_changed', 'unresolved_quantity', 'duplicate_definitions', 'talent_activation',
        'trigger_reachability', 'conditional_generation', 'conditional_trigger', 'multiple_trigger_paths',
        'multiple_generation_sources', 'outcome_distribution', 'effective_cooldown', 'spawn_resolution',
        'unreviewed_skill_semantics',
    )
    return [code for code in priority if code in blockers], candidates


def audit_coverage(avatars=None, depots=None, analyze=None) -> dict:
    """Audit the configured roster, retaining failures and raw evidence rather than counting them as coverage.

    Candidate patterns are research groupings, not permission to generate wiki output.
    """
    from getConfig import CONFIG

    excel = Path(CONFIG.EXCEL_PATH)
    if avatars is None:
        avatars = json.loads((excel / 'AvatarExcelConfigData.json').read_text(encoding='utf-8-sig'))
    if depots is None:
        depots = json.loads((excel / 'AvatarSkillDepotExcelConfigData.json').read_text(encoding='utf-8-sig'))
    if not isinstance(avatars, list) or not isinstance(depots, list):
        raise ValueError('Avatar and skill-depot tables must contain lists.')
    analyze = analyze or particle_generation
    depot_rows = {row['Id']: row for row in depots}
    variants, excluded = [], []
    roster = []
    for avatar in avatars:
        identifier, name = avatar.get('Id'), avatar.get('NameTextMapHash')
        reason = None
        if avatar.get('UseType') != 'AVATAR_FORMAL':
            reason = 'not_formal'
        elif avatar.get('FeatureTagGroupID', identifier) != identifier:
            reason = 'trial_or_template_variant'
        elif not isinstance(identifier, int) or not isinstance(name, str) or not name:
            reason = 'invalid_identity'
        if reason:
            excluded.append({'character_id': identifier, 'character': name, 'reason': reason})
        else:
            roster.append(avatar)
    for avatar in sorted(roster, key=lambda row: (row['NameTextMapHash'].casefold(), row['Id'])):
        choices = avatar.get('CandSkillDepotIds') or [avatar.get('SkillDepotId')]
        for depot_id in dict.fromkeys(choices):
            row = {'character_id': avatar['Id'], 'character': avatar['NameTextMapHash'], 'skill_depot': depot_id}
            depot = depot_rows.get(depot_id)
            if depot is None:
                row.update(status='error', reason='Skill depot is missing from the dataset.',
                           blockers=['missing_skill_depot'], pattern_candidates=[])
            elif len(depot.get('Skills') or []) < 2 or not depot['Skills'][0] or not depot['Skills'][1] or not depot.get('EnergySkill'):
                row.update(status='incomplete_depot', reason='No complete Normal Attack, Skill and Burst.',
                           blockers=['incomplete_skill_depot'], pattern_candidates=[])
            else:
                try:
                    report = analyze(avatar['Id'], depot_id)
                    output = skill_particles(report)
                    blockers, candidates = _blockers(report, output)
                    row.update(status=output['status'], reason=output['reason'], blockers=blockers,
                               pattern_candidates=candidates, output=output, evidence=report)
                except (OSError, ValueError) as error:
                    row.update(status='error', reason=str(error), error_type=type(error).__name__,
                               blockers=['extraction_error'], pattern_candidates=[])
            variants.append(row)
    statuses = Counter(row['status'] for row in variants)
    primary = Counter(row['blockers'][0] for row in variants if row['blockers'])
    blockers = Counter(code for row in variants for code in row['blockers'])
    candidates = Counter(code for row in variants for code in row['pattern_candidates'])
    return {
        'status': 'complete_with_errors' if statuses['error'] else 'complete',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'dataset': {'excel': str(excel), 'bin_output': str(CONFIG.BIN_PATH)},
        'scope': 'Canonical AVATAR_FORMAL records, including unreleased avatars and every listed candidate depot. '
                 'Names and Traveler genders are not merged. Incomplete depots and extraction errors stay in the report.',
        'summary': {'avatar_records': len(avatars), 'avatars_audited': len(roster), 'variants': len(variants),
                    'supported': statuses['supported'], 'review_required': statuses['review_required'],
                    'incomplete_depot': statuses['incomplete_depot'], 'error': statuses['error']},
        'primary_blockers': dict(primary.most_common()),
        'blocker_counts': dict(blockers.most_common()),
        'pattern_candidates': dict(candidates.most_common()),
        'variants': variants, 'excluded': excluded,
    }
