"""Infer Talent/Constellation Infobox utilities from game-data descriptions.

Rules are tuned against the live wiki's existing infoboxes; each one is kept only
when its matches mostly agree with what editors chose. Kinds: T = Normal Attack,
Elemental Skill and Burst, P = passives, C = constellations.
"""
import re

ELEMENTS = ('Anemo', 'Geo', 'Electro', 'Dendro', 'Hydro', 'Pyro', 'Cryo', 'Physical')
PARTY = (r"(party members?|all party|your (own )?(party|team)|nearby (active )?characters|characters? within|"
         r"active characters?|other characters|all characters|characters in the aoe|characters? (that|who) (are )?(in|within))")
UP = r'(increas|increment|grant|gain|bonus|\+\d)'
# The party receives the effect, as opposed to "when a party member triggers...".
BENEFIT = (rf"(?<!when )(?<!if )(?<!after )(?<!when a )(?<!when an )(?<!when your )(?<!when the )(?<!if a )(?<!after a )"
           rf"{PARTY}(\s*\([^)]*\))?(\s*within [^,.]*?)?(,? excluding [^,.]*,)?('s?)?\s+(will )?(also )?(gain|have their|receive|obtain|get)"
           rf"|{PARTY}[^.]{{0,60}}, they (will )?(gain|receive|obtain|get)"
           rf"|(increases?|grants?|provides?) [^.]{{0,30}}{PARTY}|{PARTY}(\s*\([^)]*\))?'s? [^.]{{0,40}}(is |are )?increased")
STAT = lambda stat: rf"({BENEFIT})[^.]{{0,40}}(?<!'s )(?<!of ){stat}"
# "normal attack", "normal and charged attacks", "normal, charged, and plunging attacks"...
ATTACK = r"(normal|charged|plunging)(,? (and |or )?(normal|charged|plunging))*( attacks?| atk)"
ATTACK_DMG = lambda kind: (rf"(?=[^.]{{0,40}}{kind})({ATTACK})[^.]{{0,40}}dmg[^.]{{0,20}}{UP}"
                           rf"|{UP}\w* [^.]{{0,30}}(?=[^.]{{0,40}}{kind})({ATTACK})[^.]{{0,20}}dmg")
NOT_TYPED = r'(?<!ical )(?<!ctro )(?<!ndro )(?<!ydro )(?<!pyro )(?<!cryo )(?<!nemo )(?<! geo )(?<!crit )'

RULES = [
    ('Interruption Resistance', r'interruption'),
    ('CRIT Rate', r'crit rate'),
    ('CRIT DMG', r'crit dmg'),
    ('ATK SPD', r'attack spd|atk spd|attack speed'),
    ('Movement SPD', r'movement spd|swift stride'),
    ('Cooldown Reduction', r'\bcd\b[^.]*(decreas|reduc|shorten)|(decreas|reduc|shorten)[^.]*\bcd\b'),
    ('Cooldown Reset', r'\bcd\b[^.]*\breset|reset[^.]*\bcd\b'),
    ('DEF Reduction', r'\bdef\b[^.]*(decreas|reduc)|(decreas|reduc)[^.]*\bdef\b'),
    ('DEF Ignore', r'ignor\w* [^.]*\bdef\b'),
    ('DMG Elevation', r'is elevated'),
    ('Nightsoul Burst', r'nightsoul burst'),
    ('Vacuum Field', r'pulls? in'),
    ('Elemental Absorption', r'pyro, cryo, electro|hydro/pyro/cryo/electro'),
    ('Expedition', r'expedition'),
    ('Resource', r'resources unique to'),
    ('Local Specialty', r'resources unique to'),
    ('Healing', r'^(?!.*\bwhen\b[^.,]{0,50}\bheal)(?=.*(\bheals?\b|\bhealing (?!bonus|effects?|amount|received|interval|is|will|by)\w))'
                r'|continuously regenerate|(restor|regenerat|recover)\w* [^.]*\b(hp|health)\b'
                r'|\b(hp|health)\b (will be |is )?(restor|regenerat|recover)'),
    ('Incoming Healing Bonus', r'incoming healing bonus'),
    ('Shield', r'(creat|generat|summon|grant|form)\w* (a |an )?[^.]{0,40}\bshield\b(?! strength)'),
    ('Party ATK Increase', STAT(r'(?<!base )\batk\b(?! spd)')),
    ('ATK Increase', r'(?<!base )\batk (is |will be )?(increased|bonus)|(increases?|gains?|grants?) [^.]{0,40}(?<!base )\batk\b(?! spd)'),
    ('Party Elemental Mastery', STAT('elemental mastery')),
    ('Elemental Mastery', r'elemental mastery (is |will be )?increased|(increases?|gains?|grants?) [^.]{0,40}elemental mastery'),
    ('DEF Increase', r'\bdef (is |will be )?increased|(increases?|gains?|grants?) [^.]{0,30}\bdef\b'),
    ('Energy', r'(regenerat|restor|recover|generat)\w* [^.]{0,30}\benergy\b|\benergy\b (is |will be )?(restor|regenerat)'
               r'|\d+ (elemental )?energy', 'PC'),
    ('Duration Increase', r'duration [^.]*(is |will be )(increased|extended) by|(is|be) extended by \d|lasts? \d+s longer', 'C'),
    ('DMG Reduction', r'dmg (taken|received)[^.]*(decreas|reduc)|(decreas|reduc)\w* [^.]*dmg (taken|received)'),
    ('Taunting', r'taunt|draw\w* [^.]*(attention|aggro)|attract\w* [^.]*opponents'),
    ('Party Sprinting Stamina Reduction', r'sprinting stamina consumption[^.]*party'),
    ('Cooking', r'perfect cooking|when cooking|cooks? '),
    ('Nightsoul Point', r'nightsoul points?\b', 'T'),
    ('Nightsoul Point', r'(gain|regain|restor|recover)\w* \d+ nightsoul points?', 'PC'),
    ('Effects Retained Character Fallen', r'on the mini-map', 'P'),
    ('Plunging Attack Disabled', r'(cannot|unable to) (perform|use) [^.]*plunging attack'),
    ('Normal Attack DMG Increase', ATTACK_DMG('normal'), 'PC'),
    ('Charged Attack DMG Increase', ATTACK_DMG('charged'), 'PC'),
    ('Elemental Skill DMG Increase', r'elemental skill[^.]{0,40}dmg[^.]{0,20}' + UP + r'|' + UP + r'\w* [^.]{0,30}elemental skill[^.]{0,20}dmg', 'PC'),
    ('Additive Base DMG Bonus', r'dmg [^.]*increased by [^.]*(\d+%|equal to) [^.]*\b(atk|max hp|def|elemental mastery)\b'
                                r'|increases? [^.]*dmg [^.]*by [^.]*(\d+% of|equal to) [^.]*\b(atk|max hp|def|elemental mastery)\b', 'PC'),
    ('DMG Bonus', rf'(gains?|grants?|obtains?|a|an|\d+%) dmg bonus|{NOT_TYPED}dmg (dealt )?(is |will be )?increased by \d+%(?! of)'
                  rf'|deals? \d+% (more|increased|additional) dmg|increas\w* [^.]{{0,40}}{NOT_TYPED}\bdmg( dealt)? by \d+%(?! of)', 'PC'),
]
RULES += [(f'{e} DMG Bonus', rf'{e.lower()} dmg bonus') for e in ELEMENTS if e != 'Physical']
RULES += [(f'{e} RES Reduction', rf'{e.lower()}( and \w+)? res\b[^.]*(decreas|reduc)|(decreas|reduc)[^.]*{e.lower()} res\b')
          for e in ELEMENTS if e != 'Geo']
RULES = [(rule[0], re.compile(rule[1]), rule[2] if len(rule) > 2 else 'TPC') for rule in RULES]


def clean(desc):
    desc = re.sub(r'<i>.*?</i>', ' ', desc or '', flags=re.S)
    desc = re.sub(r'\{LINK#\w+\}|\{/LINK\}', '', desc)
    desc = re.sub(r'\{\{Color\|(?:[^|}]*\|)?([^}]*)\}\}', r'\1', desc)
    desc = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]*)\]\]', r'\1', desc)
    desc = re.sub(r'<[^>]+>|\{[^}]*\}', ' ', desc)
    desc = re.sub(r'(\d)\.(\d)', r'\1,\2', desc)
    return re.sub(r'\s+', ' ', desc).lower()


def utilities(desc, kind='TPC'):
    text = clean(desc)
    return list(dict.fromkeys(name for name, pattern, kinds in RULES if kind in kinds and pattern.search(text)))


def utility_lines(values, minimum=2):
    values = list(dict.fromkeys(values))
    values += [''] * (minimum - len(values))
    return ''.join(f'|utility{n:<7}= {value}\n' for n, value in enumerate(values, 1))
