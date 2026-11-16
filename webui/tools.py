from dataclasses import dataclass
from pathlib import Path
import re
import runpy
import sys
from typing import Annotated, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, field_validator

from dataSource import ROOT


# Image asset features (icon generation) need an up-to-date texture extraction; set to True once one is available.
IMAGE_ASSETS = False
IMAGE_FIELDS = ('element', 'generate_icons')

LANGUAGES = ('CHS', 'CHT', 'DE', 'EN', 'ES', 'FR', 'ID', 'JP', 'KR', 'PT', 'RU', 'TH', 'VI', 'TR', 'IT')


class Inputs(BaseModel):
    model_config = ConfigDict(extra='forbid')


class LanguageInputs(Inputs):
    text: str = Field(min_length=1, max_length=20000, title='Text to look up',
                      description='An exact name or phrase from the selected language TextMap.')
    input_lang: Literal['CHS', 'CHT', 'DE', 'EN', 'ES', 'FR', 'ID', 'JP', 'KR', 'PT', 'RU', 'TH', 'VI', 'TR', 'IT'] = Field(default='EN', title='Input language')
    translation: bool = Field(default=True, title='Include translation fields')
    romanization: bool = Field(default=True, title='Include romanization fields')

    @field_validator('text')
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Enter text to look up.')
        return value


class RedirectInputs(Inputs):
    lines: str = Field(min_length=1, max_length=50000, title='Redirects',
                       description='One source%%%target pair per line. Blank lines are ignored.')

    @field_validator('lines')
    @classmethod
    def valid_lines(cls, value: str) -> str:
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        if not lines or len(lines) > 500:
            raise ValueError('Enter between 1 and 500 redirects.')
        for index, line in enumerate(lines, 1):
            parts = line.split('%%%')
            if len(parts) != 2 or not all(part.strip() for part in parts):
                raise ValueError(f'Line {index} must contain source%%%target.')
            if not re.sub(r'[^\w\s]', '', parts[0]).strip():
                raise ValueError(f'Line {index} needs a source with letters or numbers.')
        return '\n'.join(lines)


def _hide_image_fields(schema: dict) -> None:
    if not IMAGE_ASSETS:
        for field in IMAGE_FIELDS:
            schema.get('properties', {}).pop(field, None)


class CharacterInputs(Inputs):
    model_config = ConfigDict(extra='forbid', json_schema_extra=_hide_image_fields)

    character_id: int = Field(ge=1, le=999999999, title='Character')
    version: str = Field(min_length=1, max_length=32, title='Introduced in version', description='Used in the generated Change History templates.')
    element: Literal['Pyro', 'Hydro', 'Anemo', 'Electro', 'Dendro', 'Cryo', 'Geo'] = Field(default='Pyro', title='Icon background element')
    generate_icons: bool = Field(default=False, title='Generate talent and constellation icons',
                                 description='Requires local extracted textures and talent backgrounds.')
    natlan: bool = Field(default=False, title='Nightsoul')
    nodkrai: bool = Field(default=False, title='Moonsign')
    hexerei: bool = Field(default=False, title="Hexerei")
    stellar: bool = Field(default=False, title='Stellar')
    traveler: bool = Field(default=False, title='Traveler')
    skill_depot: int | None = Field(default=None, ge=1, title='Skill depot override',
                                   description='Optional advanced override, including Traveler variants.')
    attribute_scaling: bool = Field(default=True, title='Include Attribute Scaling',
                                    description='Fills the talent pages\' Attribute Scaling sections. Requires Node.js.')
    advanced_properties: bool = Field(default=True, title='Include Advanced Properties',
                                      description='Fills the Advanced Properties of the talent pages, and of the passive '
                                                  'and constellation pages that deal damage, from the attack data. '
                                                  'Review titles and remove attacks the wiki does not list.')
    data_pages: bool = Field(default=True, title='Update Combat Data Pages',
                             description='Adds the character to the current revisions of the Elemental Gauge, Internal '
                                         'Cooldown, Area of Effect, Hitlag and Targeting data pages. Requires Advanced '
                                         'Properties; review the generated rows before posting.')
    update_existing: bool = Field(default=False, title='Update Existing Entries',
                                 description="Replaces this character's existing combat data rows. Requires Update Combat "
                                             'Data Pages; review carefully because wiki edits and notes may be replaced.')
    normal_attack: int = Field(default=11, ge=1, le=15, title='Normal Attack')
    elemental_skill: int = Field(default=13, ge=1, le=15, title='Elemental Skill')
    elemental_burst: int = Field(default=13, ge=1, le=15, title='Elemental Burst')

    @field_validator('generate_icons')
    @classmethod
    def icons_available(cls, value: bool) -> bool:
        if value and not IMAGE_ASSETS:
            raise ValueError('Icon generation is disabled until an updated texture extraction is available.')
        return value


class ScalingInputs(Inputs):
    character_id: int = Field(ge=1, le=999999999, title='Character')
    normal_attack: int = Field(default=11, ge=1, le=15, title='Normal Attack')
    elemental_skill: int = Field(default=13, ge=1, le=15, title='Elemental Skill')
    elemental_burst: int = Field(default=13, ge=1, le=15, title='Elemental Burst')


class EnemyInputs(Inputs):
    enemy_ids: list[int] = Field(min_length=1, max_length=2000, title='Enemies',
                                 description='Each selected enemy gets a page (one per name) and a row in the stat tables.')
    version: str = Field(min_length=1, max_length=32, title='Introduced in version',
                         description='Used in the generated Change History templates.')


class FishingInputs(Inputs):
    pool_ids: list[int] = Field(min_length=1, max_length=2000, title='Fishing Point',
                                description='Generate Fishing Point pages.')


class BountyInputs(Inputs):
    bounty_ids: list[int] = Field(min_length=1, max_length=2000, title='Bounties',
                                  description='Player\'s Choice bounties, grouped by region as on Bounty/List.')


class CookingInputs(Inputs):
    images: Literal['none', 'missing', 'all'] = Field(
        default='none', title='Dial images',
        description='Also draw the dial images: none, only those missing from the English wiki, or every combination in use.')


StartDate = Annotated[str, StringConstraints(pattern=r'^\d{4}-\d{2}-\d{2}$')]


class AbyssInputs(Inputs):
    starts: list[StartDate] = Field(default_factory=list, max_length=200, title='Rotations',
                                    description='Each selected rotation gets a page, titled by its start date. '
                                                'None selected means the newest rotation in the data.',
                                    json_schema_extra={'periods': 'abyss'})
    version: str = Field(default='', max_length=32, title='Start version',
                         description='The header\'s startVersion. When empty, each page uses the version live at its '
                                     'start, per the wiki\'s Date to Version.')


class StygianInputs(Inputs):
    starts: list[StartDate] = Field(default_factory=list, max_length=50, title='Events',
                                    description='Each selected event gets a page, titled by its start date. '
                                                'None selected means the newest event in the data.',
                                    json_schema_extra={'periods': 'stygian'})
    version: str = Field(default='', max_length=32, title='Version',
                         description='The event\'s version and Change History. When empty, each page uses the version '
                                     'live at its start, per the wiki\'s Date to Version.')


class TheaterInputs(Inputs):
    starts: list[StartDate] = Field(default_factory=list, max_length=100, title='Seasons',
                                    description='Each selected season gets a page, titled by its start date. '
                                                'None selected means the newest season in the data.',
                                    json_schema_extra={'periods': 'theater'})
    version: str = Field(default='', max_length=32, title='Start version',
                         description='The header\'s startVersion. When empty, each page uses the version live at its '
                                     'start, per the wiki\'s Date to Version.')


def other_languages(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = LanguageInputs.model_validate(parameters)
    import OLGen

    # In the resident worker this loads the TextMaps only on first use in the session.
    OLGen.load_data()
    result = OLGen.gen_ol(inputs.text, inputs.input_lang, inputs.translation, inputs.romanization)
    if result == 'Not found.':
        raise ValueError(f'Text was not found in the {inputs.input_lang} TextMap. Use an exact match.')
    (output / 'Other Languages.wikitext').write_text(result, encoding='utf-8')


def redirects(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = RedirectInputs.model_validate(parameters)
    from utils.redirect import main_redirect

    for line in inputs.lines.splitlines():
        source, target = line.split('%%%')
        main_redirect(source.strip(), target.strip())


def character_kit(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = CharacterInputs.model_validate(parameters)
    from getConfig import CONFIG

    if inputs.generate_icons:
        for name, directory in (('textures', CONFIG.IMAGE_PATH), ('talent backgrounds', CONFIG.TALENT_BG_PATH)):
            if not directory:
                raise FileNotFoundError(f'No {name} directory is configured, so icons cannot be generated.')
            if not Path(directory).is_dir():
                raise FileNotFoundError(f'Configured {name} directory does not exist: {directory}')
    arguments = [
        str(ROOT / 'parseCharKit.py'), '--id', str(inputs.character_id),
        '--ver', inputs.version, '--elem', inputs.element, '--nodetect', 'True',
    ]
    for option in ('natlan', 'nodkrai', 'hexerei', 'stellar'):
        if getattr(inputs, option):
            arguments.extend([f'--{option}', 'True'])
    if inputs.generate_icons:
        arguments.extend(['--files', 'True'])
    if inputs.traveler:
        arguments.extend(['--traveler', '1'])
    if inputs.skill_depot is not None:
        arguments.extend(['--skilldepot', str(inputs.skill_depot)])
    if inputs.attribute_scaling:
        arguments.extend(['--levels', str(inputs.normal_attack), str(inputs.elemental_skill), str(inputs.elemental_burst)])
    else:
        arguments.extend(['--noscaling', 'True'])
    if not inputs.advanced_properties:
        arguments.extend(['--noap', 'True'])
    if not inputs.data_pages:
        arguments.extend(['--nodatapages', 'True'])
    elif inputs.update_existing:
        arguments.append('--updateexisting')
    sys.argv = arguments
    runpy.run_path(str(ROOT / 'parseCharKit.py'), run_name='__main__')

    pages = [path for path in output.rglob('*.wikitext') if 'Redirects' not in path.relative_to(output).parts]
    if not pages:
        raise RuntimeError('The character tool did not produce any pages.')
    if inputs.generate_icons:
        images = {path.name for path in output.rglob('*.png')}
        for page in pages:
            if page.name == 'NA.wikitext' and page.parent.name == 'Skills':
                continue
            match = re.search(r'^\|image\s*=\s*(.+?\.png)\s*$', page.read_text(encoding='utf-8'), re.MULTILINE)
            if match:
                filename = match.group(1).replace(':', '').replace('"', '').replace('?', '')
                if filename not in images:
                    raise RuntimeError(f'Icon generation failed for {filename}. See the job log for missing assets.')


def attribute_scaling(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = ScalingInputs.model_validate(parameters)
    from talentScaling import talent_scaling

    talents = talent_scaling(inputs.character_id, inputs.normal_attack, inputs.elemental_skill, inputs.elemental_burst)
    for number, (_, name, template) in enumerate(talents, 1):
        filename = f'{number} - {UNSAFE_FILENAME.sub("", name).strip()}.wikitext'
        (output / filename).write_text(template + '\n', encoding='utf-8')

UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def enemy(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = EnemyInputs.model_validate(parameters)
    from types import SimpleNamespace
    import OLGen
    from utils.enemies import parse_enemies

    OLGen.load_data()
    count = parse_enemies(SimpleNamespace(ver=inputs.version), OLGen.gen_ol, inputs.enemy_ids, icons=IMAGE_ASSETS,
                          stats_file='Enemy Stats.wikitext')
    print(f'Generated {count} enemy page{"" if count == 1 else "s"}.', flush=True)


def fishing_points(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = FishingInputs.model_validate(parameters)
    from utils.fishing import write_fishing_points

    count = write_fishing_points(inputs.pool_ids, str(output))
    print(f'Generated {count} fishing point page{"" if count == 1 else "s"}.', flush=True)


def bounties(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = BountyInputs.model_validate(parameters)
    from utils.hunting import bounties_wikitext

    (output / 'Bounties.wikitext').write_text(bounties_wikitext(inputs.bounty_ids) + '\n', encoding='utf-8')


def fish_weights(output: Path, parameters: dict[str, JsonValue]) -> None:
    Inputs.model_validate(parameters)
    from utils.fishing import write_fish_weights

    count = write_fish_weights(str(output))
    print(f'Wrote spawn weights for {count} fish.', flush=True)


def character_data(output: Path, parameters: dict[str, JsonValue]) -> None:
    Inputs.model_validate(parameters)
    from utils.charasc import write_character_data

    characters, talents = write_character_data(str(output))
    print(f'Wrote ascension data for {characters} characters and talent materials for {talents} entries.', flush=True)


def manual_cooking(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = CookingInputs.model_validate(parameters)
    from utils.cooking import cooking_qte_2, parse_cooking_qte

    parse_cooking_qte()
    if inputs.images != 'none':
        drawn = cooking_qte_2(only_missing=inputs.images == 'missing')
        print(f'Drew {len(drawn)} dial image{"" if len(drawn) == 1 else "s"}.', flush=True)


def spiral_abyss(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = AbyssInputs.model_validate(parameters)
    from utils.abyss import write_abyss_page

    for start in dict.fromkeys(inputs.starts) or [None]:
        write_abyss_page(start, inputs.version.strip(), str(output))


def stygian_onslaught(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = StygianInputs.model_validate(parameters)
    import OLGen
    from utils.stygian import write_stygian_page

    OLGen.load_data()
    for start in dict.fromkeys(inputs.starts) or [None]:
        write_stygian_page(start, inputs.version.strip(), str(output))


def imaginarium_theater(output: Path, parameters: dict[str, JsonValue]) -> None:
    inputs = TheaterInputs.model_validate(parameters)
    from utils.theater import write_theater_page

    for start in dict.fromkeys(inputs.starts) or [None]:
        write_theater_page(start, inputs.version.strip(), str(output))


@dataclass(frozen=True)
class Tool:
    id: str
    name: str
    category: str
    description: str
    model: type[Inputs]
    execute: Callable[[Path, dict[str, JsonValue]], None]
    requires_dataset: bool = True


TOOLS = {
    tool.id: tool for tool in (
        Tool('other-languages', 'Other Languages', 'Localization',
             'Generate an Other Languages template based on the current data source.',
             LanguageInputs, other_languages),
        Tool('character-kit', 'Character Kit', 'Characters',
             'Generate talent, passive, and constellation pages'
             + (', with optional icons.' if IMAGE_ASSETS else '.'),
             CharacterInputs, character_kit),
        Tool('attribute-scaling', 'Attribute Scaling', 'Characters',
             'Generate the Talent Scaling tables for a character\'s Attribute Scaling sections.',
             ScalingInputs, attribute_scaling),
        Tool('character-data', 'Character Data', 'Characters',
             'Generate Module:Character Ascensions and Stats/data and Module:Talent Upgrade/data for every character.',
             Inputs, character_data),
        Tool('enemy', 'Enemy', 'Enemies',
             'Generate pages and stat tables for any enemies, or those added between two versions.',
             EnemyInputs, enemy),
        Tool('spiral-abyss', 'Spiral Abyss', 'Enemies',
             'Generate a Spiral Abyss/Floors page with Ley Line Disorder and each chamber\'s level, target and enemies.',
             AbyssInputs, spiral_abyss),
        Tool('imaginarium-theater', 'Imaginarium Theater', 'Enemies',
             'Generate an Imaginarium Theater season page with each act\'s battles, stage effects, objectives, levels and enemies.',
             TheaterInputs, imaginarium_theater),
        Tool('stygian-onslaught', 'Stygian Onslaught', 'Enemies',
             'Generate a Stygian Onslaught event page with each difficulty\'s lineup, mechanics, descriptions and rewards.',
             StygianInputs, stygian_onslaught),
        Tool('fishing-points', 'Fishing Point', 'World',
             'Generate Fishing Point pages with their fish, area and limits, for any points or those added between two versions.',
             FishingInputs, fishing_points),
        Tool('fish-weights', 'Fish Weights', 'World',
             'Generate Module:Fishing Point Fish List/data with the spawn weight of every fish at fishing points.',
             Inputs, fish_weights),
        Tool('manual-cooking', 'Manual Cooking Data', 'World',
             'Generate Module:Manual Cooking/data and, optionally, the dial images it links to.',
             CookingInputs, manual_cooking),
        Tool('bounties', 'Bounties', 'World',
             'Generate Player\'s Choice bounty entries for the Bounty/List page.',
             BountyInputs, bounties),
        Tool('redirects', 'Redirect Builder', 'Utilities',
             'Create a batch of wiki redirect pages from simple source and target pairs.',
             RedirectInputs, redirects, requires_dataset=False),
    )
}
