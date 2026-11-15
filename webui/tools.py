from dataclasses import dataclass
from pathlib import Path
import re
import runpy
import sys
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from dataSource import ROOT


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


class CharacterInputs(Inputs):
    character_id: int = Field(ge=1, le=999999999, title='Character')
    version: str = Field(min_length=1, max_length=32, title='Introduced in version', description='Used in the generated Change History templates.')
    element: Literal['Pyro', 'Hydro', 'Anemo', 'Electro', 'Dendro', 'Cryo', 'Geo'] = Field(default='Pyro', title='Icon background element')
    generate_icons: bool = Field(default=False, title='Generate talent and constellation icons',
                                 description='Requires local extracted textures and talent backgrounds.')
    natlan: bool = Field(default=False, title='Night Realm mechanics')
    nodkrai: bool = Field(default=False, title='Moonsign mechanics')
    hexerei: bool = Field(default=False, title="Witch's Eve Rite mechanics")
    stellar: bool = Field(default=False, title='Stellar passive')
    traveler: bool = Field(default=False, title='Traveler')
    skill_depot: int | None = Field(default=None, ge=1, title='Skill depot override',
                                   description='Optional advanced override, including Traveler variants.')


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
            if not Path(directory).is_dir():
                raise FileNotFoundError(f'Configured {name} directory does not exist: {directory}')
    arguments = [
        str(ROOT / 'parseCharKit.py'), '--id', str(inputs.character_id),
        '--ver', inputs.version, '--elem', inputs.element,
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
             'Turn a name or phrase into a ready-to-copy multilingual wiki template.',
             LanguageInputs, other_languages),
        Tool('character-kit', 'Character Kit', 'Characters',
             'Generate talent, passive, and constellation pages, with optional icons.',
             CharacterInputs, character_kit),
        Tool('redirects', 'Redirect Builder', 'Utilities',
             'Create a batch of wiki redirect pages from simple source and target pairs.',
             RedirectInputs, redirects, requires_dataset=False),
    )
}
