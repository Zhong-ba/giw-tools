import io
import json
from pathlib import Path
import tempfile
import time
import unittest
import urllib.parse
from unittest.mock import patch
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
        self.assertEqual({tool['id'] for tool in tools}, {'redirects', 'character-kit', 'other-languages',
                                                         'attribute-scaling', 'character-data', 'enemy', 'bounties', 'fishing-points', 'fish-weights',
                                                         'manual-cooking', 'spiral-abyss', 'stygian-onslaught', 'imaginarium-theater'})
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
        manager = JobManager(self.config, root)
        self.addCleanup(manager.close)
        recovered = manager.get(job.id)
        self.assertEqual(recovered.status, 'failed')
        self.assertIn('server stopped', recovered.error)
        self.assertIsNotNone(recovered.finished_at)

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
        self.assertEqual(self.client.get('/api/characters').json()[0]['name'], 'Amber')
        self.assertFalse((self.root / 'existing-output').exists())


if __name__ == '__main__':
    unittest.main()
