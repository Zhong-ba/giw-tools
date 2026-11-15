import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient

from webui.app import create_app
from webui.jobs import Job, JobManager
from webui.tools import LANGUAGES


class WebTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / 'config.json'
        self.config.write_text(json.dumps({
            'DataSource': 'local', 'RepoPath': str(self.root / 'dataset'),
            'RepoPathOld': str(self.root / 'previous'),
            'ImgPath': str(self.root / 'textures'), 'TalentBGPath': str(self.root / 'backgrounds'),
            'OutputPath': str(self.root / 'existing-output'),
        }), encoding='utf-8')
        self.dataset = self.root / 'dataset'
        maps = self.dataset / 'TextMap'
        maps.mkdir(parents=True)
        for language in LANGUAGES:
            (maps / f'TextMap{language}.json').write_text(
                json.dumps({'101': 'Ambre' if language == 'FR' else 'Amber'}), encoding='utf-8',
            )
        excel = self.dataset / 'MappedExcelBinOutput_EN'
        excel.mkdir()
        (excel / 'AvatarExcelConfigData.json').write_text(json.dumps([
            {'Id': 10000021, 'NameTextMapHash': 'Amber', 'SkillDepotId': 2101},
        ]), encoding='utf-8')
        self.jobs = self.root / 'jobs'
        self.client = TestClient(create_app(self.config, self.jobs, self.root / 'no-frontend'))
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def wait(self, job_id):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = self.client.get(f'/api/jobs/{job_id}')
            self.assertEqual(response.status_code, 200)
            job = response.json()
            if job['status'] in ('succeeded', 'failed'):
                return job
            time.sleep(.05)
        self.fail('Background job did not finish in time.')

    def test_redirect_job_preview_archive_and_path_isolation(self):
        response = self.client.post('/api/jobs', json={
            'tool_id': 'redirects', 'parameters': {'lines': 'First%%%Target\nSecond%%%Target'},
        })
        self.assertEqual(response.status_code, 202, response.text)
        job = self.wait(response.json()['id'])
        self.assertEqual(job['status'], 'succeeded', self.client.get(f"/api/jobs/{job['id']}/logs").text)
        self.assertEqual(len(job['files']), 2)
        self.assertFalse((self.root / 'existing-output').exists())
        name = job['files'][0]['path']
        preview = self.client.get(f"/api/jobs/{job['id']}/preview/{name}")
        self.assertIn('#REDIRECT [[Target]]', preview.json()['text'])
        download = self.client.get(f"/api/jobs/{job['id']}/files/{name}")
        self.assertIn('attachment', download.headers['content-disposition'])
        archive = self.client.get(f"/api/jobs/{job['id']}/archive")
        with ZipFile(io.BytesIO(archive.content)) as zipped:
            self.assertEqual(len(zipped.namelist()), 2)
        for path in ('../config.json', 'config.json', '/etc/passwd'):
            self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/files/{path}").status_code, 404)
        self.assertIn('completed successfully', self.client.get(f"/api/jobs/{job['id']}/logs").json()['text'])
        self.assertEqual(self.client.get('/api/jobs/not-a-job').status_code, 404)

    def test_schema_validation_and_browser_request_boundaries(self):
        tools = self.client.get('/api/tools').json()
        self.assertEqual({tool['id'] for tool in tools}, {'redirects', 'character-kit', 'other-languages'})
        self.assertIn('properties', tools[0]['schema'])
        for parameters in ({'lines': 'invalid'}, {'lines': 'A%%%B', 'command': 'anything'}, {'lines': '%%%Target'}):
            self.assertEqual(self.client.post('/api/jobs', json={
                'tool_id': 'redirects', 'parameters': parameters,
            }).status_code, 422)
        self.assertEqual(self.client.post('/api/jobs', json={'tool_id': 'arbitrary-script'}).status_code, 404)
        self.assertEqual(self.client.post('/api/jobs', json={
            'tool_id': 'redirects', 'parameters': {'lines': 'A%%%B'},
        }, headers={'Origin': 'https://other.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/health', headers={'Host': 'other.example'}).status_code, 400)
        self.assertEqual(self.client.get('/api/jobs').json(), [])

    def test_language_job_and_explicit_failure(self):
        success = self.client.post('/api/jobs', json={
            'tool_id': 'other-languages', 'parameters': {'text': 'Amber'},
        })
        job = self.wait(success.json()['id'])
        self.assertEqual(job['status'], 'succeeded', self.client.get(f"/api/jobs/{job['id']}/logs").text)
        result = self.client.get(f"/api/jobs/{job['id']}/preview/{job['files'][0]['path']}").json()['text']
        self.assertIn('|en       = Amber', result)
        self.assertIn('|fr       = Ambre', result)
        missing = self.client.post('/api/jobs', json={
            'tool_id': 'other-languages', 'parameters': {'text': 'Not in this dataset'},
        })
        failed = self.wait(missing.json()['id'])
        self.assertEqual(failed['status'], 'failed')
        self.assertTrue(failed['error'])
        self.assertEqual(failed['files'], [])
        self.assertIn('not found', self.client.get(f"/api/jobs/{failed['id']}/logs").json()['text'])

    def test_textmaps_load_once_per_session_and_jobs_keep_own_config(self):
        first = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'other-languages', 'parameters': {'text': 'Amber'},
        }).json()['id'])
        self.assertEqual(first['status'], 'succeeded', self.client.get(f"/api/jobs/{first['id']}/logs").text)
        self.assertIn('Loading OL', self.client.get(f"/api/jobs/{first['id']}/logs").json()['text'])
        # Proves the next job reads the already-loaded maps rather than the files.
        (self.dataset / 'TextMap' / 'TextMapFR.json').unlink()
        redirect = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'redirects', 'parameters': {'lines': 'Between%%%Target'},
        }).json()['id'])
        self.assertEqual([item['path'] for item in redirect['files']], ['Redirects/Between.wikitext'])
        second = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'other-languages', 'parameters': {'text': 'Ambre', 'input_lang': 'FR'},
        }).json()['id'])
        log = self.client.get(f"/api/jobs/{second['id']}/logs").json()['text']
        self.assertEqual(second['status'], 'succeeded', log)
        self.assertIn('already loaded', log)
        self.assertNotIn('Loading OL', log)
        self.assertEqual(len(second['files']), 1)

    def test_dataset_status_and_character_choices(self):
        dataset = self.client.get('/api/dataset').json()
        self.assertTrue(dataset['ready'])
        self.assertEqual(dataset['languages'], 15)
        self.assertEqual(self.client.get('/api/characters').json(), [
            {'id': 10000021, 'name': 'Amber', 'skill_depot': 2101},
        ])
        self.config.write_text(json.dumps({'DataSource': 'github'}), encoding='utf-8')
        status = self.client.get('/api/dataset').json()
        self.assertFalse(status['ready'])
        self.assertIn('quickSetup', status['error'])
        response = self.client.post('/api/jobs', json={
            'tool_id': 'other-languages', 'parameters': {'text': 'Amber'},
        })
        self.assertEqual(response.status_code, 409)

    def test_interrupted_job_is_reported_after_restart(self):
        root = self.root / 'recovery'
        job = Job(id=uuid4().hex, tool_id='redirects', name='Redirect Builder', status='running')
        directory = root / job.id
        directory.mkdir(parents=True)
        (directory / 'job.json').write_text(job.model_dump_json(), encoding='utf-8')
        manager = JobManager(self.config, root)
        self.addCleanup(manager.close)
        recovered = manager.get(job.id)
        self.assertEqual(recovered.status, 'failed')
        self.assertIn('server stopped', recovered.error)
        self.assertIsNotNone(recovered.finished_at)

    def test_dataset_setup_job_uses_original_profile(self):
        raw = self.dataset / 'ExcelBinOutput'
        raw.mkdir()
        for name in ('Material', 'Npc', 'Avatar', 'HomeWorldFurniture', 'Weapon', 'Reliquary',
                     'Monster', 'MonsterDescribe', 'MonsterAffix', 'Reward', 'GCGChar', 'GCGDeckCard'):
            (raw / f'{name}ExcelConfigData.json').write_text('[]', encoding='utf-8')
        (raw / 'AvatarExcelConfigData.json').write_text(
            json.dumps([{'Id': 10000021, 'NameTextMapHash': 101}]), encoding='utf-8',
        )
        maps = self.dataset / 'TextMap'
        for language in LANGUAGES:
            if language not in ('RU', 'TH'):
                (maps / f'TextMap_Medium{language}.json').write_text('{}', encoding='utf-8')
        for language in ('RU', 'TH'):
            for suffix in ('_0', '_1'):
                (maps / f'TextMap{language}{suffix}.json').write_text('{"101": "Amber"}', encoding='utf-8')
                (maps / f'TextMap_Medium{language}{suffix}.json').write_text('{}', encoding='utf-8')
        response = self.client.post('/api/dataset/setup', json={})
        self.assertEqual(response.status_code, 202, response.text)
        job = self.wait(response.json()['id'])
        self.assertEqual(job['status'], 'succeeded', self.client.get(f"/api/jobs/{job['id']}/logs").text)
        self.assertTrue((self.dataset / 'MappedToID' / 'AvatarExcelConfigData.json').is_file())
        self.assertEqual(self.client.get('/api/characters').json()[0]['name'], 'Amber')
        self.assertFalse((self.root / 'existing-output').exists())


if __name__ == '__main__':
    unittest.main()
