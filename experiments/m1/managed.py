"""Manifest validation for the relocatable, local-only M1 runtime."""

import hashlib
import json
from pathlib import Path, PurePosixPath
import stat

from platform_adapters.detect import platform_key


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
    manifest = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1:
        raise ValueError('unsupported runtime manifest')
    if manifest.get('platform', 'darwin-arm64') != platform_key():
        raise ValueError('runtime manifest belongs to another platform')
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
    manifest = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
    key = manifest.get('platform', 'darwin-arm64')
    if key != 'darwin-arm64' or key != platform_key():
        raise ValueError('No verified compiler entry point for this runtime platform.')
    return {'platform': key, 'tex_root': str(root / 'tex'), 'engine': str(root / 'tex/bin/xelatex'),
            'driver': str(root / 'tex/bin/xdvipdfmx'),
            'fonts_root': str(root / 'tex/fonts'), 'isolated': True}
