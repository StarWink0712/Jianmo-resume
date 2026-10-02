import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import light_runtime as runtime
from scripts.check_contracts import ROOT


class LightRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def archive(self, entries):
        target = self.root / 'sample.tar.xz'
        with tarfile.open(target, 'w:xz') as stream:
            for name, data, kind in entries:
                entry = tarfile.TarInfo(name)
                entry.type = kind
                entry.size = len(data)
                stream.addfile(entry, io.BytesIO(data))
        return target

    def package(self, data=b'fake-engine'):
        archive = self.archive([('bin/xetex', data, tarfile.REGTYPE)])
        return archive, {'name': 'xetex', 'member': 'bin/xetex', 'target': 'tex/bin/xelatex',
                         'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                         'archive_bytes': archive.stat().st_size,
                         'archive_sha512': hashlib.sha512(archive.read_bytes()).hexdigest(),
                         'urls': ['https://example.invalid/engine.tar.xz']}

    def test_published_bundle_matches_lock_and_baseline(self):
        lock = json.loads((ROOT / 'runtime/tex.lock.json').read_text())
        self.assertEqual(lock['baseline_sha256'], runtime.digest(ROOT / 'docs/m1/runtime-inputs.json'))
        archive = ROOT / 'runtime' / lock['support']['archive']
        runtime.check_archive(archive, lock['support']['bytes'], lock['support']['sha256'])
        runtime.unpack_support(archive, self.root, lock['support']['unpacked_bytes'])
        support = self.root / 'support-inventory.json'
        self.assertEqual(runtime.digest(support), lock['support']['inventory_sha256'])
        for item in json.loads(support.read_text())['files']:
            self.assertEqual(runtime.digest(self.root / item['path']), item['sha256'])
        seed = json.loads((ROOT / 'docs/m1/runtime-inputs.json').read_text())
        for item in seed['tex_inputs'] + seed['format_inputs']:
            if not item['path'].startswith('bin/'):
                file = self.root / 'tex' / item['path']
                if not file.exists():
                    file = self.root / 'format-sources' / item['path']
                self.assertEqual(runtime.digest(file), item['sha256'])
        self.assertFalse((self.root / 'tex/bin').exists())
        self.assertFalse((self.root / 'tex/formats').exists())

    def test_unsafe_paths_are_rejected(self):
        for name in ('../outside', '/absolute', 'tex/../../outside', 'tex//file', '.', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                runtime.safe_name(name)

    def test_support_links_and_duplicates_are_rejected(self):
        for entries in ([('tex/link', b'', tarfile.SYMTYPE)],
                        [('tex/file', b'a', tarfile.REGTYPE), ('tex/file', b'b', tarfile.REGTYPE)]):
            with self.subTest(entries=entries):
                with tempfile.TemporaryDirectory(dir=self.root) as target:
                    with self.assertRaises(ValueError):
                        runtime.unpack_support(self.archive(entries), Path(target), 2)

    def test_unpack_limit_is_enforced(self):
        archive = self.archive([('tex/file', b'123', tarfile.REGTYPE)])
        with self.assertRaises(ValueError):
            runtime.unpack_support(archive, self.root / 'stage', 2)

    def test_engine_only_extracts_selected_regular_member(self):
        archive, package = self.package()
        runtime.unpack_engine(archive, package, self.root / 'stage')
        self.assertEqual((self.root / 'stage/tex/bin/xelatex').read_bytes(), b'fake-engine')
        self.assertEqual((self.root / 'stage/tex/bin/xelatex').stat().st_mode & 0o777, 0o755)

    def test_engine_hash_mismatch_is_rejected(self):
        archive, package = self.package()
        package['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            runtime.unpack_engine(archive, package, self.root / 'stage')

    def test_engine_symlink_or_duplicate_is_rejected(self):
        _, package = self.package()
        for entries in ([('bin/xetex', b'', tarfile.SYMTYPE)],
                        [('bin/xetex', b'fake-engine', tarfile.REGTYPE)] * 2):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                runtime.unpack_engine(self.archive(entries), package, self.root / 'stage')

    def test_cached_package_is_verified_and_never_downloaded(self):
        archive, package = self.package()
        cache = self.root / (package['archive_sha512'] + '.tar.xz')
        archive.rename(cache)
        with patch.object(runtime.urllib.request, 'build_opener', side_effect=AssertionError('network used')):
            self.assertEqual(runtime.download(package, self.root, offline=True), cache)
            cache.write_bytes(b'bad')
            with self.assertRaises(ValueError):
                runtime.download(package, self.root)

    def test_offline_missing_cache_fails(self):
        _, package = self.package()
        with self.assertRaisesRegex(ValueError, 'Offline'):
            runtime.download(package, self.root, offline=True)

    def test_non_https_urls_and_redirects_are_rejected(self):
        _, package = self.package()
        package['urls'] = ['http://example.invalid/engine']
        with self.assertRaises(ValueError):
            runtime.download(package, self.root)
        with self.assertRaises(ValueError):
            runtime.HTTPSOnlyRedirect().redirect_request(None, None, 302, '', {}, 'http://example.invalid/')

    def test_failed_mirror_falls_back_without_changing_expected_hash(self):
        archive, package = self.package()
        package['urls'].append('https://second.invalid/archive')
        opener = unittest.mock.Mock()
        opener.open.side_effect = [io.BytesIO(b'corrupted'), io.BytesIO(archive.read_bytes())]
        with patch.object(runtime.urllib.request, 'build_opener', return_value=opener):
            cached = runtime.download(package, self.root)
        runtime.check_archive(cached, package['archive_bytes'], package['archive_sha512'], 'sha512')
        self.assertEqual(opener.open.call_count, 2)

    def test_failed_download_does_not_leave_partial_cache(self):
        _, package = self.package()
        opener = unittest.mock.Mock()
        opener.open.return_value = io.BytesIO(b'bad')
        with patch.object(runtime.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(ValueError):
                runtime.download(package, self.root)
        self.assertFalse((self.root / (package['archive_sha512'] + '.tar.xz')).exists())
        self.assertFalse(list(self.root.glob('.download-*')))

    def test_install_lock_is_exclusive_and_released(self):
        prefix = self.root / 'prefix'
        with runtime.install_lock(prefix):
            with self.assertRaises(ValueError):
                with runtime.install_lock(prefix):
                    pass
        with runtime.install_lock(prefix):
            pass


if __name__ == '__main__':
    unittest.main()
