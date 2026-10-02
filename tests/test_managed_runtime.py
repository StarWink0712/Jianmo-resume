import json
from pathlib import Path
import sys
import tempfile
import unittest

from experiments.m1.managed import inventory, verify
from experiments.m1.runtime import profile, run_bounded
from experiments.m1.validate_managed import redact_evidence


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'data').write_bytes(b'original')
        (self.root / 'alias').symlink_to('data')
        self.save_manifest()

    def save_manifest(self):
        (self.root / 'runtime.json').write_text(json.dumps({'schema': 1, 'version': 'test', 'files': inventory(self.root)}))

    def test_relative_internal_links_verify(self):
        self.assertEqual(verify(self.root)['version'], 'test')

    def test_changed_file_rejected(self):
        (self.root / 'data').write_bytes(b'changed!')
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_extra_file_rejected(self):
        (self.root / 'extra').write_bytes(b'extra')
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_missing_file_rejected(self):
        (self.root / 'alias').unlink()
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_executable_mode_change_rejected(self):
        (self.root / 'data').chmod(0o755)
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_external_symlink_rejected(self):
        (self.root / 'alias').unlink()
        (self.root / 'alias').symlink_to('/bin/sh')
        with self.assertRaises(ValueError):
            inventory(self.root)

    def test_manifest_traversal_rejected(self):
        manifest = json.loads((self.root / 'runtime.json').read_text())
        manifest['files'][0]['path'] = '../escape'
        (self.root / 'runtime.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            verify(self.root)

    def test_explicit_fonts_do_not_add_developer_runtime(self):
        generated = profile(self.root / 'job', self.root / 'tex', fonts_root=self.root / 'tex/fonts')
        self.assertNotIn('.m1-runtime', generated)
        self.assertNotIn('/opt/homebrew', generated)

    def test_plain_and_json_escaped_paths_are_redacted(self):
        work = self.root / '\u4e2d\u6587'
        payload = {'plain': str(work / 'report'), 'escaped': json.dumps({'report': str(work / 'report')})}
        result = redact_evidence(payload, work)
        self.assertEqual(result['plain'], '<test-root>/report')
        self.assertIn('<test-root>/report', result['escaped'])


@unittest.skipUnless(sys.platform == 'darwin', 'macOS process supervisor')
class MemorySupervisorTests(unittest.TestCase):
    def test_memory_excess_stops_group_and_recovery_works(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_bounded([sys.executable, '-c', 'import time; data=bytearray(32*1024*1024); time.sleep(10)'],
                                 root, {'PATH': '/usr/bin:/bin'}, timeout=5, memory_limit_bytes=16*1024*1024)
            self.assertTrue(result['memory_exceeded'])
            self.assertFalse(result['timed_out'])
            recovered = run_bounded(['/usr/bin/true'], root, {'PATH': '/usr/bin:/bin'})
            self.assertEqual(recovered['returncode'], 0)

    def test_wall_timeout_still_works(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = run_bounded(['/bin/sleep', '2'], Path(temporary), {'PATH': '/usr/bin:/bin'}, timeout=.1)
            self.assertTrue(result['timed_out'])
            self.assertFalse(result['memory_exceeded'])


if __name__ == '__main__':
    unittest.main()
