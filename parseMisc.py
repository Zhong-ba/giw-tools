import argparse
import os

from utils.redirect import main_redirect
import OLGen

from getConfig import CONFIG

parser = argparse.ArgumentParser()
parser.add_argument('--blessingscan', type = bool)
parser.add_argument('--newenemies', type = str)
parser.add_argument('--fishingpoints', type = str)
parser.add_argument('--huntingv2', type = str)
parser.add_argument('--cookingqte', type = str)
parser.add_argument('--cookingqte2', type = str)
parser.add_argument('--ver', type = str)
parser.add_argument('--capkeys', type = str)
parser.add_argument('--redirectfromstr', type = str)

args = parser.parse_args()

if not os.path.exists(CONFIG.OUTPUT_PATH):
    os.makedirs(CONFIG.OUTPUT_PATH)


if args.blessingscan:
    from utils.blessingscan import parse_blessing_scan
    parse_blessing_scan()

if args.newenemies:
    from utils.enemies import parse_new_enemies, parse_new_enemies_2
    OLGen.load_data()
    parse_new_enemies(args, OLGen.gen_ol)
    parse_new_enemies_2()
    
if args.huntingv2:
    from utils.hunting import parse_hunting_v2
    parse_hunting_v2()
    
if args.cookingqte:
    from utils.cooking import parse_cooking_qte
    parse_cooking_qte()
    
if args.cookingqte2:
    from utils.cooking import cooking_qte_2
    cooking_qte_2()
    
if args.capkeys:
    from utils.misc import capkeys
    capkeys()
    
if args.redirectfromstr:
    from utils.redirect import redirects_from_str
    redirects_from_str(args.redirectfromstr)