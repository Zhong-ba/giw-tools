import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
LANGS = ['CHS', 'CHT', 'DE', 'EN', 'ES', 'FR', 'ID', 'JP', 'KR', 'PT', 'RU', 'TH', 'VI', 'TR', 'IT']


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.excel = self.work / 'MappedExcelBinOutput_EN'
        self.old = self.work / 'old' / 'MappedExcelBinOutput_EN'
        self.output = self.work / 'output'
        for directory in (self.excel, self.old, self.output, self.work / 'TextMap', self.work / 'BinOutput' / 'Monster'):
            directory.mkdir(parents=True)
        self.write_json(self.work / 'scriptconfig.json', {
            'RepoPath': str(self.work),
            'RepoPathOld': str(self.work / 'old'),
            'ImgPath': str(self.work),
            'TalentBGPath': str(self.work),
            'OutputPath': str(self.output),
        })
        environment = patch.dict(os.environ, {'GENSHIN_TOOLS_CONFIG': str(self.work / 'scriptconfig.json')})
        environment.start()
        self.addCleanup(environment.stop)
        previous_cwd = Path.cwd()
        os.chdir(self.work)
        self.addCleanup(os.chdir, previous_cwd)
        modules = patch.dict(sys.modules)
        modules.start()
        self.addCleanup(modules.stop)
        for name in list(sys.modules):
            if name in ('getConfig', 'OLGen', 'utils') or name.startswith('utils.'):
                del sys.modules[name]
        self.stdout = io.StringIO()
        capture = contextlib.redirect_stdout(self.stdout)
        capture.__enter__()
        self.addCleanup(capture.__exit__, None, None, None)

    def write_json(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def read_output(self, name):
        return (self.output / name).read_text(encoding='utf-8')

    def load_ol(self):
        module = importlib.import_module('OLGen')
        module.data = {lang: {'1': 'Normal Attack: Strike', '2': 'Duplicate'} for lang in LANGS}
        module.data['EN']['3'] = 'Duplicate'
        module.data['FR']['1'] = 'Attaque normale : Frappe'
        return module

    def character_tool(self, *arguments, fetters=(), desc='ATK and Skill. {LINK#N7}Detail{/LINK}'):
        self.load_ol()
        for lang in LANGS:
            self.write_json(self.work / 'TextMap' / f'TextMap{lang}.json', {'1': 'Strike'})
        self.write_json(self.excel / 'AvatarExcelConfigData.json', [
            {'Id': 10000001, 'NameTextMapHash': 'Tester'},
        ])
        self.write_json(self.excel / 'AvatarSkillDepotExcelConfigData.json', [{
            'Id': 101, 'Skills': [1, 2], 'EnergySkill': 5,
            'InherentProudSkillOpens': [{'ProudSkillGroupId': n} for n in (11, 14, 19)],
            'SpecialProudSkillOpens': [{'ProudSkillGroupId': 20}],
            'Talents': list(range(101, 107)),
        }])
        self.write_json(self.excel / 'AvatarSkillExcelConfigData.json', [
            {'Id': n, 'NameTextMapHash': name, 'DescTextMapHash': desc,
             'CdTime': 0, 'SkillIcon': 'Icon'}
            for n, name in ((1, 'Strike'), (2, 'Skill'), (5, 'Burst'))
        ])
        self.write_json(self.excel / 'ProudSkillExcelConfigData.json', [
            {'ProudSkillId': n, 'ProudSkillGroupId': n,
             'NameTextMapHash': "Witch's Eve Rite: Spark" if n == 20 else f'Passive {n}',
             'DescTextMapHash': '{LINK#S1}Strike{/LINK} {LINK#S1}Strike{/LINK}'}
            for n in (11, 14, 19, 20)
        ])
        self.write_json(self.excel / 'AvatarTalentExcelConfigData.json', [
            {'TalentId': n, 'NameTextMapHash': f'Cons {n}',
             'DescTextMapHash': '{LINK#S2}Skill{/LINK} Burst'}
            for n in range(101, 107)
        ])
        self.write_json(self.excel / 'HyperLinkNameExcelConifgData.json', [
            {'Id': 7, 'NameTextMapHash': 'Title', 'DescTextMapHash': 'Content'},
        ])
        self.write_json(self.excel / 'FetterInfoExcelConfigData.json', list(fetters))
        with patch.object(sys, 'argv', ['parseCharKit.py', '--id', '10000001', '--ver', '1.0', '--elem', 'Pyro', *arguments]):
            return runpy.run_path(str(ROOT / 'parseCharKit.py'))

    def test_witchs_eve_rite_passive(self):
        self.character_tool('--hexerei', 'True')
        page = self.read_output('Tester/Passives/WER.wikitext')
        self.assertTrue(page.startswith('<%-- [PAGE_INFO]\n    pageTitle = #Spark#\n'))
        self.assertIn("|type          = Witch's Eve Rite Passive", page)
        self.assertEqual(sorted(path.name for path in (self.output / 'Tester' / 'Passives').iterdir()),
                         ['A1.wikitext', 'A4.wikitext', 'UP.wikitext', 'WER.wikitext'])

    def test_stellar_passive(self):
        self.character_tool('--stellar', 'True')
        self.assertIn("pageTitle = #Witch's Eve Rite: Spark#", self.read_output('Tester/Passives/SP.wikitext'))
        self.assertIn('pageTitle = #Passive 19#', self.read_output('Tester/Passives/UP.wikitext'))

    def test_passive_type_detection(self):
        from passiveTypes import passive_types
        rows = [{'ProudSkillGroupId': n, 'NameTextMapHash': name} for n, name in (
            (3, "Night Realm's Gift: A"), (4, 'Moonsign Benediction: B'), (5, 'Stellar Jubilee: C'), (6, 'Utility'),
            (7, "Witch's Eve Rite: D"), (8, 'A Star With Which to Start the Journey'))]
        depot = lambda third, special=None: {'InherentProudSkillOpens': [{}, {}, {'ProudSkillGroupId': third}, {}, {}],
                                             'SpecialProudSkillOpens': [{'ProudSkillGroupId': special}] if special else []}
        self.assertEqual([passive_types(depot(n), rows) for n in (3, 4, 5, 6)], [['natlan'], ['nodkrai'], ['stellar'], []])
        self.assertEqual(passive_types(depot(6, 7), rows), ['hexerei'])
        self.assertEqual(passive_types(depot(6, 8), rows), ['stellar'])
        # The kit tool detects the type itself unless one is given or --nodetect is set.
        self.character_tool('--skilldepot', '101')
        self.assertIn('Detected special passive type: --hexerei', self.stdout.getvalue())
        self.assertTrue((self.output / 'Tester' / 'Passives' / 'WER.wikitext').is_file())
        shutil.rmtree(self.output / 'Tester')
        self.character_tool('--skilldepot', '101', '--nodetect', 'True')
        self.assertFalse((self.output / 'Tester' / 'Passives' / 'WER.wikitext').exists())

    def test_other_languages_order_fallback_and_options(self):
        module = self.load_ol()
        text = module.gen_ol('Normal Attack: Strike')
        self.assertTrue(text.startswith('{{Other Languages\n|en       = Strike\n|zhs      = Strike'))
        self.assertIn('|fr       = Frappe\n|fr_tl    = ', text)
        self.assertNotIn('|zhs_rm', text)
        self.assertNotIn('|fr_tl', module.gen_ol('Normal Attack: Strike', tl=False))
        module.data['FR']['2'] = 'First duplicate'
        module.data['FR']['3'] = 'Second duplicate'
        self.assertIn('First duplicate', module.gen_ol('Duplicate'))
        self.assertEqual(module.gen_ol('Missing'), 'Not found.')

    def test_character_pages_and_effects(self):
        tool = self.character_tool()
        self.assertEqual(len(list((self.output / 'Tester').rglob('*.wikitext'))), 12)
        skill = self.read_output('Tester/Skills/NA.wikitext')
        self.assertTrue(skill.startswith('<%-- [PAGE_INFO]\n    pageTitle = #Strike#\n[END_PAGE_INFO] --%>\n\n{{Talent Infobox'))
        self.assertIn('[[ATK]] and [[Skill]]. {{Extra Effect|Detail|Title|Content}}', skill)
        self.assertIn('* {{Talent Note|ascension|1|Passive 11}}\n* {{Talent Note|ascension|2|Passive 14}}', skill)
        self.assertIn('|energyCost    = \n|scale_att1    = \n|scale_att2    = \n|utility1      = \n|utility2      = \n}}', skill)
        self.assertEqual(tool['passive_effects']['1'], [['Passive 11', 1], ['Passive 14', 2]])
        self.assertIn('|utility2      = Elemental Burst Level Increase', self.read_output('Tester/Constellations/C3.wikitext'))
        self.assertEqual(tool['add_wikilinks']('ATK ATK {LINK#N7}HP{/LINK}'), '[[ATK]] ATK {LINK#N7}HP{/LINK}')
        self.assertEqual(tool['parse_hyperlink']('{LINK#S1}Strike{/LINK}'), 'Strike')

    def test_character_kit_arkhe(self):
        fetters = [{'AvatarId': {'Name': 'Tester'}, 'AvatarAssocType': 'ASSOC_TYPE_FONTAINE',
                    'AvatarVisionBeforTextMapHash': 'Pyro'}]
        self.character_tool(fetters=fetters, desc="'''Arkhe: Pneuma'''<br>Dealing Pneuma- or Ousia-aligned DMG.")
        self.assertIn('|utility2      = \n|arkhe         = Pneuma;Ousia\n}}', self.read_output('Tester/Skills/NA.wikitext'))
        self.character_tool(fetters=fetters)
        self.assertIn('|utility2      = \n|arkhe         = \n}}', self.read_output('Tester/Skills/NA.wikitext'))

    def test_character_kit_utilities(self):
        self.character_tool(desc='Gains {{Color|Pyro|Pyro DMG Bonus}} and resistance to interruption. CRIT Rate +10%. '
                                 'If a character within the AoE is above 70% HP, they gain an ATK Bonus.')
        self.assertIn('|utility1      = Interruption Resistance\n|utility2      = CRIT Rate\n'
                      '|utility3      = Party ATK Increase\n|utility4      = ATK Increase\n'
                      '|utility5      = Pyro DMG Bonus\n}}', self.read_output('Tester/Skills/E.wikitext'))

    def test_character_kit_attribute_scaling(self):
        import talentScaling
        tables = [(1, 'Strike', '{{Talent Scaling\n|levels=10\n|order=hit,heal\n|titles=Hit DMG (%),Healing\n'
                                '|hit_1=40\n|heal_1=4.4% Max HP + 424\n}}'),
                  (5, 'Burst', '{{Talent Scaling\n|levels=14\n|order=bonus\n|titles=ATK Bonus (%DEF)\n|bonus_1=50\n}}')]
        with patch.object(talentScaling, 'talent_scaling', return_value=tables) as scaling:
            self.character_tool('--levels', '10', '12', '14')
        scaling.assert_called_once_with(10000001, 10, 12, 14)
        self.assertIn('|scale_att1    = ATK\n|scale_att2    = Max HP\n', self.read_output('Tester/Skills/NA.wikitext'))
        self.assertIn('|scale_att1    = DEF\n|scale_att2    = \n', self.read_output('Tester/Skills/Q.wikitext'))
        self.assertIn(f'==Attribute Scaling==\n{tables[0][2]}\n\n==Talent Leveling==',
                      self.read_output('Tester/Skills/NA.wikitext'))
        self.assertIn(f'==Attribute Scaling==\n{tables[1][2]}\n\n==Talent Leveling==',
                      self.read_output('Tester/Skills/Q.wikitext'))
        self.assertIn('==Attribute Scaling==\n\n\n==Talent Leveling==', self.read_output('Tester/Skills/E.wikitext'))
        with patch.object(talentScaling, 'talent_scaling', side_effect=ValueError('Traveler')):
            self.character_tool()
        self.assertIn('Attribute Scaling skipped: Traveler', self.stdout.getvalue())
        self.assertIn('==Attribute Scaling==\n\n\n==Talent Leveling==', self.read_output('Tester/Skills/NA.wikitext'))
        with patch.object(talentScaling, 'talent_scaling') as scaling:
            self.character_tool('--noscaling', 'True')
        scaling.assert_not_called()

    def test_character_kit_advanced_properties(self):
        import advancedProperties
        template = '{{Advanced Properties\n|title   = Strike\n}}'
        talent_pages = ({11: '{{Advanced Properties\n|title   = Bolt\n}}'}, {102: '{{Advanced Properties\n|title   = Nova\n}}'})
        with patch.object(advancedProperties, 'advanced_properties', return_value={1: template}) as advanced, \
                patch.object(advancedProperties, 'talent_advanced_properties', return_value=talent_pages) as talents:
            self.character_tool('--skilldepot', '101')
        advanced.assert_called_once_with(10000001, 101)
        talents.assert_called_once_with(10000001, 101)
        self.assertIn(f'==Advanced Properties==\n{template}\n\n==Preview==', self.read_output('Tester/Skills/NA.wikitext'))
        self.assertIn('Cons 106}}\n\n==Preview==', self.read_output('Tester/Skills/E.wikitext'))
        self.assertIn('==Gameplay Notes==\n-->\n==Advanced Properties==\n{{Advanced Properties\n|title   = Bolt\n}}\n'
                      '==Other Languages==', self.read_output('Tester/Passives/A1.wikitext'))
        self.assertIn('==Gameplay Notes==\n-->\n==Other Languages==', self.read_output('Tester/Passives/A4.wikitext'))
        self.assertIn('==Gameplay Notes==\n-->\n==Advanced Properties==\n{{Advanced Properties\n|title   = Nova\n}}\n'
                      '<!--\n==Preview==', self.read_output('Tester/Constellations/C2.wikitext'))
        self.assertIn('==Gameplay Notes==\n--><!--\n==Preview==', self.read_output('Tester/Constellations/C1.wikitext'))
        with patch.object(advancedProperties, 'advanced_properties', side_effect=FileNotFoundError('no talents')):
            self.character_tool()
        self.assertIn('Advanced Properties skipped: no talents', self.stdout.getvalue())
        self.assertIn('==Advanced Properties==\n\n\n==Preview==', self.read_output('Tester/Skills/E.wikitext'))
        with patch.object(advancedProperties, 'advanced_properties') as advanced, \
                patch.object(advancedProperties, 'talent_advanced_properties') as talents:
            self.character_tool('--noap', 'True')
        advanced.assert_not_called()
        talents.assert_not_called()

    def test_talent_advanced_properties_from_binoutput(self):
        def attack(damage, tag='Elemental_Art', **prop):
            return {'attackInfo': {'attackTag': tag, 'hitPattern': {'hitImpulseType': 'LV2'},
                                   'attackProperty': {'elementType': 'Fire', 'elementDurability': 25,
                                                      'damagePercentage': damage, **prop}}}

        def gated(param, success, fail=None):
            node = {'$type': 'Predicated', 'predicates': [{'$type': 'ByUnlockTalentParam', 'talentParam': param}],
                    'successActions': [success]}
            return dict(node, failActions=[fail]) if fail else node

        bin_path = self.work / 'BinOutput'
        for folder in ('Talent/AvatarTalents', 'Ability/Temp/AvatarAbilities'):
            (bin_path / folder).mkdir(parents=True, exist_ok=True)
        self.write_json(self.excel / 'AvatarExcelConfigData.json', [
            {'Id': 10000001, 'IconName': 'UI_AvatarIcon_Tester', 'SkillDepotId': 101}])
        self.write_json(self.excel / 'AvatarSkillDepotExcelConfigData.json', [{
            'Id': 101, 'Skills': [1, 2], 'EnergySkill': 5, 'InherentProudSkillOpens': [{'ProudSkillGroupId': 11}],
            'Talents': [101, 102, 103, 104]}])
        self.write_json(self.excel / 'AvatarSkillExcelConfigData.json', [{'Id': n, 'ProudSkillGroupId': n} for n in (1, 2, 5)])
        self.write_json(self.excel / 'ProudSkillExcelConfigData.json', [
            {'ProudSkillGroupId': 2, 'Level': 1, 'OpenConfig': 'Tester_2', 'ParamDescList': ['Skill DMG|{param1:F1P}']},
            {'ProudSkillGroupId': 11, 'Level': 1, 'OpenConfig': 'Tester_P1', 'NameTextMapHash': 'Bolt'},
        ])
        self.write_json(self.excel / 'AvatarTalentExcelConfigData.json', [
            {'TalentId': 100 + n, 'OpenConfig': f'Tester_C{n}', 'NameTextMapHash': name}
            for n, name in ((1, 'Nova'), (2, 'Echo'), (3, 'Edge'), (4, 'Spark'))])
        self.write_json(self.excel / 'AttackAttenuationExcelConfigData.json', [])

        def special(name, ability='Avatar_Tester'):
            return {'$type': 'ModifyAbility', 'abilityName': ability, 'paramSpecial': name, 'paramDelta': '%1'}

        def unlock(param):
            return {'$type': 'UnlockTalentParam', 'abilityName': 'Avatar_Tester', 'talentParam': param}

        self.write_json(bin_path / 'Talent' / 'AvatarTalents' / 'ConfigTalent_Tester.json', {
            'Tester_2': [special('Skill')], 'Tester_P1': [special('Bolt_DMG')],
            'Tester_C1': [{'$type': 'AddAbility', 'abilityName': 'Avatar_Tester_Nova'}],
            'Tester_C2': [unlock('Echo'), special('Echo_Crit')], 'Tester_C3': [unlock('Edge')],
            'Tester_C4': [unlock('Spark')],
        })
        self.write_json(bin_path / 'Ability' / 'Temp' / 'AvatarAbilities' / 'ConfigAbility_Avatar_Tester.json', [
            {'abilityName': 'Avatar_Tester', 'actions': [
                attack('Skill'),
                attack('Bolt_DMG', enBreak=50),
                attack('Skill', bonusCritical='Echo_Crit', enBreak=60),
                gated('Edge', attack('Skill', enBreak=70), attack('Skill')),
                gated('Spark', attack('Skill', enBreak=80)),
            ]},
            {'abilityName': 'Avatar_Tester_Nova', 'actions': [attack('Nova_DMG', tag='MoonShockDamage', enBreak=90)]},
        ])

        from advancedProperties import talent_advanced_properties
        passives, constellations = talent_advanced_properties(10000001)
        self.assertEqual(passives, {11: '{{Advanced Properties\n|title   = Bolt\n|gu      = 1U\n|icdtag  = none\n'
                                        '|poise   = 50\n|impulse = 2\n}}'})
        self.assertEqual(sorted(constellations), [101, 104])
        self.assertIn('|title   = Nova Lunar-Charged\n', constellations[101])
        self.assertIn('|title   = Skill\n|gu      = 1U\n|icdtag  = none\n|poise   = 80\n', constellations[104])

    def test_advanced_properties_from_binoutput(self):
        def attack(tag, damage=None, **extra):
            prop = {'elementType': 'Fire', 'elementDurability': 25}
            if damage:
                prop['damagePercentage'] = damage
            return {'attackTag': tag, 'attackProperty': {**prop, **extra.pop('prop', {})},
                    'hitPattern': extra.pop('pattern', {'hitImpulseType': 'LV3'}), **extra}

        bin_path = self.work / 'BinOutput'
        for folder in ('Avatar', 'Talent/AvatarTalents', 'Ability/Temp/AvatarAbilities'):
            (bin_path / folder).mkdir(parents=True, exist_ok=True)
        self.write_json(self.excel / 'AvatarExcelConfigData.json', [
            {'Id': 10000001, 'IconName': 'UI_AvatarIcon_Tester', 'SkillDepotId': 101, 'WeaponType': 'WEAPON_BOW'}])
        self.write_json(self.excel / 'AvatarSkillDepotExcelConfigData.json', [{'Id': 101, 'Skills': [1, 2], 'EnergySkill': 5}])
        self.write_json(self.excel / 'AvatarSkillExcelConfigData.json', [{'Id': n, 'ProudSkillGroupId': n} for n in (1, 2, 5)])
        self.write_json(self.excel / 'ProudSkillExcelConfigData.json', [
            {'ProudSkillGroupId': 1, 'Level': 1, 'OpenConfig': 'Tester_1',
             'ParamDescList': ['1-Hit DMG|{param1:F1P}×2', 'Aimed Shot|{param2:F1P}', '']},
            {'ProudSkillGroupId': 2, 'Level': 1, 'OpenConfig': 'Tester_2',
             'ParamDescList': ['Spin DMG|{param1:F1P}+{param2:F1P}', 'Mixed DMG|{param3:F1P} ATK+{param4:F1P} DEF']},
            {'ProudSkillGroupId': 5, 'Level': 1, 'OpenConfig': 'Tester_5', 'ParamDescList': ['Skill DMG|{param1:F1P}']},
        ])
        self.write_json(self.excel / 'AttackAttenuationExcelConfigData.json', [
            {'Group': 'default', 'ResetCycle': 2.5, 'HBPHCDMFLAH': [1, 0, 0, 1, 0, 0]},
            {'Group': 'Tester_Burst', 'ResetCycle': 1.600000023841858, 'HBPHCDMFLAH': [1, 0, 0, 0]},
        ])
        self.write_json(bin_path / 'Talent' / 'AvatarTalents' / 'ConfigTalent_Tester.json', {
            f'Tester_{talent}': [{'$type': 'ModifyAbility', 'abilityName': 'Avatar_Tester', 'paramSpecial': special,
                                  'paramDelta': f'%{n}'} for special, n in links]
            for talent, links in ((1, [('Attack_01', 1), ('Aimed', 2)]), (2, [('Spin_A', 1), ('Spin_B', 2), ('Mixed', 3)]),
                                  (5, [('Burst', 1)]))
        })
        self.write_json(bin_path / 'Avatar' / 'ConfigAvatar_Tester.json', {'combat': {'animEvents': {
            'ATK01': {'attackInfo': attack('NormalAttack_01', prop={'elementType': 'None'}, attenuationTag='Normal')}}}})
        self.write_json(bin_path / 'Ability' / 'Temp' / 'AvatarAbilities' / 'ConfigAbility_Avatar_Tester.json', [
            {'abilityName': 'Avatar_Tester', 'abilityMixins': [
                {'$type': 'ModifyDamageMixin', 'animEventNames': ['ATK01'], 'damagePercentage': 'Attack_01'},
                {'$type': 'ModifyDamageMixin', 'attackTags': ['ExtraAttack'], 'damagePercentage': 'Aimed'}],
             'actions': [
                 {'attackInfo': attack('ExtraAttack', prop={'elementType': 'None', 'enBreak': 10}, pattern={'hitImpulseType': 'LV2'})},
                 {'attackInfo': attack('Elemental_Art', '%Spin_A', attenuationTag='ElementalArt')},
                 {'attackInfo': attack('Elemental_Art', 'Spin_B', attenuationTag='ElementalArt',
                                       pattern={'overrideHitImpulse': {'hitLevel': 'Air', 'hitImpulseY': 600}})},
                 {'attackInfo': attack('Elemental_Art', 'Mixed', prop={'strikeType': 'Blunt'})},
                 {'attackInfo': attack('Elemental_Burst', 'Burst', attenuationTag='ElementalBurst',
                                       attenuationGroup='Tester_Burst', prop={'elementDurability': 50},
                                       pattern={'overrideHitImpulse': {'hitLevel': 'Heavy', 'hitImpulseX': 200}})},
             ]}])

        from advancedProperties import advanced_properties
        pages = advanced_properties(10000001)
        self.assertIn('|title   = Normal Attack 1-Hit A\n|gu      = &mdash;\n|icdtag  = Normal Attack\n'
                      '|icdtype = 2.5s/3 Hits\n|poise   = 30\n|impulse = 3\n\n|title2   = Normal Attack 1-Hit B\n', pages[1])
        self.assertIn('|title3   = Aimed Shot\n|gu3      = &mdash;\n|icdtag3  = none\n|poise3   = 10\n|impulse3 = 2\n\n'
                      '|title4   = Aimed Shot (Hit Weak Spot)\n|gu4      = &mdash;\n|icdtag4  = none\n|poise4   = 30\n|impulse4 = 5', pages[1])
        self.assertIn('|title7   = High Plunge\n|gu7      = &mdash;\n|icdtag7  = none\n|poise7   = 100\n|impulse7 = 3\n}}', pages[1])
        self.assertEqual(pages[2], (
            '{{Advanced Properties\n|title   = Spin 1-Hit\n|gu      = 1U\n|icdtag  = Elemental Skill\n|icdtype = 2.5s/3 Hits\n'
            '|poise   = 30\n|impulse = 3\n\n|title2   = Spin 2-Hit\n|gu2      = 1U\n|icdtag2  = Elemental Skill\n'
            '|icdtype2 = 2.5s/3 Hits\n|poise2   = 30\n|impulse2 = Air, 0, 600\n\n|title3   = Mixed\n|gu3      = 1U\n'
            '|icdtag3  = none\n|poise3   = 30\n|impulse3 = 3\n|blunt3   = 1\n}}'))
        self.assertIn('|title   = Skill\n|gu      = 2U\n|icdtag  = Elemental Burst\n|icdtype = 1.6s\n|poise   = 30\n|impulse = 3\n',
                      pages[5])
        with self.assertRaisesRegex(ValueError, 'not in the dataset'):
            advanced_properties(1)

    def test_advanced_properties_irregular_icd_and_grouping(self):
        from advancedProperties import _group_icd, icd_type
        self.assertEqual(icd_type({'ResetCycle': 10, 'X': [1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0]}),
                         '10s: <small>1st, 4th, 7th Hits Apply Element</small>')
        self.assertEqual(icd_type({'ResetCycle': 2.5, 'X': [1, 0, 0, 1, 0, 0]}), '2.5s/3 Hits')
        rows = [{'title': title, 'icdtag': tag, 'icdtype': kind} for title, tag, kind in (
            ('A', 'Skill', '10s'), ('B', 'none', ''), ('C', 'Skill', '2s'), ('D', 'none', ''), ('E', 'Skill', '10s'))]
        self.assertEqual([row['title'] for row in _group_icd(rows)], ['A', 'E', 'B', 'C', 'D'])

    def test_talent_effects_signals(self):
        from talentEffects import talent_effects
        skills = [
            {'Id': 1, 'NameTextMapHash': 'Normal Attack: Strike', 'ProudSkillGroupId': 11, 'DescTextMapHash': 'Hits.'},
            {'Id': 2, 'NameTextMapHash': 'Flame Dance', 'ProudSkillGroupId': 12,
             'DescTextMapHash': "Summons '''Ember Ring''' and enters {LINK#N1}Nightsoul's Blessing{/LINK}."},
            {'Id': 9, 'NameTextMapHash': 'Inferno', 'ProudSkillGroupId': 19, 'DescTextMapHash': 'Explodes.'},
            {'Id': 50, 'NameTextMapHash': 'Other Skill', 'DescTextMapHash': "{LINK#N2}Nightsoul's Blessing{/LINK}"},
        ]
        proud = [{'ProudSkillGroupId': 12, 'Level': 1, 'OpenConfig': 'X_SkillUpgrade_2'},
                 {'ProudSkillGroupId': 19, 'Level': 1, 'OpenConfig': 'X_SkillUpgrade_9'},
                 {'ProudSkillGroupId': 21, 'Level': 1, 'NameTextMapHash': 'A1', 'DescTextMapHash': 'Inferno DMG +20%.'},
                 {'ProudSkillGroupId': 22, 'Level': 1, 'NameTextMapHash': 'A4', 'DescTextMapHash': 'In Nightsoul\'s Blessing, gain ATK.'}]
        talents = [{'TalentId': 101, 'NameTextMapHash': 'C1', 'DescTextMapHash': 'The Ember Ring lasts longer.'},
                   {'TalentId': 102, 'NameTextMapHash': 'C2', 'DescTextMapHash': 'Buff.', 'OpenConfig': 'X_C2'},
                   {'TalentId': 103, 'NameTextMapHash': 'C3', 'DescTextMapHash': 'Level up.', 'OpenConfig': 'X_C3'},
                   {'TalentId': 104, 'NameTextMapHash': 'C4', 'DescTextMapHash': 'Uses {LINK#S1}Strike{/LINK}.'},
                   {'TalentId': 105, 'NameTextMapHash': 'C5', 'DescTextMapHash': 'Faster.', 'OpenConfig': 'X_C5'},
                   {'TalentId': 106, 'NameTextMapHash': 'C6', 'DescTextMapHash': 'Shared.', 'OpenConfig': 'X_C6'}]
        configs = {
            'X_SkillUpgrade_2': [{'$type': 'ModifyAbility', 'abilityName': 'Ring'}, {'$type': 'ModifyAbility', 'abilityName': 'Both'}],
            'X_SkillUpgrade_9': [{'$type': 'ModifyAbility', 'abilityName': 'Both'}],
            'X_C2': [{'$type': 'ModifyAbility', 'abilityName': 'Ring', 'paramSpecial': 'Duration'}],
            'X_C3': [{'$type': 'AddTalentExtraLevel', 'talentIndex': 9}],
            'X_C5': [{'$type': 'ModifySkillCD', 'skillID': 2}],
            'X_C6': [{'$type': 'UnlockTalentParam', 'abilityName': 'Both'}],
        }
        depot = {'Skills': [1, 2], 'EnergySkill': 9, 'InherentProudSkillOpens': [{'ProudSkillGroupId': 21}, {'ProudSkillGroupId': 22}],
                 'Talents': [101, 102, 103, 104, 105, 106]}
        passives, constellations = talent_effects(depot, skills, proud, talents, configs)
        # A4's term is linked by another character's skill too, and C6's ability belongs to two skills.
        self.assertEqual(passives, {'9': [['A1', 1]]})
        self.assertEqual(constellations, {'1': [['C4', 4]], '2': [['C1', 1], ['C2', 2], ['C5', 5]], '9': [['C3', 3]]})

    def test_icon_compositing_and_redirects(self):
        from PIL import Image
        tool = self.character_tool()
        Image.new('RGBA', (2, 2), (255, 0, 0, 128)).save(self.work / 'Icon.png')
        Image.new('RGBA', (4, 4), (0, 0, 255, 255)).save(self.work / 'Talent Pyro.png')
        tool['processIcon']('Icon', 'Talent', 'Test: Icon?', 'Icons')
        with Image.open(self.output / 'Images' / 'Icons' / 'Test Icon.png') as image:
            self.assertEqual(image.getpixel((0, 0)), (0, 0, 255, 255))
            self.assertEqual(image.getpixel((1, 1)), (128, 0, 127, 255))
        self.assertIn('#REDIRECT [[File:Test Icon.png]]', self.read_output('Redirects/Test Icon.png.wikitext'))

    def test_character_skill_omitted_cooldown_matches_zero(self):
        tool = self.character_tool()
        parse_skill = tool['parse_skill']
        expected = parse_skill(1, '1.0', 'Normal Attack', {})
        skill = tool['skillexcel'][0]
        del skill['CdTime']
        self.assertEqual(parse_skill(1, '1.0', 'Normal Attack', {}), expected)
        skill['CdTime'] = 10
        self.assertIn('|CD            = 10s', parse_skill(1, '1.0', 'Normal Attack', {}))

    def test_lua_serialization_and_capitalization(self):
        module = importlib.import_module('utils.misc')
        self.assertEqual(module.dict_to_table({'a"b': ['x"y', 2], 'nested': {'n': 3}}),
                         '{\n\t["a\\"b"] = {"x\\"y", 2},\n\t["nested"] = {\n\t\t["n"] = 3,\n\t},\n}')
        self.write_json(self.excel / 'one.json', {'camelCase': [{'innerKEY': 1}], 'UPPER': 2, '': 3})
        self.write_json(self.excel / 'two.json', {'otherKey': 4})
        module.capkeys()
        self.assertEqual(json.loads((self.excel / 'one.json').read_text()), {'Camelcase': [{'Innerkey': 1}], 'UPPER': 2, '': 3})
        self.assertEqual(json.loads((self.excel / 'two.json').read_text()), {'Otherkey': 4})

    def test_bounty_output(self):
        self.write_json(self.excel / 'HuntingV2MonsterBundleExcelConfigData.json', [{
            'Id': 1, 'MonsterId': 5, 'MechanismTitle1TextMapHash': 'Mechanism', 'MechanismTitle2TextMapHash': 123,
            'MechanismDesc1TextMapHash': 'Description 5%', 'NewsTextTextMapHash': 'At {0}.',
            'TraitTextTextMapHash': 'a<br />Invulnerability to Pyro damage<br />c<br />d<br />DEF decreased ',
        }])
        self.write_json(self.excel / 'HuntingV2RegionExcelConfigData.json', [
            {'Id': 1, 'MOLHJPBEIKK': [1], 'RegionInfoTextMapHash': 'First'},
            {'Id': 2, 'MOLHJPBEIKK': [1], 'RegionInfoTextMapHash': 'Last', 'CityId': 3},
        ])
        self.write_json(self.excel / 'MonsterExcelConfigData.json', [{'Id': 5, 'DescribeName': 'Enemy'}])
        self.write_json(self.excel / 'CityConfigData.json', [{'CityId': 3, 'CityNameTextMapHash': 'Natlan'}])
        importlib.import_module('utils.hunting').parse_hunting_v2()
        self.assertEqual(self.read_output('Bounties_V2_Output.wikitext'), """==Natlan==
{{Bounty
|enemy      = Enemy
|difficulty = Player's Choice
|strength   = Immune to {{Color|Pyro damage}};[[Mechanism]]: Description 5<nowiki>%</nowiki>
|weakness   = {{Color|DEF}} decreased by '''120<nowiki>%</nowiki>'''.
|desc       = At Last.
|notes      = 
}}
""")

    def test_bounty_output_list_format(self):
        self.write_json(self.excel / 'HuntingV2MonsterBundleExcelConfigData.json', [{
            'Id': 1, 'MonsterId': 5, 'MechanismTitle1TextMapHash': 'Mechanism',
            'MechanismDesc1TextMapHash': 'Description', 'NewsTextTextMapHash': 'At {0}.',
            'TraitTextTextMapHash': 'Traits: <br><ul><li> Invulnerability to Geo DMG </li><br>Weakness:<br><li> Pyro RES decreased</li></ul>',
        }])
        self.write_json(self.excel / 'HuntingV2RegionExcelConfigData.json', [
            {'Id': 1, 'CenterPosList': [1.5, 2.5], 'GKBGLPFNIHO': [1], 'RegionInfoTextMapHash': 'Region'},
        ])
        self.write_json(self.excel / 'MonsterExcelConfigData.json', [{'Id': 5, 'DescribeName': 'Enemy'}])
        self.write_json(self.excel / 'CityConfigData.json', [])
        importlib.import_module('utils.hunting').parse_hunting_v2()
        output = self.read_output('Bounties_V2_Output.wikitext')
        self.assertIn('|strength   = Immune to {{Color|Geo DMG}};[[Mechanism]]: Description', output)
        self.assertIn("|weakness   = {{Color|Pyro RES}} decreased by '''120<nowiki>%</nowiki>'''.", output)
        self.assertIn('|desc       = At Region.', output)

    def test_cooking_data_duplicate_ids(self):
        self.write_json(self.excel / 'CookRecipeExcelConfigData.json', [
            {'Id': 1, 'NameTextMapHash': 'Old', 'QteParam': '0.1,0.2'},
            {'Id': 1, 'NameTextMapHash': 'New', 'QteParam': '0.5,0.17'},
        ])
        importlib.import_module('utils.cooking').parse_cooking_qte()
        text = self.read_output('Manual_Cooking_data.lua')
        self.assertTrue(text.startswith('--[=[<%-- [PAGE_INFO]\n    pageTitle = #Module:Manual Cooking/data#\n[END_PAGE_INFO] --%>--]=]\n'))
        self.assertNotIn('Old', text)
        self.assertIn('["New"] = {\n\t\t["center"] = 0.5,\n\t\t["width"] = 0.17,', text)

    def test_blessing_targets_duplicates_and_fallback(self):
        self.write_json(self.excel / 'BlessingScanExcelConfigData.json', [
            {'TypeId': 1, 'RefId': 5, 'ScanType': 'BLESSING_SCAN_TYPE_MONSTER'},
            {'TypeId': 1, 'RefId': 8, 'ScanType': 'BLESSING_SCAN_TYPE_GATHER'},
        ])
        self.write_json(self.excel / 'MonsterExcelConfigData.json', [
            {'DescribeId': 5, 'DescribeName': 'Enemy'},
            {'DescribeId': 5, 'DescribeName': 'Enemy'},
        ])
        self.write_json(self.excel / 'GadgetExcelConfigData.json', [{'Id': 8, 'InteractNameTextMapHash': 'Plant'}])
        self.write_json(self.excel / 'AnimalDescribeExcelConfigData.json', [])
        self.write_json(self.excel / 'BlessingScanTypeExcelConfigData.json', [{'TypeNameTextMapHash': 'Targets', 'TypeId': 1}])
        module = importlib.import_module('utils.blessingscan')
        self.assertEqual(module.ls_blessing_scan_targets(1), ['Enemy', 'Enemy', 'Plant'])
        module.parse_blessing_scan()
        self.assertTrue(self.stdout.getvalue().startswith('==Targets==\n'))
        self.assertEqual(self.stdout.getvalue().count('Enemy\n'), 1)

    def test_enemy_tables_filtering_and_section_order(self):
        module = importlib.import_module('utils.enemies')
        def monster(id, name):
            return {'Id': id, 'DescribeName': name, 'HpBase': 13.584, 'AttackBase': 12.56,
                    'PropGrowCurves': [{'GrowCurve': 'GROW_CURVE_HP'}, {'GrowCurve': 'GROW_CURVE_ATTACK'}, {}],
                    'CombatConfigHash': 0, 'MonsterName': 'Test'}
        self.write_json(self.excel / 'MonsterExcelConfigData.json', [
            monster(1, 'Old ID'), monster(2, 'Old name'), monster(3, 'New'), monster(4, ''),
        ])
        self.write_json(self.old / 'MonsterExcelConfigData.json', [
            {'Id': 1, 'DescribeName': 'Old name'}, {'Id': 0, 'DescribeName': ''},
        ])
        self.write_json(self.work / 'BinOutput' / 'Monster' / '3.json', {
            'combat': {'property': {'weight': 10, 'endureType': 'Monster_Slime'}},
        })
        module.parse_new_enemies_2()
        text = self.read_output('New_Enemies_Output.wikitext')
        self.assertNotIn('Old', text)
        self.assertEqual(text.count('{{Enemy|New|20}}'), 4)
        self.assertIn('{{Enemy|New|20}} || 10', text)
        self.assertIn('{{Enemy|New|20}} || Slime', text)
        self.assertLess(text.index('HP ---'), text.index('ATK ---'))
        self.assertLess(text.index('ATK ---'), text.index('Weight ---'))
        self.assertLess(text.index('Weight ---'), text.index('Endure Type ---'))

    def test_new_enemy_pages_against_raw_revision_rows(self):
        module = importlib.import_module('utils.enemies')
        def monster(id, describe, name):
            return {'Id': id, 'DescribeId': describe, 'DescribeName': name, 'HpBase': 13.584, 'AttackBase': 12.56,
                    'PropGrowCurves': [{'GrowCurve': 'GROW_CURVE_HP'}, {'GrowCurve': 'GROW_CURVE_ATTACK'}, {}],
                    'FireSubHurt': 0.1, 'GrassSubHurt': 0.1, 'WaterSubHurt': 0.1, 'ElecSubHurt': 0.1,
                    'WindSubHurt': 0.1, 'IceSubHurt': 0.1, 'RockSubHurt': 0.1, 'PhysicalSubHurt': 0.1,
                    'HpDrops': [], 'KillDropId': 22010010}
        self.write_json(self.excel / 'MonsterExcelConfigData.json', [
            monster(1, 10, 'Old'), monster(2, 10, 'Old'), monster(3, 30, 'New'), monster(4, 30, 'New'),
        ])
        self.write_json(self.excel / 'MonsterDescribeExcelConfigData.json', [
            {'Id': 10, 'NameTextMapHash': 'Old', 'Icon': 'Missing'}, {'Id': 30, 'NameTextMapHash': 'New', 'Icon': 'Missing'},
        ])
        self.write_json(self.excel / 'AnimalCodexExcelConfigData.json', [])
        old = module.old_monsters([{'id': 1, 'describeId': 10}, {'id': 0}])
        self.assertEqual(old, ({1}, {'Old'}))
        with self.assertRaisesRegex(ValueError, 'no readable id'):
            module.old_monsters([{'ABCDEFGHIJK': 1}])

        module.parse_new_enemies(types.SimpleNamespace(ver='7.2'), lambda name: name, old, icons=False, new_names_only=True)
        pages = sorted(path.name for path in (self.output / 'Enemies').iterdir())
        self.assertEqual(pages, ['New.wikitext'])
        self.assertIn('{{Change History|7.2}}', self.read_output('Enemies/New.wikitext'))
        self.assertFalse((self.output / 'Images').exists())
        self.assertFalse((self.output / 'Redirects').exists())

        from setupData import game_version
        self.assertEqual(game_version('CNRELWin7.1.0_R48652077_S48511369'), (7, 1))
        self.assertIsNone(game_version('Edit README.md'))

        shutil.rmtree(self.output)
        with patch.object(module, 'write_enemy_stats') as stats:
            self.assertEqual(module.parse_enemies(types.SimpleNamespace(ver='7.2'), lambda name: name, [4, 3, 1],
                                                  icons=False, stats_file='Enemy Stats.wikitext'), 2)
        self.assertEqual(sorted(path.name for path in (self.output / 'Enemies').iterdir()), ['New.wikitext', 'Old.wikitext'])
        self.assertEqual([row['Id'] for row in stats.call_args.args[0]], [1, 3, 4])
        self.assertEqual(stats.call_args.args[1], 'Enemy Stats.wikitext')
        with self.assertRaisesRegex(ValueError, 'Not named enemies in the active dataset: 9'):
            module.parse_enemies(types.SimpleNamespace(ver='7.2'), lambda name: name, [1, 9], icons=False)

    def test_enemy_version_options_and_comparison(self):
        from enemyList import added_monsters, version_options
        from setupData import game_version
        revisions = [{'commit': commit, 'title': title, 'date': '2026-11-01T00:00:00Z'} for commit, title in (
            ('d', 'CNRELWin7.3.0_R2'), ('c', 'CNRELWin7.2.0_R2'), ('b', 'CNRELWin7.2.0_R1'),
            ('x', 'Edit README.md'), ('a', 'CNRELWin7.1.0_R3'), ('z', 'CNRELWin7.1.0_R1'),
        )]
        options, older = version_options(revisions, 'b', game_version)
        self.assertEqual(older, 'a')
        self.assertEqual([option['value'] for option in options], ['current', 'd', 'c', 'a'])
        self.assertEqual(options[0]['label'], 'Active dataset (7.2)')

        rows = [{'Id': 1, 'DescribeName': 'Old'}, {'Id': 2, 'DescribeName': 'Old'}, {'Id': 3, 'DescribeName': 'New'},
                {'Id': 4, 'DescribeName': 'New'}, {'Id': 5, 'DescribeName': 'Later'}, {'Id': 6, 'DescribeName': 123}]
        older_build, newer_build = ({1}, {'Old'}), ({1, 2, 3, 4, 6}, {'Old', 'New'})
        self.assertEqual([row['Id'] for row in added_monsters(rows, older_build, newer_build)], [2, 3, 4])
        self.assertEqual([row['Id'] for row in added_monsters(rows, older_build, newer_build, True)], [3])
    def test_enemy_config_by_readable_name_and_string_hash(self):
        module = importlib.import_module('utils.enemies')
        self.write_json(self.work / 'BinOutput' / 'Monster' / 'Aahigaru_Male_01.json', {
            'combat': {'property': {'weight': 50, 'endureType': 'Monster_Minion'}},
        })
        monster = {'Id': 25050301, 'DescribeName': 'Aahigaru', 'MonsterName': 'Aahigaru_Male_01',
                   'CombatConfigHash': '15783791637045877499'}
        self.assertEqual(module.parse_enemy_stats_weight(monster), '|-\n| {{Enemy|Aahigaru|20}} || 50')
        self.assertEqual(module.parse_enemy_stats_enduretype(monster), '|-\n| {{Enemy|Aahigaru|20}} || Minion')

    def test_scrambled_monster_config(self):
        from utils.monsterConfig import monster_property
        scrambled = {'AAAAAAAAAAA': {'BBBBBBBBBBB': {'CCCCCCCCCCC': 'Monster_TauntLevel_1', 'DDDDDDDDDDD': 3}},
                     'EEEEEEEEEEE': {'FFFFFFFFFFF': {'GCOKCICMHFH': 'Monster_Grunt_Humanoid', 'BEHGCPKMLNN': 75,
                                                     'XXXXXXXXXXX': True, 'YYYYYYYYYYY': 9}}}
        self.assertEqual(monster_property(scrambled), {'weight': 75, 'endureType': 'Monster_Grunt_Humanoid'})
        renamed = {'EEEEEEEEEEE': {'FFFFFFFFFFF': {'ZZZZZZZZZZZ': 'Monster_Slime', 'QQQQQQQQQQQ': 40, 'RRRRRRRRRRR': True}}}
        self.assertEqual(monster_property(renamed), {'endureType': 'Monster_Slime', 'weight': 40})
        self.assertEqual(monster_property({'combat': {'property': {'weight': 10}}}), {'weight': 10})
        partly = {'combat': {'property': {'endureType': 'Monster_Slime', 'QQQQQQQQQQQ': 40}}}
        self.assertEqual(monster_property(partly), {'endureType': 'Monster_Slime', 'weight': 40, 'QQQQQQQQQQQ': 40})
        self.assertIsNone(monster_property({'common': {'x': {'y': 'Monster_Slime'}}}))
        self.assertIsNone(monster_property({}))

    def test_scrambled_binoutput_keys_are_learned_from_values(self):
        import binKeys
        readable_root, scrambled_root = self.work / 'readable', self.work / 'scrambled'
        readable = {'combat': {'property': {'weight': 0.1, 'endureType': 'Monster_Slime'}},
                    'abilities': [{'abilityName': 'Fire', '$type': 'ConfigAbility'}, {'abilityName': 'Ice', '$type': 'ConfigAbility'}],
                    'name': 'Slime'}
        # Scrambled copies spell floats at float32 precision and write default fields the readable copy omits.
        scrambled = {'AAAAAAAAAAA': {'BBBBBBBBBBB': {'CCCCCCCCCCC': 0.10000000149011612, 'DDDDDDDDDDD': 'Monster_Slime',
                                                    'EEEEEEEEEEE': False}},
                     'FFFFFFFFFFF': [{'GGGGGGGGGGG': 'Fire', '$type': 'HHHHHHHHHHH'}, {'GGGGGGGGGGG': 'Ice', '$type': 'HHHHHHHHHHH'}],
                     'name': 'Slime'}
        for root, data in ((readable_root, readable), (scrambled_root, scrambled)):
            (root / 'Avatar').mkdir(parents=True)
            self.write_json(root / 'Avatar' / 'ConfigAvatar_Slime.json', data)
        self.assertTrue(binKeys.looks_scrambled(scrambled_root))
        self.assertFalse(binKeys.looks_scrambled(readable_root))
        result = binKeys.deobfuscate(readable_root, scrambled_root)
        self.assertEqual((result['translated'], result['remaining']), (7, 1))
        with (scrambled_root / 'Avatar' / 'ConfigAvatar_Slime.json').open(encoding='utf-8') as file:
            self.assertEqual(json.load(file), {
                'combat': {'property': {'weight': 0.10000000149011612, 'endureType': 'Monster_Slime', 'EEEEEEEEEEE': False}},
                'abilities': [{'abilityName': 'Fire', '$type': 'ConfigAbility'}, {'abilityName': 'Ice', '$type': 'ConfigAbility'}],
                'name': 'Slime'})
        # A learned name never replaces a field that already exists in the same object.
        self.assertEqual(binKeys.translate({'AAAAAAAAAAA': 1, 'combat': 2}, {'AAAAAAAAAAA': 'combat'}, {}),
                         {'AAAAAAAAAAA': 1, 'combat': 2})

    def test_fishing_points(self):
        self.write_json(self.excel / 'FishPoolExcelConfigData.json', [
            {'Id': 5, 'CityId': 1, 'PoolNameTextMapHash': 'Lake', 'PoolDescTextMapHash': 'Calm', 'MaxNum': 4, 'StockList': [7, 8],
             'StockLimitList': [{'StockType': 'FISH_STOCK_TYPE_DAY', 'MinNum': 2, 'MaxNum': 3},
                                {'StockType': 'FISH_STOCK_TYPE_NIGHT', 'MinNum': 1, 'MaxNum': 1}]},
            {'Id': 6, 'CityId': 1, 'PoolNameTextMapHash': 'Lake'},
            {'Id': 1, 'PoolNameTextMapHash': 'Test'}])
        self.write_json(self.excel / 'FishExcelConfigData.json', [{'Id': 1, 'ItemId': 'Koi'}, {'Id': 2, 'ItemId': 'Koi', 'FishCateId': 3},
                                                                 {'Id': 3, 'ItemId': 'Medaka'}])
        self.write_json(self.excel / 'FishStockExcelConfigData.json', [
            {'Id': 7, 'FishWeight': {'2': 1, '1': 1}, 'Type': 'FISH_STOCK_TYPE_ANY'},
            {'Id': 8, 'FishWeight': {'3': 1}, 'Type': 'FISH_STOCK_TYPE_NIGHT'}])
        self.write_json(self.excel / 'CityConfigData.json', [{'CityId': 1, 'CityNameKey': 'Mondstadt', 'Icon': 'UI_City'}])
        self.write_json(self.excel / 'WorldAreaConfigData.json', [])
        fishing = importlib.import_module('utils.fishing')
        self.assertEqual(fishing.fishing_points(), {5: 'Lake (1)', 6: 'Lake (2)'})
        text = fishing.fishing_point_pages([5])['Fishing Point/Lake (1)']
        self.assertIn('|region        = Mondstadt\n', text)
        self.assertIn('|day           = Koi; Ornamental Koi\n', text)
        self.assertIn('|night         = Koi; Medaka; Ornamental Koi\n', text)
        self.assertIn('|total         = 3-4\n', text)

    def test_fish_weights(self):
        fishing = importlib.import_module('utils.fishing')
        pools = [{'Id': 5, 'CityId': 1, 'PoolNameTextMapHash': 'Lake', 'StockList': [7, 8]},
                 {'Id': 6, 'CityId': 1, 'PoolNameTextMapHash': 'Pond', 'StockList': [9]},
                 {'Id': 1, 'PoolNameTextMapHash': 'Event', 'StockList': [10]}]
        fish = [{'Id': 1, 'ItemId': 'Koi'}, {'Id': 2, 'ItemId': 'Koi', 'FishCateId': 1}, {'Id': 3, 'ItemId': "Angler's Fish"}]
        stocks = [{'Id': 7, 'FishWeight': {'2': 12, '1': 200}}, {'Id': 8, 'FishWeight': {'1': 200, '3': ''}},
                  {'Id': 9, 'FishWeight': {'1': 50, '3': 300}}, {'Id': 10, 'FishWeight': {'1': 100}}]
        weights = fishing.fish_weights(pools, stocks, fish)
        self.assertEqual(list(weights.items()), [('Koi', 200), ("Angler's Fish", 300), ('Ornamental Koi', 12)])
        self.assertIn("\t['Angler\\'s Fish'] = 300,\n", fishing.fish_weights_lua(weights))

    def test_character_data_materials(self):
        charasc = importlib.import_module('utils.charasc')
        costs = lambda *items: {'CostItems': [{'Id': item, 'Count': count} for item, count in items]}
        proud = {1: [{'Level': 1}, {'Level': 2, **costs(('Teachings of Order', 3), ('Scroll', 6))},
                     *({'Level': level, **costs(('Philosophies of Order', 4), ('Curse', 12), ('Boss', 1))} for level in (7, 8, 9)),
                     {'Level': 10, **costs(('Philosophies of Order', 16), ('Curse', 12), ('Boss', 1), (charasc.CROWN, 1))}]}
        self.assertEqual(charasc._talent_materials(1, proud),
                         {'books': 'Order', 'boss': 'Boss', 'common': ['Scroll', 'Curse'], 'bossCost': 1})
        gem = ('Varunada Lazurite Sliver', 'Varunada Lazurite Fragment', 'Transoceanic Chunk', 'Lumidouce Bell', 'Weekly')
        rows = [{'PromoteLevel': 0}, {'PromoteLevel': 1, **costs((gem[0], 1), (gem[3], 3), ('Transoceanic Pearl', 3))},
                {'PromoteLevel': 2, **costs((gem[1], 3), ('Weekly', 2), (gem[3], 10), (gem[2], 15)),
                 'AddProps': [{'PropType': 'FIGHT_PROP_CRITICAL', 'Value': 0.048}]},
                {'PromoteLevel': 3, **costs((gem[1], 6), ('Weekly', 4), (gem[3], 20), ('Xenochromatic Crystal', 3)),
                 'AddProps': [{'PropType': 'FIGHT_PROP_CRITICAL', 'Value': 0.096}]}]
        avatar = {'PropGrowCurves': [{'Type': 'FIGHT_PROP_BASE_HP', 'GrowCurve': 'GROW_CURVE_HP_S5'}]}
        with patch.object(charasc, '_load', return_value = [{'NameTextMapHash': gem[3], 'MaterialType': 'MATERIAL_EXCHANGE'}]):
            entry = charasc.ascension_data({'Neuvillette': (avatar, rows)})['Neuvillette']
        self.assertEqual((entry['gem'], entry['boss'], entry['local'], entry['common'], entry['spec_base']),
                         ('Varunada Lazurite', 'Weekly', gem[3], ['Transoceanic Pearl', 'Transoceanic Chunk', 'Xenochromatic Crystal'], 4.8))

    def test_bounty_traits(self):
        hunting = importlib.import_module('utils.hunting')
        listed = ('According to intelligence, the target has the following special traits: <br><ul><li> Invulnerability to '
                  'Geo DMG </li><br>Additionally, the target has the following weakness:<br><li> Pyro RES decreased</li></ul>')
        self.assertEqual(hunting._traits(listed), ('Immune to {{Color|Geo DMG}}',
                                                   "{{Color|Pyro RES}} decreased by '''120<nowiki>%</nowiki>'''."))
        self.assertEqual(hunting._traits('Nothing known.'), ('', ''))

    def test_cooking_file_name(self):
        cooking = importlib.import_module('utils.cooking')
        self.assertEqual(cooking.qte_file_name(0.29, 0.57), 'Manual Cooking C-29 W-57.png')

    def test_textmap_merging_and_cleanup(self):
        textmaps = self.work / 'TextMap'
        for lang in LANGS:
            if lang != 'RU' and lang != 'TH':
                self.write_json(textmaps / f'TextMap{lang}.json', {'original': lang})
                self.write_json(textmaps / f'TextMap_Medium{lang}.json', {'medium': lang})
        for lang in ('RU', 'TH'):
            for suffix in ('_0', '_1'):
                self.write_json(textmaps / f'TextMap{lang}{suffix}.json', {suffix: lang})
                self.write_json(textmaps / f'TextMap_Medium{lang}{suffix}.json', {f'medium{suffix}': lang})
        self.write_json(textmaps / 'TextMap_MediumEN.json', {
            'original': 'Override',
            'description': r'Line\n<color=#FF9999FF>Hot</color><color=#3399CCFF>Buzz</color>',
        })
        runpy.run_path(str(ROOT / 'textMapCleanup.py'))
        self.assertEqual(json.loads((textmaps / 'TextMapEN.json').read_text(encoding='utf-8')), {
            'original': 'Override',
            'description': 'Line<br>{{Color|Hot}}{{Color|buzz|Buzz}}',
        })
        self.assertEqual(json.loads((textmaps / 'TextMapFR.json').read_text()), {'original': 'FR', 'medium': 'FR'})
        self.assertEqual(json.loads((textmaps / 'TextMapRU.json').read_text()), {
            '_0': 'RU', '_1': 'RU', 'medium_0': 'RU', 'medium_1': 'RU',
        })
        self.assertFalse((textmaps / 'TextMapRU_Temp1.json').exists())

    def test_textmap_merging_gura_layout(self):
        textmaps = self.work / 'TextMap'
        for lang in LANGS:
            if lang != 'TH':
                self.write_json(textmaps / f'TextMap{lang}.json', {'1': 'main', '2': 'main'})
                self.write_json(textmaps / f'TextMap_Medium{lang}.json', {'2': 'medium'})
        self.write_json(textmaps / 'TextMapTH_1.json', {'1': 'part1', '2': 'part1'})
        self.write_json(textmaps / 'TextMapTH_2.json', {'2': 'part2', '3': 'part2'})
        self.write_json(textmaps / 'TextMap_MediumTH.json', {'3': 'medium'})
        self.write_json(textmaps / 'TextMapTH_Temp1.json', {'4': 'stale leftover'})
        runpy.run_path(str(ROOT / 'textMapCleanup.py'))
        self.assertEqual(json.loads((textmaps / 'TextMapRU.json').read_text()), {'1': 'main', '2': 'medium'})
        self.assertEqual(json.loads((textmaps / 'TextMapTH.json').read_text()), {'1': 'part1', '2': 'part2', '3': 'medium'})

    def test_misc_cli_redirects(self):
        with patch.object(sys, 'argv', ['parseMisc.py', '--redirectfromstr', 'Source%%%Target\nOther%%%Target']):
            runpy.run_path(str(ROOT / 'parseMisc.py'))
        self.assertIn('#REDIRECT [[Target]]', self.read_output('Redirects/Source.wikitext'))
        self.assertIn('#REDIRECT [[Target]]', self.read_output('Redirects/Other.wikitext'))

    def test_github_source_requires_preparation_and_preserves_local_mode(self):
        from dataSource import load_config
        path = self.work / 'scriptconfig.json'
        config = load_config()
        self.assertEqual(config['RepoPath'], str(self.work))
        config['DataSource'] = 'github'
        self.write_json(path, config)
        with self.assertRaisesRegex(FileNotFoundError, 'quickSetup'):
            load_config()
        node = subprocess.run(
            ['node', '-e', 'require("./leo/config")'], cwd=ROOT, capture_output=True, text=True,
        )
        self.assertNotEqual(node.returncode, 0)
        self.assertIn('quickSetup', node.stderr)
        config['DataSource'] = 'invalid'
        self.write_json(path, config)
        with self.assertRaisesRegex(ValueError, 'DataSource'):
            load_config()

    def make_repository(self, name, files):
        upstream = self.work / name
        for relative, value in files.items():
            target = upstream / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            self.write_json(target, value)

        def git(*args):
            return subprocess.run(['git', '-C', str(upstream), *args], check=True, capture_output=True, text=True)

        def commit(message):
            git('add', '-A')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-m',
                message + '\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>')

        git('init', '-b', 'main')
        commit('Initial fixture')
        return upstream, commit

    def excel_fixture(self, avatar, textmaps, extra=None):
        files = {f'ExcelBinOutput/{name}ExcelConfigData.json': [] for name in (
            'Material', 'Npc', 'HomeWorldFurniture', 'Weapon', 'Reliquary', 'Monster',
            'MonsterDescribe', 'MonsterAffix', 'Reward', 'GCGChar', 'GCGDeckCard')}
        files['ExcelBinOutput/AvatarExcelConfigData.json'] = avatar
        files.update({f'TextMap/{name}': value for name, value in textmaps.items()})
        files.update(extra or {})
        return files

    def dimbreath_maps(self):
        maps = {}
        for lang in LANGS:
            if lang in ('RU', 'TH'):
                for suffix in ('_0', '_1'):
                    maps[f'TextMap{lang}{suffix}.json'] = {'101': 'Example'}
                    maps[f'TextMap_Medium{lang}{suffix}.json'] = {}
            else:
                maps[f'TextMap{lang}.json'] = {'101': 'Example'}
                maps[f'TextMap_Medium{lang}.json'] = {'101': '<color=#FF9999FF>Example</color>'}
        return maps

    def test_keep_versions_prepares_previous_version_and_prunes(self):
        import setupData
        from dataSource import SOURCES, data_root, load_config
        from webui.datasets import prepared_datasets

        upstream, commit = self.make_repository('dimbreath', self.excel_fixture(
            [{'id': 1, 'nameTextMapHash': 101}], self.dimbreath_maps(),
            {'BinOutput/Monster/Aahigaru_Male_01_25050301.json': {'combat': {'property': {'weight': 50}}}}))
        head = lambda: subprocess.run(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], check=True,
                                      capture_output=True, text=True).stdout.strip()
        builds = [('CNRELWin7.1.0_R1', head())]
        for build, avatar in (('CNRELWin7.1.0_R2', 2), ('CNRELWin7.2.0_R3', 3)):
            self.write_json(upstream / 'ExcelBinOutput' / 'AvatarExcelConfigData.json', [{'id': avatar, 'nameTextMapHash': 101}])
            commit(build)
            builds.append((build, head()))
        listing = [{'commit': sha, 'title': title, 'date': ''} for title, sha in reversed(builds)]

        path = self.work / 'scriptconfig.json'
        config = dict(load_config(), DataSource='remote', BinOutputSource='dimbreath',
                      ExcelRevision=builds[0][1], BinOutputRevision=builds[0][1])
        self.write_json(path, config)
        with patch.dict(SOURCES['dimbreath'], url=upstream.as_uri()), \
                patch.object(setupData, 'list_revisions', return_value=listing):
            setupData.prepare(path)  # an old build that pruning must remove
            del config['ExcelRevision'], config['BinOutputRevision']
            self.write_json(path, config)
            setupData.prepare(path, keep_versions=2)
            cache = data_root(path) / 'AnimeGameData'
            self.assertEqual(sorted(item.name[:40] for item in (cache / 'datasets').iterdir()),
                             sorted([builds[1][1], builds[2][1]]))
            self.assertEqual([item.name for item in (cache / 'binoutput').iterdir()], [builds[2][1]])
            self.assertEqual(sorted(item['commit'] for item in prepared_datasets(path)['excel']),
                             sorted([builds[1][1], builds[2][1]]))
            # The removed build's worktree registration is gone, so it can be prepared again.
            self.write_json(path, dict(config, ExcelRevision=builds[0][1]))
            self.assertEqual(setupData.prepare(path).name[:40], builds[0][1])

    def test_remote_setup_split_sources_cache_and_failed_update(self):
        import setupData
        from dataSource import SOURCES, data_root, load_config

        dimbreath_maps = self.dimbreath_maps()
        dimbreath, commit_dimbreath = self.make_repository('dimbreath', self.excel_fixture(
            [{'id': 1, 'nameTextMapHash': 101}], dimbreath_maps, {
                'BinOutput/Monster/10018765187514261229.json': {'combat': {'property': {'weight': 10}}},
                'Readable/unused.json': {},
            }))
        gura_maps = {f'TextMap{lang}.json': {'101': 'Gura'} for lang in LANGS if lang != 'TH'}
        gura_maps.update({f'TextMap_Medium{lang}.json': {} for lang in LANGS})
        gura_maps.update({'TextMapTH_1.json': {'101': 'Gura'}, 'TextMapTH_2.json': {'102': 'Thai'}})
        gura, _ = self.make_repository('gura', self.excel_fixture(
            [{'id': 1, 'nameTextMapHash': 101, 'critical': 0.05000000074505806, 'combatConfigHash': '15783791637045877499'}],
            gura_maps, {
                'ExcelBinOutput/HyperLinkNameExcelConifgData.json': [{'ID': 7, 'nameTextMapHash': 101}],
                'BinOutput/Monster/Aahigaru_Male_01_25050301.json': {'combat': {'property': {'weight': 50}}},
            }))

        path = self.work / 'scriptconfig.json'
        config = load_config()
        config['DataSource'] = 'remote'
        self.write_json(path, config)
        with patch.dict(SOURCES['dimbreath'], url=dimbreath.as_uri()), patch.dict(SOURCES['gura'], url=gura.as_uri()):
            dataset = setupData.prepare(path)
            loaded = load_config()
            self.assertEqual(Path(loaded['RepoPath']), dataset)
            self.assertIn('AnimeGameData', dataset.parts)
            self.assertEqual(loaded['RepoPathOld'], str(self.work / 'old'))
            self.assertFalse((dataset / 'Readable').exists())
            self.assertFalse((dataset / 'BinOutput').exists())
            binpath = Path(loaded['BinPath'])
            self.assertIn('YuanShenResources', binpath.parts)
            self.assertEqual([item.name for item in (binpath / 'Monster').iterdir()], ['Aahigaru_Male_01_25050301.json'])
            mapped = json.loads((dataset / 'MappedExcelBinOutput_EN' / 'AvatarExcelConfigData.json').read_text())
            self.assertEqual(mapped[0]['NameTextMapHash'], '{{Color|Example}}')
            node = subprocess.run(
                ['node', '-e', 'const c = require("./leo/config"); process.stdout.write(JSON.stringify([c.RepoPath, c.BinPath]))'],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            self.assertEqual([Path(item) for item in json.loads(node.stdout)], [dataset, binpath])
            self.assertEqual(setupData.prepare(path), dataset)
            self.assertIn('already-prepared Excel', self.stdout.getvalue())
            self.assertIn('already-prepared BinOutput', self.stdout.getvalue())

            (dimbreath / 'ExcelBinOutput' / 'MaterialExcelConfigData.json').unlink()
            commit_dimbreath('Incomplete update')
            with self.assertRaises(subprocess.CalledProcessError):
                setupData.prepare(path)
            self.assertEqual(Path(load_config()['RepoPath']), dataset)
            self.assertFalse((data_root(path) / 'setup.lock').exists())

            self.write_json(dimbreath / 'ExcelBinOutput' / 'MaterialExcelConfigData.json', [])
            commit_dimbreath('Repaired update')
            updated = setupData.prepare(path)
            self.assertNotEqual(updated, dataset)
            self.assertEqual(Path(load_config()['RepoPath']), updated)

            config['ExcelRevision'] = dataset.name[:40]
            self.write_json(path, config)
            with self.assertRaisesRegex(ValueError, 'ExcelRevision'):
                load_config()
            self.assertEqual(setupData.prepare(path), dataset)
            self.assertEqual(Path(load_config()['RepoPath']), dataset)
            config['ExcelRevision'] = 'not-a-commit'
            self.write_json(path, config)
            with self.assertRaisesRegex(ValueError, 'ExcelRevision'):
                load_config()
            del config['ExcelRevision']

            config['ExcelSource'] = 'gura'
            self.write_json(path, config)
            with self.assertRaisesRegex(ValueError, 'ExcelSource'):
                load_config()
            gura_dataset = setupData.prepare(path)
            self.assertIn('YuanShenResources', gura_dataset.parts)
            textmap_th = json.loads((gura_dataset / 'TextMap' / 'TextMapTH.json').read_text(encoding='utf-8'))
            self.assertEqual(textmap_th, {'101': 'Gura', '102': 'Thai'})
            mapped = json.loads((gura_dataset / 'MappedExcelBinOutput_EN' / 'AvatarExcelConfigData.json').read_text())
            self.assertEqual(mapped[0]['NameTextMapHash'], 'Gura')
            self.assertEqual(mapped[0]['Critical'], 0.05)
            self.assertEqual(mapped[0]['CombatConfigHash'], '15783791637045877499')
            hyperlinks = json.loads((gura_dataset / 'MappedExcelBinOutput_EN' / 'HyperLinkNameExcelConifgData.json').read_text())
            self.assertEqual(hyperlinks, [{'Id': 7, 'NameTextMapHash': 'Gura'}])
            self.assertIn('Warning: AvatarSkillDepotExcelConfigData is not in this build', self.stdout.getvalue())

        config['ExcelSource'] = 'unknown'
        self.write_json(path, config)
        with self.assertRaisesRegex(ValueError, 'ExcelSource'):
            load_config()

if __name__ == '__main__':
    unittest.main()
