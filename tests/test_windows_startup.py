"""Native startup argument/exit propagation and exclusive listener behavior."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'win32', 'native PowerShell and socket semantics')
class WindowsStartupTests(unittest.TestCase):
    def test_powershell_preserves_arguments_and_failed_setup_exit(self):
        with tempfile.TemporaryDirectory(prefix='startup 中文 & (test)-') as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'scripts/start-local.ps1', root / 'scripts/start-local.ps1')
            (root / 'scripts/bootstrap.py').write_text(
                'import json,sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(42)\n', encoding='utf-8')
            args = ['--port', '8791', '--data-dir', str(root / 'data & (saved)'), '--offline']
            result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(root / 'scripts/start-local.ps1'), *args],
                                    cwd=root, env=os.environ | {'PYTHON': sys.executable}, capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 42, result.stderr)
            self.assertEqual(json.loads(result.stdout.decode('ascii')), args)

    def test_listener_cannot_be_hijacked_by_reuseaddr(self):
        from platform_adapters.windows import configure_listener
        with socket.socket() as first, socket.socket() as second:
            configure_listener(first)
            first.bind(('127.0.0.1', 0))
            first.listen()
            second.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            with self.assertRaises(OSError):
                second.bind(first.getsockname())

    def test_execution_without_verified_scope_is_rejected(self):
        from platform_adapters.windows import run_bounded
        from platform_adapters.contracts import PlatformUnavailable
        with self.assertRaises(PlatformUnavailable):
            run_bounded(['C:/unapproved.exe'], Path('.'), {})

    def test_service_rejects_junction_before_opening_data(self):
        import _winapi
        from backend.service import Service
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / 'outside'
            outside.mkdir()
            alias = root / 'alias'
            _winapi.CreateJunction(str(outside), str(alias))
            try:
                with self.assertRaises(ValueError):
                    Service(alias, compiler=object())
                self.assertEqual(list(outside.iterdir()), [])
            finally:
                alias.rmdir()

    def test_store_rejects_linked_database_before_sqlite_writes(self):
        from backend.store import Store
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            external = root / 'external'
            external.write_bytes(b'not a database')
            data = root / 'data'
            data.mkdir()
            os.link(external, data / 'resumes.sqlite3')
            with self.assertRaises(ValueError):
                Store(data / 'resumes.sqlite3')
            self.assertEqual(external.read_bytes(), b'not a database')


if __name__ == '__main__':
    unittest.main()
