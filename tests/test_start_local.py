import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.check_contracts import ROOT


class StartupScriptTests(unittest.TestCase):
    def run_script(self, fail_setup):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'scripts/start-local.sh', root / 'scripts/start-local.sh')
            commands = root / 'commands'
            commands.mkdir()
            for name, body in {
                'uname': 'if [ "$1" = -s ]; then echo Darwin; else echo arm64; fi',
                'kpsewhich': 'exit 99', 'xelatex': 'exit 99', 'brew': 'exit 99', 'python3': 'exit 0',
            }.items():
                target = commands / name
                target.write_text('#!/bin/sh\n' + body + '\n')
                target.chmod(0o755)
            (root / '.venv/bin').mkdir(parents=True)
            python = root / '.venv/bin/python'
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_LOG"\n'
                              + ('case "$*" in *scripts.light_runtime*) exit 42;; esac\n' if fail_setup else '')
                              + 'exit 0\n')
            python.chmod(0o755)
            (root / 'output/runtime').mkdir(parents=True)
            (root / 'output/runtime/install-runtime.sh').write_text('#!/bin/sh\necho INSTALLER >> "$TEST_LOG"\n')
            result = subprocess.run(['/bin/sh', str(root / 'scripts/start-local.sh'), '--port', '8791'],
                                    env=os.environ | {'PATH': str(commands) + ':/usr/bin:/bin',
                                                      'PYTHON': 'python3', 'TEST_LOG': str(root / 'calls')},
                                    capture_output=True, text=True)
            calls = (root / 'calls').read_text()
            self.assertIn('scripts.light_runtime', calls)
            self.assertNotIn('experiments.m1.build_runtime', calls)
            self.assertNotIn('requirements-build', calls)
            self.assertNotIn('INSTALLER', calls)
            return result, calls

    def test_failed_setup_never_starts_backend(self):
        result, calls = self.run_script(True)
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertNotIn('-m backend', calls)

    def test_success_starts_backend_without_tex_or_homebrew(self):
        result, calls = self.run_script(False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('-m backend --port 8791', calls)


if __name__ == '__main__':
    unittest.main()
