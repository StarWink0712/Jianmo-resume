import copy
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.app import create_app
from backend.backup import import_backup
from backend.domain import AppError, new_resume, validate
from backend.examples import EXAMPLES, example_document
from backend.service import Service
from backend.store import Store
from scripts.check_contracts import ROOT


class UnusedCompiler:
    fingerprint = 'reference-resume-test'

    def __call__(self, *_args):
        raise AssertionError('Reference initialization must not compile automatically')


class ReferenceResumeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def service(self, **kwargs):
        service = Service(self.root, compiler=UnusedCompiler(), **kwargs)
        self.addCleanup(service.close)
        return service

    def test_bundled_json_and_portable_backups_match_and_are_fictional(self):
        self.assertEqual(list(EXAMPLES), ['java', 'algorithm', 'testing'])
        for kind, filename in EXAMPLES.items():
            document = example_document(kind)
            validate(document, {})
            self.assertIn('虚构', document['title'])
            self.assertIn('虚构', document['basics']['name'])
            self.assertTrue(document['basics']['email'].endswith('@example.com'))
            self.assertEqual(document['attachments'], [])
            self.assertGreaterEqual(len(document['sections']), 5)
            self.assertTrue(all(entry['body'] for section in document['sections'] for entry in section['entries']))
            restored = import_backup((ROOT / 'examples/backups' / (filename + '.resume.zip')).read_bytes())
            self.assertEqual(restored, (document, {}))

    def test_default_app_first_start_has_three_independent_editable_resumes(self):
        app = create_app(self.root, compiler=UnusedCompiler())
        with TestClient(app, base_url='http://127.0.0.1:8770') as client:
            token = client.get('/api/session', headers={'X-Resume-Bootstrap': '1'}).json()['token']
            client.headers.update({'X-Resume-Token': token, 'Origin': 'http://127.0.0.1:8770'})
            records = client.get('/api/resumes').json()
            self.assertEqual([item['title'] for item in records], [example_document(kind)['title'] for kind in EXAMPLES])
            self.assertEqual(len({item['id'] for item in records}), 3)
            saved = client.get('/api/resumes/' + records[0]['id']).json()['resume']
            self.assertNotEqual(saved['id'], example_document('java')['id'])
            saved['basics']['name'] = '用户自己的内容'
            result = client.put('/api/resumes/' + saved['id'], json={'expected_revision': 1, 'resume': saved})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['resume']['basics']['name'], '用户自己的内容')

    def test_editing_or_deleting_examples_survives_restart_without_reseeding(self):
        service = self.service()
        docs = service.store.documents()
        edited = copy.deepcopy(docs[0]); edited['basics']['name'] = '已编辑'
        service.save(edited['id'], 1, edited)
        service.store.delete(docs[1]['id'], 1)
        service.close()
        restarted = self.service()
        self.assertEqual(len(restarted.list()), 2)
        self.assertEqual(restarted.store.get(edited['id'])['basics']['name'], '已编辑')
        for document in restarted.store.documents():
            restarted.store.delete(document['id'], document['revision'])
        restarted.close()
        self.assertEqual(self.service().list(), [])

    def test_failed_initialization_rolls_back_and_retries_on_next_start(self):
        def interrupted():
            yield new_resume('first', 'java')
            raise RuntimeError('injected interruption')
        with patch.object(Service, '_examples', staticmethod(interrupted)):
            with self.assertRaises(RuntimeError):
                Service(self.root, compiler=UnusedCompiler())
        with closing(sqlite3.connect(self.root / 'resumes.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM resumes').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT value FROM app_metadata WHERE key='bundled_examples'").fetchone()[0], 'pending')
        self.assertEqual(len(self.service().list()), 3)

    def test_existing_populated_or_empty_databases_are_not_modified(self):
        for populated in (True, False):
            with self.subTest(populated=populated), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'resumes.sqlite3'
                store = Store(path)
                if populated:
                    document, assets = new_resume('existing', 'blank')
                    store.insert(document, assets)
                # Simulate an earlier application version, including an intentionally empty library.
                store.db.execute('DROP TABLE app_metadata')
                store.close()
                service = Service(directory, compiler=UnusedCompiler())
                try:
                    self.assertEqual(len(service.list()), int(populated))
                    if populated:
                        self.assertEqual(service.store.get(document['id']), document)
                finally:
                    service.close()

    def test_explicit_empty_start_is_remembered(self):
        service = self.service(seed_examples=False)
        self.assertEqual(service.list(), [])
        service.close()
        self.assertEqual(self.service().list(), [])

    def test_reference_selection_is_explicit_after_deletion_and_copies_are_independent(self):
        service = self.service()
        for doc in service.store.documents():
            service.store.delete(doc['id'], doc['revision'])
        for kind in EXAMPLES:
            first = service.create('first ' + kind, kind)['resume']
            second = service.create('second ' + kind, kind)['resume']
            self.assertNotEqual(first['id'], second['id'])
            self.assertNotEqual(first['sections'][0]['id'], second['sections'][0]['id'])
            self.assertEqual(first['style'], example_document(kind)['style'])
        service.close()
        self.assertEqual(len(self.service().list()), 6)

    def test_invalid_example_selection_has_a_controlled_error(self):
        for kind in ('unknown', '../java', [], {}, None, False):
            with self.subTest(kind=kind), self.assertRaises(AppError):
                new_resume('test', kind)


if __name__ == '__main__':
    unittest.main()
