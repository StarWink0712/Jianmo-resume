"""Repeatable local checks before pushing source code; never accesses user resumes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
PDF_CHECKS = (
    'check_backend.py', 'check_english_resume.py', 'check_achievement_modules.py',
    'check_style.py', 'check_entry_headings.py', 'check_fixed_spacing.py',
    'check_date_alignment.py', 'check_markdown_toolbar.py', 'check_avatar_crop.py',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='Also run real HTTP/TeX/PDF checks with the installed runtime.')
    args = parser.parse_args()
    output = ROOT / 'tmp/pre-push'
    output.mkdir(parents=True, exist_ok=True)
    for name in ('tmp/m2', 'tmp/pdfs'):
        (ROOT / name).mkdir(parents=True, exist_ok=True)
    report = {'scope': 'source-code pre-push checks, not installer or browser acceptance',
              'full': args.full, 'checks': [], 'passed': False}

    def run(name, command):
        print(f'Checking {name}...', flush=True)
        started = time.monotonic()
        try:
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            code, log = result.returncode, result.stdout + result.stderr
        except OSError as error:
            code, log = 1, str(error)
        (output / (name + '.log')).write_text(log)
        report['checks'].append({'name': name, 'passed': code == 0, 'exit_code': code,
                                 'seconds': round(time.monotonic() - started, 2)})
        print(f'{"PASS" if code == 0 else "FAIL"}: {name}', flush=True)
        if code:
            print(log[-4000:], flush=True)

    run('dependencies', [sys.executable, '-m', 'pip', 'check'])
    run('contracts', [sys.executable, 'scripts/check_contracts.py'])
    run('python-tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-q'])
    node_tests = sorted(str(path.relative_to(ROOT)) for path in (ROOT / 'tests').iterdir()
                        if path.name.endswith(('.test.mjs', '.test.cjs')))
    run('node-tests', ['node', '--test', *node_tests])
    for path in sorted((ROOT / 'web').iterdir()):
        if path.suffix in ('.js', '.mjs'):
            run('syntax-' + path.name, ['node', '--check', str(path)])
    if args.full:
        for script in PDF_CHECKS:
            module = 'scripts.' + script.removesuffix('.py')
            run(script.removesuffix('.py'), [sys.executable, '-m', module])
    run('diff-whitespace', ['git', 'diff', '--check', 'HEAD'])
    report['passed'] = all(check['passed'] for check in report['checks'])
    (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Results: tmp/pre-push/results.json', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
