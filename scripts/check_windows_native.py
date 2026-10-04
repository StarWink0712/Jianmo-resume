"""Repeatable Windows development gate; never reports application/release readiness."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import locale
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', action='store_true', help='Also compile pinned native TeX fixtures inside AppContainer.')
    parser.add_argument('--offline', action='store_true', help='Do not download missing engine archives.')
    parser.add_argument('--network', action='store_true', help='Check live DNS, public TCP and local LAN isolation with host controls.')
    args = parser.parse_args()
    if sys.platform != 'win32' or struct.calcsize('P') != 8 or platform.machine().lower() not in ('amd64', 'x86_64'):
        parser.error('Real Windows x64 with 64-bit Python is required.')
    parent = ROOT / '.m1-build'
    parent.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='windows-check-', dir=parent))
    report = {'schema': 1, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'platform': platform.platform(), 'python': platform.python_version(),
              'default_encoding': locale.getencoding(), 'application_ready': False,
              'scope': 'shared and native prototype acceptance; not a release gate',
              'engine_requested': args.engine, 'checks': [],
              'source_sha256': {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                  for folder in ('platform_adapters', 'core', 'scripts', 'tests')
                  for path in sorted((ROOT / folder).glob('*.py'))}}
    from platform_adapters import windows_native as native
    import ctypes as C
    from ctypes import wintypes as W
    token, size, elevated = W.HANDLE(), W.DWORD(), W.DWORD()
    native.checked(native.OpenProcessToken(native.GetCurrentProcess(), 8, C.byref(token)))
    try:
        native.checked(native.GetTokenInformation(token, 20, C.byref(elevated), C.sizeof(elevated), C.byref(size)))
        report['token_elevated'] = bool(elevated.value)
    finally:
        native.CloseHandle(token)

    def command(name, argv):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=90)
        (output / (name + '.log')).write_bytes(result.stdout + result.stderr)
        report['checks'].append({'name': name, 'passed': result.returncode == 0, 'exit_code': result.returncode})
        print(('PASS ' if result.returncode == 0 else 'FAIL ') + name, flush=True)

    try:
        command('dependencies', [sys.executable, '-m', 'pip', 'check'])
        command('imports', [sys.executable, str(ROOT / 'scripts/check_platform_imports.py')])
        command('data-contracts', [sys.executable, str(ROOT / 'scripts/check_contracts.py')])
        loader = unittest.TestLoader()
        for name in ('test_platform_shared', 'test_contracts', 'test_m1', 'test_markdown_linebreaks', 'test_windows_native',
                     'test_runtime_transactions', 'test_windows_startup', 'test_backend', 'test_reference_resumes'):
            stream = io.StringIO()
            suite = loader.discover(str(ROOT / 'tests'), pattern=name + '.py')
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
            (output / (name + '.log')).write_text(stream.getvalue(), encoding='utf-8')
            passed = result.wasSuccessful() and result.testsRun > 0 and not result.skipped
            report['checks'].append({'name': name, 'passed': passed, 'tests': result.testsRun,
                                     'skipped': len(result.skipped), 'failures': len(result.failures), 'errors': len(result.errors)})
            print(('PASS ' if passed else 'FAIL ') + name + f' ({result.testsRun} tests)', flush=True)
        node = shutil.which('node')
        if node:
            files = sorted(str(path) for suffix in ('*.test.mjs', '*.test.cjs') for path in (ROOT / 'tests').glob(suffix))
            command('node-models', [node, '--test', *files])
        else:
            report['node_models'] = 'NOT_RUN: Node not installed'
        if args.network:
            command('network-isolation', [sys.executable, str(ROOT / 'scripts/check_windows_network.py'),
                                         '--output', str(output / 'network.json')])
        if args.engine:
            from scripts.probe_windows_engine import run
            engine_output = output / 'engine'
            engine_output.mkdir()
            engine = run(engine_output, ROOT / '.m1-build/engine-cache', args.offline)
            report['checks'].append({'name': 'native-engine', 'passed': engine['prototype_passed']})
        report['passed'] = all(check['passed'] for check in report['checks'])
    except Exception as error:
        report['passed'] = False
        report['error'] = str(error)
        print('FAIL ' + str(error), flush=True)
    finally:
        (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Report: ' + str(output / 'summary.json'), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
