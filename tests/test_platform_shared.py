"""Shared import/detection/executor contracts. No host-specific tests are skipped."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from core.tex_pipeline import compile_tex
from platform_adapters import windows
from platform_adapters.contracts import Capabilities, PlatformUnavailable
from platform_adapters.detect import get_adapter, platform_key
from scripts.check_contracts import ROOT


class SharedPlatformTests(unittest.TestCase):
    def test_production_import_graph_has_no_unix_or_experiment_dependency(self):
        result = subprocess.run([sys.executable, 'scripts/check_platform_imports.py'], cwd=ROOT,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_supported_platform_keys(self):
        self.assertEqual(platform_key('Darwin', 'arm64', 64), 'darwin-arm64')
        for arch in ('AMD64', 'x86_64'):
            self.assertEqual(platform_key('Windows', arch, 64), 'windows-x64')

    def test_unsupported_hosts_and_32bit_python_are_rejected(self):
        for system, machine, bits in [('Darwin', 'x86_64', 64), ('Windows', 'ARM64', 64),
                                      ('Windows', 'AMD64', 32), ('Linux', 'aarch64', 64)]:
            with self.subTest(host=(system, machine, bits)), self.assertRaises(PlatformUnavailable):
                platform_key(system, machine, bits)

    def test_windows_selection_is_lazy_and_does_not_choose_macos(self):
        with patch('platform_adapters.detect.platform_key', return_value='windows-x64'):
            self.assertIs(get_adapter(), windows)

    def test_missing_capabilities_fail_before_writing_a_job(self):
        disabled = Mock(KEY='windows-x64', CAPABILITIES=Capabilities(False, False, 'none', 'none', 'none', 'none'))
        with tempfile.TemporaryDirectory() as temporary:
            job = Path(temporary) / 'not-created'
            with self.assertRaises(PlatformUnavailable):
                compile_tex('ignored', job, {}, adapter=disabled)
            self.assertFalse(job.exists())

    def test_windows_data_and_install_do_not_fall_back_to_chmod_or_system_tex(self):
        from scripts.light_runtime import install
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'not-created'
            with patch('scripts.light_runtime.get_adapter', return_value=windows):
                with self.assertRaises(PlatformUnavailable):
                    install(target, target / 'cache')
            with self.assertRaises(PlatformUnavailable):
                windows.sandbox_prefix(target, target)
            self.assertFalse(target.exists())

    def test_runtime_platform_mismatch_fails_before_writing(self):
        adapter = Mock(KEY='darwin-arm64')
        adapter.CAPABILITIES = Capabilities(True, True, 'group', 'sampled', 'rlimit', 'rlimit')
        with self.assertRaisesRegex(ValueError, 'platform'):
            compile_tex('', Path('unused'), {'platform': 'windows-x64'}, adapter=adapter)
        adapter.private_directory.assert_not_called()

    def test_stages_share_remaining_wall_budget_and_use_explicit_driver(self):
        adapter = Mock(KEY='darwin-arm64')
        adapter.CAPABILITIES = Capabilities(True, True, 'group', 'sampled', 'rlimit', 'rlimit')
        adapter.prepare_fonts.return_value = None
        adapter.process_environment.return_value = {}
        adapter.sandbox_prefix.return_value = ['sandbox']
        with tempfile.TemporaryDirectory() as temporary:
            job = Path(temporary).resolve()
            clock = iter([10.0, 10.75])

            def execute(command, cwd, env, timeout, **kwargs):
                first = command[1] == 'engine'
                (job / ('main.xdv' if first else 'main.pdf')).write_bytes(b'output')
                return {'returncode': 0, 'seconds': .5 if first else .2, 'peak_group_rss_bytes': 100,
                        'timed_out': False, 'memory_exceeded': False}

            adapter.run_bounded.side_effect = execute
            manifest = {'engine': 'engine', 'driver': 'approved-driver', 'tex_root': temporary}
            with patch('core.tex_pipeline.verify_fonts'), patch('core.tex_pipeline.time.monotonic', side_effect=lambda: next(clock)):
                result = compile_tex('', job, manifest, timeout=1, adapter=adapter)
            self.assertTrue(result['ok'])
            calls = adapter.run_bounded.call_args_list
            self.assertEqual(calls[1].args[0][1], 'approved-driver')
            self.assertEqual(calls[1].args[3], .25)
            self.assertNotIn('limit_wrapper', calls[0].kwargs)


if __name__ == '__main__':
    unittest.main()
