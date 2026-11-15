"""Runs leo/MiscTools.js to build a character's {{Talent Scaling}} templates."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TALENT_SECTION = re.compile(r'^==([^=\n]+)==\n(\{\{Talent Scaling\n.*?^\}\})', re.MULTILINE | re.DOTALL)
# "(%)" titles are percentages of ATK; "(%Max HP)" titles and "4.4% Max HP + 424" values name their stat.
TITLE_STAT = re.compile(r'\(%([^)]*)\)')
STAT_NAMES = {'': 'ATK', 'EM': 'Elemental Mastery'}
VALUE_STAT = re.compile(r'\d%\s*([A-Za-z][A-Za-z ]*?)\s*(?=[+/,]|$|\bper\b|\bPer\b)')


def scaling_stats(template: str) -> list[str]:
    """Stats the template's rows scale on, in row order, for the infobox's scale_att params."""
    fields = dict(re.findall(r'^\|([^=\n]+)=(.*)$', template, re.MULTILINE))
    stats = []
    for key, title in zip(fields.get('order', '').split(','), fields.get('titles', '').split(',')):
        found = TITLE_STAT.findall(title) + VALUE_STAT.findall(fields.get(f'{key}_1', ''))
        stats += [STAT_NAMES.get(stat.strip(), stat.strip()) for stat in found]
    # The stat most rows scale on comes first, as it's the one the skill mainly scales on.
    stats = [stat for stat in stats if stat != 'Current HP']
    return sorted(dict.fromkeys(stats), key=lambda stat: -stats.count(stat))


def talent_scaling(character_id: int, normal_attack: int = 11, elemental_skill: int = 13,
                   elemental_burst: int = 13) -> list[tuple[int, str, str]]:
    """Returns (skill id, talent name, template) for each leveled talent, in the script's table order."""
    if shutil.which('node') is None:
        raise FileNotFoundError('Node.js is required for Attribute Scaling. Install it and make sure "node" is on PATH.')
    from getConfig import CONFIG

    def table(name: str) -> list[dict]:
        return json.loads((Path(CONFIG.EXCEL_PATH) / f'{name}.json').read_text(encoding='utf-8'))

    avatar = next((item for item in table('AvatarExcelConfigData') if item.get('Id') == character_id), None)
    if avatar is None:
        raise ValueError(f'Character {character_id} is not in the dataset.')
    # The script matches characters by name and has no output for element-switching characters, so it would
    # return the Traveler's discarded test avatars instead.
    if avatar.get('CandSkillDepotIds'):
        raise ValueError('Characters with selectable elements, such as the Traveler, are not supported.')
    # The script assigns levels by table position: depot skills (Normal Attack, Skill, then e.g. an alternate sprint)
    # followed by the Burst, skipping skills without level data.
    depot = next((item for item in table('AvatarSkillDepotExcelConfigData') if item.get('Id') == avatar.get('SkillDepotId')), {})
    skills = {item['Id']: item.get('ProudSkillGroupId') for item in table('AvatarSkillExcelConfigData') if 'Id' in item}
    leveled = {item.get('ProudSkillGroupId') for item in table('ProudSkillExcelConfigData')}
    ids = [skill for skill in depot.get('Skills', []) if skill > 0] + [depot.get('EnergySkill')]
    ids = [skill for skill in ids if skill in skills and skills[skill] in leveled]
    if not ids:
        raise ValueError(f'Character {character_id} has no talents with level data.')
    levels = [elemental_burst if skill == depot.get('EnergySkill')
              else normal_attack if index == 0 else elemental_skill
              for index, skill in enumerate(ids)]
    with tempfile.TemporaryDirectory() as output:
        result = subprocess.run(
            ['node', 'MiscTools.js', 'abilities', '-charId', str(character_id), '-wt',
             '-l', ';'.join(map(str, levels)), '-o', output],
            cwd=ROOT / 'leo', capture_output=True, text=True, encoding='utf-8', errors='replace',
        )
        print(result.stdout + result.stderr, end='', flush=True)
        if result.returncode:
            raise RuntimeError(f'The scaling tool exited with code {result.returncode}. Open the log for details.')
        produced = Path(output) / f'abilities_{character_id}.txt'
        text = produced.read_text(encoding='utf-8') if produced.is_file() else ''
    talents = TALENT_SECTION.findall(text)
    if not talents:
        raise RuntimeError('No talent scaling was produced for this character. '
                           'Characters with selectable elements, such as the Traveler, are not supported.')
    if len(talents) != len(ids):
        raise RuntimeError(f'Expected {len(ids)} talent scaling tables but the scaling tool produced {len(talents)}.')
    return [(skill, name, template) for skill, (name, template) in zip(ids, talents)]
