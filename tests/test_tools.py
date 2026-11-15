import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
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

    def character_tool(self):
        self.load_ol()
        for lang in LANGS:
            self.write_json(self.work / 'TextMap' / f'TextMap{lang}.json', {'1': 'Strike'})
        self.write_json(self.excel / 'AvatarExcelConfigData.json', [
            {'Id': 10000001, 'NameTextMapHash': 'Tester'},
        ])
        self.write_json(self.excel / 'AvatarSkillDepotExcelConfigData.json', [{
            'Id': 101, 'Skills': [1, 2], 'EnergySkill': 5,
            'InherentProudSkillOpens': [{'ProudSkillGroupId': n} for n in (11, 14, 19)],
            'Talents': list(range(101, 107)),
        }])
        self.write_json(self.excel / 'AvatarSkillExcelConfigData.json', [
            {'Id': n, 'NameTextMapHash': name, 'DescTextMapHash': 'ATK and Skill. {LINK#N7}Detail{/LINK}',
             'CdTime': 0, 'SkillIcon': 'Icon'}
            for n, name in ((1, 'Strike'), (2, 'Skill'), (5, 'Burst'))
        ])
        self.write_json(self.excel / 'ProudSkillExcelConfigData.json', [
            {'ProudSkillId': n, 'ProudSkillGroupId': n, 'NameTextMapHash': f'Passive {n}',
             'DescTextMapHash': '{LINK#S1}Strike{/LINK} {LINK#S1}Strike{/LINK}'}
            for n in (11, 14, 19)
        ])
        self.write_json(self.excel / 'AvatarTalentExcelConfigData.json', [
            {'TalentId': n, 'NameTextMapHash': f'Cons {n}',
             'DescTextMapHash': '{LINK#S2}Skill{/LINK} Burst'}
            for n in range(101, 107)
        ])
        self.write_json(self.excel / 'HyperLinkNameExcelConifgData.json', [
            {'Id': 7, 'NameTextMapHash': 'Title', 'DescTextMapHash': 'Content'},
        ])
        self.write_json(self.excel / 'FetterInfoExcelConfigData.json', [])
        with patch.object(sys, 'argv', ['parseCharKit.py', '--id', '10000001', '--ver', '1.0', '--elem', 'Pyro']):
            return runpy.run_path(str(ROOT / 'parseCharKit.py'))

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
        self.assertIn('[[ATK]] and [[Skill]]. {{Extra Effect|Detail|Title|Content}}', skill)
        self.assertIn('* {{Talent Note|ascension|1|Passive 11}}\n* {{Talent Note|ascension|2|Passive 14}}', skill)
        self.assertIn('|energyCost    = \n', skill)
        self.assertEqual(tool['passive_effects']['1'], [['Passive 11', 1], ['Passive 14', 2]])
        self.assertIn('|utility2      = Elemental Burst Level Increase', self.read_output('Tester/Constellations/C3.wikitext'))
        self.assertEqual(tool['add_wikilinks']('ATK ATK {LINK#N7}HP{/LINK}'), '[[ATK]] ATK {LINK#N7}HP{/LINK}')
        self.assertEqual(tool['parse_hyperlink']('{LINK#S1}Strike{/LINK}'), 'Strike')

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
            'Id': 1, 'MonsterId': 5, 'MechanismTitle1TextMapHash': 'Mechanism',
            'MechanismDesc1TextMapHash': 'Description', 'NewsTextTextMapHash': 'At {0}.',
            'TraitTextTextMapHash': 'a<br />Invulnerability to Pyro damage<br />c<br />d<br />DEF decreased ',
        }])
        self.write_json(self.excel / 'HuntingV2RegionExcelConfigData.json', [
            {'Id': 1, 'MOLHJPBEIKK': [1], 'RegionInfoTextMapHash': 'First'},
            {'Id': 2, 'MOLHJPBEIKK': [1], 'RegionInfoTextMapHash': 'Last'},
        ])
        self.write_json(self.excel / 'MonsterExcelConfigData.json', [{'Id': 5, 'DescribeName': 'Enemy'}])
        importlib.import_module('utils.hunting').parse_hunting_v2()
        self.assertEqual(self.read_output('Bounties_V2_Output.wikitext'), """
{{Bounty
|enemy      = Enemy
|difficulty = Player's Choice
|strength   = Immune to {{Color|Pyro}}damage;[[Mechanism]]: Description
|weakness   = {{Color|DEF}} decreased by '''120<nowiki>%</nowiki>'''.
|desc       = At Last.
|notes      = 
}}""")

    def test_cooking_data_duplicate_ids(self):
        self.write_json(self.excel / 'CookRecipeExcelConfigData.json', [
            {'Id': 1, 'NameTextMapHash': 'Old', 'QteParam': '0.1,0.2'},
            {'Id': 1, 'NameTextMapHash': 'New', 'QteParam': '0.5,0.17'},
        ])
        importlib.import_module('utils.cooking').parse_cooking_qte()
        text = self.read_output('Manual_Cooking_data.lua')
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

    def test_fishing_membership(self):
        self.write_json(self.excel / 'FishPoolExcelConfigData.json', [{'Id': 1}, {'Id': 2}])
        self.write_json(self.old / 'FishPoolExcelConfigData.json', [{'Id': 1}])
        testing = self.old.parent / 'Testing'
        testing.mkdir()
        self.write_json(testing / 'fishstock.json', [])
        importlib.import_module('utils.fimsh').parse_fishing_points()
        self.assertEqual(self.stdout.getvalue(), 'Skipping 1.\n')

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

    def test_github_setup_mapping_cache_and_failed_update(self):
        import setupData
        from dataSource import cache_path, load_config

        upstream = self.work / 'upstream'
        upstream.mkdir()
        raw = upstream / 'ExcelBinOutput'
        raw.mkdir()
        for name in ('Material', 'Npc', 'Avatar', 'HomeWorldFurniture', 'Weapon', 'Reliquary',
                     'Monster', 'MonsterDescribe', 'MonsterAffix', 'Reward', 'GCGChar', 'GCGDeckCard'):
            self.write_json(raw / f'{name}ExcelConfigData.json', [])
        self.write_json(raw / 'AvatarExcelConfigData.json', [{'Id': 1, 'NameTextMapHash': 101}])
        textmaps = upstream / 'TextMap'
        textmaps.mkdir()
        for lang in LANGS:
            if lang not in ('RU', 'TH'):
                self.write_json(textmaps / f'TextMap{lang}.json', {'101': 'Example'})
                self.write_json(textmaps / f'TextMap_Medium{lang}.json', {'101': '<color=#FF9999FF>Example</color>'})
        for lang in ('RU', 'TH'):
            for suffix in ('_0', '_1'):
                self.write_json(textmaps / f'TextMap{lang}{suffix}.json', {'101': 'Example'})
                self.write_json(textmaps / f'TextMap_Medium{lang}{suffix}.json', {})
        monster = upstream / 'BinOutput' / 'Monster'
        monster.mkdir(parents=True)
        self.write_json(monster / '1.json', {'combat': {'property': {'weight': 10}}})
        ignored = upstream / 'Readable'
        ignored.mkdir()
        (ignored / 'unused.txt').write_text('Not needed by these tools.')

        def git(*args):
            return subprocess.run(['git', '-C', str(upstream), *args], check=True, capture_output=True, text=True)

        def commit(message):
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                '-c', 'commit.gpgsign=false', 'commit', '-m',
                message + '\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>')

        git('init', '-b', 'main')
        commit('Initial fixture')
        path = self.work / 'scriptconfig.json'
        config = load_config()
        config['DataSource'] = 'github'
        self.write_json(path, config)
        with patch.object(setupData, 'GITHUB_REPOSITORY', upstream.as_uri()):
            dataset = setupData.prepare(path)
            self.assertEqual(Path(load_config()['RepoPath']), dataset)
            self.assertEqual(load_config()['RepoPathOld'], str(self.work / 'old'))
            self.assertFalse((dataset / 'Readable').exists())
            self.assertTrue((dataset / 'BinOutput' / 'Monster' / '1.json').is_file())
            mapped = json.loads((dataset / 'MappedExcelBinOutput_EN' / 'AvatarExcelConfigData.json').read_text())
            self.assertEqual(mapped[0]['NameTextMapHash'], '{{Color|Example}}')
            node = subprocess.run(
                ['node', '-e', 'process.stdout.write(require("./leo/config").RepoPath)'],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            self.assertEqual(Path(node.stdout), dataset)
            self.assertEqual(setupData.prepare(path), dataset)
            self.assertIn('already-prepared', self.stdout.getvalue())

            (raw / 'MaterialExcelConfigData.json').unlink()
            commit('Incomplete update')
            with self.assertRaises(subprocess.CalledProcessError):
                setupData.prepare(path)
            self.assertEqual(Path(load_config()['RepoPath']), dataset)
            self.assertFalse((cache_path(path) / 'setup.lock').exists())

            self.write_json(raw / 'MaterialExcelConfigData.json', [])
            commit('Repaired update')
            updated = setupData.prepare(path)
            self.assertNotEqual(updated, dataset)
            self.assertEqual(Path(load_config()['RepoPath']), updated)
            self.assertTrue((dataset / '.prepared.json').is_file())


if __name__ == '__main__':
    unittest.main()
