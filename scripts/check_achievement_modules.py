"""Real HTTP lifecycle and PDF layout checks for achievement/custom modules."""

import argparse
import copy
import json
from pathlib import Path
import tempfile

from pypdf import PdfReader

from backend.backup import import_backup
from experiments.m1.pdf_checks import inspect_pdf
from core.resume_checks import compact, expected_text

from scripts.check_backend import Harness
from scripts.check_contracts import ROOT, json_bytes


def semantic_sections(document):
    result = copy.deepcopy(document['sections'])
    for section in result:
        section.pop('id')
        for entry in section['entries']:
            entry.pop('id')
    return result


def run(h):
    report = {'checks':{}}
    checks = report['checks']
    h.start()
    document = h.request('POST', '/api/resumes', 201, json={'title':'成果模块验证（虚构）', 'kind':'sample'}).json()['resume']
    document['sections'] = json.loads((ROOT / 'fixtures/achievement-sections.json').read_text())
    document['sections'].append({'id':'section-legacy', 'type':'custom', 'title':'旧自定义兼容', 'visible':True,
                                 'entries':[{'id':'entry-legacy', 'visible':True, 'heading':'旧标题', 'body':'旧正文保持不变。'}]})
    hidden = copy.deepcopy(document['sections'][0]['entries'][0])
    hidden.update(id='entry-hidden', heading='HIDDEN_HEADING', role='HIDDEN_ROLE', visible=False)
    document['sections'][0]['entries'].append(hidden)
    document = h.save(document)
    original = copy.deepcopy(document)
    job = h.compile(document)
    assert job['pages'] == 1
    pdf = h.request('GET', '/api/jobs/' + job['id'] + '/pdf').content
    assert pdf == h.request('GET', '/api/jobs/' + job['id'] + '/pdf?download=true').content
    path = ROOT / 'tmp/pdfs/achievement-modules.pdf'
    path.write_bytes(pdf)
    info = inspect_pdf(path)
    # Layout extraction retains link-run positions across PDF q/Q graphics-state changes.
    # The ordinary text visitor may flush link text after its text matrix was reset.
    lines = [line for page in PdfReader(path).pages for line in page.extract_text(extraction_mode='layout').splitlines()]
    assert all(compact(fragment) in compact(info['text']) for fragment in expected_text(document))
    assert 'HIDDEN_HEADING' not in info['text'] and 'HIDDEN_ROLE' not in info['text']
    for section in document['sections'][:3]:
        entry = section['entries'][0]
        date = entry['start_date'] + ' - ' + ('至今' if entry['ongoing'] else entry['end_date'])
        assert any(all(compact(value) in compact(line) for value in (entry['heading'], entry['role'], date)) for line in lines)
        if entry['url']:
            assert entry['url'] in info['links']
    checks.update(real_compilation=True, inline_title_role_date=True, optional_links_preserved=True,
                  hidden_entries_omitted=True, legacy_custom_preserved=True, preview_equals_export=True)
    for patch in ({'start_date':'2025-99'}, {'end_date':'2024-01'}, {'url':'javascript:alert(1)'}, {'role':'x'*201}):
        bad = copy.deepcopy(document)
        bad['sections'][0]['entries'][0].update(patch)
        h.request('PUT', '/api/resumes/' + document['id'], 422,
                  json={'expected_revision':document['revision'], 'resume':bad})
    assert h.request('GET', '/api/resumes/' + document['id']).json()['resume'] == document
    checks['invalid_metadata_does_not_save'] = True
    archive = h.request('GET', f'/api/resumes/{document["id"]}/backup?expected_revision={document["revision"]}').content
    assert import_backup(archive)[0] == document
    h.stop(); h.start()
    assert h.request('GET', '/api/resumes/' + document['id']).json()['resume'] == document
    copied = h.request('POST', f'/api/resumes/{document["id"]}/copy', 201,
                       json={'expected_revision':document['revision'], 'title':'成果模块独立副本', 'version':'saved'}).json()['resume']
    assert semantic_sections(copied) == semantic_sections(document)
    copied['sections'][0]['entries'][0]['role'] = '副本角色'
    h.save(copied)
    assert h.request('GET', '/api/resumes/' + document['id']).json()['resume'] == original
    checks.update(restart_preserves_metadata=True, copy_is_independent=True)
    h.stop(); h.start('fresh-import')
    imported = h.request('POST', '/api/import', 201, content=archive, headers={'Content-Type':'application/zip'}).json()['resume']
    assert semantic_sections(imported) == semantic_sections(document)
    assert h.compile(imported)['pages'] == 1
    checks['backup_import_into_fresh_database'] = True
    report.update(passed=all(checks.values()), pages=1)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8772)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='achievement-check-', dir=ROOT / 'tmp/m2') as temporary:
        h = Harness(Path(temporary), (ROOT / '.m1-build/local-install/current').resolve(), args.port)
        try:
            report = run(h)
        finally:
            h.stop(); h.client.close()
    (ROOT / 'work-logs/evidence/m2-achievement-modules.json').write_bytes(json_bytes(report))
    print(report)


if __name__ == '__main__':
    main()
