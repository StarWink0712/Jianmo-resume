"""Native macOS contract tests; Windows requires its own native acceptance."""

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from platform_adapters.contracts import LockBusy


@unittest.skipUnless(sys.platform == 'darwin', 'macOS native implementation')
class MacOSPlatformTests(unittest.TestCase):
    def setUp(self):
        from platform_adapters import macos
        self.adapter = macos
        self.temporary = tempfile.TemporaryDirectory(prefix='platform space & (test)-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def run_child(self, command, **kwargs):
        return self.adapter.run_bounded(command, self.root, {'PATH': '/usr/bin:/bin'}, **kwargs)

    def test_lock_uses_normalized_directory_identity(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        lease = self.adapter.acquire_lock(self.root, '.lock')
        try:
            with self.assertRaises(LockBusy):
                self.adapter.acquire_lock(alias, '.lock')
        finally:
            lease.close()
        self.adapter.acquire_lock(alias, '.lock').close()

    def test_lock_release_after_process_exit(self):
        code = ('import sys; from platform_adapters.macos import acquire_lock; '
                'lease=acquire_lock(sys.argv[1], ".lock"); print("locked", flush=True); '
                'import time; time.sleep(30)')
        process = subprocess.Popen([sys.executable, '-c', code, str(self.root)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'locked')
            with self.assertRaises(LockBusy):
                self.adapter.acquire_lock(self.root, '.lock')
        finally:
            process.kill()
            process.wait(timeout=5)
            process.stdout.close()
        self.adapter.acquire_lock(self.root, '.lock').close()

    def test_lock_symlinks_are_rejected(self):
        (self.root / 'outside').write_text('untouched')
        (self.root / '.lock').symlink_to('outside')
        with self.assertRaises(OSError):
            self.adapter.acquire_lock(self.root, '.lock')
        self.assertEqual((self.root / 'outside').read_text(), 'untouched')

    def test_private_directory_and_file_permissions(self):
        job = self.root / 'private'
        self.adapter.private_directory(job)
        file = job / 'data'
        file.write_text('test')
        self.adapter.private_file(file)
        self.assertEqual(job.stat().st_mode & 0o777, 0o700)
        self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_listener_cannot_take_over_claimed_port(self):
        with socket.socket() as first, socket.socket() as second:
            self.adapter.configure_listener(first)
            self.adapter.configure_listener(second)
            first.bind(('127.0.0.1', 0))
            first.listen(1)
            with self.assertRaises(OSError):
                second.bind(first.getsockname())

    def test_environment_does_not_inherit_arbitrary_path_or_tex_settings(self):
        with patch.dict(os.environ, {'PATH': '/unapproved', 'TEXINPUTS': '/secrets', 'DYLD_LIBRARY_PATH': '/unapproved'}):
            env = self.adapter.process_environment(self.root, self.root / 'runtime/bin/xelatex')
        self.assertNotIn('/unapproved', env['PATH'])
        self.assertNotIn('TEXINPUTS', env)
        self.assertNotIn('DYLD_LIBRARY_PATH', env)

    def test_threaded_execution_never_uses_preexec_fn(self):
        original = subprocess.Popen
        with patch.object(self.adapter.subprocess, 'Popen', wraps=original) as popen:
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(self.run_child, ['/usr/bin/true']).result(timeout=10)
        self.assertEqual(result['reason'], 'success')
        self.assertTrue(all('preexec_fn' not in call.kwargs for call in popen.call_args_list))

    def test_expired_budget_never_launches_process(self):
        with patch.object(self.adapter.subprocess, 'Popen') as popen:
            result = self.run_child(['/usr/bin/true'], timeout=0)
        popen.assert_not_called()
        self.assertEqual(result['reason'], 'wall_timeout')
        self.assertEqual(result['process_tree_cleanup'], 'not_started')

    def test_native_file_isolation_has_positive_and_negative_controls(self):
        secret = self.root / 'synthetic-secret'
        secret.write_text('FICTIONAL_TEST_SECRET')
        job, tex, fonts = (self.root / name for name in ('job', 'tex', 'fonts'))
        for path in (job, tex, fonts):
            path.mkdir()
        for allowed in (False, True):
            prefix = self.adapter.sandbox_prefix(job, tex, (secret,) if allowed else (), fonts_root=fonts)
            read = self.adapter.run_bounded(prefix + ['/bin/sh', '-c', 'IFS= read -r value < "$1"; printf "%s" "$value"', 'probe', str(secret)],
                                            job, {'PATH': '/usr/bin:/bin'}, memory_limit_bytes=None)
            self.assertEqual('FICTIONAL_TEST_SECRET' in (job / 'process.log').read_text(), allowed)
            self.assertFalse(read['timed_out'])
        prefix = self.adapter.sandbox_prefix(job, tex, fonts_root=fonts)
        for target, allowed in ((job / 'inside', True), (self.root / 'outside', False)):
            write = self.adapter.run_bounded(prefix + ['/bin/sh', '-c', 'printf TEST > "$1"', 'probe', str(target)],
                                             job, {'PATH': '/usr/bin:/bin'}, memory_limit_bytes=None)
            self.assertEqual(write['returncode'] == 0, allowed)
            self.assertEqual(target.exists(), allowed)

    def test_launch_failure_is_not_timeout(self):
        with patch.object(self.adapter.subprocess, 'Popen', side_effect=OSError('launch failure')):
            result = self.run_child(['/usr/bin/true'])
        self.assertEqual(result['reason'], 'start_failed')
        self.assertFalse(result['timed_out'])

    def test_exit_failure_is_not_timeout(self):
        result = self.run_child(['/usr/bin/false'])
        self.assertEqual(result['reason'], 'exit_error')
        self.assertFalse(result['timed_out'])

    def test_exception_kills_descendants_and_releases_log(self):
        original = self.adapter.group_rss_bytes
        def fail_after_child(pgid):
            if (self.root / 'child.pid').exists():
                raise RuntimeError('injected supervisor failure')
            return original(pgid)
        with patch.object(self.adapter, 'group_rss_bytes', side_effect=fail_after_child):
            with self.assertRaisesRegex(RuntimeError, 'injected'):
                self.run_child(['/bin/sh', '-c', 'sleep 20 & echo $! > child.pid; wait'])
        pid = (self.root / 'child.pid').read_text().strip()
        deadline = time.monotonic() + 3
        while True:
            state = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', pid], capture_output=True, text=True).stdout.strip()
            if not state or state.startswith('Z') or time.monotonic() >= deadline:
                break
            time.sleep(.02)
        self.assertTrue(not state or state.startswith('Z'), state)
        (self.root / 'process.log').unlink()


if __name__ == '__main__':
    unittest.main()
