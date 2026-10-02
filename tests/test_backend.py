import copy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
import warnings
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.backup import export_backup, import_backup
from backend.domain import AppError
from backend.service import Service
from scripts.check_contracts import build_case, cases, json_bytes, synthetic_png


ORIGIN = 'http://127.0.0.1:8770'


class FakeCompiler:
    fingerprint = 'fake-test-runtime'

    def __init__(self):
        self.gate = threading.Event()
        self.gate.set()
        self.snapshots = []

    def __call__(self, document, assets, job):
        self.gate.wait(3)
        self.snapshots.append(copy.deepcopy(document))
        if document['basics']['name'] == 'FAIL':
            raise AppError(422, 'compile_failed', '测试编译失败')
        return b'%PDF-1.4\nFAKE_UNIT_TEST\n' + json_bytes({'id': document['id'], 'revision': document['revision']}), 1


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.compiler = FakeCompiler()
        self.start()

    def start(self):
        self.app = create_app(self.root, compiler=self.compiler, seed_examples=False)
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.client.__enter__()
        response = self.client.get('/api/session', headers={'X-Resume-Bootstrap': '1'})
        self.token = response.json()['token']
        self.client.headers.update({'Origin': ORIGIN, 'X-Resume-Token': self.token})

    def tearDown(self):
        self.compiler.gate.set()
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def create(self, title='测试简历', kind='sample'):
        response = self.client.post('/api/resumes', json={'title': title, 'kind': kind})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['resume']

    def test_fonts_are_local_allowlisted_assets(self):
        from experiments.m1.fonts import FONT_FILES, font_media_type
        import hashlib
        for name, (size, sha256) in FONT_FILES.items():
            response = self.client.get('/assets/' + name)
            self.assertEqual(response.headers['content-type'], font_media_type(name))
            self.assertEqual(len(response.content), size)
            self.assertEqual(hashlib.sha256(response.content).hexdigest(), sha256)
        self.assertEqual(self.client.get('/assets/PingFang.ttc').status_code, 404)

    def test_explicit_linebreaks_survive_save_and_backup(self):
        document = self.create()
        body = '[1] **Example Author**. First paper.  \n[2] *Second paper*.\n\nNew paragraph.'
        document['sections'][0]['entries'][0]['body'] = body
        saved = self.save(document).json()['resume']
        restored = self.client.get('/api/resumes/' + document['id']).json()['resume']
        self.assertEqual(restored['sections'][0]['entries'][0]['body'], body)
        archive = self.client.get(f'/api/resumes/{saved["id"]}/backup?expected_revision={saved["revision"]}').content
        self.assertEqual(import_backup(archive)[0]['sections'][0]['entries'][0]['body'], body)

    def test_pixel_style_and_awards_survive_restart_copy_backup(self):
        document = self.create()
        self.assertEqual(document['style']['version'], 3)
        document['style'].update(theme_color='#0F766E', section_title_size_px=18, content_size_px=15,
                                 line_height=1.4, section_gap_px=9, name_size_px=20)
        document['style']['margins_px'].update(top=25, bottom=5, left=20, right=20)
        document['sections'][-1]['type'] = 'awards'
        document['sections'][-1]['title'] = '获奖经历'
        saved = self.save(document).json()['resume']
        self.client.__exit__(None, None, None)
        self.start()
        restored = self.client.get('/api/resumes/' + saved['id']).json()['resume']
        self.assertEqual(restored, saved)
        copied = self.client.post(f'/api/resumes/{saved["id"]}/copy', json={
            'expected_revision':saved['revision'], 'title':'style copy', 'version':'saved'}).json()['resume']
        archive = self.client.get(f'/api/resumes/{saved["id"]}/backup?expected_revision={saved["revision"]}').content
        imported = self.client.post('/api/import', content=archive, headers={'Content-Type':'application/zip'}).json()['resume']
        for result in (copied, imported):
            self.assertEqual(result['style'], saved['style'])
            self.assertEqual(result['sections'][-1]['type'], 'awards')
        bad = copy.deepcopy(saved)
        bad['style']['theme_color'] = '#000000; bad'
        self.assertEqual(self.save(bad).status_code, 422)
        self.assertEqual(self.client.get('/api/resumes/' + saved['id']).json()['resume'], saved)
        for key in ('section_title_size_px', 'section_gap_px'):
            bad = copy.deepcopy(saved)
            bad['style'][key] = 15.94
            self.assertEqual(self.save(bad).status_code, 422)
        bad = copy.deepcopy(saved)
        bad['style']['margins_px']['left'] = 45.354
        self.assertEqual(self.save(bad).status_code, 422)

    def save(self, document, expected=None):
        return self.client.put('/api/resumes/' + document['id'], json={'expected_revision': expected or document['revision'], 'resume': document})

    def compile(self, document):
        response = self.client.post(f'/api/resumes/{document["id"]}/compile', json={'expected_revision': document['revision']})
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def wait(self, job):
        for _ in range(200):
            result = self.client.get('/api/jobs/' + job['id']).json()
            if result['status'] not in ('queued', 'running'):
                return result
            time.sleep(.01)
        self.fail('job did not finish')

    def test_create_save_restart_and_session_rotation(self):
        document = self.create()
        document['basics']['name'] = '持久化测试'
        saved = self.save(document).json()['resume']
        self.assertEqual(saved['revision'], 2)
        old_token = self.token
        self.client.__exit__(None, None, None)
        self.start()
        loaded = self.client.get('/api/resumes/' + document['id']).json()['resume']
        self.assertEqual(loaded, saved)
        self.assertNotEqual(old_token, self.token)
        self.assertEqual(self.client.get('/api/resumes', headers={'X-Resume-Token': old_token}).status_code, 403)

    def test_optimistic_conflict_and_noop_save(self):
        document = self.create()
        self.assertEqual(self.save(document).json()['resume']['revision'], 1)
        altered = copy.deepcopy(document)
        altered['basics']['name'] = 'first writer'
        self.assertEqual(self.save(altered).status_code, 200)
        document['basics']['name'] = 'stale writer'
        conflict = self.save(document)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.json()['current_revision'], 2)
        self.assertEqual(self.client.get('/api/resumes/' + document['id']).json()['resume']['basics']['name'], 'first writer')

    def test_gender_age_and_blank_link_survive_restart_copy_and_import(self):
        document = self.create()
        self.assertEqual(document['basics']['gender'], '')
        self.assertIsNone(document['basics']['age'])
        document['basics'].update(gender='女', age=28)
        document['basics']['links'][0]['label'] = ''
        saved = self.save(document).json()['resume']
        self.client.__exit__(None, None, None)
        self.start()
        self.assertEqual(self.client.get('/api/resumes/' + saved['id']).json()['resume'], saved)
        copied = self.client.post(f'/api/resumes/{saved["id"]}/copy', json={
            'expected_revision':saved['revision'], 'title':'copy', 'version':'saved'}).json()['resume']
        archive = self.client.get(f'/api/resumes/{saved["id"]}/backup?expected_revision={saved["revision"]}').content
        imported = self.client.post('/api/import', content=archive, headers={'Content-Type':'application/zip'}).json()['resume']
        for target in (copied, imported):
            self.assertEqual(target['basics']['gender'], '女')
            self.assertEqual(target['basics']['age'], 28)
            self.assertEqual(target['basics']['links'][0]['label'], '')
        saved['basics']['age'] = None
        cleared = self.save(saved).json()['resume']
        self.assertIsNone(cleared['basics']['age'])

    def test_old_resume_without_demographic_fields_remains_compatible(self):
        document = self.create()
        document['basics'].pop('gender')
        document['basics'].pop('age')
        saved = self.save(document).json()['resume']
        self.assertNotIn('gender', saved['basics'])
        self.assertEqual(self.save(saved).json()['resume'], saved)
        archive = self.client.get(f'/api/resumes/{saved["id"]}/backup?expected_revision={saved["revision"]}').content
        imported = self.client.post('/api/import', content=archive, headers={'Content-Type':'application/zip'})
        self.assertEqual(imported.status_code, 201)
        self.assertNotIn('age', imported.json()['resume']['basics'])

    def test_two_concurrent_writers_only_one_commits(self):
        document = self.create()
        barrier = threading.Barrier(2)
        results = []
        def write(name):
            draft = copy.deepcopy(document)
            draft['basics']['name'] = name
            barrier.wait()
            try:
                self.app.state.service.save(document['id'], 1, draft)
                results.append('saved')
            except AppError as error:
                results.append(error.code)
        threads = [threading.Thread(target=write, args=(name,)) for name in ('one','two')]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertCountEqual(results, ['saved', 'revision_conflict'])

    def test_save_acknowledges_its_own_revision(self):
        document = self.create()
        service = self.app.state.service
        original_save = service.store.save
        first_written, second_done = threading.Event(), threading.Event()
        results = {}

        def hooked_save(*args, **kwargs):
            saved = original_save(*args, **kwargs)
            if saved['basics']['name'] == 'first writer':
                results['first_snapshot'] = saved
                first_written.set()
                second_done.wait(.15)
            return saved

        def first():
            draft = copy.deepcopy(document)
            draft['basics']['name'] = 'first writer'
            results['first'] = service.save(document['id'], 1, draft)

        def second():
            first_written.wait(2)
            draft = copy.deepcopy(results['first_snapshot'])
            draft['basics']['name'] = 'second writer'
            results['second'] = service.save(document['id'], 2, draft)
            second_done.set()

        with patch.object(service.store, 'save', side_effect=hooked_save):
            threads = [threading.Thread(target=first), threading.Thread(target=second)]
            for thread in threads: thread.start()
            for thread in threads: thread.join(3)
        self.assertEqual(results['first']['resume']['revision'], 2)
        self.assertEqual(results['first']['resume']['basics']['name'], 'first writer')
        self.assertEqual(results['second']['resume']['revision'], 3)

    def test_invalid_contract_and_immutable_fields_do_not_write(self):
        document = self.create()
        for field, value in [('id','resume-other'), ('revision',7), ('created_at','2020-01-01T00:00:00Z')]:
            draft = copy.deepcopy(document); draft[field] = value
            response = self.client.put('/api/resumes/' + document['id'], json={'expected_revision': 1, 'resume': draft})
            self.assertEqual(response.status_code, 422, response.text)
        draft = copy.deepcopy(document); draft['basics']['extra'] = 'invalid'
        self.assertEqual(self.save(draft).status_code, 422)
        self.assertEqual(self.app.state.service.store.get(document['id'])['revision'], 1)

    def test_disk_failure_rolls_back_revision(self):
        document = self.create(); document['basics']['name'] = 'unsaved'
        with patch.object(self.app.state.service.store, 'put_blobs', side_effect=sqlite3.OperationalError('test failure')):
            self.assertEqual(self.save(document).status_code, 503)
        self.assertEqual(self.app.state.service.store.get(document['id'])['revision'], 1)

    def test_saved_and_draft_copy_are_independent_with_new_ids(self):
        source = self.create()
        draft = copy.deepcopy(source); draft['basics']['name'] = 'draft only'
        saved_copy = self.client.post(f'/api/resumes/{source["id"]}/copy', json={'expected_revision':1,'title':'saved copy','version':'saved'}).json()['resume']
        draft_copy = self.client.post(f'/api/resumes/{source["id"]}/copy', json={'expected_revision':1,'title':'draft copy','version':'draft','draft':draft}).json()['resume']
        self.assertEqual(saved_copy['basics']['name'], source['basics']['name'])
        self.assertEqual(draft_copy['basics']['name'], 'draft only')
        self.assertNotEqual(saved_copy['sections'][0]['entries'][0]['id'], source['sections'][0]['entries'][0]['id'])
        self.assertEqual(self.app.state.service.store.get(source['id']), source)
        self.assertIsNone(self.client.get('/api/resumes/' + draft_copy['id']).json()['pdf'])

    def test_avatar_backup_import_and_delete_source_preserve_copy(self):
        source = self.create()
        response = self.client.put(f'/api/resumes/{source["id"]}/avatar?expected_revision=1', content=synthetic_png(), headers={'Content-Type':'application/octet-stream'})
        self.assertEqual(response.status_code, 200, response.text)
        source = response.json()['resume']
        backup = self.client.get(f'/api/resumes/{source["id"]}/backup?expected_revision=2')
        self.assertEqual(backup.status_code, 200)
        restored = self.client.post('/api/import', content=backup.content, headers={'Content-Type':'application/zip'})
        self.assertEqual(restored.status_code, 201, restored.text)
        imported = restored.json()['resume']
        self.assertNotEqual(imported['attachments'][0]['id'], source['attachments'][0]['id'])
        self.assertEqual(imported['attachments'][0]['sha256'], source['attachments'][0]['sha256'])
        self.assertEqual(self.client.request('DELETE', '/api/resumes/' + source['id'], json={'expected_revision':2}).status_code, 200)
        self.assertTrue(self.app.state.service.store.assets(imported))
        self.assertEqual(self.wait(self.compile(imported))['status'], 'succeeded')

    def test_bad_avatar_and_backup_leave_no_partial_records(self):
        source = self.create()
        self.assertEqual(self.client.put(f'/api/resumes/{source["id"]}/avatar?expected_revision=1', content=b'not an image', headers={'Content-Type':'application/octet-stream'}).status_code, 422)
        self.assertEqual(self.client.post('/api/import',content=b'bad archive',headers={'Content-Type':'application/zip'}).status_code,422)
        self.assertEqual(len(self.app.state.service.list()),1)
        self.assertEqual(self.app.state.service.store.get(source['id'])['revision'],1)

    def test_avatar_read_is_authenticated_and_keeps_resume_unchanged(self):
        source = self.create()
        path = f'/api/resumes/{source["id"]}/avatar'
        self.assertEqual(self.client.get(path, params={'attachment_id': 'missing'}).status_code, 404)
        source = self.client.put(path + '?expected_revision=1', content=synthetic_png(),
                                 headers={'Content-Type': 'application/octet-stream'}).json()['resume']
        params = {'attachment_id': source['attachments'][0]['id']}
        response = self.client.get(path, params=params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['content-type'], 'image/png')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.content, next(iter(self.app.state.service.store.assets(source).values())))
        self.assertEqual(self.client.get(path, params=params, headers={'X-Resume-Token': 'wrong'}).status_code, 403)
        self.assertEqual(self.client.get(path, params=params, headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.app.state.service.store.get(source['id']), source)

    def test_avatar_read_rejects_other_resumes_and_replaced_attachments(self):
        source, other = self.create(), self.create()
        path = f'/api/resumes/{source["id"]}/avatar'
        source = self.client.put(path + '?expected_revision=1', content=synthetic_png(),
                                 headers={'Content-Type': 'application/octet-stream'}).json()['resume']
        previous_id = source['attachments'][0]['id']
        self.assertEqual(self.client.get(f'/api/resumes/{other["id"]}/avatar',
                                        params={'attachment_id': previous_id}).status_code, 404)
        source = self.client.put(path + '?expected_revision=2', content=synthetic_png(),
                                 headers={'Content-Type': 'application/octet-stream'}).json()['resume']
        self.assertEqual(self.client.get(path, params={'attachment_id': previous_id}).status_code, 409)
        self.assertEqual(self.client.get(path, params={'attachment_id': source['attachments'][0]['id']}).status_code, 200)

    def test_cropped_portrait_survives_backup_and_stale_replacement_is_rejected(self):
        from PIL import Image
        image = io.BytesIO()
        Image.new('RGB', (600, 800), '#2457a7').save(image, format='JPEG')
        source = self.create()
        path = f'/api/resumes/{source["id"]}/avatar?expected_revision=1'
        source = self.client.put(path, content=image.getvalue(),
                                 headers={'Content-Type': 'application/octet-stream'}).json()['resume']
        item = source['attachments'][0]
        self.assertEqual((item['width_px'], item['height_px']), (600, 800))
        self.assertEqual(self.client.put(path, content=synthetic_png(),
                                        headers={'Content-Type': 'application/octet-stream'}).status_code, 409)
        self.assertEqual(self.app.state.service.store.get(source['id']), source)
        archive = self.client.get(f'/api/resumes/{source["id"]}/backup?expected_revision=2').content
        restored, assets = import_backup(archive)
        self.assertEqual(restored, source)
        self.assertEqual(assets, self.app.state.service.store.assets(source))

    def test_avatar_upload_limit_cannot_bypass_backend_or_replace_previous_avatar(self):
        from backend.domain import MAX_AVATAR_UPLOAD_BYTES
        source = self.create()
        path = f'/api/resumes/{source["id"]}/avatar?expected_revision=1'
        exact = synthetic_png()
        exact += b'\0' * (MAX_AVATAR_UPLOAD_BYTES - len(exact))
        response = self.client.put(path, content=exact, headers={'Content-Type':'application/octet-stream'})
        self.assertEqual(response.status_code, 200)
        source = response.json()['resume']
        before = self.app.state.service.store.assets(source)
        response = self.client.put(f'/api/resumes/{source["id"]}/avatar?expected_revision=2',
            content=b'x' * (MAX_AVATAR_UPLOAD_BYTES + 1), headers={'Content-Type':'application/octet-stream'})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()['code'], 'avatar_too_large')
        self.assertIn('1 MB', response.json()['message'])
        self.assertEqual(self.app.state.service.store.get(source['id']), source)
        self.assertEqual(self.app.state.service.store.assets(source), before)

    def test_queue_snapshot_dedup_and_old_preview_stays_stale(self):
        document = self.create(); self.compiler.gate.clear()
        old_job = self.compile(document)
        self.assertEqual(self.compile(document)['id'], old_job['id'])
        document['basics']['name'] = 'new revision'
        updated = self.save(document).json()['resume']
        self.assertEqual(self.client.request('DELETE', '/api/resumes/' + document['id'], json={'expected_revision':2}).status_code,409)
        self.compiler.gate.set()
        self.assertEqual(self.wait(old_job)['status'],'succeeded')
        detail = self.client.get('/api/resumes/' + document['id']).json()
        self.assertNotEqual(detail['build_key'], detail['pdf']['build_key'])
        new_job = self.wait(self.compile(updated))
        self.assertEqual(new_job['status'],'succeeded')
        self.assertNotEqual(self.compiler.snapshots[0]['basics']['name'], 'new revision')
        self.assertEqual(self.client.get('/api/resumes/' + document['id']).json()['pdf']['revision'],2)

    def test_failed_compile_keeps_saved_content_and_last_pdf(self):
        document = self.create(); good = self.wait(self.compile(document))
        document['basics']['name'] = 'FAIL'; document = self.save(document).json()['resume']
        bad = self.wait(self.compile(document))
        self.assertEqual(bad['status'],'failed')
        detail = self.client.get('/api/resumes/' + document['id']).json()
        self.assertEqual(detail['resume']['basics']['name'],'FAIL')
        self.assertEqual(detail['pdf']['id'],good['id'])
        self.assertEqual(self.client.get('/api/jobs/' + bad['id'] + '/pdf').status_code,409)
        retry = self.compile(document)
        self.assertNotEqual(retry['id'],bad['id'])
        self.wait(retry)

    def test_preview_and_download_are_same_bytes_and_survive_restart(self):
        document = self.create(); job = self.wait(self.compile(document))
        first = self.client.get('/api/jobs/' + job['id'] + '/pdf')
        self.assertEqual(first.content,self.client.get('/api/jobs/' + job['id'] + '/pdf?download=true').content)
        self.assertEqual(first.headers['x-build-key'],job['build_key'])
        self.client.__exit__(None,None,None); self.start()
        self.assertEqual(first.content,self.client.get('/api/jobs/' + job['id'] + '/pdf').content)

    def test_recovery_marks_interrupted_jobs_failed(self):
        document = self.create()
        with self.app.state.service.store.transaction() as db:
            db.execute("INSERT INTO jobs(id,resume_id,revision,build_key,status,created_at) VALUES('job-abandoned',?,1,'key','running','2026-10-01T00:00:00Z')",(document['id'],))
        self.client.__exit__(None,None,None); self.start()
        self.assertEqual(self.client.get('/api/jobs/job-abandoned').json()['status'],'failed')

    def test_instance_lock_rejects_second_service(self):
        with self.assertRaises(AppError): Service(self.root,compiler=FakeCompiler())

    def test_security_boundaries_and_session_bootstrap(self):
        self.assertEqual(self.client.get('/api/session').status_code,403)
        self.assertEqual(self.client.get('/api/resumes',headers={'X-Resume-Token':'bad'}).status_code,403)
        self.assertEqual(self.client.get('/api/resumes',headers={'Host':'evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/resumes',headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/api/resumes',headers=[('Host','127.0.0.1:8770'),('Host','evil.example')]).status_code,400)
        self.assertEqual(self.client.post('/api/resumes',json={'title':'no origin','kind':'blank'},headers={'Origin':''}).status_code,403)
        self.assertEqual(self.client.post('/api/resumes',content='{}',headers={'Content-Type':'text/plain'}).status_code,415)
        self.assertEqual(self.client.options('/api/resumes',headers={'Origin':'https://evil.example'}).status_code,403)

    def test_duplicate_json_unknown_fields_and_size_limits(self):
        self.assertEqual(self.client.post('/api/resumes',content='{"title":"a","title":"b","kind":"blank"}',headers={'Content-Type':'application/json'}).status_code,422)
        self.assertEqual(self.client.post('/api/resumes',json={'title':'a','kind':'blank','other':1}).status_code,422)
        self.assertEqual(self.client.post('/api/resumes',content=b' '*(2*1024**2+1),headers={'Content-Type':'application/json'}).status_code,413)

    def test_pdf_requests_need_token(self):
        document = self.create(); job = self.wait(self.compile(document))
        self.assertEqual(self.client.get('/api/jobs/' + job['id'] + '/pdf',headers={'X-Resume-Token':''}).status_code,403)

    def test_static_allowlist_and_local_viewer_policy(self):
        response = self.client.get('/assets/pdf.worker.min.mjs')
        self.assertEqual(response.status_code, 200)
        self.assertIn('javascript', response.headers['content-type'])
        self.assertIn("worker-src 'self'", response.headers['content-security-policy'])
        self.assertEqual(self.client.get('/assets/resumes.sqlite3').status_code, 404)
        self.assertEqual(self.client.get('/assets/app.py').status_code, 404)
        for name in ('markdown-model.mjs', 'markdown-editor.mjs', 'section-model.mjs', 'avatar-model.mjs',
                     'avatar-crop-model.mjs', 'avatar-crop.mjs'):
            response = self.client.get('/assets/' + name)
            self.assertEqual(response.status_code, 200)
            self.assertIn('javascript', response.headers['content-type'])

    def test_achievement_modules_survive_restart_copy_backup(self):
        from scripts.check_contracts import ROOT
        document = self.create()
        document['sections'].extend(json.loads((ROOT / 'fixtures/achievement-sections.json').read_text()))
        saved = self.save(document).json()['resume']
        self.client.__exit__(None, None, None)
        self.start()
        self.assertEqual(self.client.get('/api/resumes/' + saved['id']).json()['resume'], saved)
        copied = self.client.post(f'/api/resumes/{saved["id"]}/copy', json={
            'expected_revision':saved['revision'], 'title':'achievement copy', 'version':'saved'}).json()['resume']
        archive = self.client.get(f'/api/resumes/{saved["id"]}/backup?expected_revision={saved["revision"]}').content
        imported = self.client.post('/api/import', content=archive, headers={'Content-Type':'application/zip'}).json()['resume']
        for result in (copied, imported):
            for actual, original in zip(result['sections'], saved['sections']):
                self.assertEqual((actual['type'], actual['title'], actual['visible']),
                                 (original['type'], original['title'], original['visible']))
                self.assertNotEqual(actual['id'], original['id'])
                for entry, old in zip(actual['entries'], original['entries']):
                    self.assertEqual({k:v for k,v in entry.items() if k != 'id'},
                                     {k:v for k,v in old.items() if k != 'id'})
                    self.assertNotEqual(entry['id'], old['id'])
        copied['sections'][-1]['entries'][0]['role'] = '副本中的角色'
        self.assertEqual(self.save(copied).status_code, 200)
        self.assertEqual(self.client.get('/api/resumes/' + saved['id']).json()['resume'], saved)

    def test_compiler_fingerprint_change_invalidates_cached_pdf(self):
        document = self.create()
        first = self.wait(self.compile(document))
        self.compiler.fingerprint = 'changed-template-or-runtime'
        detail = self.client.get('/api/resumes/' + document['id']).json()
        self.assertNotEqual(detail['pdf']['build_key'], detail['build_key'])
        second = self.wait(self.compile(document))
        self.assertNotEqual(first['id'], second['id'])

    def test_deep_json_rejected_without_mutation(self):
        response = self.client.post('/api/resumes', content='[' * 3000 + '0' + ']' * 3000,
                                    headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.app.state.service.list(), [])


class ArchiveTests(unittest.TestCase):
    def test_duplicate_archive_member_rejected(self):
        buffer = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(buffer, 'w') as archive:
                archive.writestr('manifest.json', '{}')
                archive.writestr('resume.json', '{}')
                archive.writestr('resume.json', '{}')
        with self.assertRaises(AppError):
            import_backup(buffer.getvalue())

    def test_traversal_symlink_duplicates_and_oversize_rejected(self):
        for name in ('../escape','/absolute','assets/../../escape','assets\\bad.png','folder/'):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer,'w') as archive:
                archive.writestr('manifest.json','{}'); archive.writestr(name,'x')
            with self.subTest(name=name), self.assertRaises(AppError): import_backup(buffer.getvalue())
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer,'w') as archive:
            archive.writestr('manifest.json','{}'); item=zipfile.ZipInfo('resume.json'); item.external_attr=0o120777<<16; archive.writestr(item,'target')
        with self.assertRaises(AppError): import_backup(buffer.getvalue())
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json','{}'); archive.writestr('resume.json',b' '*(2*1024**2+1))
        with self.assertRaises(AppError): import_backup(buffer.getvalue())

    def test_real_fixture_roundtrip_preserves_bytes(self):
        document, assets = build_case(next(item for item in cases() if item['id']=='avatar'))
        restored, copied = import_backup(export_backup(document,assets))
        self.assertEqual(restored,document); self.assertEqual(copied,assets)


if __name__ == '__main__':
    unittest.main()
