"""Semantic PDF and fixture checks, with no experiment-runner import."""

import time

from core.resume_checks import case_passes, compact, expected_text
from core.tex_pipeline import compile_tex
from experiments.m1.managed import compiler_manifest
from experiments.m1.fonts import uses_bundled_fonts
from experiments.m1.pdf_checks import ensure_unicode_maps, inspect_pdf
from experiments.m1.render import RenderError, render_resume
from scripts.check_contracts import build_case, cases


def compile_and_check(source, avatar, resume, job, runtime):
    started = time.perf_counter()
    result = compile_tex(source, job, runtime, avatar)
    if result['ok']:
        result['unicode_maps_added'] = ensure_unicode_maps(job / 'main.pdf')
        check = inspect_pdf(job / 'main.pdf')
        text = compact(check.pop('text'))
        missing = [value for value in expected_text(resume) if compact(value) not in text]
        result.update(check)
        result['missing_text_fragments'] = len(missing)
        result['ok'] = not missing and uses_bundled_fonts(result['fonts'])
        result['ok'] = result['ok'] and result['overfull_boxes'] == 0
    result['pipeline_seconds'] = round(time.perf_counter() - started, 6)
    return result


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
