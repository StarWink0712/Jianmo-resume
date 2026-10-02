"""Real HTTP + installed TeX smoke test. Uses only isolated fictional data."""

import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from PIL import Image

from backend.backup import export_backup, import_backup
from backend.domain import MAX_AVATAR_UPLOAD_BYTES
from experiments.m1.pdf_checks import inspect_pdf
from experiments.m1.fonts import FONT_FILES, font_media_type, uses_bundled_fonts
from experiments.m1.run import compact, expected_text
from scripts.check_contracts import build_case, cases, json_bytes, synthetic_png


class Harness:
    def __init__(self, root, runtime, port):
        self.root, self.runtime, self.port = root, runtime, port
        self.origin = f'http://127.0.0.1:{port}'
        self.process = None
        self.client = httpx.Client(base_url=self.origin, timeout=15, trust_env=False)

    def start(self, name='primary'):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', self.port))
        self.process = subprocess.Popen([sys.executable, '-m', 'backend', '--port', str(self.port),
            '--data-dir', str(self.root / name), '--runtime', str(self.runtime)], cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError('Test service failed to start; verify the installed runtime.')
            try:
                response = self.client.get('/api/health')
                if response.status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError('Test service startup timed out.')
        self.token = self.client.get('/api/session', headers={'X-Resume-Bootstrap': '1'}).json()['token']
        self.client.headers.update({'Origin': self.origin, 'X-Resume-Token': self.token})

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(45)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
                raise RuntimeError('Test service did not shut down gracefully.')

    def request(self, method, path, status=200, **kwargs):
        response = self.client.request(method, path, **kwargs)
        if response.status_code != status:
            raise AssertionError(f'{method} API returned {response.status_code}, expected {status}')
        return response

    def save(self, document):
        return self.request('PUT', '/api/resumes/' + document['id'],
            json={'expected_revision': document['revision'], 'resume': document}).json()['resume']

    def compile(self, document, expected='succeeded'):
        job = self.request('POST', f'/api/resumes/{document["id"]}/compile', 202,
            json={'expected_revision': document['revision']}).json()
        deadline = time.monotonic() + 45
        while job['status'] in ('queued', 'running') and time.monotonic() < deadline:
            time.sleep(.1)
            job = self.request('GET', '/api/jobs/' + job['id']).json()
        if job['status'] != expected:
            raise AssertionError(f'Compile status {job["status"]}, expected {expected}: {job.get("error")}')
        return job


def run(h, output):
    report = {'stage': 'M2 local integration, not release acceptance', 'checks': {}, 'pdfs': {}}
    checks = report['checks']
    h.start()
    for name, (size, sha256) in FONT_FILES.items():
        response = h.request('GET', '/assets/' + name)
        assert response.headers['content-type'] == font_media_type(name)
        assert len(response.content) == size and hashlib.sha256(response.content).hexdigest() == sha256
    checks['shared_bundled_font_assets'] = True
    h.request('GET', '/api/resumes', 403, headers={'X-Resume-Token': 'wrong'})
    h.request('GET', '/api/resumes', 403, headers={'Host': 'evil.example'})
    h.request('GET', '/api/resumes', 403, headers={'Origin': 'https://evil.example'})
    checks['http_security'] = True
    standard = h.request('POST', '/api/resumes', 201, json={'title': 'M2 fictional standard', 'kind': 'sample'}).json()['resume']
    standard['style']['margins_px']['top'] = 25
    standard['basics'].update(gender='女', age=26)
    standard['basics']['links'][0]['label'] = ''
    standard['sections'][-1]['entries'][0]['body'] += '\n\nUnicode: A-B / A‐B / A‑B / A→B. **Bold ABC** and *Italic ABC* and ***Both ABC***.'
    standard = h.save(standard)
    first = h.compile(standard)
    previous_pdf = h.request('GET', f'/api/jobs/{first["id"]}/pdf').content
    assert previous_pdf == h.request('GET', f'/api/jobs/{first["id"]}/pdf?download=true').content
    checks['preview_equals_download'] = True
    output.mkdir(parents=True, exist_ok=True)
    for document, job, filename, pages in [(standard, first, 'm2-standard.pdf', 1)]:
        path = output / filename
        path.write_bytes(previous_pdf)
        inspected = inspect_pdf(path)
        assert inspected['pages'] == pages
        assert all(compact(value) in compact(inspected['text']) for value in expected_text(document))
        assert uses_bundled_fonts(inspected['fonts'])
        report['pdfs'][filename] = {'pages': pages, 'sha256': hashlib.sha256(previous_pdf).hexdigest(), 'text_and_fonts': True}
    checks['header_fields_and_blank_link_label'] = True
    checks['sans_hyphen_arrow_and_italic_text_fidelity'] = True
    long_doc, assets = build_case(next(case for case in cases() if case['id'] == 'two-page-target'))
    long_doc = h.request('POST', '/api/import', 201, content=export_backup(long_doc, assets), headers={'Content-Type': 'application/zip'}).json()['resume']
    long_job = h.compile(long_doc)
    content = h.request('GET', f'/api/jobs/{long_job["id"]}/pdf').content
    path = output / 'm2-long.pdf'
    path.write_bytes(content)
    inspected = inspect_pdf(path)
    assert inspected['pages'] == 2
    assert all(compact(value) in compact(inspected['text']) for value in expected_text(long_doc))
    assert uses_bundled_fonts(inspected['fonts'])
    report['pdfs'][path.name] = {'pages': 2, 'sha256': hashlib.sha256(content).hexdigest(), 'text_and_fonts': True}
    checks['real_compilation'] = True
    clone = h.request('POST', f'/api/resumes/{standard["id"]}/copy', 201,
        json={'expected_revision': standard['revision'], 'title': 'independent copy', 'version': 'saved'}).json()['resume']
    clone['basics']['name'] = '副本独立测试'
    clone = h.save(clone)
    assert h.request('GET', '/api/resumes/' + standard['id']).json()['resume'] == standard
    checks['copy_independence'] = True
    original = copy.deepcopy(standard)
    standard['sections'][0]['entries'][0]['body'] = '<b>unsupported HTML</b>'
    standard = h.save(standard)
    h.compile(standard, 'failed')
    detail = h.request('GET', '/api/resumes/' + standard['id']).json()
    assert detail['resume'] == standard and detail['pdf']['id'] == first['id']
    assert detail['build_key'] != detail['pdf']['build_key']
    assert h.request('GET', f'/api/jobs/{first["id"]}/pdf').content == previous_pdf
    checks['failure_retains_data_and_old_pdf'] = True
    original.update(revision=standard['revision'], updated_at=standard['updated_at'])
    standard = h.save(original)
    standard = h.request('PUT', f'/api/resumes/{standard["id"]}/avatar?expected_revision={standard["revision"]}',
        content=synthetic_png(), headers={'Content-Type': 'application/octet-stream'}).json()['resume']
    rejected = h.request('PUT', f'/api/resumes/{standard["id"]}/avatar?expected_revision={standard["revision"]}', 413,
        content=b'x' * (MAX_AVATAR_UPLOAD_BYTES + 1), headers={'Content-Type':'application/octet-stream'})
    assert rejected.json()['code'] == 'avatar_too_large'
    assert h.request('GET', '/api/resumes/' + standard['id']).json()['resume'] == standard
    wide = io.BytesIO()
    Image.new('RGB', (5000, 1000), '#527994').save(wide, format='PNG')
    wide_content = wide.getvalue()
    assert len(wide_content) < MAX_AVATAR_UPLOAD_BYTES
    clone = h.request('PUT', f'/api/resumes/{clone["id"]}/avatar?expected_revision={clone["revision"]}',
        content=wide_content, headers={'Content-Type':'application/octet-stream'}).json()['resume']
    assert (clone['attachments'][0]['width_px'], clone['attachments'][0]['height_px']) == (1024, 205)
    assert h.compile(clone)['pages'] == 1
    checks['avatar_one_mb_limit_and_wide_photo_normalization'] = True
    avatar_job = h.compile(standard)
    archive = h.request('GET', f'/api/resumes/{standard["id"]}/backup?expected_revision={standard["revision"]}').content
    old_token = h.token
    h.stop()
    h.start()
    assert h.token != old_token
    h.request('GET', '/api/resumes', 403, headers={'X-Resume-Token': old_token})
    assert h.request('GET', '/api/resumes/' + standard['id']).json()['resume'] == standard
    assert h.request('GET', f'/api/jobs/{first["id"]}/pdf').content == previous_pdf
    assert not list((h.root / 'primary' / 'jobs').iterdir())
    checks['restart_restores_revision_attachments_pdf'] = True
    checks['token_rotates_and_job_temp_cleaned'] = True
    h.stop()
    h.start('fresh-import')
    assert h.request('GET', '/api/resumes').json() == []
    imported = h.request('POST', '/api/import', 201, content=archive, headers={'Content-Type': 'application/zip'}).json()['resume']
    assert imported['id'] != standard['id'] and imported['revision'] == 1
    assert imported['style'] == standard['style']
    assert imported['attachments'][0]['sha256'] == standard['attachments'][0]['sha256']
    for key in standard['basics']:
        if key not in ('links', 'avatar_attachment_id'):
            assert imported['basics'][key] == standard['basics'][key]
    restored_archive = h.request('GET', f'/api/resumes/{imported["id"]}/backup?expected_revision=1').content
    _, original_assets = import_backup(archive)
    _, restored_assets = import_backup(restored_archive)
    assert list(original_assets.values()) == list(restored_assets.values())
    assert h.compile(imported)['pages'] == avatar_job['pages']
    checks['backup_import_into_fresh_database_with_avatar'] = True
    h.stop()
    report['passed'] = all(checks.values())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=ROOT / '.m1-build/local-install/current')
    parser.add_argument('--port', type=int, default=8771)
    args = parser.parse_args()
    parent = ROOT / 'tmp/m2'
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='self-check-', dir=parent) as temporary:
        h = Harness(Path(temporary), args.runtime.resolve(), args.port)
        try:
            report = run(h, ROOT / 'output/pdf')
        finally:
            h.stop()
            h.client.close()
    report_dir = ROOT / 'docs/m2'
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / 'results.json').write_bytes(json_bytes(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
