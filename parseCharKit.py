import json
import toolLog as report
import argparse
import os
import re
import OLGen
from OLGen import gen_ol
from PIL import Image

from utils.redirect import file_redirect
from utils.files import write_file
from utils.pageinfo import pageinfo
from getConfig import CONFIG
from talentScaling import scaling_stats
from talentUtilities import utilities, utility_lines
from travelerKits import REGIONS, TRAVELER_IDS, element_for, select_depots

# Each concept is linked once per description, at the first occurrence of any of its forms. Matching ignores case
# except for CASE_SENSITIVE_KEYWORDS, whose lowercase forms are usually the plain word ("the water", "energy stored",
# "burning", "frozen"). A keyword is never linked inside a longer keyword or one of the character's talent names.
LINK_KEYWORDS = [
    ('Nightsoul point',),
    ('Liquid Phlogiston',),
    ('Phlogiston',),
    ('Nightsoul\'s Blessing',),
    ('ATK',),
    ('DEF',),
    ('HP',),
    ('Elemental Mastery',),
    ('Energy Recharge',),
    ('CRIT Rate',),
    ('CRIT DMG',),
    ('Healing Bonus',),
    ('Shield Strength',),
    ('Interruption Resistance',),
    ('Healing', 'Heal'),
    ('Talent',),
    ('Sprinting', 'Sprint'),
    ('Climbing',),
    ('Swimming',),
    ('Party',),
    ('Elemental RES',),
    ('RES',),
    ('Movement SPD',),
    ('Conversion',),
    ('Water',),
    ('Stamina',),
    ('CD',),
    ('Energy',),
    ('Nightsoul Burst',),
    ('Nightsoul Transmission',),
    ('Natlan',),
    # Elemental reactions
    ('Elemental Reaction',),
    ('Lunar Reaction',),
    ('Swirl',),
    ('Stellar Swirl',),
    ('Bloom',),
    ('Hyperbloom',),
    ('Burgeon',),
    ('Quicken',),
    ('Aggravate',),
    ('Spread',),
    ('Burning',),
    ('Superconduct',),
    ('Overloaded',),
    ('Electro-Charged',),
    ('Crystallize',),
    ('Frozen',),
    ('Shatter',),
    ('Vaporize',),
    ('Melt',),
    ('Lunar-Charged',),
    ('Lunar-Bloom',),
    ('Lunar-Crystallize',),
    ('Stellar-Conduct',),
    # Combat mechanics
    ('AoE',),
    ('Bond of Life',),
    ('Elemental Absorption',),
    ('Geo Construct',),
    ('Shield',),
    ('CRIT Hit',),
    ('ATK SPD',),
    # Team bonuses and Arkhe
    ('Moonsign: Ascendant Gleam', 'Moonsign'),
    ('Ascendant Gleam',),
    ('Hexerei',),
    ('Arkhe', 'Pneuma', 'Ousia'),
    # Activities
    ('Expedition',),
    ('Spiral Abyss',),
    ('Trounce Domain',),
    ('Domain',),
    # Attack types
    ('Normal Attack',),
    ('Charged Attack',),
    ('Plunging Attack',),
    ('Aimed Shot',),
    ('Elemental Skill',),
    ('Elemental Burst',),
]
CASE_SENSITIVE_KEYWORDS = {
    'Water', 'Energy', 'Elemental Reaction', 'Lunar Reaction', 'Swirl', 'Stellar Swirl', 'Bloom', 'Hyperbloom', 'Burgeon',
    'Quicken', 'Aggravate', 'Spread', 'Burning', 'Superconduct', 'Overloaded', 'Electro-Charged', 'Crystallize', 'Frozen',
    'Shatter', 'Vaporize', 'Melt', 'Lunar-Charged', 'Lunar-Bloom', 'Lunar-Crystallize', 'Stellar-Conduct', 'AoE',
    'Bond of Life', 'Elemental Absorption', 'Geo Construct', 'Moonsign: Ascendant Gleam', 'Ascendant Gleam', 'Hexerei',
    'Arkhe', 'Expedition', 'Spiral Abyss', 'Trounce Domain', 'Domain', 'Normal Attack', 'Charged Attack',
    'Plunging Attack', 'Aimed Shot', 'Elemental Skill', 'Elemental Burst',
}
# Game terms that contain a keyword without being one, such as the Moonsign Benediction passive type.
KEYWORD_BLOCKERS = ['Moonsign Benediction']
# "Anemo RES" or "Physical RES" is one stat; linking just its "RES" splits it.
ELEMENT_BEFORE = ''.join(f'(?<!{element} )' for element in ('Anemo', 'Geo', 'Electro', 'Dendro', 'Hydro', 'Pyro', 'Cryo', 'Physical'))
KEYWORD_PATTERNS = [re.compile(
    (ELEMENT_BEFORE if forms == ('RES',) else '')
    + r'\b(' + '|'.join(re.escape(form) for form in sorted(forms, key=len, reverse=True)) + r')(?=s?\b)',
    0 if forms[0] in CASE_SENSITIVE_KEYWORDS else re.IGNORECASE,
) for forms in LINK_KEYWORDS]
# For each keyword, the other keywords' forms (and blockers) it would otherwise match inside, like "Bloom" in "Lunar-Bloom".
CONTAINING_FORMS = [
    [form for form in [*(form for other in LINK_KEYWORDS if other is not forms for form in other), *KEYWORD_BLOCKERS]
     if (found := pattern.search(form)) and found.group(0) != form]
    for forms, pattern in zip(LINK_KEYWORDS, KEYWORD_PATTERNS)
]

parser = argparse.ArgumentParser()
parser.add_argument('--id', type=int)
parser.add_argument('--ver', type=str, help='Release version; looked up in the wiki article\'s Change History if omitted.')
parser.add_argument('--files', type=bool)
parser.add_argument('--elem', type=str)
parser.add_argument('--natlan', type=bool)
parser.add_argument('--nodkrai', type=bool)
parser.add_argument('--hexerei', type=bool)
parser.add_argument('--stellar', type=bool)
parser.add_argument('--traveler', type=int, help='Legacy option; canonical Traveler IDs are detected automatically.')
parser.add_argument('--skilldepot', type=int, help='Generate only this skill depot; Traveler defaults to all elemental kits.')
parser.add_argument('--levels', type=int, nargs=3, default=[11, 13, 13], metavar=('NA', 'E', 'Q'),
                    help='Max talent levels for the Attribute Scaling tables.')
parser.add_argument('--noscaling', type=bool)
parser.add_argument('--noap', type=bool, help='Leave the Advanced Properties sections empty (talents, passives, constellations).')
parser.add_argument('--noparticles', action='store_true',
                    help='Skip particle-generation notes, the review report and Energy/Data output.')
parser.add_argument('--nodatapages', type=bool, help="Don't add the character to the current combat data pages (Elemental Gauge, "
                    'ICD, Area of Effect, Hitlag, Targeting, Energy).')
parser.add_argument('--updateexisting', action='store_true',
                    help="Replace the character's existing combat data rows. Review the generated pages before posting.")
parser.add_argument('--nodetect', type=bool, help="Don't detect the special passive type when no --natlan/--nodkrai/--hexerei/--stellar is given.")

args = parser.parse_args()
traveler = args.id in TRAVELER_IDS
if traveler:
    args.traveler = 1

OLGen.load_data()


with open(f'{CONFIG.EXCEL_PATH}/AvatarSkillExcelConfigData.json', 'r', encoding='utf-8') as file:
    skillexcel = json.load(file)
        
with open(f'{CONFIG.EXCEL_PATH}/ProudSkillExcelConfigData.json', 'r', encoding='utf-8') as file:
    proudskillexcel = json.load(file)
    
with open(f'{CONFIG.EXCEL_PATH}/AvatarTalentExcelConfigData.json', 'r', encoding='utf-8') as file:
    talentexcel = json.load(file)
    
with open(f'{CONFIG.EXCEL_PATH}/HyperLinkNameExcelConifgData.json', 'r', encoding='utf-8') as file:
    hyperlinkexcel = json.load(file)

SPECIAL_PASSIVE_PREFIX = re.compile(r"^(?:Night Realm's Gift|Moonsign Benediction|Witch's Eve Rite)\s*[:·]\s*")


def passive_title(name):
    '''The wiki page title of a passive: special passive types drop their "Night Realm's Gift: " style prefix.'''
    return SPECIAL_PASSIVE_PREFIX.sub('', name)


# Page titles of the talents and constellations that {LINK#S/P/T<id>} tags in descriptions refer to.
TAG_TITLES = {
    'S': {block['Id']: block['NameTextMapHash'] for block in skillexcel if isinstance(block.get('NameTextMapHash'), str)},
    'P': {block['ProudSkillId']: passive_title(block['NameTextMapHash']) for block in proudskillexcel
          if isinstance(block.get('NameTextMapHash'), str) and 'ProudSkillId' in block},
    'T': {block['TalentId']: block['NameTextMapHash'] for block in talentexcel if isinstance(block.get('NameTextMapHash'), str)},
}
# This character's talent and constellation titles, linked where a description quotes them; set below.
own_titles = []
    

files = args.files

if args.id and not (args.natlan or args.nodkrai or args.hexerei or args.stellar or args.traveler or args.nodetect):
    from passiveTypes import character_passive_types, passive_types
    if args.skilldepot:
        with open(f'{CONFIG.EXCEL_PATH}/AvatarSkillDepotExcelConfigData.json', 'r', encoding='utf-8') as file:
            detected = passive_types(next((block for block in json.load(file) if block['Id'] == args.skilldepot), {}), proudskillexcel)
    else:
        detected = character_passive_types(args.id)
    for kind in detected:
        setattr(args, kind, True)
        report.info(f'Detected special passive type: --{kind}')


def special_slot(depot):
    # Stellar Jubilee passives sit in the third inherent slot with the Utility Passive in the fifth, like Night
    # Realm's Gift; other Stellar passives (e.g. Cyno's) are quest-unlocked special passives.
    opens = depot['InherentProudSkillOpens']
    return len(opens) > 4 and bool(opens[4].get('ProudSkillGroupId'))

ability_list = [
    [lambda depot: depot['Skills'][0], 'NA', 'Normal Attack'],
    [lambda depot: depot['Skills'][1], 'E', 'Elemental Skill'],
    [lambda depot: depot['EnergySkill'], 'Q', 'Elemental Burst']
]

passive_list = [
    [lambda depot: depot['InherentProudSkillOpens'][0]['ProudSkillGroupId'], 'A1', '1st Ascension Passive'],
    [lambda depot: depot['InherentProudSkillOpens'][1]['ProudSkillGroupId'], 'A4', '4th Ascension Passive'],
]
if args.natlan:
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'], 'NRG', "Night Realm's Gift Passive"])
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][4]['ProudSkillGroupId'], 'UP', 'Utility Passive'])
if args.nodkrai:
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'], 'MB', 'Moonsign Benediction Passive'])
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][4]['ProudSkillGroupId'], 'UP', 'Utility Passive'])
if args.hexerei:
    passive_list.append([lambda depot: depot['SpecialProudSkillOpens'][0]['ProudSkillGroupId'], 'WER', "Witch's Eve Rite Passive"])
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'], 'UP', 'Utility Passive'])
if args.stellar:
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'] if special_slot(depot)
                         else depot['SpecialProudSkillOpens'][0]['ProudSkillGroupId'], 'SP', 'Passive'])
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][4 if special_slot(depot) else 2]['ProudSkillGroupId'],
                         'UP', 'Utility Passive'])
elif not args.traveler and not args.natlan and not args.nodkrai and not args.hexerei:
    passive_list.append([lambda depot: depot['InherentProudSkillOpens'][2]['ProudSkillGroupId'], 'UP', 'Utility Passive'])
    
cons_list = [
    [lambda depot: depot['Talents'][0], 'C1'],
    [lambda depot: depot['Talents'][1], 'C2'],
    [lambda depot: depot['Talents'][2], 'C3'],
    [lambda depot: depot['Talents'][3], 'C4'],
    [lambda depot: depot['Talents'][4], 'C5'],
    [lambda depot: depot['Talents'][5], 'C6']
]

character = ''

passive_effects = {}
cons_effects = {}
        

def processIcon(path, type, name, folder):
    try:
        icon = Image.open(f'{CONFIG.IMAGE_PATH}/{path}.png').convert('RGBA')
        bg = Image.open(f'{CONFIG.TALENT_BG_PATH}/{type} {bg_element}.png').convert('RGBA')

        x = (bg.width - icon.width) // 2
        y = (bg.height - icon.height) // 2

        base_image = Image.new('RGBA', bg.size, (0, 0, 0, 0))

        base_image.paste(icon, (x, y), None)

        final_image = Image.alpha_composite(bg, base_image)

        output_path = f'{CONFIG.OUTPUT_PATH}/Images/{folder}'
        if not os.path.exists(output_path):
            os.makedirs(output_path)
            
        file_name_clean = name.replace(":", "").replace("\"", "").replace('?', '')
        
        if file_name_clean != name:
            file_redirect(f'{name}.png', f'{file_name_clean}.png')

        final_image.save(f'{output_path}/{file_name_clean}.png')
        report.debug(f'Processed icon saved to: {output_path}/{file_name_clean}.png')
    except FileNotFoundError as error:
        report.warning(f'Icon source file was not found: {error.filename}')
        
        
def parse_hyperlink(desc):
    hyperlinks = re.findall(r'\{LINK#N.*?\}.*?\{/LINK\}', desc)
    
    for hyperlink in hyperlinks:
        hyperlink_id = re.search(r'\{LINK#N(\d+)\}', hyperlink).group(1)
        text = re.search(r'\{LINK#N\d+\}(.*?)\{/LINK\}', hyperlink).group(1)
        
        for block in hyperlinkexcel:
            if block['Id'] == int(hyperlink_id):
                title = block['NameTextMapHash']
                content = block['DescTextMapHash']
                replace = f'{{{{Extra Effect|{text}|{title}|{content}}}}}'
                
                desc = desc.replace(hyperlink, replace)
                
    desc = re.sub(r'\{LINK#.*?\}(.*?)\{/LINK\}', r'\1', desc)
            
    return desc
        
        
# Existing links, {LINK#N} terms (which become Extra Effects) and bold text ('''Charged Attack''' headings) are not auto-linked.
PROTECTED = re.compile(r"\{LINK#[A-Z]\d+\}.*?\{/LINK\}|\[\[.*?\]\]|'''.+?'''")
LINK_TAG = re.compile(r'\{LINK#([SPT])(\d+)\}(.*?)\{/LINK\}')
# Line breaks and list tags, after or before which the source is split onto a new line (see multiline).
BREAK_AFTER = re.compile(r'(?:<br\s*/?>)+', re.IGNORECASE)
BREAK_BEFORE = re.compile(r'</?(?:ul|ol)>|<li>', re.IGNORECASE)
SOURCE_BREAK = '<!--\n-->'


def multiline(desc):
    '''Splits a description's source over several lines without changing how it renders: comments hide the newlines,
    which would otherwise end the template parameter's paragraph or list.'''
    desc = BREAK_AFTER.sub(lambda match: match.group(0) + SOURCE_BREAK, desc)
    desc = BREAK_BEFORE.sub(lambda match: SOURCE_BREAK + match.group(0), desc)
    desc = re.sub(f'(?:{re.escape(SOURCE_BREAK)})+', SOURCE_BREAK, desc)
    return desc.removeprefix(SOURCE_BREAK).removesuffix(SOURCE_BREAK)


def mask(text, hidden=()):
    '''Hides existing links, {LINK#N} terms (which become Extra Effects) and the given phrases so nothing is linked
    inside them. Returns the masked text and a function that restores them.'''
    saved = []

    def hide(match):
        saved.append(match.group(0))
        return f'\ue000{len(saved) - 1}\ue001'
    pattern = PROTECTED
    if hidden:
        phrases = '|'.join(re.escape(phrase) for phrase in sorted(hidden, key=len, reverse=True))
        pattern = re.compile(rf'{PROTECTED.pattern}|(?<!\w)(?:{phrases})s?(?!\w)', re.IGNORECASE)
    masked = pattern.sub(hide, text)
    return masked, lambda value: re.sub('\ue000(\\d+)\ue001', lambda match: saved[int(match.group(1))], value)


def add_wikilinks(ability_description, names=()):
    '''Links LINK_KEYWORDS, never inside a longer keyword or one of the given talent names.'''
    desc = ability_description
    for pattern, containing in zip(KEYWORD_PATTERNS, CONTAINING_FORMS):
        masked, restore = mask(desc, [*containing, *(name for name in names if name and pattern.search(name))])
        desc = restore(pattern.sub(lambda match: f'[[{match.group(1)}]]', masked, count=1))
    return desc


def link_tags(desc, linked):
    '''Turns the game's {LINK#S/P/T<id>}Name{/LINK} references to talents and constellations into wiki links.'''
    def replace(match):
        kind, ref, text = match.groups()
        target = TAG_TITLES[kind].get(int(ref))
        # Quotes and commas inside the tag ("Plan to Get Paid,") stay outside the link.
        lead, core, tail = re.fullmatch(r'(["\s]*)(.*?)(["\s,.;:]*)', text, re.S).groups()
        if not target or target in linked or not core:
            return text
        linked.add(target)
        return f'{lead}[[{target}]]{tail}' if core == target else f'{lead}[[{target}|{core}]]{tail}'
    return LINK_TAG.sub(replace, desc)


def link_name(desc, name, linked, quoted):
    '''Links the first mention of a talent name, as a whole word or only inside quotes ("Name" or "Name,").'''
    if not name or name in linked:
        return desc
    escaped = re.escape(name)
    pattern = rf'(?<=")({escaped})(?=[,.]?")' if quoted else rf'(?<![\w\[])({escaped})(?![\w\]])'
    masked, restore = mask(desc)
    masked, count = re.subn(pattern, lambda match: f'[[{match.group(1)}]]', masked, count=1)
    if count:
        linked.add(name)
    return restore(masked)


def link_description(desc, title, unquoted=()):
    '''Wiki-links a talent or constellation description: the game's references to other talents, the given talent
    names, quoted names of this character's other talents, then LINK_KEYWORDS. Each page is linked once, never itself.'''
    linked = {title}
    desc = link_tags(desc, linked)
    for name in unquoted:
        desc = link_name(desc, name, linked, quoted=False)
    for name in own_titles:
        desc = link_name(desc, name, linked, quoted=True)
    return multiline(parse_hyperlink(add_wikilinks(desc, [title, *unquoted, *own_titles])))


def parse_skill(id, ver, type = None, ability_dict = None, scaling = '', advanced: str | None = '', particles = ''):
    for block in skillexcel:
        if block['Id'] == id:
            talentname = block['NameTextMapHash']
            
            if not type:
                if id % 10 == 1:
                    type = 'Normal Attack'
                elif id % 10 == 2:
                    type = 'Elemental Skill'
                elif id % 10 == 5:
                    type = 'Elemental Burst'
                
            if files and type != 'Normal Attack':
                icon = block['SkillIcon']
                if type == 'Elemental Burst':
                    icon = icon + '_HD'
                processIcon(icon, 'Talent', f'Talent {talentname}', f'{character} Talent Icons')
            
            energyCost = block.get('CostElemVal', '')
                
            if block.get('CdTime'):
                cd = str(block['CdTime']) + 's'
            else:
                cd = ''
                
            desc = block['DescTextMapHash']
            utility = utility_lines(utilities(desc, 'T'))
            
            extradesc = block.get('ExtraDescTextMapHash')
            flavortxt_wikitext = ''
            
            if isinstance(extradesc, str):
                flavortxt_wikitext = f'\n{{{{Description|{extradesc[11:-4]}}}}}'
            else:
                parts = desc.split('<br><br><i>', 1)
                if len(parts) > 1:
                    desc = parts[0]
                    extradesc = parts[1].split('</i>', 1)[0]
                    flavortxt_wikitext = f'\n{{{{Description|{extradesc}}}}}'
            
            ol_text = gen_ol(talentname)
            vo_text = '==Voice-Overs==\n{{Talent VO}}\n\n'
            if traveler:
                vo_text = ('==Voice-Overs==\n===Aether===\n{{Talent VO/Traveler|character=Aether}}\n\n'
                           '===Lumine===\n{{Talent VO/Traveler|character=Lumine}}\n\n')
                    
            # "Pneuma-aligned", or "Pneuma- or Ousia-aligned" for attacks that use either.
            arkhe = ';'.join(dict.fromkeys(re.findall(r'\b(Pneuma|Ousia)-(?:aligned|\s+or\b)', desc)))
            
            desc = link_description(desc, talentname, [ability for checktype, ability in ability_dict.items() if checktype != type])
            
            # talent note
            passive_effect_wikitext = ''
            cons_effects_wikitext = ''
            note_context = f'|character={character}|talent={talentname}' if traveler else ''
            
            if passive_effects.get(str(id)):
                for name, i in passive_effects[str(id)]:
                    passive_effect_wikitext = f'{passive_effect_wikitext}\n* {{{{Talent Note{note_context}|ascension|{i}|{name}}}}}'

            if passive_effect_wikitext:
                passive_effect_wikitext = f';<big>Passive Effects</big>{passive_effect_wikitext}\n'
            else:
                passive_effect_wikitext = f';<big>Passive Effects</big>\n* {{{{Talent Note{note_context}|ascension||}}}}\n'
            
            if cons_effects.get(str(id)):
                for name, i in cons_effects[str(id)]:
                    cons_effects_wikitext = f'{cons_effects_wikitext}\n* {{{{Talent Note{note_context}|constellation|{i}|{name}}}}}'
            
            if cons_effects_wikitext:
                cons_effects_wikitext = f';<big>Constellation Effects</big>{cons_effects_wikitext}\n'
            else:
                cons_effects_wikitext = f';<big>Constellation Effects</big>\n* {{{{Talent Note{note_context}|constellation||}}}}\n'
            
            passive_effect_wikitext = f'{passive_effect_wikitext}\n'
            cons_effects_wikitext = f'{cons_effects_wikitext}\n'
    
    stats = scaling_stats(scaling)
    scale_att = ''.join(f'|scale_att{n:<5}= {stat}\n' for n, stat in enumerate(stats + [''] * (2 - len(stats)), 1))
    arkhe_line = f'|arkhe         = {arkhe}\n' if fontaine else ''
    # None means Advanced Properties didn't run, so the section stays for manual filling.
    advanced_wikitext = '==Advanced Properties==\n\n\n' if advanced is None else f'{advanced_section(advanced)}\n' if advanced else ''
    particle_notes = f'{particles.rstrip()}\n\n' if type == 'Elemental Skill' and particles else ''
    upgrade_names = [REGIONS[bg_element]] if traveler else [character]
    if traveler and type == 'Normal Attack':
        if not args.noscaling:
            scaling = '{{Past Memories}}'
            scale_att = '|scale_att1    = ATK\n|scale_att2    = \n'
        vo_text = ''
        if bg_element == 'Geo':
            upgrade_names = ['Mondstadt', 'Liyue']
    upgrade_wikitext = '\n'.join(f'{{{{Talent Upgrade|{name}}}}}' for name in upgrade_names)
            
    page_content = f"""{pageinfo(talentname)}
{{{{Talent Infobox
|image         = Talent {talentname}.png
|character     = {character}
|type          = {type}
|info          = {desc}
|CD            = {cd}
|energyCost    = {energyCost}
{scale_att}{utility}{arkhe_line}}}}}{flavortxt_wikitext}
'''{talentname}''' is [[{character}]]'s [[{type}]].

==Gameplay Notes==
{particle_notes}{passive_effect_wikitext}{cons_effects_wikitext}{advanced_wikitext}==Preview==
{{{{Preview
|file1 = {talentname} Preview
}}}}

==Attribute Scaling==
{scaling}

==Talent Leveling==
{upgrade_wikitext}

{vo_text}==Other Languages==
{ol_text}

==Change History==
{{{{Change History|{ver}}}}}

==Navigation==
{{{{Talent Navbox|{character}}}}}"""
    
    return page_content


def advanced_section(advanced):
    return f'==Advanced Properties==\n{advanced}\n' if advanced else ''


def parse_passive(id, ver, type = None, ability_dict = None, advanced = ''):
    for block in proudskillexcel:
        if block['ProudSkillId'] == id or block.get('ProudSkillGroupId') == id:
            
            name = block['NameTextMapHash']
            desc = block['DescTextMapHash']
            utility = utility_lines(utilities(desc, 'P'))

            if not type:
                try:
                    if block['BreakLevel'] == 1:
                        type = '1st Ascension Passive'
                    elif block['BreakLevel'] == 4:
                        type = '4th Ascension Passive'
                except KeyError:
                    if args.natlan and "Night Realm's Gift" in name:
                        type = "Night Realm's Gift Passive"
                    if args.nodkrai and "Moonsign Benediction" in name:
                        type = "Moonsign Benediction Passive"
                    if args.hexerei and "Witch's Eve Rite" in name:
                        type = "Witch's Eve Rite Passive"
                    else:
                        type = 'Utility Passive'
            
            ol_text = gen_ol(name)
            
            if type == "Night Realm's Gift Passive":
                name = name[20:]
            if type == "Moonsign Benediction Passive":
                name = name[22:]
            if type == "Witch's Eve Rite Passive":
                name = re.sub(r"^Witch's Eve Rite\s*[:·]\s*", '', name)
             
            if files:
                icon = block['Icon']
                processIcon(icon, 'Talent', f'Talent {name}', f'{character} Talent Icons')
    
    desc = link_description(desc, name, [ability for checktype, ability in ability_dict.items() if checktype != type])

    page_content = f"""{pageinfo(name)}
{{{{Talent Infobox
|image         = Talent {name}.png
|character     = {character}
|type          = {type}
|info          = {desc}
|scale_att1    = 
|scale_att2    = 
{utility}}}}}
'''{name}''' is [[{character}]]'s [[{type}]].
<!--
==Gameplay Notes==
-->
{advanced_section(advanced)}==Other Languages==
{ol_text}

==Change History==
{{{{Change History|{ver}}}}}

==Navigation==
{{{{Talent Navbox|{character}}}}}
"""
    
    return page_content


def parse_cons(id, ver, ability_dict, advanced = ''):
    for block in talentexcel:
        if block['TalentId'] == id:
            name = block['NameTextMapHash']
            rank = id % 10
            desc = block['DescTextMapHash']
            
            if files:
                icon = block['Icon']
                processIcon(icon, 'Constellation', f'Constellation {name}', f'{character} Constellation Icons')
                
            ol_text = gen_ol(name)
            
            utility1 = ''
            utility2 = ''
            
            for checktype in ('Normal Attack', 'Elemental Skill', 'Elemental Burst'):
                if ability_dict[checktype] in desc and rank in (3, 5):
                    utility2 = f'{checktype} Level Increase'
                
            if utility2:
                utility1 = 'Talent Level Increase'
            utility = utility_lines([u for u in (utility1, utility2) if u] + utilities(desc, 'C'))
    
    desc = link_description(desc, name, ability_dict.values())
    constellation_advanced = f'\n{advanced_section(advanced)}' if advanced else ''
    
    page_content = f"""{pageinfo(name)}
{{{{Constellation Infobox
|image         = Constellation {name}.png
|character     = {character}
|level         = {rank}
|description   = {desc}
|scale_att1    = 
|scale_att2    = 
{utility}}}}}
'''{name}''' is [[{character}]]'s [[Level {rank} Constellation]].
<!--
==Gameplay Notes==
-->{constellation_advanced}<!--
==Preview==
{{{{Preview
|file = {name} Preview
}}}}
-->
==Other Languages==
{ol_text}

==Change History==
{{{{Change History|{ver}}}}}

==Navigation==
{{{{Talent Navbox|{character}}}}}
"""
    
    return page_content


def get_skill_name(id):
    for block in skillexcel:
        if block['Id'] == id:
            name = block['NameTextMapHash']
    
    return name


def get_passive_name(id):
    for block in proudskillexcel:
        if block['ProudSkillId'] == id or block.get('ProudSkillGroupId') == id:
            name = block['NameTextMapHash']
    
    return name


def get_cons_name(id):
    for block in talentexcel:
        if block['TalentId'] == id:
            name = block['NameTextMapHash']
    
    return name


def get_cons_desc(id):
    for block in talentexcel:
        if block['TalentId'] == id:
            desc = block['DescTextMapHash']
    
    return desc


with open(f'{CONFIG.EXCEL_PATH}/AvatarExcelConfigData.json', 'r', encoding='utf-8') as file:
    avatarconfig = json.load(file)
    
with open(f'{CONFIG.EXCEL_PATH}/AvatarSkillDepotExcelConfigData.json', 'r', encoding='utf-8') as file:
    skilldepotconfig = json.load(file)
    
with open(f'{CONFIG.EXCEL_PATH}/FetterInfoExcelConfigData.json', 'r', encoding='utf-8') as file:
    fetterinfoconfig = json.load(file)
     
avatar = next((block for block in avatarconfig if block['Id'] == args.id), None)
if avatar is None:
    raise SystemExit(f'Character {args.id} is not in the dataset.')
try:
    kits = select_depots(avatar, skilldepotconfig, skillexcel, args.skilldepot)
except ValueError as error:
    raise SystemExit(str(error)) from error
base_passives = passive_list[:]
pending_pages = {}


def current_data_pages(titles):
    from wikiVersion import page_texts
    missing = [title for title in titles if title not in pending_pages]
    texts = page_texts(missing) if missing else {}
    texts.update({title: pending_pages[title] for title in titles if title in pending_pages})
    return texts


if traveler and args.ver and not args.skilldepot:
    report.info('Generating all Traveler kits; release versions are looked up per element. Use --skilldepot to override one kit.')
if traveler and not args.noparticles and not args.nodatapages:
    from pathlib import Path
    Path(f'{CONFIG.OUTPUT_PATH}/Traveler/Data Pages/Energy Data.wikitext').unlink(missing_ok=True)

for skilldepot in kits:
    report.stage(f'Generating character {args.id}, skill depot {skilldepot["Id"]}')
    character = avatar['NameTextMapHash']
    bg_element = element_for(skilldepot, skillexcel) if traveler else args.elem
    if traveler:
        character = f'Traveler ({bg_element})'
        report.info(f'Generating {character}, skill depot {skilldepot["Id"]}.')
    selected_depot = skilldepot['Id'] if traveler else args.skilldepot
    ver = args.ver if not traveler or args.skilldepot else None
    if not ver:
        report.stage(f'Looking up the release version for {character}')
        from wikiVersion import release_version
        try:
            ver = release_version(character)
        except OSError as error:
            report.warning(f'Could not check the wiki for the release version: {error}')
        if not ver:
            raise SystemExit(f'No release version found for {character} on the wiki; pass --ver.')
        report.info(f'Release version from the wiki Change History: {ver}')
            
    if not bg_element:
        for block in fetterinfoconfig:
            if block['AvatarId'].get('Name', block['AvatarId'].get('name')) == character:
                bg_element = block['AvatarVisionBeforTextMapHash']
    # Only Fontaine characters' talents have the infobox's arkhe param.
    fontaine = (bg_element == 'Hydro' if traveler else
                any(block.get('AvatarAssocType') == 'ASSOC_TYPE_FONTAINE' for block in fetterinfoconfig
                    if block['AvatarId'].get('Name', block['AvatarId'].get('name')) == character))
    passive_list = base_passives[:]
    if traveler:
        passive_list = base_passives[:2]
        for index, passive in enumerate(skilldepot.get('InherentProudSkillOpens') or []):
            if index >= 2 and passive.get('ProudSkillGroupId'):
                passive_list.append([lambda depot, index=index: depot['InherentProudSkillOpens'][index]['ProudSkillGroupId'],
                                     'SP' if index == 2 else f'P{index + 1}', 'Passive'])

    for folder in ('Skills', 'Passives', 'Constellations'):
        output_path = f'{CONFIG.OUTPUT_PATH}/{character}/{folder}'
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        
    ability_dict = {
        'Normal Attack': get_skill_name(ability_list[0][0](skilldepot)),
        'Elemental Skill': get_skill_name(ability_list[1][0](skilldepot)),
        'Elemental Burst': get_skill_name(ability_list[2][0](skilldepot)),
        '1st Ascension Passive': get_passive_name(passive_list[0][0](skilldepot)),
        '4th Ascension Passive': get_passive_name(passive_list[1][0](skilldepot)),
    }
    own_titles[:] = dict.fromkeys(
        [get_skill_name(ability[0](skilldepot)) for ability in ability_list]
        + [passive_title(get_passive_name(passive[0](skilldepot))) for passive in passive_list]
        + [get_cons_name(cons[0](skilldepot)) for cons in cons_list]
    )
    
    from pathlib import Path
    from talentEffects import load_talent_configs, talent_effects
    depot_groups = {block.get('ProudSkillGroupId') for block in skillexcel
                    if block['Id'] in (skilldepot['Skills'][:2] + [skilldepot['EnergySkill']])}
    depot_groups |= {item.get('ProudSkillGroupId') for item in skilldepot.get('InherentProudSkillOpens') or []}
    open_configs = {block.get('OpenConfig') for block in proudskillexcel if block.get('Level', 1) == 1 and block.get('ProudSkillGroupId') in depot_groups}
    open_configs |= {block.get('OpenConfig') for block in talentexcel if block['TalentId'] in skilldepot.get('Talents', [])}
    icon_name = next((block.get('IconName', '') for block in avatarconfig if block['Id'] == args.id), '').removeprefix('UI_AvatarIcon_')
    talent_configs = load_talent_configs(Path(CONFIG.BIN_PATH) / 'Talent' / 'AvatarTalents', open_configs - {None, ''}, icon_name)
    if not talent_configs:
        report.warning('No talent configs in BinOutput/Talent/AvatarTalents; Passive/Constellation Effects use descriptions only.')
    found_passives, found_cons = talent_effects(skilldepot, skillexcel, proudskillexcel, talentexcel, talent_configs)
    passive_effects.clear()
    cons_effects.clear()
    passive_effects.update(found_passives)
    cons_effects.update(found_cons)
    report.debug('Passive effects: %s', passive_effects)
    report.debug('Constellation effects: %s', cons_effects)
    
    scaling = {}
    if not args.noscaling:
        try:
            from talentScaling import talent_scaling
            depot_options = {'skill_depot': selected_depot} if selected_depot is not None else {}
            scaling = {skill: template for skill, _, template in talent_scaling(args.id, *args.levels, **depot_options)}
        except (OSError, ValueError, RuntimeError) as error:
            report.warning(f'Attribute Scaling skipped: {error}')
    else:
        report.info('Attribute Scaling disabled by request.')

    advanced, passive_advanced, cons_advanced = {}, {}, {}
    ran_ap = False
    if not args.noap:
        report.stage('Generating Advanced Properties')
        try:
            from advancedProperties import advanced_properties, talent_advanced_properties
            advanced = advanced_properties(args.id, selected_depot)
            ran_ap = True
            passive_advanced, cons_advanced = talent_advanced_properties(args.id, selected_depot)
            if traveler:
                normal_id = skilldepot['Skills'][0]
                normal_sections = []
                for sibling_id, gender in ((10000005, 'Aether'), (10000007, 'Lumine')):
                    if sibling_id == args.id:
                        sibling_depot, sibling_advanced = skilldepot, advanced
                    else:
                        sibling = next((block for block in avatarconfig if block['Id'] == sibling_id), None)
                        if sibling is None:
                            raise ValueError(f'Traveler {sibling_id} is missing; both Normal Attack variants are required.')
                        sibling_depot = next((depot for depot in select_depots(sibling, skilldepotconfig, skillexcel)
                                              if element_for(depot, skillexcel) == bg_element), None)
                        if sibling_depot is None:
                            raise ValueError(f'Traveler {sibling_id} has no {bg_element} kit.')
                        sibling_advanced = advanced_properties(sibling_id, sibling_depot['Id'])
                    normal = sibling_advanced.get(sibling_depot['Skills'][0], '')
                    if normal:
                        normal_sections.append(f';{gender}\n{normal}')
                advanced[normal_id] = '\n\n'.join(normal_sections)
        except (OSError, ValueError) as error:
            report.warning(f'Advanced Properties skipped: {error}')
            if traveler:
                ran_ap = False
    else:
        report.info('Advanced Properties disabled by request.')

    particles = {'status': 'disabled', 'notes': ''}
    if not args.noparticles:
        report.stage('Analyzing particle generation')
        from particleGeneration import particle_generation
        from particlePages import skill_particles
        particle_report = {'character_id': args.id}
        try:
            particle_report = particle_generation(args.id, selected_depot)
            particles = skill_particles(particle_report)
        except (OSError, ValueError) as error:
            particles = {'status': 'error', 'reason': str(error), 'notes': ''}
        particle_message = f'Particle generation: {particles["status"]}; {particles["reason"]}'
        (report.warning if particles['status'] in ('error', 'review_required') else report.info)(particle_message)
        particle_report['output'] = particles
        write_file(f'{CONFIG.OUTPUT_PATH}/{character}/Particle Generation.json',
                   json.dumps(particle_report, ensure_ascii=False, indent=2), overwrite = True)
    else:
        report.info('Particle Generation disabled by request.')
        
    for ability in report.track(ability_list, 'Writing talent pages'):
        file_write_path = f'{CONFIG.OUTPUT_PATH}/{character}/Skills/{ability[1]}.wikitext'
        id = ability[0](skilldepot)
        
        write_file(file_write_path, parse_skill(id, ver, ability[2], ability_dict, scaling.get(id, ''),
                   advanced.get(id, '') if ran_ap else None, particles['notes']), overwrite = True)
        
    for passive in report.track(passive_list, 'Writing passive pages'):
        file_write_path = f'{CONFIG.OUTPUT_PATH}/{character}/Passives/{passive[1]}.wikitext'
        id = passive[0](skilldepot)
        
        write_file(file_write_path, parse_passive(id, ver, passive[2], ability_dict, passive_advanced.get(id, '')), overwrite = True)
        
    for cons in report.track(cons_list, 'Writing constellation pages'):
        file_write_path = f'{CONFIG.OUTPUT_PATH}/{character}/Constellations/{cons[1]}.wikitext'
        id = cons[0](skilldepot)
        
        write_file(file_write_path, parse_cons(id, ver, ability_dict, cons_advanced.get(id, '')), overwrite = True)

    if ran_ap and not args.nodatapages:
        report.stage('Updating combat data pages')
        try:
            from combatPages import combat_pages
            data_options = {'fetch': current_data_pages} if traveler else {}
            data_pages, _ = combat_pages(args.id, selected_depot, character,
                                        update_existing=args.updateexisting, **data_options)
            if traveler:
                pending_pages.update(data_pages)
            else:
                os.makedirs(f'{CONFIG.OUTPUT_PATH}/{character}/Data Pages', exist_ok = True)
                for title, text in data_pages.items():
                    write_file(f'{CONFIG.OUTPUT_PATH}/{character}/Data Pages/{title.replace("/", " ")}.wikitext',
                               f'{pageinfo(title)}\n{text}', overwrite = True)
        except (OSError, ValueError) as error:
            report.warning(f'Combat data pages skipped: {error}')

    if not args.noparticles and not args.nodatapages:
        report.stage('Updating Energy data page')
        try:
            from particlePages import energy_pages
            if not traveler:
                Path(f'{CONFIG.OUTPUT_PATH}/{character}/Data Pages/Energy Data.wikitext').unlink(missing_ok=True)
            data_options = {'fetch': current_data_pages} if traveler else {}
            data_pages, _ = energy_pages(character, particles, update_existing=args.updateexisting, **data_options)
            if traveler:
                pending_pages.update(data_pages)
            else:
                for title, text in data_pages.items():
                    os.makedirs(f'{CONFIG.OUTPUT_PATH}/{character}/Data Pages', exist_ok = True)
                    write_file(f'{CONFIG.OUTPUT_PATH}/{character}/Data Pages/{title.replace("/", " ")}.wikitext',
                               f'{pageinfo(title)}\n{text}', overwrite = True)
        except (OSError, ValueError) as error:
            report.warning(f'Energy data page skipped: {error}')

if traveler:
    for title, text in report.track(list(pending_pages.items()), 'Writing combined Traveler data pages'):
        os.makedirs(f'{CONFIG.OUTPUT_PATH}/Traveler/Data Pages', exist_ok=True)
        write_file(f'{CONFIG.OUTPUT_PATH}/Traveler/Data Pages/{title.replace("/", " ")}.wikitext',
                   f'{pageinfo(title)}\n{text}', overwrite=True)
    