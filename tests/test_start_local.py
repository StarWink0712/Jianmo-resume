import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.check_contracts import ROOT


class StartupScriptTests(unittest.TestCase):
    def test_failed_build_never_runs_installer_or_backend(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'scripts').mkdir()
            shutil.copyfile(ROOT / 'scripts/start-local.sh', root / 'scripts/start-local.sh')
            commands = root / 'commands'
            commands.mkdir()
            for name, body in {
                'uname': 'if [ "$1" = -s ]; then echo Darwin; else echo arm64; fi',
                'kpsewhich': 'exit 0', 'xelatex': 'exit 0', 'brew': 'exit 0', 'python3': 'exit 0',
            }.items():
                target = commands / name
                target.write_text('#!/bin/sh\n' + body + '\n')
                target.chmod(0o755)
            (root / '.venv/bin').mkdir(parents=True)
            python = root / '.venv/bin/python'
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_LOG"\n'
                              'case "$*" in *experiments.m1.build_runtime*) exit 42;; esac\nexit 0\n')
            python.chmod(0o755)
            (root / 'output/runtime').mkdir(parents=True)
            (root / 'output/runtime/install-runtime.sh').write_text('#!/bin/sh\necho INSTALLER >> "$TEST_LOG"\n')
            result = subprocess.run(['/bin/sh', str(root / 'scripts/start-local.sh')],
                                    env=os.environ | {'PATH': str(commands) + ':/usr/bin:/bin',
                                                      'PYTHON': 'python3', 'TEST_LOG': str(root / 'calls')},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 42, result.stderr)
            calls = (root / 'calls').read_text()
            self.assertIn('experiments.m1.build_runtime', calls)
            self.assertNotIn('INSTALLER', calls)
            self.assertNotIn('-m backend', calls)


if __name__ == '__main__':
    unittest.main()
