"""Compile a fictional English CV through an isolated backend and installed TeX."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.backup import export_backup, import_backup
from experiments.m1.fonts import uses_bundled_fonts
from experiments.m1.pdf_checks import inspect_pdf
from core.resume_checks import compact, expected_text

from scripts.check_backend import Harness
from scripts.check_contracts import json_bytes


def run(h):
    h.start()
    fixture = json.loads((ROOT / 'fixtures/resumes/english.json').read_text())
    document = h.request('POST', '/api/import', 201, content=export_backup(fixture, {}),
                         headers={'Content-Type': 'application/zip'}).json()['resume']
    checks, pdfs = {}, []
    for size in (12, 14):
        document['style']['content_size_px'] = size
        document = h.save(document)
        job = h.compile(document)
        pdf = h.request('GET', f'/api/jobs/{job["id"]}/pdf').content
        assert pdf == h.request('GET', f'/api/jobs/{job["id"]}/pdf?download=true').content
        path = ROOT / f'output/pdf/english-fictional-{size}px.pdf'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pdf)
        info = inspect_pdf(path)
        assert 1 <= info['pages'] <= 2
        assert uses_bundled_fonts(info['fonts'])
        assert all(compact(fragment) in compact(info['text']) for fragment in expected_text(document))
        assert not re.search(r'[\u4e00-\u9fff]', info['text'])
        assert 'https://example.com/papers/reconstruction?version=1&format=pdf' in info['links']
        assert any('BoldItalic' in name for name in info['fonts'])
        pdfs.append({'size_px': size, 'pages': info['pages'], 'sha256': hashlib.sha256(pdf).hexdigest()})
    checks.update(real_compilation=True, literal_text_and_punctuation=True, bundled_fonts_and_emphasis=True,
                  external_links_preserved=True, preview_equals_download=True, no_unrequested_chinese_labels=True)
    original = copy.deepcopy(document)
    archive = h.request('GET', f'/api/resumes/{document["id"]}/backup?expected_revision={document["revision"]}').content
    assert import_backup(archive)[0] == original
    copied = h.request('POST', f'/api/resumes/{document["id"]}/copy', 201, json={
        'title': 'Independent English copy', 'version': 'saved', 'expected_revision': document['revision']}).json()['resume']
    copied['basics']['headline'] = 'Independent copy only'
    h.save(copied)
    assert h.request('GET', '/api/resumes/' + document['id']).json()['resume'] == original
    h.stop()
    h.start()
    assert h.request('GET', '/api/resumes/' + document['id']).json()['resume'] == original
    assert h.request('GET', '/api/jobs/' + job['id'] + '/pdf').content == pdf
    checks.update(backup_roundtrip=True, copy_independence=True, restart_retains_resume_and_pdf=True)
    return {'passed': all(checks.values()), 'checks': checks, 'pdfs': pdfs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8773)
    args = parser.parse_args()
    parent = ROOT / 'tmp/m2'
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='english-check-', dir=parent) as directory:
        h = Harness(Path(directory), (ROOT / '.m1-build/local-install/current').resolve(), args.port)
        try:
            report = run(h)
        finally:
            h.stop()
            h.client.close()
    (ROOT / 'work-logs/evidence/m2-english-resume.json').write_bytes(json_bytes(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
