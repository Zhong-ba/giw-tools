"""Enemy selection shared by the enemy generator and the web UI's Enemy picker."""


def monster_set(rows, describe_names=None):
    """(ids, names) of a build's monsters.

    Mapped rows carry DescribeName; raw ExcelBinOutput rows only have describe IDs, resolved with describe_names."""
    if describe_names is None:
        pairs = [(row.get('Id'), row.get('DescribeName')) for row in rows]
    else:
        if not any('id' in row or 'Id' in row for row in rows):
            raise ValueError('The older MonsterExcelConfigData has no readable id field.')
        pairs = [(row.get('id', row.get('Id')), describe_names.get(row.get('describeId', row.get('DescribeId'))))
                 for row in rows]
    return {mons_id for mons_id, _ in pairs if mons_id}, {name for _, name in pairs if name}


def has_name(row):
    name = row.get('DescribeName')
    return bool(name) and isinstance(name, str)


def added_monsters(rows, older, newer=None, new_names_only=False):
    """Named rows missing from the older build (and present in the newer one, when given).

    With new_names_only, enemies that already existed under another ID, and repeat IDs of a new one, are skipped."""
    old_ids, old_names = older
    new_ids = newer[0] if newer else None
    known_names = set(old_names) if new_names_only else None
    result = []
    for row in rows:
        mons_id = row.get('Id')
        if mons_id in old_ids or (new_ids is not None and mons_id not in new_ids) or not has_name(row):
            continue
        if known_names is not None:
            if row['DescribeName'] in known_names:
                continue
            known_names.add(row['DescribeName'])
        result.append(row)
    return result


def version_options(revisions, active, game_version):
    """Picker options: the active dataset, then the newest revision of each game version (newest first).

    Returns (options, default older value): the newest revision of a game version before the active one."""
    index = next((index for index, revision in enumerate(revisions) if revision['commit'] == active), None)
    active_version = game_version(revisions[index]['title']) if index is not None else None
    label = lambda version: f'{version[0]}.{version[1]}'
    options = [{'value': 'current', 'version': label(active_version) if active_version else None,
                'label': f'Active dataset ({label(active_version)})' if active_version else 'Active dataset'}]
    seen, older = set(), None
    for position, revision in enumerate(revisions):
        version = game_version(revision['title'])
        if not version or version in seen:
            continue
        seen.add(version)
        if revision['commit'] != active:
            options.append({'value': revision['commit'], 'version': label(version),
                            'label': f'{label(version)} · {revision["title"]} · {revision["date"][:10]}'})
        if older is None and active_version and version < active_version and position > index:
            older = revision['commit']
    return options, older
