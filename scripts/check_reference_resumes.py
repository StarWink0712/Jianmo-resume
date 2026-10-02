"""Validate first-use examples, actual PDFs, portable backups and durable deletion."""
import json
from pathlib import Path
import tempfile

from backend.backup import import_backup
from backend.examples import EXAMPLES, example_document
from experiments.m1.pdf_checks import inspect_pdf
from experiments.m1.run import compact, expected_text
from scripts.check_backend import Harness
from scripts.check_contracts import ROOT, json_bytes


def run(h, output):
    h.start()
    summaries = h.request('GET', '/api/resumes').json()
    assert [item['title'] for item in summaries] == [example_document(kind)['title'] for kind in EXAMPLES]
    original_ids = {item['id'] for item in summaries}
    output.mkdir(parents=True, exist_ok=True)
    pages = {}
    for kind, summary in zip(EXAMPLES, summaries):
        document = h.request('GET', '/api/resumes/' + summary['id']).json()['resume']
        job = h.compile(document)
        assert 1 <= job['pages'] <= 2, (kind, job['pages'])
        pdf = h.request('GET', f'/api/jobs/{job["id"]}/pdf').content
        assert pdf == h.request('GET', f'/api/jobs/{job["id"]}/pdf?download=true').content
        path = output / (EXAMPLES[kind] + '.pdf'); path.write_bytes(pdf)
        info = inspect_pdf(path)
        assert all(compact(text) in compact(info['text']) for text in expected_text(document))
        pages[kind] = info['pages']
        portable = ROOT / 'examples/backups' / (EXAMPLES[kind] + '.resume.zip')
        assert import_backup(portable.read_bytes()) == (example_document(kind), {})
    edited = h.request('GET', '/api/resumes/' + summaries[0]['id']).json()['resume']
    edited['basics']['name'] = '独立编辑验证'
    edited = h.save(edited)
    h.stop(); h.start()
    assert len(h.request('GET', '/api/resumes').json()) == 3
    assert h.request('GET', '/api/resumes/' + edited['id']).json()['resume'] == edited
    for item in h.request('GET', '/api/resumes').json():
        h.request('DELETE', '/api/resumes/' + item['id'], json={'expected_revision': item['revision']})
    h.stop(); h.start()
    assert h.request('GET', '/api/resumes').json() == []
    for kind in EXAMPLES:
        created = h.request('POST', '/api/resumes', 201, json={'title': 'Explicit reference choice', 'kind': kind}).json()['resume']
        assert created['id'] not in original_ids and created['style'] == example_document(kind)['style']
    h.stop(); h.start()
    assert len(h.request('GET', '/api/resumes').json()) == 3
    h.stop(); h.start('another-install')
    new_ids = {item['id'] for item in h.request('GET', '/api/resumes').json()}
    assert len(new_ids) == 3 and new_ids.isdisjoint(original_ids)
    return {'passed': True, 'pages': pages, 'first_start_three_examples': True,
            'portable_backups_match': True, 'edits_survive_restart': True,
            'deleted_examples_stay_deleted': True, 'explicit_recreation_supported': True,
            'new_install_has_independent_ids': True}


def main():
    parent = ROOT / 'tmp/reference-resumes'
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='check-', dir=parent) as directory:
        h = Harness(Path(directory), (ROOT / '.m1-build/local-install/current').resolve(), 8782, seed_examples=True)
        try:
            report = run(h, ROOT / 'output/pdf/reference-resumes')
        finally:
            h.stop(); h.client.close()
    (ROOT / 'work-logs/evidence/reference-resumes.json').write_bytes(json_bytes(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
