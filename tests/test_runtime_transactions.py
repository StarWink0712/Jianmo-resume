"""Runtime activation failures must never damage the previous immutable release."""

import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from core.runtime_install import current_release, install_release
from core.runtime_manifest import inventory, safe_relative, unpack_support, verify_inventory


class RuntimeNamesTests(unittest.TestCase):
    def test_reject_platform_ambiguous_archive_names(self):
        for name in ('', '.', '/root', '../root', 'a/../b', 'a//b', 'a\\b', 'C:/x', '//server/x',
                     'a:x', 'a/NUL.txt', 'con', 'LPT9.x', 'COM¹.txt', 'x.', 'x ', 'x\x00', 'a/?'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_relative(name)
        self.assertEqual(str(safe_relative('tex/中文 (font)/font.otf')), 'tex/中文 (font)/font.otf')

    def test_archive_duplicate_case_and_links_are_rejected(self):
        for members in [('tex/file', 'tex/FILE'), ('tex/NUL',), ('tex/a:stream',), ('../escape',), ('link',)]:
            with self.subTest(members=members), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive = root / 'archive.tar.xz'
                with tarfile.open(archive, 'w:xz') as stream:
                    for name in members:
                        entry = tarfile.TarInfo(name)
                        if name == 'link':
                            entry.type, entry.linkname = tarfile.SYMTYPE, '../escape'
                            stream.addfile(entry)
                        else:
                            entry.size = 1
                            stream.addfile(entry, io.BytesIO(b'x'))
                stage = root / 'stage'
                stage.mkdir()
                with self.assertRaises(ValueError):
                    unpack_support(archive, stage, len(members))
                self.assertFalse((root / 'escape').exists())

    def test_inventory_detects_tampering_and_hardlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'engine.exe'
            path.write_bytes(b'one')
            entries = inventory(root)
            path.write_bytes(b'two')
            with self.assertRaises(ValueError):
                verify_inventory(root, entries)
            os.link(path, root / 'alias')
            with self.assertRaises(ValueError):
                inventory(root)


@unittest.skipUnless(sys.platform == 'win32', 'native Windows install leases')
class RuntimeTransactionTests(unittest.TestCase):
    def setUp(self):
        from platform_adapters import windows_native
        self.native = windows_native
        temporary = tempfile.TemporaryDirectory(prefix='runtime 中文 & (transaction)-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.prefix = self.root / 'install'
        self.calls = 0

    def build(self, stage):
        self.calls += 1
        (stage / 'engine.exe').write_bytes(b'fixed test engine')
        (stage / 'runtime.json').write_text(json.dumps({'files': inventory(stage)}), encoding='utf-8')

    def verify(self, root):
        verify_inventory(root, json.loads((root / 'runtime.json').read_text(encoding='utf-8'))['files'])

    def install(self, identity='a', build=None, verify=None):
        return install_release(self.prefix, identity * 64, 'windows-x64', self.native,
                               build or self.build, verify or self.verify)

    def test_reuse_verified_release_without_rebuilding(self):
        first = self.install()
        self.assertEqual(self.install(), first)
        self.assertEqual(self.calls, 1)
        self.assertEqual(current_release(self.prefix, 'windows-x64'), first)

    def test_published_engine_has_a_fresh_file_identity(self):
        identities = []
        def build(stage):
            self.build(stage)
            identities.append((stage / 'engine.exe').stat().st_ino)
        release = self.install(build=build)
        self.assertNotEqual((release / 'engine.exe').stat().st_ino, identities[0])

    def test_build_failure_preserves_previous_release(self):
        old = self.install()
        previous = (self.prefix / 'current.json').read_bytes()
        def broken(stage):
            self.build(stage)
            raise ValueError('format generation failed')
        with self.assertRaises(ValueError):
            self.install('b', broken)
        self.assertEqual((self.prefix / 'current.json').read_bytes(), previous)
        self.verify(old)
        self.assertFalse((self.prefix / 'releases' / ('b' * 64)).exists())

    def test_native_selftest_failure_cannot_activate(self):
        old = self.install()
        def fail(root):
            raise ValueError('PDF check failed')
        with self.assertRaises(ValueError):
            self.install('b', verify=fail)
        self.assertEqual(current_release(self.prefix, 'windows-x64'), old)

    def test_locked_active_record_preserves_old_version_then_retry_succeeds(self):
        old = self.install()
        with self.native.acquire_lock(self.prefix, 'current.json'):
            with self.assertRaises(OSError):
                self.install('b')
        self.assertEqual(current_release(self.prefix, 'windows-x64'), old)
        new = self.install('b')
        self.assertNotEqual(old, new)
        self.assertEqual(current_release(self.prefix, 'windows-x64'), new)
        self.verify(old)

    def test_atomic_switch_failure_keeps_valid_orphan_for_retry(self):
        old = self.install()
        import core.runtime_install as installer
        original = installer.replace
        def fail_activation(source, target):
            if target.name == 'current.json':
                raise PermissionError('simulated antivirus file lock')
            original(source, target)
        with patch.object(installer, 'replace', side_effect=fail_activation), self.assertRaises(PermissionError):
            self.install('b')
        self.assertEqual(current_release(self.prefix, 'windows-x64'), old)
        calls = self.calls
        self.install('b')
        self.assertEqual(self.calls, calls)

    def test_concurrent_install_is_rejected(self):
        from platform_adapters.contracts import LockBusy
        self.native.private_directory(self.prefix)
        with self.native.acquire_lock(self.prefix, '.install.lock'):
            with self.assertRaises(LockBusy):
                self.install()
        self.assertEqual(self.calls, 0)

    def test_corrupt_cached_release_is_not_silently_replaced(self):
        root = self.install()
        (root / 'engine.exe').write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(self.calls, 1)

    def test_unsafe_current_record_is_rejected_without_overwrite(self):
        self.native.private_directory(self.prefix)
        for relative in ('../escape', 'releases/../x', 'releases/NUL', 'releases/a:stream', 'C:/escape'):
            with self.subTest(relative=relative):
                current = self.prefix / 'current.json'
                current.write_text(json.dumps({'schema': 1, 'platform': 'windows-x64', 'release': relative}))
                before = current.read_bytes()
                with self.assertRaises(ValueError):
                    self.install()
                self.assertEqual(current.read_bytes(), before)
        self.assertEqual(self.calls, 0)

    def test_reparse_release_directory_cannot_escape_prefix(self):
        import _winapi
        self.native.private_directory(self.prefix)
        outside = self.root / 'outside'
        outside.mkdir()
        link = self.prefix / 'releases'
        _winapi.CreateJunction(str(outside), str(link))
        try:
            with self.assertRaises(ValueError):
                self.install()
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            link.rmdir()


if __name__ == '__main__':
    unittest.main()
