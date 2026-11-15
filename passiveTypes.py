"""Detects which special passive (Nightsoul, Moonsign, Hexerei, Stellar) a character's skill depot has."""
import json
from pathlib import Path

TYPES = ('natlan', 'nodkrai', 'hexerei', 'stellar')


def _name(group: int | None, proud_rows: list[dict]) -> str:
    name = next((row.get('NameTextMapHash') for row in proud_rows if group and row.get('ProudSkillGroupId') == group), '')
    return name if isinstance(name, str) else ''


def passive_types(depot: dict, proud_rows: list[dict]) -> list[str]:
    """Night Realm's Gift, Moonsign Benediction and Stellar Jubilee passives sit in the third inherent slot;
    Witch's Eve Rite and other quest-unlocked passives (e.g. Cyno's) are the first special passive."""
    inherent = depot.get('InherentProudSkillOpens') or []
    third = _name(inherent[2].get('ProudSkillGroupId'), proud_rows) if len(inherent) > 2 else ''
    special = next((item['ProudSkillGroupId'] for item in depot.get('SpecialProudSkillOpens') or []
                    if item.get('ProudSkillGroupId')), None)
    special_name = _name(special, proud_rows)
    found = {
        'natlan': third.startswith("Night Realm's Gift"),
        'nodkrai': third.startswith('Moonsign Benediction'),
        'hexerei': special_name.startswith("Witch's Eve Rite"),
        'stellar': third.startswith('Stellar Jubilee') or bool(special and not special_name.startswith("Witch's Eve Rite")),
    }
    return [kind for kind in TYPES if found[kind]]


def character_passive_types(character_id: int, excel_path: str | Path | None = None) -> list[str]:
    if excel_path is None:
        from getConfig import CONFIG
        excel_path = CONFIG.EXCEL_PATH

    def table(name: str) -> list[dict]:
        return json.loads((Path(excel_path) / f'{name}.json').read_text(encoding='utf-8'))

    avatar = next((item for item in table('AvatarExcelConfigData') if item.get('Id') == character_id), None)
    if avatar is None:
        raise ValueError(f'Character {character_id} is not in the dataset.')
    # Element-switching characters (the Traveler) use the Traveler option instead.
    if avatar.get('CandSkillDepotIds'):
        return []
    depot = next((item for item in table('AvatarSkillDepotExcelConfigData') if item.get('Id') == avatar.get('SkillDepotId')), {})
    return passive_types(depot, table('ProudSkillExcelConfigData'))
