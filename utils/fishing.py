'''Fishing Point pages from the fish pool, stock and fish tables.'''

from collections import Counter
import json
import os
import re

from getConfig import CONFIG
import toolLog as report
from utils.files import write_file
from utils.pageinfo import pageinfo

STOCK_TYPES = (('day', 'FISH_STOCK_TYPE_DAY'), ('night', 'FISH_STOCK_TYPE_NIGHT'))
UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _load(name):
    with open(f'{CONFIG.EXCEL_PATH}/{name}.json', 'r', encoding = 'utf-8') as file:
        return json.load(file)


def city_names(rows = None):
    '''CityId -> region name. The name column is obfuscated, so it is the text column every named city has.'''
    rows = rows if rows is not None else _load('CityConfigData')
    texts = lambda row: {key: value for key, value in row.items()
                         if isinstance(value, str) and not re.fullmatch(r'[A-Z0-9_]+|UI_\w+', value)}
    counts = Counter(key for row in rows for key in texts(row))
    if not counts:
        return {}
    key = counts.most_common(1)[0][0]
    return {row['CityId']: row[key] for row in rows if isinstance(row.get(key), str)}


def fishing_points(pools = None):
    '''{pool id: wiki title} of real fishing points (pools assigned to a region).

    Points sharing a name get " (1)", " (2)"... in ID order, as on the wiki.'''
    pools = pools if pools is not None else _load('FishPoolExcelConfigData')
    named = sorted((pool['Id'], pool['PoolNameTextMapHash'].strip()) for pool in pools
                   if pool.get('CityId') and isinstance(pool.get('PoolNameTextMapHash'), str) and pool['PoolNameTextMapHash'].strip())
    totals, seen, result = Counter(name for _, name in named), Counter(), {}
    for pool_id, name in named:
        seen[name] += 1
        result[pool_id] = f'{name} ({seen[name]})' if totals[name] > 1 else name
    return result


def _area_lookup():
    '''Name -> (subarea, area) from the world map areas: level 2 areas are subareas of their level 1 area.'''
    level1, lookup = {}, {}
    rows = _load('WorldAreaConfigData')
    for row in rows:
        name = row.get('AreaNameTextMapHash')
        if row.get('AreaType') == 'LEVEL_1' and isinstance(name, str):
            level1[(row.get('SceneID'), row.get('AreaID1'))] = name
            lookup.setdefault(name, ('', name))
    for row in rows:
        name = row.get('AreaNameTextMapHash')
        parent = level1.get((row.get('SceneID'), row.get('AreaID1')))
        if row.get('AreaType') == 'LEVEL_2' and isinstance(name, str) and parent:
            lookup.setdefault(name, (name, parent))
    return lookup


def _fish_name(fish):
    # Ornamental fish are variants of a base fish (FishCateId) and drop the same item.
    name = fish.get('ItemId')
    if not isinstance(name, str):
        return None
    return f'Ornamental {name}' if fish.get('FishCateId') else name


def _fish_list(stocks, fish):
    names = []
    for stock in stocks:
        names.extend(name for name in (_fish_name(fish.get(int(fish_id), {})) for fish_id in stock.get('FishWeight', {}))
                     if name and name not in names)
    # The wiki lists regular fish before their ornamental variants.
    return '; '.join(sorted(names, key = lambda name: name.startswith('Ornamental ')))


def _count_range(low, high):
    if not high:
        return ''
    return str(high) if low == high or not low else f'{low}-{high}'


def fishing_point_pages(pool_ids):
    '''{wiki title: page wikitext} for the given pool IDs.'''
    report.stage('Loading fishing point data')
    pools = {pool['Id']: pool for pool in _load('FishPoolExcelConfigData')}
    titles = fishing_points(pools.values())
    stocks = {stock['Id']: stock for stock in _load('FishStockExcelConfigData')}
    fish = {item['Id']: item for item in _load('FishExcelConfigData')}
    cities, areas = city_names(), _area_lookup()

    pages = {}
    for pool_id in report.track(pool_ids, 'Generating fishing points'):
        pool = pools.get(pool_id)
        if pool is None:
            raise ValueError(f'Fish pool {pool_id} does not exist.')
        title = titles.get(pool_id) or pool.get('PoolNameTextMapHash') or str(pool_id)
        name = pool.get('PoolNameTextMapHash') or ''
        subarea, area = areas.get(name) or areas.get(name.split(':')[0].strip()) or ('', '')

        pool_stocks = [stocks[stock_id] for stock_id in pool.get('StockList', []) if stock_id in stocks]
        limits = {limit.get('StockType'): limit for limit in pool.get('StockLimitList', []) if limit}
        fish_lists, low, high = {}, 0, 0
        for key, stock_type in STOCK_TYPES:
            fish_lists[key] = _fish_list([stock for stock in pool_stocks if stock.get('Type') in (stock_type, 'FISH_STOCK_TYPE_ANY')], fish)
            low += limits.get(stock_type, {}).get('MinNum', 0)
            high += limits.get(stock_type, {}).get('MaxNum', 0)

        page_title = f'Fishing Point/{title}'
        pages[page_title] = f'''{pageinfo(page_title)}{{{{Fishing Point
|title         = {title}
|id            = {pool_id}
|subarea       = {subarea}
|area          = {area}
|region        = {cities.get(pool.get('CityId'), '')}
|description   = {pool.get('PoolDescTextMapHash') or ''}
|day           = {fish_lists['day']}
|night         = {fish_lists['night']}
|display limit = {pool.get('MaxNum', '')}
|total         = {_count_range(low, high)}
}}}}'''
    return pages


def write_fishing_points(pool_ids, directory = None):
    directory = directory or f'{CONFIG.OUTPUT_PATH}/Fishing Points'
    os.makedirs(directory, exist_ok = True)
    pages = fishing_point_pages(pool_ids)
    for title, text in report.track(list(pages.items()), 'Writing fishing point pages'):
        name = UNSAFE_FILENAME.sub('', title.split('/', 1)[1]).strip()
        write_file(f'{directory}/{name}.wikitext', text + '\n', overwrite = True)
    return len(pages)


def fish_weights(pools = None, stocks = None, fish = None):
    '''{fish name: spawn weight} for Module:Fishing Point Fish List/data, regular fish first, then ornamental ones.

    Only stocks of real fishing points count (event and quest stocks use other weights); a fish weighted
    differently between points takes its most common weight.'''
    report.stage('Loading fish spawn data')
    pools = pools if pools is not None else _load('FishPoolExcelConfigData')
    stocks = {stock['Id']: stock for stock in (stocks if stocks is not None else _load('FishStockExcelConfigData'))}
    fish = {item['Id']: item for item in (fish if fish is not None else _load('FishExcelConfigData'))}
    real = fishing_points(pools)

    weights = {}
    for pool in report.track(sorted(pools, key = lambda pool: pool['Id']), 'Calculating fish spawn weights'):
        if pool['Id'] not in real:
            continue
        for stock_id in pool.get('StockList', []):
            for fish_id, weight in stocks.get(stock_id, {}).get('FishWeight', {}).items():
                item = fish.get(int(fish_id), {})
                if _fish_name(item) and isinstance(weight, (int, float)) and not isinstance(weight, bool):
                    weights.setdefault(int(fish_id), Counter())[weight] += 1

    ordered = sorted(weights, key = lambda fish_id: (bool(fish[fish_id].get('FishCateId')),
                                                    fish[fish_id].get('FishCateId') or fish_id))
    result = {}
    for fish_id in ordered:
        result.setdefault(_fish_name(fish[fish_id]), weights[fish_id].most_common(1)[0][0])
    return result


def fish_weights_lua(weights = None):
    weights = weights if weights is not None else fish_weights()
    title = 'Module:Fishing Point Fish List/data'
    rows = ''.join(f"\t['{name.replace(chr(92), chr(92) * 2).replace(chr(39), chr(92) + chr(39))}'] = {weight:g},\n"
                   for name, weight in weights.items())
    return f'''--[=[<%-- [PAGE_INFO]
    pageTitle = #{title}#
[END_PAGE_INFO] --%>--]=]

return {{
{rows}}}
'''


def write_fish_weights(directory = None):
    directory = directory or CONFIG.OUTPUT_PATH
    weights = fish_weights()
    report.stage('Writing fish spawn-weight module')
    write_file(f'{directory}/Fishing_Point_Fish_List_data.lua', fish_weights_lua(weights), overwrite = True)
    return len(weights)


def parse_fishing_points(selection, old_pools = None):
    '''CLI entry: selection is "new" (pools missing from old_pools, or from RepoPathOld), "all", or comma-separated IDs.'''
    current = fishing_points()
    if selection == 'all':
        pool_ids = list(current)
    elif selection == 'new':
        if old_pools is None:
            if CONFIG.EXCEL_PATH_OLD is None:
                raise FileNotFoundError('RepoPathOld is not configured; choose an older revision to compare against.')
            with open(f'{CONFIG.EXCEL_PATH_OLD}/FishPoolExcelConfigData.json', 'r', encoding = 'utf-8') as file:
                old_pools = json.load(file)
        old_ids = {pool.get('Id', pool.get('id')) for pool in old_pools}
        pool_ids = [pool_id for pool_id in current if pool_id not in old_ids]
    else:
        pool_ids = [int(value) for value in selection.split(',') if value.strip()]
    count = write_fishing_points(pool_ids)
    report.info(f'Generated {count} fishing point page{"" if count == 1 else "s"}.')
