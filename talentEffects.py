"""Finds which Normal Attack/Skill/Burst pages list each passive and constellation under Passive/Constellation Effects.

A talent affects a skill when its description links or names the skill, uses a term that only that skill's description
links or bolds, or when its ConfigTalent entry raises the skill's level, changes its CD/charges, or modifies an ability
that only that skill's level-up config touches. Checked against the wiki's Talent Notes: ~92% precision, ~89% recall.
"""
import collections
import json
import re
from pathlib import Path

LINKED_SKILL = re.compile(r'\{LINK#S(\d+)\}')
LINKED_TERM = re.compile(r'\{LINK#N\d+\}(.*?)\{/LINK\}')
BOLD_TERM = re.compile(r"'''(.+?)'''")
MIN_TERM_LENGTH = 4


def _terms(description: str) -> set[str]:
    terms = {term.strip() for term in LINKED_TERM.findall(description) + BOLD_TERM.findall(description)}
    return {term for term in terms if len(term) >= MIN_TERM_LENGTH}


def _plain(description: str) -> str:
    return re.sub(r'\{/?LINK[^}]*\}', '', description)


def load_talent_configs(talent_dir: Path, open_configs: set[str], name: str = '') -> dict:
    """Reads ConfigTalent_*.json until every wanted config is found, starting with ConfigTalent_<name>."""
    files = sorted(talent_dir.glob('ConfigTalent_*.json')) if talent_dir.is_dir() else []
    files.sort(key=lambda path: path.stem.lower() != f'configtalent_{name}'.lower())
    found = {}
    for path in files:
        if open_configs <= found.keys():
            break
        data = json.loads(path.read_text(encoding='utf-8'))
        found.update({key: data[key] for key in open_configs & data.keys()})
    return found


def talent_effects(depot: dict, skill_rows: list, proud_rows: list, talent_rows: list, talent_configs: dict | None = None,
                   passive_count: int = 2) -> tuple[dict, dict]:
    """Returns ({skill id: [[passive name, n]]}, {skill id: [[constellation name, n]]}) with string skill ids, for the
    first passive_count inherent passives (A1, A4) and the six constellations."""
    skills = {row['Id']: row for row in skill_rows if 'Id' in row}
    proud = {(row.get('ProudSkillGroupId'), row.get('Level', 1)): row for row in proud_rows}
    talents = {row.get('TalentId'): row for row in talent_rows}
    skill_ids = [sid for sid in ((depot.get('Skills') or [])[:2] + [depot.get('EnergySkill')]) if sid in skills]
    configs = talent_configs or {}

    # Terms linked or bolded by several skills (shared mechanics like Nightsoul) say nothing about which page to use.
    owners = collections.defaultdict(set)
    for row in skills.values():
        for term in _terms(str(row.get('DescTextMapHash') or '')):
            owners[term].add(row.get('NameTextMapHash'))
    own_terms, groups, abilities = {}, {}, collections.defaultdict(set)
    for sid in skill_ids:
        own_terms[sid] = {term for term in _terms(str(skills[sid].get('DescTextMapHash') or '')) if len(owners[term]) == 1}
        groups[sid] = skills[sid].get('ProudSkillGroupId')
        upgrade = proud.get((groups[sid], 1), {}).get('OpenConfig')
        for entry in configs.get(upgrade) or []:
            if isinstance(entry, dict) and entry.get('abilityName'):
                abilities[entry['abilityName']].add(sid)

    opens = [item['ProudSkillGroupId'] for item in depot.get('InherentProudSkillOpens') or []
             if isinstance(item, dict) and item.get('ProudSkillGroupId')][:passive_count]
    sources = ([proud.get((group, 1)) or {} for group in opens], [talents.get(tid) or {} for tid in depot.get('Talents') or []])
    results = ({}, {})
    for result, rows in zip(results, sources):
        for index, row in enumerate(rows, 1):
            affected = _affected(row, skill_ids, skills, groups, own_terms, abilities, configs)
            for sid in skill_ids:
                if sid in affected:
                    result.setdefault(str(sid), []).append([row.get('NameTextMapHash'), index])
    return results


def _affected(row, skill_ids, skills, groups, own_terms, abilities, configs) -> set[int]:
    description = str(row.get('DescTextMapHash') or '')
    plain = _plain(description)
    affected = {int(sid) for sid in LINKED_SKILL.findall(description)}
    for sid in skill_ids:
        name = skills[sid].get('NameTextMapHash')
        if (isinstance(name, str) and name in plain) or any(term in plain for term in own_terms[sid]):
            affected.add(sid)
    for entry in configs.get(row.get('OpenConfig')) or []:
        if not isinstance(entry, dict):
            continue
        kind = entry.get('$type')
        if kind == 'AddTalentExtraLevel':
            affected |= {sid for sid in skill_ids if isinstance(groups[sid], int) and groups[sid] % 10 == entry.get('talentIndex')}
        elif kind in ('ModifySkillCD', 'ModifySkillPoint'):
            affected.add(entry.get('skillID'))
        elif kind in ('ModifyAbility', 'UnlockTalentParam'):
            owner = abilities.get(entry.get('abilityName'), set())
            if len(owner) == 1:
                affected |= owner
    return affected
