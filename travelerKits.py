"""Dataset-driven selection and wiki conventions for the Traveler's elemental kits."""
import toolLog as report

TRAVELER_IDS = {10000005, 10000007}
ELEMENTS = {
    'Wind': 'Anemo', 'Rock': 'Geo', 'Electric': 'Electro', 'Grass': 'Dendro',
    'Water': 'Hydro', 'Fire': 'Pyro', 'Ice': 'Cryo',
}
REGIONS = {
    'Anemo': 'Mondstadt', 'Geo': 'Liyue', 'Electro': 'Inazuma', 'Dendro': 'Sumeru',
    'Hydro': 'Fontaine', 'Pyro': 'Natlan', 'Cryo': 'Snezhnaya',
}


def element_for(depot: dict, skills: list[dict]) -> str:
    burst = next((skill for skill in skills if skill['Id'] == depot.get('EnergySkill')), {})
    element = ELEMENTS.get(burst.get('CostElemType'))
    if element is None:
        raise ValueError(f'Skill depot {depot["Id"]} has no recognized elemental Burst.')
    return element


def select_depots(avatar: dict, depots: list[dict], skills: list[dict],
                  selected: int | None = None) -> list[dict]:
    """Select all complete elemental Traveler kits by default, or validate an explicit depot."""
    traveler = avatar['Id'] in TRAVELER_IDS
    candidates = list(dict.fromkeys(avatar.get('CandSkillDepotIds') or []))
    if traveler and selected is not None and selected not in candidates:
        raise ValueError(f'Skill depot {selected} does not belong to Traveler {avatar["Id"]}.')
    default = avatar.get('SkillDepotId', (avatar['Id'] - 10000000) * 100 + 1)
    ids = [selected] if selected is not None else candidates if traveler else [default]
    result = []
    for identifier in ids:
        depot = next((depot for depot in depots if depot['Id'] == identifier), None)
        if depot is None:
            raise ValueError(f'Skill depot {identifier} is not in the dataset.')
        if traveler:
            talents = depot.get('Skills') or []
            if len(talents) < 2 or not all(talents[:2]) or not depot.get('EnergySkill'):
                if selected is not None:
                    raise ValueError(f'Skill depot {identifier} is elementless or incomplete.')
                report.debug('Skipping elementless or incomplete Traveler skill depot %s.', identifier)
                continue
            element_for(depot, skills)
        result.append(depot)
    if not result:
        raise ValueError(f'Character {avatar["Id"]} has no complete elemental kits.')
    return result
