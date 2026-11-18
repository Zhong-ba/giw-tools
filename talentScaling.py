"""Runs leo/MiscTools.js to build a character's {{Talent Scaling}} templates."""
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import toolLog as report

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
                   elemental_burst: int = 13, *, skill_depot: int | None = None) -> list[tuple[int, str, str]]:
    """Returns (skill id, talent name, template) for each leveled talent, in the script's table order."""
    if shutil.which('node') is None:
        raise FileNotFoundError('Node.js is required for Attribute Scaling. Install it and make sure "node" is on PATH.')
    from getConfig import CONFIG
    report.stage(f'Loading scaling data for character {character_id}')

    def table(name: str) -> list[dict]:
        return json.loads((Path(CONFIG.EXCEL_PATH) / f'{name}.json').read_text(encoding='utf-8'))

    avatar = next((item for item in table('AvatarExcelConfigData') if item.get('Id') == character_id), None)
    if avatar is None:
        raise ValueError(f'Character {character_id} is not in the dataset.')
    if avatar.get('CandSkillDepotIds') and skill_depot is None:
        raise ValueError('Choose a skill depot for characters with selectable elements, such as the Traveler.')
    # The script assigns levels by table position: depot skills (Normal Attack, Skill, then e.g. an alternate sprint)
    # followed by the Burst, skipping skills without level data.
    from travelerKits import select_depots
    skill_table = table('AvatarSkillExcelConfigData')
    depot = select_depots(avatar, table('AvatarSkillDepotExcelConfigData'), skill_table, skill_depot)[0]
    skills = {item['Id']: item.get('ProudSkillGroupId') for item in skill_table if 'Id' in item}
    leveled = {item.get('ProudSkillGroupId') for item in table('ProudSkillExcelConfigData')}
    ids = [skill for skill in depot.get('Skills', []) if skill > 0] + [depot.get('EnergySkill')]
    ids = [skill for skill in ids if skill in skills and skills[skill] in leveled]
    if not ids:
        raise ValueError(f'Character {character_id} has no talents with level data.')
    levels = [elemental_burst if skill == depot.get('EnergySkill')
              else normal_attack if index == 0 else elemental_skill
              for index, skill in enumerate(ids)]
    with tempfile.TemporaryDirectory() as output:
        depot_args = ['-skillDepot', str(skill_depot)] if skill_depot is not None else []
        report.stage(f'Generating scaling tables at levels {"/".join(map(str, levels))}')
        with subprocess.Popen(
            ['node', 'MiscTools.js', 'abilities', '-charId', str(character_id), '-wt',
             '-l', ';'.join(map(str, levels)), '-o', output, *depot_args],
            cwd=ROOT / 'leo', stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
        ) as process:
            if process.stdout is None:
                raise RuntimeError('The scaling tool did not provide an output stream.')
            for line in process.stdout:
                report.info(line.rstrip())
            code = process.wait()
        if code:
            raise RuntimeError(f'The scaling tool exited with code {code}. Open the log for details.')
        produced = Path(output) / f'abilities_{character_id}.txt'
        text = produced.read_text(encoding='utf-8') if produced.is_file() else ''
    talents = TALENT_SECTION.findall(text)
    if not talents:
        raise RuntimeError('No talent scaling was produced for this character and skill depot.')
    if len(talents) != len(ids):
        raise RuntimeError(f'Expected {len(ids)} talent scaling tables but the scaling tool produced {len(talents)}.')
    report.info(f'Generated {len(talents)} talent scaling tables.')
    return [(skill, name, template) for skill, (name, template) in zip(ids, talents)]
