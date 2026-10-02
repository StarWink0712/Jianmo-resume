"""Run repeatable M1 experiments on the current Mac, without changing global tools."""

import argparse
import fcntl
import json
import math
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import time
import unicodedata

from markdown_it import MarkdownIt

from experiments.m1.boundaries import boundary_server
from experiments.m1.fonts import uses_bundled_fonts
from experiments.m1.style import content_only
from experiments.m1.pdf_checks import ensure_unicode_maps, inspect_pdf
from experiments.m1.render import RenderError, contact_link_text, render_resume
from experiments.m1.runtime import compile_tex, prepare_runtime, profile, resource_manifest, run_bounded
from scripts.check_contracts import ROOT, build_case, cases, json_bytes


WORK = ROOT / 'tmp' / 'pdfs' / 'm1'
REPORT = ROOT / 'docs' / 'm1'
OUTPUT = ROOT / 'output' / 'pdf'
PAGE_TARGETS = {'standard-one-page-target': 1, 'two-page-target': 2}


def case_passes(case, result):
    expected_rejection = not case['valid'] or bool(case.get('render_expectation'))
    if expected_rejection:
        return result.get('rejected', False)
    return bool(result.get('ok')) and (case['id'] not in PAGE_TARGETS or result.get('pages') == PAGE_TARGETS[case['id']])


def benchmark_passes(benchmark):
    if benchmark['iterations'] < 30:
        return None
    return benchmark['pages'] == 2 and benchmark['p95_seconds'] <= benchmark['p95_target_seconds']


def compact(text):
    return ''.join(unicodedata.normalize('NFC', text).split())


def expected_text(resume):
    expected = [resume['basics'][key] for key in ('name', 'headline', 'email', 'phone', 'location') if resume['basics'][key]]
    if resume['basics'].get('gender'):
        expected.append(resume['basics']['gender'])
    if resume['basics'].get('age') is not None:
        expected.append(f"{int(resume['basics']['age'])}岁")
    expected += [contact_link_text(item) for item in resume['basics']['links']]
    parser = MarkdownIt('commonmark')
    names = {'education': ['school', 'degree', 'field_of_study', 'location'],
             'employment': ['organization', 'role', 'location'], 'project': ['name', 'role'],
             'skills': ['label'], 'custom': ['heading', 'role'],
             'academic': ['heading', 'role'], 'competition': ['heading', 'role']}
    for section in resume['sections']:
        visible = [entry for entry in section['entries'] if entry['visible']]
        if not section['visible'] or not visible:
            continue
        expected.append(section['title'])
        for entry in visible:
            if not content_only(section):
                expected.extend(entry[key] for key in names[section['type']] if entry.get(key))
                expected.extend(value for value in (entry.get('start_date'), '至今' if entry.get('ongoing') else entry.get('end_date')) if value)
            for token in parser.parse(entry['body']):
                if token.type == 'inline':
                    expected.extend(child.content for child in token.children or [] if child.type == 'text' and child.content.strip())
    return expected


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


def probe_isolation(runtime, blank_source):
    result = {}
    secret = WORK / 'probe-secret.txt'
    secret.write_text('M1_SYNTHETIC_SECRET\n', encoding='ascii')
    code = '\\newread\\probe\n\\openin\\probe="' + str(secret) + '"\n' + r'\ifeof\probe\typeout{M1_READ_DENIED}\else\read\probe to\line\typeout{M1_READ_ALLOWED}\fi\closein\probe'
    source = blank_source.replace(r'\end{document}', code + '\n' + r'\end{document}')
    try:
        for label, extra in [('denied', ()), ('allowed-control', (secret,))]:
            job = WORK / ('probe-read-' + label)
            compilation = compile_tex(source, job, runtime, extra_read=extra, openin='a')
            log = (job / 'process.log').read_text(errors='replace')
            expected = 'M1_READ_DENIED' if label == 'denied' else 'M1_READ_ALLOWED'
            result['file-read-' + label] = compilation['ok'] and expected in log
    finally:
        secret.unlink(missing_ok=True)

    outside = WORK / 'probe-outside.txt'
    outside.unlink(missing_ok=True)
    code = r'\newwrite\probe\immediate\openout\probe="' + str(outside) + r'"\immediate\write\probe{TEST}\immediate\closeout\probe'
    job = WORK / 'probe-write'
    compilation = compile_tex(blank_source.replace(r'\end{document}', code + '\n' + r'\end{document}'), job, runtime)
    result['file-write-outside-denied'] = not compilation['ok'] and not outside.exists()
    result['file-write-inside-allowed'] = (job / 'main.log').exists()

    shell_job = WORK / 'probe-shell'
    code = r'\immediate\write18{touch shell-escape-marker}'
    compilation = compile_tex(blank_source.replace(r'\end{document}', code + '\n' + r'\end{document}'), shell_job, runtime)
    result['shell-escape-disabled'] = compilation['ok'] and not (shell_job / 'shell-escape-marker').exists()

    with boundary_server() as (origin, token):
        for allowed in (True, False):
            job = WORK / ('probe-network-' + str(allowed))
            job.mkdir(exist_ok=True)
            sandbox = job / 'network.sb'
            sandbox.write_text(profile(job.resolve(), runtime['tex_root'], extra_read=('/private/etc/ssl/openssl.cnf',), network=allowed))
            command = ['/usr/bin/sandbox-exec', '-f', str(sandbox), '/usr/bin/curl', '--noproxy', '*',
                       '--max-time', '2', '-fsS', '-H', 'X-Resume-Token: ' + token, origin]
            attempt = run_bounded(command, job, {'PATH': '/usr/bin:/bin', 'HOME': str(job), 'OPENSSL_CONF': '/dev/null'}, timeout=4)
            log = (job / 'process.log').read_text(errors='replace')
            result['network-' + ('allowed-control' if allowed else 'denied')] = (
                attempt['returncode'] == 0 and '"probe":true' in log if allowed
                else attempt['returncode'] != 0 and ('Operation not permitted' in log or 'Failed to connect' in log))
    return result


def probe_timeout(runtime, blank_source):
    job = WORK / 'probe-timeout'
    endless = blank_source.replace(r'\end{document}', r'\newcount\forever\loop\advance\forever by1\iftrue\repeat')
    attempt = compile_tex(endless, job, runtime, timeout=0.25)
    recovery = compile_tex(blank_source, WORK / 'probe-recovery', runtime)
    # A separate process-group test verifies descendants rather than only the direct engine.
    group = WORK / 'probe-process-group'
    group.mkdir(exist_ok=True)
    command = ['/bin/sh', '-c', 'sleep 20 & echo $! > child.pid; wait']
    killed = run_bounded(command, group, {'PATH': '/usr/bin:/bin'}, timeout=0.1)
    pid = int((group / 'child.pid').read_text())
    status = subprocess.run(['/bin/ps', '-o', 'stat=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
    return {'engine_timeout': attempt['timed_out'], 'next_compile_succeeds': recovery['ok'],
            'process_group_timeout': killed['timed_out'], 'child_not_running': not status or status.startswith('Z')}


def run_experiments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100:
        parser.error('iterations must be between 1 and 100')
    for path in (WORK, REPORT, OUTPUT):
        path.mkdir(parents=True, exist_ok=True)
    for name in ('m1-standard.pdf', 'm1-long.pdf'):
        (OUTPUT / name).unlink(missing_ok=True)
    runtime = prepare_runtime()
    report = {'stage': 'M1 in progress; not release acceptance', 'platform': platform.platform(),
              'python': platform.python_version(), 'engine': runtime['engine_version'],
              'cpu': subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip(),
              'memory_bytes': int(subprocess.check_output(['sysctl', '-n', 'hw.memsize'], text=True)),
              'runtime_mode': runtime['mode'], 'font_bytes': runtime['font_bytes'], 'cases': {}}
    for case in cases():
        resume, assets = build_case(case)
        expected_rejection = not case['valid'] or bool(case.get('render_expectation'))
        try:
            source, avatar = render_resume(resume, assets)
        except RenderError as error:
            report['cases'][case['id']] = {'rejected': True, 'expected': expected_rejection, 'reason': str(error)}
            continue
        if expected_rejection:
            report['cases'][case['id']] = {'rejected': False, 'ok': False, 'reason': 'expected rejection but renderer accepted input'}
            continue
        job = WORK / case['id']
        result = compile_and_check(source, avatar, resume, job, runtime)
        report['cases'][case['id']] = result
        print(case['id'], 'PASS' if case_passes(case, result) else 'FAIL', result.get('pages'), flush=True)
        if case_passes(case, result) and case['id'] in PAGE_TARGETS:
            name = 'm1-standard.pdf' if case['id'] == 'standard-one-page-target' else 'm1-long.pdf'
            shutil.copyfile(job / 'main.pdf', OUTPUT / name)
    long_case = next(case for case in cases() if case['id'] == 'two-page-target')
    resume, assets = build_case(long_case)
    source, avatar = render_resume(resume, assets)
    samples = []
    for index in range(args.iterations):
        result = compile_and_check(source, avatar, resume, WORK / 'benchmark', runtime)
        if not result['ok']:
            raise RuntimeError('benchmark compilation or semantic check failed')
        samples.append(result['pipeline_seconds'])
        if (index + 1) % 10 == 0:
            print('timing samples', index + 1, flush=True)
    ordered = sorted(samples)
    report['benchmark'] = {'method': 'one XeLaTeX pass + ToUnicode normalization + PDF semantic checks; warm OS caches, fresh process per run; no download or renderer time',
                           'samples_seconds': samples, 'iterations': len(samples), 'p50_seconds': statistics.median(samples),
                           'p95_seconds': ordered[math.ceil(len(samples) * .95) - 1], 'max_seconds': max(samples),
                           'p95_target_seconds': 3, 'pages': result['pages'], 'true_cold_boot': 'not measured'}
    report['benchmark']['target_passed'] = benchmark_passes(report['benchmark'])
    blank, blank_assets = build_case(next(case for case in cases() if case['id'] == 'blank'))
    blank_source, _ = render_resume(blank, blank_assets)
    report['isolation_probes'] = probe_isolation(runtime, blank_source)
    report['timeout_probes'] = probe_timeout(runtime, blank_source)
    resources = resource_manifest(WORK / 'standard-one-page-target', Path(runtime['tex_root']))
    report['recorded_tex_input_count'] = len(resources)
    report['recorded_tex_input_bytes'] = sum(item['bytes'] for item in resources)
    report['scope_limits'] = ['Not a clean Mac install', 'System TeX Live macros and engine still required',
                              'No hard memory limit verified on macOS', 'No actual download/installer bundle validated',
                              'No Safari/Chrome acceptance', 'Tectonic not compared; final engine not selected']
    (REPORT / 'runtime-inputs.json').write_bytes(json_bytes({'fonts': runtime['fonts'], 'cmap': runtime['cmap'], 'tex_inputs': resources,
                                                           'warning': 'recorder inputs are NOT a complete redistributable runtime closure'}))
    failures = [case['id'] for case in cases() if not case_passes(case, report['cases'][case['id']])]
    failures += [name for name, passed in report['isolation_probes'].items() if not passed]
    failures += [name for name, passed in report['timeout_probes'].items() if not passed]
    if report['benchmark']['target_passed'] is False:
        failures.append('benchmark-target')
    report['failures'] = failures
    (REPORT / 'results.json').write_bytes(json_bytes(report))
    print(json.dumps({'benchmark': report['benchmark'], 'isolation': report['isolation_probes'], 'timeout': report['timeout_probes'], 'failures': failures}, ensure_ascii=False), flush=True)
    return bool(failures)


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    with (WORK / '.experiment.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another M1 experiment is running; wait before reusing its output directory.')
        return run_experiments()


if __name__ == '__main__':
    raise SystemExit(main())
