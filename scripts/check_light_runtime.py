"""Validate the trimmed installer, offline compiler and fresh-source startup."""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

import httpx

from backend.compiler import Compiler
from experiments.m1 import run as experiment
from experiments.m1.managed import compiler_manifest, inventory
from experiments.m1.packaged_cli import check_cases
from experiments.m1.render import render_resume
from scripts.check_contracts import ROOT, build_case, cases, json_bytes
from scripts.light_runtime import install


def check_startup(parent):
    source = parent / 'fresh source 新项目'
    source.mkdir()
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).split(b'\0')
    for raw in names:
        if not raw:
            continue
        name = raw.decode()
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    assert not (source / '.venv').exists() and not (source / '.m1-build').exists()
    origin = 'http://127.0.0.1:8791'
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 8791))
    environment = os.environ | {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin',
                               'PYTHON': sys.executable, 'TEXFORMATS': '/nonexistent-host-cache'}
    data = parent / 'private-test-data'
    log_path = ROOT / 'tmp/light-runtime-startup.log'
    with log_path.open('wb') as log:
        process = subprocess.Popen(['/bin/sh', 'scripts/start-local.sh', '--port', '8791',
                                    '--data-dir', str(data)], cwd=source, env=environment,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            with httpx.Client(base_url=origin, timeout=10, trust_env=False) as client:
                deadline = time.monotonic() + 600
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise AssertionError('Fresh startup failed; see tmp/light-runtime-startup.log')
                    try:
                        if client.get('/api/health').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(.25)
                else:
                    raise AssertionError('Fresh startup did not become ready within 10 minutes.')
                token = client.get('/api/session', headers={'X-Resume-Bootstrap': '1'}).json()['token']
                client.headers.update({'Origin': origin, 'X-Resume-Token': token})
                summaries = client.get('/api/resumes').json()
                assert len(summaries) == 3
                pages = []
                for item in summaries:
                    document = client.get('/api/resumes/' + item['id']).json()['resume']
                    job = client.post('/api/resumes/' + item['id'] + '/compile',
                                      json={'expected_revision': document['revision']}).json()
                    until = time.monotonic() + 45
                    while job['status'] in ('running', 'queued') and time.monotonic() < until:
                        time.sleep(.1)
                        job = client.get('/api/jobs/' + job['id']).json()
                    assert job['status'] == 'succeeded', job.get('error')
                    assert client.get('/api/jobs/' + job['id'] + '/pdf').content.startswith(b'%PDF-')
                    pages.append(job['pages'])
                return {'empty_venv_and_runtime': True, 'no_homebrew_or_tex_in_path': True,
                        'real_engine_download': True, 'service_ready': True, 'reference_pages': pages}
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(45)
                except subprocess.TimeoutExpired:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-dir', type=Path, default=ROOT / '.m1-build/engine-cache')
    parser.add_argument('--fresh-startup', action='store_true')
    args = parser.parse_args()
    parent = ROOT / 'tmp/light-runtime-validation'
    parent.mkdir(parents=True, exist_ok=True)
    report = {'scope': 'isolated project on current Mac, not clean-Mac acceptance', 'passed': False}
    with tempfile.TemporaryDirectory(prefix='安装 verification-', dir=parent) as temporary:
        work = Path(temporary)
        prefix = work / 'install'
        old = prefix / 'releases/previous'
        old.mkdir(parents=True)
        (old / 'marker').write_text('previous installation')
        (prefix / 'current').symlink_to('releases/previous')
        with patch('scripts.light_runtime.make_format', side_effect=ValueError('injected format failure')):
            try:
                install(prefix, args.cache_dir.resolve(), offline=True)
            except ValueError as error:
                assert 'injected format failure' in str(error)
            else:
                raise AssertionError('Format failure was accepted.')
        assert (prefix / 'current').resolve() == old
        assert not list(prefix.glob('.light-stage-*'))
        report['failure_preserves_previous_installation'] = True
        installed = install(prefix, args.cache_dir.resolve(), offline=True)
        with patch('scripts.light_runtime.urllib.request.build_opener', side_effect=AssertionError('unexpected network')):
            assert install(prefix, args.cache_dir.resolve(), offline=True) == installed
        report['offline_install_and_repeat'] = True
        files = inventory(installed)
        report['installed_bytes'] = sum(item.get('bytes', 0) for item in files)
        report['installed_files'] = len(files)
        assert not (installed / 'resume-runtime').exists()
        assert {p.name for p in (installed / 'tex/bin').iterdir()} == {'xelatex', 'xdvipdfmx'}
        report['only_two_executables_no_frozen_python'] = True
        moved = work / 'moved runtime 中文'
        shutil.copytree(installed, moved)
        checked = check_cases(moved, parent / 'pdf-cases')
        assert not checked['failures'], checked['failures']
        report['valid_cases'] = sum(bool(x.get('ok')) for x in checked['cases'].values())
        report['rejected_cases'] = sum(bool(x.get('rejected')) for x in checked['cases'].values())
        for job in (parent / 'pdf-cases').iterdir():
            recorder = job / 'main.fls'
            if recorder.is_file():
                lines = recorder.read_text().splitlines()
                formats = [line[6:] for line in lines if line.startswith('INPUT ') and line.endswith('.fmt')]
                assert formats and all(Path(name).is_relative_to(moved / 'tex/formats') for name in formats)
        report['only_project_format_read'] = True
        manifest = compiler_manifest(moved)
        blank = next(c for c in cases() if c['id'] == 'standard-one-page-target')
        resume, assets = build_case(blank)
        source, _ = render_resume(resume, assets)
        probes = work / 'probes'
        probes.mkdir()
        with patch.object(experiment, 'WORK', probes):
            report['isolation'] = experiment.probe_isolation(manifest, source)
            report['timeouts'] = experiment.probe_timeout(manifest, source)
        assert all(report['isolation'].values()) and all(report['timeouts'].values())
        long_case = next(c for c in cases() if c['id'] == 'two-page-target')
        resume, assets = build_case(long_case)
        source, avatar = render_resume(resume, assets)
        samples = []
        compiler = Compiler(moved)
        for _ in range(30):
            started = time.perf_counter()
            pdf, pages = compiler(resume, assets, work / 'benchmark')
            assert pdf.startswith(b'%PDF-') and pages == 2
            samples.append(time.perf_counter() - started)
        report['benchmark'] = {'samples': 30, 'p50_seconds': round(statistics.median(samples), 3),
                               'p95_seconds': round(sorted(samples)[28], 3)}
        assert report['benchmark']['p95_seconds'] <= 3
        if args.fresh_startup:
            report['fresh_startup'] = check_startup(work)
    report['passed'] = True
    target = ROOT / 'work-logs/evidence/lightweight-tex.json'
    target.write_bytes(json_bytes(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
