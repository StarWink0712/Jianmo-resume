"""Frozen M1 self-test executable, not the production editor backend."""

import argparse
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import traceback

from experiments.m1.managed import compiler_manifest, verify
from experiments.m1.fonts import uses_bundled_fonts, verify_fonts
from experiments.m1.pdf_checks import ensure_unicode_maps, inspect_pdf
from experiments.m1.render import RenderError, render_resume
from experiments.m1.run import case_passes, compact, expected_text
from experiments.m1.runtime import compile_tex
from scripts.check_contracts import build_case, cases


def check_cases(root, output, outer_sandbox=False):
    runtime = compiler_manifest(root)
    results = {}
    for case in cases():
        resume, assets = build_case(case)
        try:
            source, avatar = render_resume(resume, assets)
        except RenderError:
            results[case['id']] = {'rejected': True}
            continue
        if not case['valid'] or case.get('render_expectation'):
            results[case['id']] = {'ok': False, 'reason': 'unexpected acceptance'}
            continue
        job = output / case['id']
        result = compile_tex(source, job, runtime, avatar, fixture_outer_sandbox=outer_sandbox)
        if result['ok']:
            ensure_unicode_maps(job / 'main.pdf', root / 'tex/cmaps/Adobe-GB1-UCS2')
            checked = inspect_pdf(job / 'main.pdf')
            extracted = compact(checked.pop('text'))
            missing = sum(compact(fragment) not in extracted for fragment in expected_text(resume))
            result.update(checked)
            result['missing_text_fragments'] = missing
            result['ok'] = missing == 0 and result['overfull_boxes'] == 0 and uses_bundled_fonts(checked['fonts'])
        results[case['id']] = result
    failures = [case['id'] for case in cases() if not case_passes(case, results[case['id']])]
    return {'cases': results, 'failures': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('verify', 'self-test'))
    parser.add_argument('--runtime', type=Path, help='development-only runtime location')
    parser.add_argument('--output', type=Path, help='new directory for fictional self-test results')
    parser.add_argument('--outer-sandbox', action='store_true', help='fixed-fixture harness only; requires external sandbox and supervisor')
    args = parser.parse_args()
    root = (args.runtime or Path(sys.executable).parent).resolve()
    manifest = verify(root)
    verify_fonts(root / 'tex/fonts')
    if args.command == 'verify':
        print(json.dumps({'verified': True, 'version': manifest['version'], 'files': len(manifest['files'])}))
        return 0
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='resume-m1-selftest-'))
    if args.output:
        output.mkdir(parents=True, exist_ok=False)
    result = check_cases(root, output, args.outer_sandbox)
    result.update({'platform': platform.platform(), 'python': platform.python_version(),
                   'frozen': bool(getattr(sys, 'frozen', False)),
                   'sandbox_mode': 'external fixture harness required' if args.outer_sandbox else 'per-compiler sandbox',
                   'clean_mac': 'not tested; explicitly skipped by user'})
    (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'report': str(output / 'results.json'), 'failures': result['failures']}))
    return int(bool(result['failures']))


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError) as error:
        if os.environ.get('M1_DEBUG') == '1':
            traceback.print_exc()
        print('Runtime check failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
