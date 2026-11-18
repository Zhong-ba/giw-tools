import io
import json
from pathlib import Path
import tempfile
from threading import Event
import time
import unittest
import urllib.parse
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient

from webui.app import create_app
from webui.jobs import Job, JobManager
from webui.tools import LANGUAGES, TOOLS


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
        self.assertEqual(job['progress']['stage'], 'Completed')
        self.assertEqual((job['progress']['completed'], job['progress']['total']), (1, 1))
        log_path = self.jobs / job['id'] / 'log.txt'
        log = log_path.read_text(encoding='utf-8')
        self.assertNotIn('File saved successfully:', log)
        self.assertEqual(log.count('Job completed successfully.'), 1)
        self.assertLess(log.index('Finalizing output'), log.index('completed successfully'))
        with log_path.open('a', encoding='utf-8') as file:
            file.write('BEGIN FULL LOG\n' + 'Long output\n' * 15000 + 'END FULL LOG\n')
        tail = self.client.get(f"/api/jobs/{job['id']}/logs").json()
        full = self.client.get(f"/api/jobs/{job['id']}/logs?full=true").json()
        self.assertTrue(tail['truncated'])
        self.assertNotIn('BEGIN FULL LOG', tail['text'])
        self.assertIn('END FULL LOG', tail['text'])
        self.assertFalse(full['truncated'])
        self.assertEqual(full['text'], log_path.read_bytes().decode('utf-8'))
        self.assertEqual(self.client.get('/api/jobs/not-a-job').status_code, 404)

    def test_reporting_live_progress_and_output_validation_failure(self):
        from toolLog import write_progress

        manager = JobManager(self.config, self.root / 'progress-jobs')
        entered, release, finalizing, finish = Event(), Event(), Event(), Event()
        self.addCleanup(manager.close)
        self.addCleanup(release.set)
        self.addCleanup(finish.set)

        def execute(directory):
            write_progress(directory / 'progress.json', {
                'stage': 'Writing pages', 'completed': 2, 'total': 5, 'warnings': 1,
            })
            entered.set()
            release.wait(5)

        def validate(directory):
            finalizing.set()
            finish.wait(5)
            raise ValueError('Output validation failed.')

        with patch.object(manager.worker, 'run', side_effect=execute), patch.object(manager, '_artifacts', side_effect=validate):
            job = manager.submit('redirects', {'lines': 'A%%%B'})
            self.assertTrue(entered.wait(5))
            live = manager.get(job.id)
            self.assertEqual(live.status, 'running')
            self.assertEqual((live.progress.completed, live.progress.total, live.progress.warnings), (2, 5, 1))
            self.assertEqual(manager.list_jobs()[0].progress, live.progress)
            release.set()
            self.assertTrue(finalizing.wait(5))
            pending = manager.get(job.id)
            self.assertEqual(pending.progress.stage, 'Finalizing output')
            self.assertIsNone(pending.progress.total)
            path = manager.root / job.id / 'log.txt'
            self.assertNotIn('completed successfully', path.read_text())
            finish.set()
            manager.executor.submit(lambda: None).result(timeout=5)
        failed = manager.get(job.id)
        self.assertEqual((failed.status, failed.progress.stage, failed.progress.warnings), ('failed', 'Failed', 1))
        self.assertIsNone(failed.progress.total)
        self.assertIn('ValueError: Output validation failed.', path.read_text())
        self.assertNotIn('completed successfully', path.read_text())
        saved = Job.model_validate_json((manager.root / job.id / 'job.json').read_text())
        self.assertEqual(saved.progress, failed.progress)

    def test_schema_validation_and_browser_request_boundaries(self):
        tools = self.client.get('/api/tools').json()
        self.assertEqual({tool['id'] for tool in tools}, {'redirects', 'character-kit', 'other-languages',
                                                         'binoutput-viewer', 'attribute-scaling', 'character-data', 'enemy', 'bounties', 'fishing-point', 'fish-weights',
                                                         'manual-cooking', 'spiral-abyss', 'stygian-onslaught', 'imaginarium-theater'})
        self.assertEqual([tool['id'] for tool in tools[-3:]], ['other-languages', 'binoutput-viewer', 'redirects'])
        self.assertEqual(next(tool['category'] for tool in tools if tool['id'] == 'other-languages'), 'Utilities')
        self.assertIn('particle-audit', TOOLS)
        self.assertIn('properties', tools[0]['schema'])
        kit = next(tool for tool in tools if tool['id'] == 'character-kit')
        self.assertTrue({'element', 'generate_icons'}.isdisjoint(kit['schema']['properties']))
        self.assertEqual(self.client.post('/api/jobs', json={
            'tool_id': 'character-kit', 'parameters': {'character_id': 1, 'version': '1.0', 'generate_icons': True},
        }).status_code, 422)
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

    def test_language_lookup_without_jobs(self):
        for language in LANGUAGES:
            values = {'101': 'Ambre' if language == 'FR' else 'Amber',
                      '102': 'Ambre' if language == 'FR' else 'Amber',
                      '103': 'Mineral' if language == 'FR' else 'Amber'}
            (self.dataset / 'TextMap' / f'TextMap{language}.json').write_text(json.dumps(values), encoding='utf-8')
        response = self.client.post('/api/other-languages', json={'text': 'aMbEr'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item['textmap_hash'] for item in response.json()], ['101', '103'])
        self.assertIn('|fr       = Mineral', response.json()[1]['text'])
        self.assertIn('|fr_tl', response.json()[0]['text'])
        by_hash = self.client.post('/api/other-languages', json={'text': '102', 'translation': False})
        self.assertEqual(by_hash.json()[0]['textmap_hash'], '102')
        self.assertNotIn('|fr_tl', by_hash.json()[0]['text'])
        localized = self.client.post('/api/other-languages', json={'text': 'ambre', 'input_lang': 'FR'})
        self.assertEqual([item['textmap_hash'] for item in localized.json()], ['101'])
        self.assertEqual(self.client.post('/api/other-languages', json={'text': 'Missing'}).status_code, 404)
        self.assertEqual(self.client.post('/api/other-languages', json={'text': '  '}).status_code, 422)
        self.assertEqual(self.client.post('/api/other-languages', json={'text': 'Amber', 'input_lang': 'XX'}).status_code, 422)
        self.assertEqual(self.client.get('/api/jobs').json(), [])

    def test_language_lookup_refreshes_changed_textmaps_and_reports_errors(self):
        first = self.client.post('/api/other-languages', json={'text': 'Amber'})
        self.assertEqual(first.status_code, 200, first.text)
        french = self.dataset / 'TextMap' / 'TextMapFR.json'
        french.write_text('{"101": "Updated French"}', encoding='utf-8')
        second = self.client.post('/api/other-languages', json={'text': 'Amber'})
        self.assertIn('|fr       = Updated French', second.json()[0]['text'])
        french.write_text('[]', encoding='utf-8')
        invalid = self.client.post('/api/other-languages', json={'text': 'Amber'})
        self.assertEqual(invalid.status_code, 409)
        self.assertIn('mapping', invalid.json()['detail'])
        import sqlite3
        index = next((self.root / '.data' / 'ol').glob('*.sqlite3'))
        with sqlite3.connect(index) as connection:
            self.assertEqual(connection.execute(
                "SELECT text FROM texts WHERE identifier = '101' AND language = 'FR'"
            ).fetchone()[0], 'Updated French')
        french.unlink()
        self.assertEqual(self.client.post('/api/other-languages', json={'text': 'Amber'}).status_code, 409)

    def test_language_index_reused_for_new_queries_after_restart(self):
        first = self.client.post('/api/other-languages', json={'text': 'Amber'})
        self.assertEqual(first.status_code, 200, first.text)
        with patch('webui.languages._load_textmap', side_effect=AssertionError('TextMaps were reloaded')):
            by_hash = self.client.post('/api/other-languages', json={'text': '101'})
            self.assertEqual(by_hash.json()[0]['textmap_hash'], '101')
            with TestClient(create_app(self.config, self.root / 'restart-jobs', self.root / 'no-frontend')) as restarted:
                localized = restarted.post('/api/other-languages', json={'text': 'ambre', 'input_lang': 'FR'})
                self.assertEqual(localized.status_code, 200, localized.text)
                self.assertIn('|en       = Amber', localized.json()[0]['text'])
                self.assertEqual(restarted.get('/api/jobs').json(), [])

    def test_language_index_concurrent_builds_and_dataset_isolation(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from webui import languages

        cache = self.root / '.data' / 'ol'
        directory = self.dataset / 'TextMap'
        barrier = Barrier(2)

        def lookup(text):
            barrier.wait(timeout=10)
            return languages.language_results(directory, cache, text, 'EN')

        with patch.object(languages, '_load_textmap', wraps=languages._load_textmap) as load:
            with ThreadPoolExecutor(max_workers=2) as executor:
                outputs = list(executor.map(lookup, ['Amber', '101']))
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(load.call_count, len(LANGUAGES))

        other = self.root / 'other-dataset' / 'TextMap'
        other.mkdir(parents=True)
        for language in LANGUAGES:
            (other / f'TextMap{language}.json').write_text('{"201": "Other"}', encoding='utf-8')
        self.assertEqual(languages.language_results(other, cache, 'Other', 'EN')[0]['textmap_hash'], '201')
        self.assertEqual(languages.language_results(other, cache, 'Amber', 'EN'), [])
        self.assertEqual(languages.language_results(directory, cache, 'Amber', 'EN')[0]['textmap_hash'], '101')

    def test_jobs_reuse_prebuilt_language_index_and_keep_own_config(self):
        response = self.client.post('/api/other-languages', json={'text': 'Amber'})
        self.assertEqual(response.status_code, 200, response.text)
        index = next((self.root / '.data' / 'ol').glob('*.sqlite3'))
        modified = index.stat().st_mtime_ns
        first = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'other-languages', 'parameters': {'text': 'Amber'},
        }).json()['id'])
        self.assertEqual(first['status'], 'succeeded', self.client.get(f"/api/jobs/{first['id']}/logs").text)
        log = self.client.get(f"/api/jobs/{first['id']}/logs").json()['text']
        self.assertIn('Using persistent Other Languages index', log)
        self.assertNotIn('Loading OL', log)
        self.assertEqual(index.stat().st_mtime_ns, modified)
        redirect = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'redirects', 'parameters': {'lines': 'Between%%%Target'},
        }).json()['id'])
        self.assertEqual([item['path'] for item in redirect['files']], ['Redirects/Between.wikitext'])
        second = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'other-languages', 'parameters': {'text': 'Ambre', 'input_lang': 'FR'},
        }).json()['id'])
        log = self.client.get(f"/api/jobs/{second['id']}/logs").json()['text']
        self.assertEqual(second['status'], 'succeeded', log)
        self.assertIn('Using persistent Other Languages index', log)
        self.assertNotIn('Loading OL', log)
        self.assertEqual(len(second['files']), 1)
        self.assertEqual(index.stat().st_mtime_ns, modified)
        self.assertEqual(list(self.root.rglob('*.sqlite3')), [index])
        (self.dataset / 'TextMap' / 'TextMapFR.json').write_text('{"101": "Updated French"}', encoding='utf-8')
        refreshed = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'other-languages', 'parameters': {'text': 'Amber'},
        }).json()['id'])
        self.assertEqual(refreshed['status'], 'succeeded',
                         self.client.get(f"/api/jobs/{refreshed['id']}/logs").text)
        text = self.client.get(f"/api/jobs/{refreshed['id']}/preview/{refreshed['files'][0]['path']}").json()['text']
        self.assertIn('|fr       = Updated French', text)

    def test_edit_wikitext_and_delete_job(self):
        job = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'redirects', 'parameters': {'lines': 'Edited%%%Target'},
        }).json()['id'])
        name = job['files'][0]['path']
        path = self.jobs / job['id'] / 'output' / name
        crlf = b'\r\n' in path.read_bytes()
        saved = self.client.put(f"/api/jobs/{job['id']}/files/{name}", json={'text': 'Line one\nLine two ü'})
        self.assertEqual(saved.status_code, 200, saved.text)
        expected = 'Line one\r\nLine two ü' if crlf else 'Line one\nLine two ü'
        self.assertEqual(path.read_bytes(), expected.encode('utf-8'))
        self.assertEqual(saved.json()['files'][0]['size'], len(expected.encode('utf-8')))
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}/preview/{name}").json()['text'], 'Line one\nLine two ü')
        for target in ('../job.json', '../request.json', 'missing.wikitext'):
            self.assertEqual(self.client.put(f"/api/jobs/{job['id']}/files/{target}", json={'text': 'x'}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/jobs/{job['id']}", headers={'Origin': 'https://other.example'}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/jobs/{job['id']}").status_code, 204)
        self.assertFalse((self.jobs / job['id']).exists())
        self.assertEqual(self.client.get(f"/api/jobs/{job['id']}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/jobs/{job['id']}").status_code, 404)

    def test_bot_queue_and_posting(self):
        import httpx
        from urllib.parse import parse_qs

        from webui import bot

        pages = {'Existing': 'Old text', 'Same': 'Same text'}
        edits = []

        def wiki(request):
            params = {**dict(request.url.params), **{k: v[0] for k, v in parse_qs(request.content.decode()).items()}}
            if request.url.path != '/api.php':
                return httpx.Response(404)
            if params.get('meta') == 'siteinfo':
                return httpx.Response(200, json={'query': {'general': {'sitename': 'Test'}}})
            if params.get('meta') == 'tokens':
                return httpx.Response(200, json={'query': {'tokens': {'logintoken': 'L', 'csrftoken': 'C'}}})
            if params.get('action') == 'login':
                ok = params['lgname'] == 'Me@Bot' and params['lgpassword'] == 'secret' and params['lgtoken'] == 'L'
                return httpx.Response(200, json={'login': {'result': 'Success' if ok else 'Failed', 'lgusername': 'Me', 'reason': 'Bad password.'}})
            if params.get('prop') == 'revisions':
                title = params['titles']
                page = {'title': title, 'missing': True} if title not in pages else {
                    'title': title, 'revisions': [{'slots': {'main': {'content': pages[title]}}}]}
                return httpx.Response(200, json={'query': {'pages': [page]}})
            if params.get('action') == 'edit':
                self.assertEqual(params['token'], 'C')
                if params['title'] == 'Locked':
                    return httpx.Response(200, json={'error': {'code': 'protectedpage', 'info': 'This page is protected.'}})
                edits.append(params)
                pages[params['title']] = params['text']
                return httpx.Response(200, json={'edit': {'result': 'Success'}})
            return httpx.Response(400)

        self.assertEqual(bot.parse_page('<%-- [PAGE_INFO]\n    pageTitle = #A#\n[END_PAGE_INFO] --%>\n\nBody\n'), ({'pageTitle': 'A'}, 'Body\n'))
        self.assertEqual(bot.parse_page('<%-- [PAGE_INFO]\r\n    pageTitle = #B#\r\n[END_PAGE_INFO] --%>\r\n#REDIRECT [[C]]'), ({'pageTitle': 'B'}, '#REDIRECT [[C]]'))
        self.assertEqual(bot.parse_page('--[=[<%-- [PAGE_INFO]\n    pageTitle = #Module:X#\n[END_PAGE_INFO] --%>--]=]\n\nreturn {}')[0], {'pageTitle': 'Module:X'})
        self.assertEqual(bot.parse_page('No header'), ({}, 'No header'))

        job = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'redirects', 'parameters': {'lines': 'New%%%Target\nExisting%%%Target\nSame%%%Target\nLocked%%%Target\nUntitled%%%Target'},
        }).json()['id'])
        output = self.jobs / job['id'] / 'output' / 'Redirects'
        (output / 'Same.wikitext').write_text('<%-- [PAGE_INFO]\n    pageTitle = #Same#\n[END_PAGE_INFO] --%>\n\nSame text\n', encoding='utf-8')
        (output / 'Untitled.wikitext').write_text('Just text', encoding='utf-8')
        names = [file['path'] for file in job['files']]

        added = self.client.post('/api/bot/queue', json={'job_id': job['id'], 'paths': names})
        self.assertEqual(added.json(), {'added': 5, 'skipped': 0}, added.text)
        self.assertEqual(self.client.post('/api/bot/queue', json={'job_id': job['id'], 'paths': names[:1]}).json(), {'added': 0, 'skipped': 1})
        self.assertEqual(self.client.post('/api/bot/queue', json={'job_id': job['id'], 'paths': ['../job.json']}).status_code, 404)
        items = {item['path'].split('/')[-1]: item for item in self.client.get('/api/bot').json()['items']}
        self.assertIsNone(items['Untitled.wikitext']['title'])
        self.assertEqual(self.client.get(f"/api/bot/queue/{items['New.wikitext']['id']}").json()['content'], '#REDIRECT [[Target]]\n[[Category:Redirect Pages]]')

        self.assertEqual(self.client.post('/api/bot/post', json={}).status_code, 409)
        self.assertEqual(self.client.put('/api/bot/settings', json={'wiki': 'http://wiki.test', 'username': 'Me@Bot', 'password': 'wrong'}).status_code, 200)
        with patch.object(bot, 'transport', httpx.MockTransport(wiki)):
            self.assertIn('Bad password', self.client.post('/api/bot/login').json()['detail'])
            settings = self.client.put('/api/bot/settings', json={'wiki': 'http://wiki.test/wiki/Main_Page', 'username': 'Me@Bot', 'password': 'secret', 'summary': 'Test'})
            self.assertTrue(settings.json()['has_password'])
            self.assertNotIn('password', json.loads((self.root / 'bot' / 'settings.json').read_text()))
            self.assertEqual(self.client.post('/api/bot/login').json(), {'username': 'Me'})
            self.assertEqual(self.client.patch(f"/api/bot/queue/{items['Untitled.wikitext']['id']}", json={'title': 'Bad|Title'}).status_code, 409)
            self.client.post('/api/bot/post', json={})
            deadline = time.monotonic() + 10
            while self.client.get('/api/bot').json()['running'] and time.monotonic() < deadline:
                time.sleep(.05)
        state = self.client.get('/api/bot').json()
        status = {item['path'].split('/')[-1]: (item['status'], item['message']) for item in state['items']}
        self.assertEqual(status['New.wikitext'], ('posted', None))
        self.assertEqual(status['Existing.wikitext'], ('posted', None))
        self.assertEqual(status['Same.wikitext'], ('skipped', 'No change from the live page.'))
        self.assertEqual(status['Locked.wikitext'], ('failed', 'This page is protected. (protectedpage)'))
        self.assertEqual(status['Untitled.wikitext'], ('pending', None))
        self.assertEqual([edit['title'] for edit in edits], ['Existing', 'New'])
        self.assertEqual((edits[0]['summary'], edits[0]['bot'], edits[0]['watchlist']), ('Test', '1', 'watch'))
        self.assertEqual(pages['New'], '#REDIRECT [[Target]]\n[[Category:Redirect Pages]]')
        self.assertTrue(any('Logged in as Me' in line for line in state['log']))

        self.client.put('/api/bot/settings', json={'wiki': 'http://wiki.test', 'username': 'Me@Bot', 'remember': True})
        self.assertEqual(json.loads((self.root / 'bot' / 'settings.json').read_text())['password'], 'secret')
        removed = self.client.post('/api/bot/queue/remove', json={'ids': [item['id'] for item in state['items'] if item['status'] == 'posted']})
        self.assertEqual(len(removed.json()['items']), 3)

    def test_bot_media_upload(self):
        from email.parser import BytesParser
        import hashlib
        import httpx
        from urllib.parse import parse_qs

        from utils.files import write_file_pages
        from webui import bot
        from webui.jobs import JobManager

        output = self.root / 'media-job'
        output.mkdir()
        for name, data in (('New.png', b'new'), ('Same.png', b'same'), ('Changed.png', b'changed')):
            (output / name).write_bytes(data)
        write_file_pages(output, {'New.png': '==Summary==\n{{File}}'})
        self.assertEqual([(artifact.path, artifact.file_page) for artifact in JobManager._artifacts(output)],
                         [('Changed.png', None), ('New.png', '==Summary==\n{{File}}'), ('Same.png', None)])

        live = {'File:Same.png': hashlib.sha1(b'same').hexdigest(), 'File:Changed.png': hashlib.sha1(b'old').hexdigest()}
        uploads = []

        def wiki(request):
            if request.headers.get('content-type', '').startswith('multipart/form-data'):
                message = BytesParser().parsebytes(b'Content-Type: ' + request.headers['content-type'].encode() + b'\r\n\r\n' + request.read())
                fields = {part.get_param('name', header='content-disposition'): part.get_payload(decode=True) for part in message.get_payload()}
                uploads.append(fields)
                return httpx.Response(200, json={'upload': {'result': 'Success'}})
            params = {**dict(request.url.params), **{k: v[0] for k, v in parse_qs(request.content.decode()).items()}}
            if params.get('meta') == 'siteinfo':
                return httpx.Response(200, json={'query': {'general': {'sitename': 'Test'}}})
            if params.get('meta') == 'tokens':
                return httpx.Response(200, json={'query': {'tokens': {'logintoken': 'L', 'csrftoken': 'C'}}})
            if params.get('action') == 'login':
                return httpx.Response(200, json={'login': {'result': 'Success', 'lgusername': 'Me'}})
            if params.get('prop') == 'imageinfo':
                title = params['titles']
                page = {'title': title, 'imageinfo': [{'sha1': live[title]}]} if title in live else {'title': title, 'missing': True}
                return httpx.Response(200, json={'query': {'pages': [page]}})
            return httpx.Response(400)

        manager = bot.BotManager(self.root / 'media-bot')
        self.assertEqual(manager.add('Job', 'j', [(name, output / name) for name in ('New.png', 'Same.png', 'Changed.png')]), (3, 0))
        items = {item.path: item for item in manager.items}
        self.assertEqual((items['New.png'].kind, items['New.png'].title, items['New.png'].content), ('file', 'File:New.png', '==Summary==\n{{File}}'))
        self.assertEqual(items['Same.png'].content, '')
        self.assertEqual(manager.update(items['Same.png'].id, title='Same.png').title, 'File:Same.png')
        (output / 'New.png').unlink()  # the queue keeps its own copy

        manager.update_settings(bot.SettingsUpdate(wiki='http://wiki.test', username='Me@Bot', password='secret'))
        with patch.object(bot, 'transport', httpx.MockTransport(wiki)):
            manager.start()
            manager.thread.join(10)
        status = {item.path: (item.status, item.message) for item in manager.items}
        self.assertEqual(status['New.png'], ('posted', None))
        self.assertEqual(status['Same.png'], ('skipped', 'The live file is identical.'))
        self.assertEqual(status['Changed.png'][0], 'posted')
        self.assertEqual([(upload['filename'], upload['file'], upload.get('ignorewarnings')) for upload in uploads],
                         [(b'New.png', b'new', None), (b'Changed.png', b'changed', b'1')])
        self.assertEqual(uploads[0]['text'].decode(), '==Summary==\n{{File}}')
        manager.remove([item.id for item in manager.items])
        self.assertEqual(list((self.root / 'media-bot' / 'media').iterdir()), [])

    def test_hosted_mode_isolates_browsers(self):
        import httpx
        from urllib.parse import parse_qs

        from webui import bot

        edits = []

        def wiki(request):
            params = {**dict(request.url.params), **{k: v[0] for k, v in parse_qs(request.content.decode()).items()}}
            if params.get('meta') == 'siteinfo':
                return httpx.Response(200, json={'query': {'general': {'sitename': 'Test'}}})
            if params.get('meta') == 'tokens':
                return httpx.Response(200, json={'query': {'tokens': {'logintoken': 'L', 'csrftoken': 'C'}}})
            if params.get('action') == 'login':
                return httpx.Response(200, json={'login': {'result': 'Success', 'lgusername': 'Me'}})
            if params.get('prop') == 'revisions':
                return httpx.Response(200, json={'query': {'pages': [{'title': params['titles'], 'missing': True}]}})
            if params.get('action') == 'edit':
                edits.append((params['title'], params['text']))
                return httpx.Response(200, json={'edit': {'result': 'Success'}})
            return httpx.Response(400)

        first, second = {'X-Client-Id': 'a' * 32}, {'X-Client-Id': 'b' * 32}
        with TestClient(create_app(self.config, self.jobs, self.root / 'no-frontend', hosted=True)) as client:
            self.assertEqual(client.get('/api/config').json(), {
                'hosted': True, 'working_directory': None, 'default_working_directory': None})
            self.assertEqual(client.get('/api/jobs').status_code, 400)
            for method, path in (('GET', '/api/bot'), ('POST', '/api/dataset/setup'), ('PUT', '/api/config'),
                                 ('PUT', '/api/dataset/sources')):
                self.assertEqual(client.request(method, path, headers=first, json={}).status_code, 403, path)
            job = client.post('/api/jobs', headers=first, json={
                'tool_id': 'redirects', 'parameters': {'lines': 'First%%%Target'}}).json()
            self.assertEqual(job['parameters'], {'lines': 'First%%%Target'})
            deadline = time.monotonic() + 15
            while client.get(f"/api/jobs/{job['id']}", headers=first).json()['status'] not in ('succeeded', 'failed'):
                self.assertLess(time.monotonic(), deadline)
                time.sleep(.05)
            self.assertEqual([item['id'] for item in client.get('/api/jobs', headers=first).json()], [job['id']])
            self.assertEqual(client.get('/api/jobs', headers=second).json(), [])
            for response in (client.get(f"/api/jobs/{job['id']}", headers=second),
                             client.get(f"/api/jobs/{job['id']}/logs?full=true", headers=second),
                             client.get(f"/api/jobs/{job['id']}/files/Redirects/First.wikitext", headers=second),
                             client.delete(f"/api/jobs/{job['id']}", headers=second)):
                self.assertEqual(response.status_code, 404)
            self.assertEqual(client.get(f"/api/jobs/{job['id']}/files/Redirects/First.wikitext", headers=first).status_code, 200)
            self.assertEqual(client.get('/api/characters', headers={**first, 'X-Dataset': 'bad'}).status_code, 409)
            missing = client.get('/api/characters', headers={**first, 'X-Dataset': f"{'1' * 40}.{'2' * 40}"})
            self.assertIn('not available on this server', missing.json()['detail'])
            self.assertEqual(client.post('/api/jobs', headers={**first, 'Origin': 'https://elsewhere.test'}, json={}).status_code, 403)

            self.assertIn('not a public wiki', client.post('/api/wiki/login', headers=first, json={
                'wiki': 'http://127.0.0.1', 'username': 'Me@Bot', 'password': 'secret'}).json()['detail'])
            with patch.object(bot, 'transport', httpx.MockTransport(wiki)), patch.object(bot, 'public_wiki'):
                session = client.post('/api/wiki/login', headers=first, json={
                    'wiki': 'http://wiki.test', 'username': 'Me@Bot', 'password': 'secret'}).json()
                self.assertEqual(session['username'], 'Me')
                body = {'session': session['session'], 'title': 'New', 'content': 'Text'}
                self.assertEqual(client.post('/api/wiki/post', headers=second, json=body).status_code, 401)
                self.assertEqual(client.post('/api/wiki/post', headers=first, json=body).json(), {'status': 'posted', 'message': None})
                self.assertEqual(client.post('/api/wiki/post', headers=first, json={**body, 'title': 'Bad|Title'}).json()['status'], 'failed')
                client.post('/api/wiki/logout', headers=first, json={'session': session['session']})
                self.assertEqual(client.post('/api/wiki/post', headers=first, json=body).status_code, 401)
            self.assertEqual(edits, [('New', 'Text')])
            client.app.state.jobs.purge(0)
            self.assertEqual(client.get('/api/jobs', headers=first).json(), [])

    def test_working_directory_setting(self):
        default = self.client.get('/api/config').json()
        self.assertEqual(default, {'hosted': False, 'working_directory': str(self.root),
                                   'default_working_directory': str(self.root)})
        old = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'redirects', 'parameters': {'lines': 'First%%%Target'}}).json()['id'])
        self.assertEqual(self.client.put('/api/config', json={'working_directory': 'relative'}).status_code, 422)
        moved = self.root / 'elsewhere'
        changed = self.client.put('/api/config', json={'working_directory': str(moved)})
        self.assertEqual(changed.json()['working_directory'], str(moved), changed.text)
        self.assertEqual(self.client.get('/api/jobs').json(), [])
        job = self.wait(self.client.post('/api/jobs', json={
            'tool_id': 'redirects', 'parameters': {'lines': 'Second%%%Target'}}).json()['id'])
        self.assertTrue((moved / 'jobs' / job['id'] / 'output' / 'Redirects' / 'Second.wikitext').is_file())
        self.assertEqual(self.client.get('/api/bot').json()['items'], [])
        self.assertTrue((moved / 'bot').is_dir())
        self.client.put('/api/config', json={'working_directory': ''})
        self.assertEqual([item['id'] for item in self.client.get('/api/jobs').json()], [old['id']])

    def test_dataset_status_and_character_choices(self):
        dataset = self.client.get('/api/dataset').json()
        self.assertTrue(dataset['ready'])
        self.assertEqual(dataset['languages'], 15)
        self.assertEqual(self.client.get('/api/characters').json(), [
            {'id': 10000021, 'name': 'Amber', 'skill_depot': 2101},
        ])
        with patch('wikiVersion.release_version', return_value='1.0') as lookup:
            self.assertEqual(self.client.get('/api/characters/10000021/version').json(), {'character': 'Amber', 'version': '1.0'})
            lookup.assert_called_once_with('Amber')
        self.assertEqual(self.client.get('/api/characters/99/version').status_code, 404)

    def test_period_choices_newest_first(self):
        excel = self.dataset / 'MappedExcelBinOutput_EN'
        (excel / 'TowerScheduleExcelConfigData.json').write_text(json.dumps([
            {'CloseTime': '2026-12-16 03:59:59', 'Schedules': [{'OpenTime': '2026-11-16 04:00:00'}]},
            {'Schedules': [{'OpenTime': '2026-12-16 04:00:00'}]},
            {'Schedules': [{}]},
        ]), encoding='utf-8')
        (excel / 'LeyLineChallengeExcelConfigData.json').write_text(json.dumps([
            {'ChallengeNameTextMapHash': 'Great Waves', 'XA': '2026-11-11 10:00:00', 'XB': '2026-12-23 09:59:59'},
        ]), encoding='utf-8')
        self.assertEqual(self.client.get('/api/periods/abyss').json(), [
            {'value': '2026-12-16', 'label': '2026-12-16'}, {'value': '2026-11-16', 'label': '2026-11-16 – 2026-12-15'}])
        self.assertEqual(self.client.get('/api/periods/stygian').json(),
                         [{'value': '2026-11-11', 'label': '2026-11-11 – 2026-12-15', 'name': 'Great Waves'}])
        # Test schedules reuse a season's config and count at its last schedule; 2099 placeholders are skipped.
        (excel / 'RoleCombatScheduleExcelConfigData.json').write_text(json.dumps([
            {'AvatarConfigId': 1, 'BeginTimeStr': '2023-03-01 04:00:00', 'XA': '2023-04-01 03:59:59'},
            {'AvatarConfigId': 1, 'BeginTimeStr': '2024-07-01 10:00:00', 'XA': '2024-08-01 03:59:59'},
            {'AvatarConfigId': 2, 'BeginTimeStr': '2024-08-01 04:00:00', 'XA': '2024-09-01 03:59:59'},
            {'AvatarConfigId': 3, 'BeginTimeStr': '2099-11-01 04:00:00', 'XA': '2099-12-01 03:59:59'},
        ]), encoding='utf-8')
        self.assertEqual(self.client.get('/api/periods/theater').json(), [
            {'value': '2024-08-01', 'label': '2024-08-01 – 2024-09-01', 'name': 'Season 2'},
            {'value': '2024-07-01', 'label': '2024-07-01 – 2024-08-01', 'name': 'Season 1'}])
        self.assertEqual(self.client.get('/api/periods/other').status_code, 404)
        with patch('urllib.request.urlopen') as urlopen:
            urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(
                {'expandtemplates': {'wikitext': '2025-12-16=Luna III\n2026-11-11=7.2'}}).encode())
            self.assertEqual(self.client.get('/api/date-versions?dates=2025-12-16,2026-11-11').json(),
                             {'2025-12-16': 'Luna III', '2026-11-11': '7.2'})
            self.assertIn('{{Date to Version|2025-12-16}}', urllib.parse.unquote_plus(urlopen.call_args[0][0].data.decode()))
        self.assertEqual(self.client.get('/api/date-versions?dates=2025-12').status_code, 422)
        with patch('passiveTypes.character_passive_types', return_value=['stellar']) as detect:
            self.assertEqual(self.client.get('/api/characters/10000021/passives').json(), {'types': ['stellar']})
            detect.assert_called_once_with(10000021, self.dataset / 'MappedExcelBinOutput_EN')
        self.config.write_text(json.dumps({'DataSource': 'github'}), encoding='utf-8')
        status = self.client.get('/api/dataset').json()
        self.assertFalse(status['ready'])
        self.assertIn('quickSetup', status['error'])
        self.assertEqual((status['excel_source'], status['binoutput_source']), ('dimbreath', 'gura'))
        self.assertEqual(set(status['sources']), {'dimbreath', 'gura'})
        saved = self.client.put('/api/dataset/sources', json={'excel': 'gura', 'binoutput': 'dimbreath'})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual((saved.json()['excel_source'], saved.json()['binoutput_source']), ('gura', 'dimbreath'))
        self.assertEqual(json.loads(self.config.read_text(encoding='utf-8')),
                         {'DataSource': 'github', 'ExcelSource': 'gura', 'BinOutputSource': 'dimbreath',
                          'ExcelRevision': 'latest', 'BinOutputRevision': 'latest'})
        self.assertEqual(self.client.put('/api/dataset/sources', json={'excel': 'elsewhere', 'binoutput': 'gura'}).status_code, 422)
        pinned = 'a' * 40
        saved = self.client.put('/api/dataset/sources', json={'excel': 'dimbreath', 'binoutput': 'gura', 'excel_revision': pinned})
        self.assertEqual(saved.json()['excel_revision'], pinned)
        self.assertNotEqual(self.client.put('/api/dataset/sources', json={
            'excel': 'dimbreath', 'binoutput': 'gura', 'excel_revision': 'main'}).status_code, 200)
        listing = [{'commit': 'b' * 40, 'title': 'CNRELWin7.2.0', 'date': '2026-11-12T08:14:35Z'}]
        with patch('webui.app.list_revisions', return_value=listing) as fake:
            for _ in range(2):
                revisions = self.client.get('/api/dataset/revisions?source=dimbreath').json()
            self.assertEqual(fake.call_count, 1)
        self.assertEqual(revisions, [dict(listing[0], downloaded=False)])
        self.assertEqual(self.client.get('/api/dataset/revisions?source=elsewhere').status_code, 404)
        response = self.client.post('/api/jobs', json={
            'tool_id': 'other-languages', 'parameters': {'text': 'Amber'},
        })
        self.assertEqual(response.status_code, 409)

    def test_character_kit_game_data_references(self):
        (self.dataset / 'MappedExcelBinOutput_EN' / 'AvatarExcelConfigData.json').write_text(json.dumps([
            {'Id': 10000021, 'NameTextMapHash': 'Amber', 'IconName': 'UI_AvatarIcon_Ambor'},
        ]), encoding='utf-8')
        binoutput = self.dataset / 'BinOutput'
        files = {
            'Avatar/ConfigAvatar_Ambor.json': '{"combat": {}}',
            'Avatar/ConfigAvatar_AmborCopy.json': '{}',
            'Ability/Temp/AvatarAbilities/ConfigAbility_Avatar_Ambor.json': '[]',
            'Ability/Temp/AvatarAniEventAbilities/ConfigAbility_Avatar_Ambor_AniEvent_Bow.json': '[]',
            'Gadget/ConfigGadget_SkillObj_Ambor_Baron.json': '{}',
        }
        for name, text in files.items():
            (binoutput / name).parent.mkdir(parents=True, exist_ok=True)
            (binoutput / name).write_text(text, encoding='utf-8')
        (self.dataset / 'ExcelBinOutput').mkdir()
        (self.dataset / 'ExcelBinOutput' / 'AttackAttenuationExcelConfigData.json').write_text(json.dumps([
            {'group': 'Ambor_Arrow', 'resetCycle': 2.5}, {'group': 'AmborOther'}, {'group': 'Klee'},
        ]), encoding='utf-8')
        root = self.root / 'reference-jobs'
        jobs = {}
        for tool in ('character-kit', 'redirects'):
            job = Job(id=uuid4().hex, tool_id=tool, name=tool, status='succeeded')
            (root / job.id).mkdir(parents=True)
            (root / job.id / 'job.json').write_text(job.model_dump_json(), encoding='utf-8')
            (root / job.id / 'request.json').write_text(json.dumps({'parameters': {'character_id': 10000021}}), encoding='utf-8')
            jobs[tool] = job.id
        with TestClient(create_app(self.config, root, self.root / 'no-frontend')) as client:
            listing = client.get(f"/api/jobs/{jobs['character-kit']}/references")
            self.assertEqual(listing.status_code, 200, listing.text)
            self.assertEqual(listing.json()['character'], 'Ambor')
            keys = [item['key'] for item in listing.json()['files']]
            self.assertEqual(keys, [
                'Avatar/ConfigAvatar_Ambor.json', 'Abilities/ConfigAbility_Avatar_Ambor.json',
                'AniEvent/ConfigAbility_Avatar_Ambor_AniEvent_Bow.json', 'Skill Objects/ConfigGadget_SkillObj_Ambor_Baron.json',
                'Attenuation/AttackAttenuationExcelConfigData.json',
            ])
            base = f"/api/jobs/{jobs['character-kit']}/references"
            self.assertEqual(client.get(f'{base}/Avatar/ConfigAvatar_Ambor.json').json()['text'], '{"combat": {}}')
            self.assertEqual(json.loads(client.get(f'{base}/{keys[-1]}').json()['text']), [{'group': 'Ambor_Arrow', 'resetCycle': 2.5}])
            for key in ('Avatar/ConfigAvatar_AmborCopy.json', 'Avatar/../../config.json', 'Avatar/ConfigAvatar_Klee.json'):
                self.assertEqual(client.get(f'{base}/{key}').status_code, 404)
            self.assertEqual(client.get(f"/api/jobs/{jobs['redirects']}/references").status_code, 404)

    def test_traveler_references_include_shared_and_gender_elemental_abilities(self):
        excel = self.dataset / 'MappedExcelBinOutput_EN'
        (excel / 'AvatarExcelConfigData.json').write_text(json.dumps([
            {'Id': 10000005, 'NameTextMapHash': 'Traveler', 'IconName': 'UI_AvatarIcon_PlayerBoy'},
            {'Id': 10000007, 'NameTextMapHash': 'Traveler', 'IconName': 'UI_AvatarIcon_PlayerGirl'},
        ]), encoding='utf-8')
        folder = self.dataset / 'BinOutput' / 'Ability' / 'Temp' / 'AvatarAbilities'
        folder.mkdir(parents=True)
        expected = ['ConfigAbility_Avatar_Player_Common.json', 'ConfigAbility_Avatar_Player_Wind.json',
                    'ConfigAbility_Avatar_PlayerBoy_Wind.json', 'ConfigAbility_Avatar_PlayerGirl_Ice.json']
        for name in [*expected, 'ConfigAbility_Avatar_PlayerOther.json', 'ConfigAbility_Avatar_Ambor.json']:
            (folder / name).write_text('[]', encoding='utf-8')
        for character in (10000005, 10000007):
            response = self.client.get(f'/api/characters/{character}/references')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(sorted(file['name'] for file in response.json()['files']), sorted(expected))

    def test_binoutput_tree_file_boundaries_and_jobless_tool(self):
        root = self.dataset / 'BinOutput'
        (root / 'Unusual' / 'Nested').mkdir(parents=True)
        (root / 'Unusual' / 'Nested' / 'Example.json').write_text('{"value": 1}', encoding='utf-8')
        (root / 'private.txt').write_text('not JSON', encoding='utf-8')
        listing = self.client.get('/api/binoutput/tree')
        self.assertEqual(listing.status_code, 200, listing.text)
        self.assertEqual(listing.json()['entries'], [
            {'key': 'Unusual/Nested', 'name': 'Unusual / Nested', 'directory': True, 'size': None},
        ])
        listing = self.client.get('/api/binoutput/tree', params={'path': 'Unusual/Nested'})
        self.assertEqual(listing.json()['entries'][0]['key'], 'Unusual/Nested/Example.json')
        response = self.client.get('/api/binoutput/file', params={'path': 'Unusual/Nested/Example.json'})
        self.assertEqual(response.json(), {'text': '{"value": 1}'})
        with patch('webui.references.MAX_FILE_SIZE', 4):
            self.assertEqual(self.client.get('/api/binoutput/file',
                                            params={'path': 'Unusual/Nested/Example.json'}).status_code, 413)
            from webui.references import read_reference
            with self.assertRaises(OverflowError):
                read_reference({'path': None, 'text': '\u00e9' * 3})
        for path in ('../config.json', r'..\config.json', '/config.json', 'C:/config.json', 'Unusual/../../config.json'):
            for endpoint in ('tree', 'file'):
                with self.subTest(path=path, endpoint=endpoint):
                    self.assertEqual(self.client.get(f'/api/binoutput/{endpoint}', params={'path': path}).status_code, 400)
        self.assertEqual(self.client.get('/api/binoutput/file', params={'path': 'private.txt'}).status_code, 404)
        self.assertEqual(self.client.get('/api/binoutput/references').status_code, 422)
        self.assertEqual(self.client.get('/api/binoutput/references',
                                        params={'character_id': 10000021, 'enemy_id': 1}).status_code, 422)
        response = self.client.post('/api/jobs', json={'tool_id': 'binoutput-viewer', 'parameters': {}})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn('without creating a job', response.text)
        self.assertEqual(self.client.get('/api/jobs').json(), [])

    def test_binoutput_filename_search_matches_basename_and_caps_results(self):
        root = self.dataset / 'BinOutput'
        for folder in ('Avatar', 'Nested', 'SwordDirectory'):
            (root / folder).mkdir(parents=True)
        for index in range(101):
            folder = 'Avatar' if index % 2 else 'Nested'
            (root / folder / f'ConfigSword{index:03}.JSON').write_text('{}', encoding='utf-8')
        (root / 'SwordDirectory' / 'Unrelated.json').write_text('{}', encoding='utf-8')
        (root / 'ConfigSword.txt').write_text('{}', encoding='utf-8')

        response = self.client.get('/api/binoutput/search', params={'name': 'SWORD config'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()['entries']), 100)
        self.assertTrue(response.json()['truncated'])
        self.assertEqual(response.json()['entries'][0], {'key': 'Nested/ConfigSword000.JSON', 'name': 'ConfigSword000.JSON'})
        self.assertEqual(self.client.get('/api/binoutput/search', params={'name': 'SwordDirectory'}).json(),
                         {'entries': [], 'truncated': False})
        self.assertEqual(self.client.get('/api/binoutput/search', params={'name': ' '}).status_code, 400)

        from webui.references import binoutput_search
        other = self.dataset / 'other-binoutput'
        other.mkdir()
        (other / 'DifferentSword.json').write_text('{}', encoding='utf-8')
        self.assertEqual(binoutput_search({'RepoPath': str(self.dataset), 'BinPath': str(other)}, 'sword'),
                         {'entries': [{'key': 'DifferentSword.json', 'name': 'DifferentSword.json'}], 'truncated': False})

    def test_binoutput_compact_folders_stop_at_files_or_branches(self):
        root = self.dataset / 'BinOutput'
        for relative in ('Chain/Only/Fork/Left/Leaf/A.json', 'Chain/Only/Fork/Right/B.json',
                         'Mixed/A.json', 'Mixed/Child/B.json'):
            path = root.joinpath(*relative.split('/'))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}', encoding='utf-8')
        (root / 'Chain' / 'ignored.txt').write_text('not shown', encoding='utf-8')
        entries = self.client.get('/api/binoutput/tree').json()['entries']
        self.assertEqual([(item['key'], item['name']) for item in entries],
                         [('Chain/Only/Fork', 'Chain / Only / Fork'), ('Mixed', 'Mixed')])
        entries = self.client.get('/api/binoutput/tree', params={'path': 'Chain/Only/Fork'}).json()['entries']
        self.assertEqual([(item['key'], item['name']) for item in entries],
                         [('Chain/Only/Fork/Left/Leaf', 'Left / Leaf'), ('Chain/Only/Fork/Right', 'Right')])
        response = self.client.get('/api/binoutput/file', params={'path': entries[0]['key'] + '/A.json'})
        self.assertEqual(response.json(), {'text': '{}'})

    def test_binoutput_character_enemy_links_and_index_refresh(self):
        excel = self.dataset / 'MappedExcelBinOutput_EN'
        tables = {
            'AvatarExcelConfigData': [{'Id': 10000021, 'NameTextMapHash': 'Amber',
                                      'IconName': 'UI_AvatarIcon_Ambor', 'SkillDepotId': 2101}],
            'AvatarSkillDepotExcelConfigData': [{'Id': 2101, 'Skills': [1, 2], 'EnergySkill': 5}],
            'AvatarSkillExcelConfigData': [{'Id': 2, 'ProudSkillGroupId': 21}],
            'ProudSkillExcelConfigData': [{'ProudSkillGroupId': 21, 'OpenConfig': 'Renamed_SkillUpgrade_2'}],
            'AvatarTalentExcelConfigData': [],
            'GadgetExcelConfigData': [{'Id': 40000001, 'JsonName': 'UnrelatedTurret'}],
            'MonsterExcelConfigData': [{'Id': 21010101, 'MonsterName': 'Hili_None_01', 'DescribeName': 'Hilichurl'}],
        }
        for name, rows in tables.items():
            (excel / f'{name}.json').write_text(json.dumps(rows), encoding='utf-8')
        files = {
            'Avatar/ConfigAvatar_Ambor.json': {'abilities': [{'abilityName': 'Shared_Explosion'}]},
            'Ability/Temp/AvatarAbilities/ConfigAbility_Avatar_Renamed.json': [],
            'Ability/Temp/MonsterAbilities/UnrelatedFilename.json': [
                {'Default': {'abilityName': 'Shared_Explosion', 'onAdded': [
                    {'$type': 'CreateGadget', 'gadgetID': 40000001},
                    {'$type': 'AddAbility', 'abilityName': 'Shared_Explosion'},
                ]}},
                {'Default': {'abilityName': 'NotReachable', 'onAdded': [
                    {'$type': 'AddAbility', 'abilityName': 'Other_Character'},
                ]}},
            ],
            'Ability/Misc/Followup.json': [{'Default': {'abilityName': 'Shared_Followup', 'modifiers': {}}}],
            'Ability/Misc/Other.json': [{'Default': {'abilityName': 'Other_Character', 'modifiers': {}}}],
            'Gadget/ConfigGadget_UnrelatedTurret.json': {'abilities': [{'abilityName': 'Shared_Followup'}]},
            'Monster/Hili_None_01.json': {'abilities': [{'abilityName': 'Shared_Explosion'}]},
            'Monster/Hili_None_010.json': {},
            'Monster/ConfigMonster_Hili_None_01.json': {},
            'Monster/21010101.json': {},
            'Monster/Variant_21010101.json': {},
            'Monster/Variant_210101010.json': {},
        }
        root = self.dataset / 'BinOutput'
        for relative, value in files.items():
            path = root.joinpath(*relative.split('/'))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding='utf-8')
        (root / 'Ability' / 'Misc' / 'Malformed.json').write_text('{broken', encoding='utf-8')
        for scope in ({'character_id': 10000021}, {'enemy_id': 21010101}):
            response = self.client.get('/api/binoutput/references', params=scope)
            self.assertEqual(response.status_code, 200, response.text)
            found = {item['key'] for item in response.json()['files']}
            self.assertTrue({'Ability/Temp/MonsterAbilities/UnrelatedFilename.json',
                             'Gadget/ConfigGadget_UnrelatedTurret.json', 'Ability/Misc/Followup.json'} <= found)
            self.assertNotIn('Ability/Misc/Other.json', found)
            self.assertNotIn('Monster/Hili_None_010.json', found)
            self.assertNotIn('Monster/Variant_210101010.json', found)
            if 'enemy_id' in scope:
                self.assertTrue({'Monster/ConfigMonster_Hili_None_01.json', 'Monster/21010101.json',
                                 'Monster/Variant_21010101.json'} <= found)
            self.assertTrue(any('Could not index Malformed.json' in warning for warning in response.json()['warnings']))
            for key in found:
                self.assertEqual(self.client.get('/api/binoutput/file', params={'path': key, **scope}).status_code, 200)
            self.assertEqual(self.client.get('/api/binoutput/file',
                                            params={'path': 'Ability/Misc/Other.json', **scope}).status_code, 404)
        found = self.client.get('/api/binoutput/references', params={'character_id': 10000021}).json()['files']
        self.assertIn('Ability/Temp/AvatarAbilities/ConfigAbility_Avatar_Renamed.json', {item['key'] for item in found})
        (root / 'Ability' / 'Misc' / 'Followup.json').write_text(json.dumps([
            {'Default': {'abilityName': 'Renamed_Followup', 'modifiers': {}}},
        ]), encoding='utf-8')
        refreshed = self.client.get('/api/binoutput/references', params={'enemy_id': 21010101}).json()
        self.assertNotIn('Ability/Misc/Followup.json', {item['key'] for item in refreshed['files']})
        self.assertTrue(any('no definition' in warning for warning in refreshed['warnings']))

    def test_binoutput_gadget_definitions_dependencies_and_scope(self):
        excel = self.dataset / 'MappedExcelBinOutput_EN'
        (excel / 'GadgetExcelConfigData.json').write_text(json.dumps([
            {'Id': 1, 'JsonName': 'Arrow', 'Type': 'Bullet'},
            {'Id': 2, 'JsonName': 'Explosion', 'Type': 'Field'},
            {'Id': 3, 'Type': 'Gadget'}, {'Id': 4, 'JsonName': 'Missing'},
        ]), encoding='utf-8')
        root = self.dataset / 'BinOutput'
        files = {
            'Gadget/Shared.json': {
                'Arrow': {'abilities': [{'abilityName': 'Arrow_Ability'}]},
                'Unrelated': {'abilities': [{'abilityName': 'Unrelated_Ability'}]},
            },
            'Gadget/OtherShared.json': {
                'Explosion': {'abilities': [{'abilityName': 'Explosion_Ability'}]},
                'AnotherUnrelated': {'abilities': [{'abilityName': 'Unrelated_Ability'}]},
            },
            'Ability/Arrow.json': [{'Default': {'abilityName': 'Arrow_Ability', 'onAdded': [
                {'gadgetID': 2}, {'gadgetId': 1}, {'gadgetIDs': [999, 0]},
            ]}}],
            'Ability/Explosion.json': [{'Default': {'abilityName': 'Explosion_Ability',
                                                    'onAdded': [{'gadgetIds': [1]}]}}],
            'Ability/Unrelated.json': [{'Default': {'abilityName': 'Unrelated_Ability', 'modifiers': {}}}],
        }
        for relative, value in files.items():
            path = root.joinpath(*relative.split('/'))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value), encoding='utf-8')
        (root / 'Gadget' / 'Broken.json').write_text('{broken', encoding='utf-8')
        picker = self.client.get('/api/gadgets')
        self.assertEqual(picker.status_code, 200, picker.text)
        self.assertIn({'id': 1, 'name': 'Arrow', 'internal': 'Bullet'}, picker.json())
        scope = {'gadget_id': 1}
        response = self.client.get('/api/binoutput/references', params=scope)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['character'], 'Arrow')
        self.assertEqual(result['files'][0]['relative'], 'Gadget/Shared.json')
        self.assertEqual({item['relative'] for item in result['files']}, {
            'Gadget/Shared.json', 'Gadget/OtherShared.json', 'Ability/Arrow.json', 'Ability/Explosion.json',
        })
        self.assertTrue(any('Could not index Broken.json' in warning for warning in result['warnings']))
        self.assertTrue(any('1 referenced gadget IDs' in warning for warning in result['warnings']))
        for item in result['files']:
            self.assertEqual(self.client.get('/api/binoutput/file',
                                            params={'path': item['relative'], **scope}).status_code, 200)
        self.assertEqual(self.client.get('/api/binoutput/file',
                                        params={'path': 'Ability/Unrelated.json', **scope}).status_code, 404)
        for params in ({'character_id': 10000021, **scope}, {'enemy_id': 1, **scope}):
            self.assertEqual(self.client.get('/api/binoutput/references', params=params).status_code, 422)
            self.assertEqual(self.client.get('/api/binoutput/file',
                                            params={'path': 'Gadget/Shared.json', **params}).status_code, 422)
        for identifier in (3, 4):
            result = self.client.get('/api/binoutput/references', params={'gadget_id': identifier}).json()
            self.assertEqual(result['files'], [])
            self.assertTrue(result['warnings'])
        self.assertEqual(self.client.get('/api/binoutput/references', params={'gadget_id': 999}).status_code, 409)
        self.assertEqual(self.client.get('/api/binoutput/references', params={'gadget_id': 0}).status_code, 422)
        (root / 'Gadget' / 'Shared.json').write_text('{"Renamed": {}}', encoding='utf-8')
        refreshed = self.client.get('/api/binoutput/references', params=scope).json()
        self.assertEqual(refreshed['files'], [])
        self.assertTrue(any('No Gadget config' in warning for warning in refreshed['warnings']))

    def test_binoutput_gadget_raw_ids_survive_text_mapping(self):
        mapped = self.dataset / 'MappedExcelBinOutput_EN' / 'GadgetExcelConfigData.json'
        mapped.write_text(json.dumps([{'Id': 'Accidentally mapped text', 'JsonName': 'Arrow'}]), encoding='utf-8')
        self.assertEqual(self.client.get('/api/gadgets').status_code, 409)
        raw = self.dataset / 'ExcelBinOutput'
        raw.mkdir()
        (raw / 'GadgetExcelConfigData.json').write_text(json.dumps([
            {'id': 42, 'jsonName': 'Arrow', 'type': 'Bullet'},
        ]), encoding='utf-8')
        folder = self.dataset / 'BinOutput' / 'Gadget'
        folder.mkdir(parents=True)
        (folder / 'Shared.json').write_text('{"Arrow": {}}', encoding='utf-8')
        self.assertEqual(self.client.get('/api/gadgets').json(), [
            {'id': 42, 'name': 'Arrow', 'internal': 'Bullet'},
        ])
        response = self.client.get('/api/binoutput/references', params={'gadget_id': 42})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item['relative'] for item in response.json()['files']], ['Gadget/Shared.json'])

    def test_attribute_scaling_job(self):
        excel = self.dataset / 'MappedExcelBinOutput_EN'
        for name in ('AvatarTalentExcelConfigData', 'ChapterExcelConfigData', 'CombineExcelConfigData', 'FettersExcelConfigData',
                     'FishExcelConfigData', 'FishStockExcelConfigData', 'HomeWorldFurnitureExcelConfigData', 'MainQuestExcelConfigData',
                     'MonsterDescribeExcelConfigData', 'TowerFloorExcelConfigData', 'TowerLevelExcelConfigData',
                     'TowerScheduleExcelConfigData', 'GCGDeckExcelConfigData', 'GCGGameExcelConfigData',
                     'GCGGameRewardExcelConfigData', 'GCGWeekLevelExcelConfigData'):
            (excel / f'{name}.json').write_text('[]', encoding='utf-8')
        tables = {
            'AvatarExcelConfigData': [
                {'Id': 10000021, 'NameTextMapHash': 'Amber', 'SkillDepotId': 2101},
                {'Id': 10000007, 'NameTextMapHash': 'Traveler', 'SkillDepotId': 704, 'CandSkillDepotIds': [704]},
            ],
            'AvatarSkillDepotExcelConfigData': [{'Id': 2101, 'Skills': [10211, 0, 10214, 10213], 'EnergySkill': 10212}],
            'AvatarSkillExcelConfigData': [
                {'Id': 10211, 'NameTextMapHash': 'Normal Attack: Sharpshooter', 'ProudSkillGroupId': 1},
                {'Id': 10212, 'NameTextMapHash': 'Fiery Rain', 'ProudSkillGroupId': 2},
                {'Id': 10213, 'NameTextMapHash': 'Sprint', 'ProudSkillGroupId': 3},
                {'Id': 10214, 'NameTextMapHash': 'Unleveled', 'ProudSkillGroupId': 4},
            ],
            'ProudSkillExcelConfigData': [
                {'ProudSkillGroupId': 1, 'Level': 1, 'ParamDescList': ['1-Hit DMG|{param1:F1P}', 'Aimed Shot|{param2:F1P}×2'],
                 'ParamList': [0.3612, 0.4]},
                {'ProudSkillGroupId': 1, 'Level': 2, 'ParamDescList': ['1-Hit DMG|{param1:F1P}', 'Aimed Shot|{param2:F1P}×2'],
                 'ParamList': [0.3906, 0.5]},
                {'ProudSkillGroupId': 2, 'Level': 1, 'ParamDescList': [
                    'Burst DMG (Hold)|{param1:F1P} DEF', 'Wave DMG|{param1:F1P} DEF+{param2:I}', 'DMG Bonus|{param1:F1P}',
                    'Bloom DMG|{param1:F1P} Elemental Mastery', 'ATK Bonus|{param1:F1P} DEF',
                    'Healing|{param2:I} + {param1:F1P} Max HP', 'Duration|{param3:F1}s',
                ], 'ParamList': [1.2, 100, 2]},
                {'ProudSkillGroupId': 3, 'Level': 1, 'ParamDescList': ['Stamina Cost|{param1:F1}'], 'ParamList': [10]},
            ],
        }
        for name, rows in tables.items():
            (excel / f'{name}.json').write_text(json.dumps(rows), encoding='utf-8')
        self.assertEqual(self.client.post('/api/jobs', json={
            'tool_id': 'attribute-scaling', 'parameters': {'character_id': 10000021, 'normal_attack': 16},
        }).status_code, 422)
        response = self.client.post('/api/jobs', json={
            'tool_id': 'attribute-scaling',
            'parameters': {'character_id': 10000021, 'normal_attack': 2, 'elemental_skill': 3, 'elemental_burst': 1},
        })
        job = self.wait(response.json()['id'])
        self.assertEqual(job['status'], 'succeeded', self.client.get(f"/api/jobs/{job['id']}/logs").text)
        files = ['1 - Sharpshooter.wikitext', '2 - Sprint.wikitext', '3 - Fiery Rain.wikitext']
        self.assertNotIn('Saved abilities_', self.client.get(f"/api/jobs/{job['id']}/logs").json()['text'])
        self.assertEqual(sorted(file['path'] for file in job['files']), files)
        attack, sprint, burst = (self.client.get(f"/api/jobs/{job['id']}/preview/{name}").json()['text'] for name in files)
        self.assertTrue(attack.startswith('{{Talent Scaling\n|levels=2\n'))
        self.assertTrue(sprint.startswith('{{Talent Scaling\n|levels=3\n'))
        self.assertTrue(burst.startswith('{{Talent Scaling\n|levels=1\n'))
        self.assertIn('|titles=1-Hit DMG (%),', attack)
        self.assertIn('|hit1_1=36.12\n|hit1_2=39.06\n', attack)
        self.assertIn('|aimed_1=40 × 2\n', attack)
        self.assertIn('|titles=Burst DMG (Hold) (%DEF),Wave DMG,DMG Bonus,Bloom DMG (%EM),ATK Bonus (%DEF),Healing,Duration\n', burst)
        self.assertIn('|wavedmg=120% DEF + 100\n', burst)
        self.assertIn('|atkbonus=120\n|healing=100 + 120% Max HP\n', burst)
        self.assertIn('DEF + 100\n', burst)
        self.assertIn('|burstdmg(hold)=120\n', burst)
        self.assertIn('|bloomdmg=120\n', burst)
        for character, reason in ((99, 'not in the dataset'), (10000007, 'Traveler')):
            failed = self.wait(self.client.post('/api/jobs', json={
                'tool_id': 'attribute-scaling', 'parameters': {'character_id': character},
            }).json()['id'])
            self.assertEqual(failed['status'], 'failed')
            self.assertIn(reason, failed['error'])

    def test_interrupted_job_is_reported_after_restart(self):
        root = self.root / 'recovery'
        job = Job(id=uuid4().hex, tool_id='redirects', name='Redirect Builder', status='running')
        directory = root / job.id
        directory.mkdir(parents=True)
        (directory / 'job.json').write_text(job.model_dump_json(), encoding='utf-8')
        (directory / 'progress.json').write_text(json.dumps({
            'stage': 'Writing pages', 'completed': 2, 'total': 5, 'warnings': 2,
        }), encoding='utf-8')
        manager = JobManager(self.config, root)
        self.addCleanup(manager.close)
        recovered = manager.get(job.id)
        self.assertEqual(recovered.status, 'failed')
        self.assertIn('server stopped', recovered.error)
        self.assertIsNotNone(recovered.finished_at)
        self.assertEqual((recovered.progress.stage, recovered.progress.warnings), ('Failed', 2))
        self.assertIsNone(recovered.progress.total)
        self.assertIn('ERROR   The server stopped', (directory / 'log.txt').read_text())

    def test_character_kit_files_in_kit_order(self):
        root = self.root / 'ordering'
        names = ['Constellations/C1', 'Constellations/C6', 'Passives/A1', 'Passives/A4', 'Passives/NRG', 'Passives/UP',
                 'Skills/E', 'Skills/NA', 'Skills/Q']
        job = Job(id=uuid4().hex, tool_id='character-kit', name='Character Kit', status='succeeded',
                  files=[{'path': f'Mavuika/{name}.wikitext', 'size': 1, 'kind': 'text'} for name in names])
        (root / job.id).mkdir(parents=True)
        (root / job.id / 'job.json').write_text(job.model_dump_json(), encoding='utf-8')
        manager = JobManager(self.config, root)
        self.addCleanup(manager.close)
        self.assertEqual([Path(file.path).stem for file in manager.get(job.id).files],
                         ['NA', 'E', 'Q', 'A1', 'A4', 'NRG', 'UP', 'C1', 'C6'])

    def test_release_version_from_change_history(self):
        from wikiVersion import release_version
        text = 'Intro {{Change History|9.9}}\n==Change History==\n{{Change History|4.6|introduced=2.4}}\n\n==References=='
        body = json.dumps({'query': {'pages': {'1': {'revisions': [{'slots': {'main': {'*': text}}}]}}}}).encode()
        with patch('urllib.request.urlopen', return_value=io.BytesIO(body)):
            self.assertEqual(release_version('Arlecchino'), '4.6')
        with patch('urllib.request.urlopen', return_value=io.BytesIO(b'{"query": {"pages": {"-1": {"missing": ""}}}}')):
            self.assertIsNone(release_version('Nobody'))

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
        log = self.client.get(f"/api/jobs/{job['id']}/logs").json()['text']
        self.assertGreater(job['progress']['warnings'], 0)
        self.assertIn('WARNING ', log)
        self.assertNotIn('Replacements completed and saved', log)
        self.assertNotRegex(log, r'\[\d+:\d+\] INFO +\[\d+:\d+\]')
        self.assertEqual(self.client.get('/api/characters').json()[0]['name'], 'Amber')
        self.assertFalse((self.root / 'existing-output').exists())


if __name__ == '__main__':
    unittest.main()
