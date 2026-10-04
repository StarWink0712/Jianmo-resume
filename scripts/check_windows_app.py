"""Real Windows application acceptance with isolated fictional resume data."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(output, runtime=None):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from backend.backup import import_backup
    from core.managed_runtime import default_runtime
    from core.resume_checks import compact
    from pypdf import PdfReader
    import io
    runtime = Path(runtime) if runtime else default_runtime()
    origin = 'http://127.0.0.1:8770'
    data = output / 'data 中文 & (app)'
    report = {'schema': 1, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'passed': False, 'scope': 'native compiler plus HTTP application, fictional data only', 'checks': {}}

    def session(client):
        response = client.get('/api/session', headers={'X-Resume-Bootstrap': '1'})
        response.raise_for_status()
        client.headers.update({'Origin': origin, 'X-Resume-Token': response.json()['token']})

    def checked(response, expected=200):
        if response.status_code != expected:
            raise ValueError(f'HTTP {response.status_code}: {response.text}')
        return response

    def portable_content(document):
        # Import intentionally creates fresh IDs, revision and timestamps. All
        # visible content, ordering, style and attachment metadata must survive.
        def normalize(value):
            if isinstance(value, list):
                return [normalize(item) for item in value]
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items() if key not in ('id', 'avatar_attachment_id')}
            return value
        return normalize({key: value for key, value in document.items() if key not in ('title', 'revision', 'created_at', 'updated_at')})

    try:
        app = create_app(data, runtime, origin)
        with TestClient(app, base_url=origin) as client:
            session(client)
            records = checked(client.get('/api/resumes')).json()
            assert len(records) == 3
            document = checked(client.get('/api/resumes/' + records[0]['id'])).json()['resume']
            document['basics']['name'] = 'Windows 验收（虚构）'
            document['style']['theme_color'] = '#0F766E'
            saved = checked(client.put('/api/resumes/' + document['id'], json={
                'expected_revision': document['revision'], 'resume': document})).json()['resume']
            report['checks']['save'] = saved['revision'] == document['revision'] + 1
            started = time.monotonic()
            job = checked(client.post('/api/resumes/' + saved['id'] + '/compile',
                                      json={'expected_revision': saved['revision']}), 202).json()
            deadline = time.monotonic() + 180
            while job['status'] in ('queued', 'running') and time.monotonic() < deadline:
                time.sleep(.2)
                job = checked(client.get('/api/jobs/' + job['id'])).json()
            if job['status'] != 'succeeded':
                raise ValueError('Native application compile failed: ' + json.dumps(job, ensure_ascii=False))
            pdf = checked(client.get('/api/jobs/' + job['id'] + '/pdf')).content
            downloaded = checked(client.get('/api/jobs/' + job['id'] + '/pdf?download=true')).content
            text = compact(''.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(pdf)).pages))
            report['checks']['real_pdf_and_download'] = pdf == downloaded and compact(saved['basics']['name']) in text
            report['compile_seconds'] = round(time.monotonic() - started, 3)
            report['pdf_sha256'] = hashlib.sha256(pdf).hexdigest()
            (output / 'windows-app.pdf').write_bytes(pdf)
            archive = checked(client.get(f'/api/resumes/{saved["id"]}/backup?expected_revision={saved["revision"]}')).content
            report['checks']['backup_preserves_document'] = import_backup(archive)[0] == saved
            imported = checked(client.post('/api/import', content=archive, headers={'Content-Type': 'application/zip'}), 201).json()['resume']
            report['checks']['import_creates_independent_copy'] = imported['id'] != saved['id'] and portable_content(imported) == portable_content(saved)
            mac_backup = (ROOT / 'examples/backups/algorithm-engineer.resume.zip').read_bytes()
            migrated = checked(client.post('/api/import', content=mac_backup, headers={'Content-Type': 'application/zip'}), 201).json()['resume']
            report['checks']['mac_backup_import'] = portable_content(migrated) == portable_content(import_backup(mac_backup)[0])
        restarted = create_app(data, runtime, origin)
        with TestClient(restarted, base_url=origin) as client:
            session(client)
            restored = checked(client.get('/api/resumes/' + saved['id'])).json()['resume']
            report['checks']['restart_preserves_save_and_pdf'] = restored == saved and checked(
                client.get('/api/jobs/' + job['id'] + '/pdf')).content == pdf
            report['checks']['job_files_cleaned'] = not any((data / 'jobs').iterdir())
        report['passed'] = all(report['checks'].values())
    except Exception as error:
        report['error'] = str(error)
    (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    output = Path(tempfile.mkdtemp(prefix='windows-app-check-', dir=ROOT / '.m1-build'))
    print('Application report: ' + str(output), flush=True)
    result = run(output)
    print('PASS Windows application' if result['passed'] else 'FAIL ' + result.get('error', 'application assertions'), flush=True)
    raise SystemExit(0 if result['passed'] else 1)
