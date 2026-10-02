"""Executable M0 contract checks, not a production importer or renderer."""

import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import struct
import sys
import unicodedata
from urllib.parse import unquote, urlsplit
import zlib

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
MAX_RESUME_BYTES = 2 * 1024 * 1024


def read_json(data):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError('nonfinite JSON number')

    return json.loads(data, object_pairs_hook=unique_object, parse_constant=reject_constant)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')


RESUME_SCHEMA = read_json((ROOT / 'schemas/resume.schema.json').read_bytes())
BACKUP_SCHEMA = read_json((ROOT / 'schemas/backup-manifest.schema.json').read_bytes())


def schema_errors(schema, value):
    # Report locations, not personal data embedded in jsonschema's full messages.
    return [
        'schema: /' + '/'.join(str(part) for part in error.absolute_path)
        for error in Draft202012Validator(schema).iter_errors(value)
    ]


def safe_url(value):
    if not isinstance(value, str) or not value or len(value) > 2048:
        return False
    if '\\' in value or any(character.isspace() for character in value):
        return False
    if any(unicodedata.category(character).startswith('C') for character in unquote(value)):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in ('https', 'http')
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except ValueError:
        return False


def timestamp(value):
    return datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')


def validate_resume(resume):
    errors = schema_errors(RESUME_SCHEMA, resume)
    if errors:
        return errors
    try:
        if len(json_bytes(resume)) > MAX_RESUME_BYTES:
            errors.append('resume exceeds 2 MiB')
    except (ValueError, UnicodeError):
        errors.append('resume is not valid UTF-8 JSON')
    try:
        if timestamp(resume['updated_at']) < timestamp(resume['created_at']):
            errors.append('updated_at precedes created_at')
    except ValueError:
        errors.append('invalid calendar timestamp')

    identifiers = set()

    def register(identifier):
        if identifier in identifiers:
            errors.append('duplicate internal ID')
        identifiers.add(identifier)

    for link in resume['basics']['links']:
        register(link['id'])
        if not safe_url(link['url']):
            errors.append('unsafe contact URL')
    for section in resume['sections']:
        register(section['id'])
        for entry in section['entries']:
            register(entry['id'])
            if section['type'] in ('education', 'employment', 'project', 'academic', 'competition', 'custom', 'awards'):
                start, end = entry.get('start_date'), entry.get('end_date')
                if entry.get('ongoing', False) and end is not None:
                    errors.append('ongoing entry has end_date')
                if start and end and end < start:
                    errors.append('end_date precedes start_date')
            if section['type'] in ('project', 'academic', 'competition', 'custom', 'awards') and entry.get('url') is not None:
                if not safe_url(entry['url']):
                    errors.append('unsafe entry URL')
    attachment_ids = set()
    for attachment in resume['attachments']:
        register(attachment['id'])
        attachment_ids.add(attachment['id'])
    avatar = resume['basics']['avatar_attachment_id']
    if attachment_ids != ({avatar} if avatar is not None else set()):
        errors.append('avatar reference and attachment set differ')
    return errors


def synthetic_png():
    def chunk(kind, content):
        checksum = zlib.crc32(kind + content) & 0xffffffff
        return struct.pack('!I', len(content)) + kind + content + struct.pack('!I', checksum)

    header = struct.pack('!IIBBBBB', 64, 64, 8, 2, 0, 0, 0)
    pixels = (b'\x00' + b'\x90\xa8\xa0' * 64) * 64
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


def cases():
    return read_json((ROOT / 'fixtures/cases.json').read_bytes())['cases']


def build_case(case):
    catalog = read_json((ROOT / 'fixtures/cases.json').read_bytes())
    resume = read_json((ROOT / 'fixtures' / catalog['base']).read_bytes())
    for patch in case['patches']:
        if patch['op'] != 'set' or not patch['path']:
            raise ValueError('unsupported fixture patch')
        parent = resume
        for part in patch['path'][:-1]:
            parent = parent[part]
        parent[patch['path'][-1]] = copy.deepcopy(patch['value'])
    assets = {}
    if case.get('synthetic_avatar'):
        content = synthetic_png()
        resume['basics']['avatar_attachment_id'] = 'asset-avatar'
        resume['attachments'] = [{
            'id': 'asset-avatar', 'media_type': 'image/png',
            'byte_size': len(content), 'sha256': hashlib.sha256(content).hexdigest(),
            'width_px': 64, 'height_px': 64,
        }]
        assets['assets/asset-avatar.png'] = content
    return resume, assets


def attachment_path(attachment):
    extension = 'png' if attachment['media_type'] == 'image/png' else 'jpg'
    return f"assets/{attachment['id']}.{extension}"


def make_manifest(resume, assets):
    payloads = {'resume.json': json_bytes(resume), **assets}
    attachment_ids = {attachment_path(item): item['id'] for item in resume['attachments']}
    files = []
    for path, content in payloads.items():
        entry = {'path': path, 'byte_size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
        if path in attachment_ids:
            entry['attachment_id'] = attachment_ids[path]
        files.append(entry)
    manifest = {
        'backup_version': 1, 'resume_schema_version': resume['schema_version'],
        'resume_id': resume['id'], 'revision': resume['revision'],
        'created_at': resume['updated_at'], 'files': files,
    }
    return manifest, payloads


def validate_backup(manifest, payloads):
    """Check an in-memory fixture mapping; deliberately does not extract ZIPs."""
    errors = schema_errors(BACKUP_SCHEMA, manifest)
    if errors:
        return errors
    try:
        timestamp(manifest['created_at'])
    except ValueError:
        errors.append('invalid backup timestamp')
    paths = [item['path'] for item in manifest['files']]
    if len(set(paths)) != len(paths):
        errors.append('duplicate manifest path')
    if set(paths) != set(payloads) or 'resume.json' not in payloads:
        return errors + ['manifest and payload file sets differ']
    if len(payloads['resume.json']) > MAX_RESUME_BYTES:
        return errors + ['resume payload exceeds 2 MiB']
    for item in manifest['files']:
        content = payloads[item['path']]
        if len(content) != item['byte_size'] or hashlib.sha256(content).hexdigest() != item['sha256']:
            errors.append('payload size or hash mismatch')
    try:
        resume = read_json(payloads['resume.json'])
    except (ValueError, UnicodeError):
        return errors + ['invalid resume JSON payload']
    resume_errors = validate_resume(resume)
    if resume_errors:
        return errors + resume_errors
    for manifest_key, resume_key in (
        ('resume_id', 'id'), ('revision', 'revision'), ('resume_schema_version', 'schema_version')
    ):
        if manifest[manifest_key] != resume[resume_key]:
            errors.append('manifest identity differs from resume')
    expected = {'resume.json'} | {attachment_path(item) for item in resume['attachments']}
    if set(paths) != expected:
        return errors + ['attachment file set differs from resume']
    by_path = {item['path']: item for item in manifest['files']}
    for attachment in resume['attachments']:
        entry = by_path[attachment_path(attachment)]
        if (entry['attachment_id'] != attachment['id']
                or entry['byte_size'] != attachment['byte_size']
                or entry['sha256'] != attachment['sha256']):
            errors.append('attachment metadata differs from manifest')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--show', metavar='CASE_ID')
    group.add_argument('--backup-manifest', metavar='CASE_ID')
    args = parser.parse_args()
    selected = args.show or args.backup_manifest
    if selected:
        case = next((case for case in cases() if case['id'] == selected), None)
        if case is None:
            parser.error('unknown fixture ID')
        resume, assets = build_case(case)
        if args.backup_manifest and validate_resume(resume):
            parser.error('cannot build a backup from an invalid fixture')
        value = make_manifest(resume, assets)[0] if args.backup_manifest else resume
        sys.stdout.buffer.write(json_bytes(value))
        return 0
    failures = 0
    for case in cases():
        resume, assets = build_case(case)
        valid = not validate_resume(resume)
        passed = valid == case['valid']
        if valid:
            passed = passed and not validate_backup(*make_manifest(resume, assets))
        failures += not passed
        suffix = ' (render checks deferred)' if case.get('render_expectation') else ''
        print(f"{'PASS' if passed else 'FAIL'} {case['id']}: expected {'accept' if case['valid'] else 'reject'}{suffix}")
    print(f'{len(cases())} fixture cases; {failures} failures; no PDF or ZIP import tested.')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
