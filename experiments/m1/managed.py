"""Manifest validation for the relocatable, local-only M1 runtime."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import stat


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    root = Path(root).resolve()
    entries = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if relative == 'runtime.json':
            continue
        if path.is_symlink():
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError('runtime link escapes bundle: ' + relative)
            entries.append({'path': relative, 'link': path.readlink().as_posix()})
        elif path.is_file():
            entries.append({'path': relative, 'bytes': path.stat().st_size,
                            'mode': stat.S_IMODE(path.stat().st_mode), 'sha256': digest(path)})
    return entries


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'runtime.json').read_text())
    if manifest.get('schema') != 1:
        raise ValueError('unsupported runtime manifest')
    expected = manifest['files']
    for entry in expected:
        path = PurePosixPath(entry['path'])
        if path.is_absolute() or '..' in path.parts or path.as_posix() != entry['path']:
            raise ValueError('unsafe manifest path')
    if expected != inventory(root):
        raise ValueError('runtime contents differ from manifest; reinstall into a new prefix')
    return manifest


def compiler_manifest(root):
    root = Path(root).resolve()
    return {'tex_root': str(root / 'tex'), 'engine': str(root / 'tex/bin/xelatex'),
            'fonts_root': str(root / 'tex/fonts'), 'isolated': True}
