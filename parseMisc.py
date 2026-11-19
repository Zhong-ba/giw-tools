import argparse
import os
from pathlib import Path

import OLGen
import toolLog as report

from getConfig import CONFIG

parser = argparse.ArgumentParser()
parser.add_argument('--blessingscan', type = bool)
parser.add_argument('--newenemies', type = str)
parser.add_argument('--fishingpoints', type = str, help = '"all", "new" (absent from RepoPathOld or --oldrev) or comma-separated fish pool IDs.')
parser.add_argument('--fishweights', type = bool, help = 'Write Module:Fishing Point Fish List/data with every fish\'s spawn weight.')
parser.add_argument('--chardata', type = bool, help = 'Write Module:Character Ascensions and Stats/data and Module:Talent Upgrade/data.')
parser.add_argument('--huntingv2', type = str, help = 'Any value for every Player\'s Choice bounty, or comma-separated bounty IDs.')
parser.add_argument('--cookingqte', type = str)
parser.add_argument('--cookingqte2', type = str, help = 'Draw manual cooking dial images for every recipe combination, or only those missing from the wiki with "missing".')
parser.add_argument('--ver', type = str)
parser.add_argument('--capkeys', type = str)
parser.add_argument('--redirectfromstr', type = str)
parser.add_argument('--oldrev', type = str, help = 'GitHub data source: compare --newenemies and --fishingpoints new against this commit, or "previous" for the newest commit of the previous game version, instead of RepoPathOld.')
parser.add_argument('--newnamesonly', type = bool, help = '--newenemies: only write pages for enemy names that did not exist in the older build.')
parser.add_argument('--enemies', type = str, help = 'Comma-separated monster IDs: write their pages and stat tables (with --ver).')
parser.add_argument('--enemyai', type = str, help = 'Comma-separated exact monster IDs: write review-only AI Logic drafts.')
parser.add_argument('--abyss', type = str, help = 'Write the Spiral Abyss/Floors page of the rotation starting on this date (YYYY-MM-DD), or "latest" (with --ver for startVersion).')
parser.add_argument('--stygian', type = str, help = 'Write the Stygian Onslaught page of the event starting on this date (YYYY-MM-DD), or "latest" (with --ver).')
parser.add_argument('--theater', type = str, help = 'Write the Imaginarium Theater page of the season starting on this date (YYYY-MM-DD), or "latest" (with --ver for startVersion).')

args = parser.parse_args()

if not os.path.exists(CONFIG.OUTPUT_PATH):
    os.makedirs(CONFIG.OUTPUT_PATH)


if args.blessingscan:
    from utils.blessingscan import parse_blessing_scan
    parse_blessing_scan()

def old_table(table):
    '''The table at --oldrev, or None to use RepoPathOld.'''
    if not args.oldrev:
        return None
    from setupData import excel_table_at, previous_version_revision
    commit = args.oldrev
    if commit == 'previous':
        revision = previous_version_revision()
        commit = revision['commit']
        report.info(f'Comparing with {revision["title"]} ({commit[:8]}).')
    return excel_table_at(commit, table)


if args.newenemies:
    from utils.enemies import parse_new_enemies, parse_new_enemies_2, old_monsters
    rows = old_table('MonsterExcelConfigData')
    old = None if rows is None else old_monsters(rows)
    OLGen.load_data()
    parse_new_enemies(args, OLGen.gen_ol, old, new_names_only = bool(args.newnamesonly))
    parse_new_enemies_2(old)

if args.enemies:
    from utils.enemies import parse_enemies
    OLGen.load_data()
    parse_enemies(args, OLGen.gen_ol, [int(value) for value in args.enemies.split(',') if value.strip()])

if args.enemyai is not None:
    from utils.enemyAI import write_ai_drafts
    try:
        ids = [int(value) for value in args.enemyai.split(',')]
        if any(monster_id <= 0 for monster_id in ids):
            raise ValueError
    except ValueError:
        parser.error('--enemyai expects comma-separated positive monster IDs.')
    count = write_ai_drafts(Path(CONFIG.OUTPUT_PATH) / 'Enemy AI Logic', Path(CONFIG.BIN_PATH), ids,
                            repo_root=Path(CONFIG.EXCEL_PATH).parent)
    report.info(f'Generated {count} AI Logic draft(s).')
    
if args.fishingpoints:
    from utils.fishing import parse_fishing_points
    parse_fishing_points(args.fishingpoints, old_table('FishPoolExcelConfigData') if args.fishingpoints == 'new' else None)

if args.fishweights:
    from utils.fishing import write_fish_weights
    report.info(f'Wrote spawn weights for {write_fish_weights()} fish.')

if args.chardata:
    from utils.charasc import write_character_data
    report.info('Wrote ascension data for {} characters and talent materials for {} entries.'.format(*write_character_data()))

if args.huntingv2:
    from utils.hunting import parse_hunting_v2
    ids = [int(value) for value in args.huntingv2.split(',') if value.strip().isdigit()]
    parse_hunting_v2(ids or None)
    
if args.cookingqte:
    from utils.cooking import parse_cooking_qte
    parse_cooking_qte()
    
if args.cookingqte2:
    from utils.cooking import cooking_qte_2
    cooking_qte_2(only_missing = args.cookingqte2 == 'missing')
    
if args.capkeys:
    from utils.misc import capkeys
    capkeys()
    
if args.redirectfromstr:
    from utils.redirect import redirects_from_str
    redirects_from_str(args.redirectfromstr)

if args.abyss:
    from utils.abyss import write_abyss_page
    write_abyss_page(None if args.abyss == 'latest' else args.abyss, args.ver or '')

if args.stygian:
    from utils.stygian import write_stygian_page
    write_stygian_page(None if args.stygian == 'latest' else args.stygian, args.ver or '')

if args.theater:
    from utils.theater import write_theater_page
    write_theater_page(None if args.theater == 'latest' else args.theater, args.ver or '')