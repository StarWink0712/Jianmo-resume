"""Portable immutable runtime inventories and strict Windows-compatible names."""

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import shutil
import tarfile


def safe_relative(name):
    if not isinstance(name, str) or not name:
        raise ValueError('Empty runtime path')
    path = PurePosixPath(name)
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$',
                *(f'{prefix}{number}' for prefix in ('COM', 'LPT') for number in '123456789¹²³')}
    if path.is_absolute() or path.as_posix() != name or name == '.' or '..' in path.parts:
        raise ValueError('Unsafe runtime path: ' + name)
    for part in path.parts:
        if (part[-1] in '. ' or any(ord(c) < 32 or c in '\\:<>"|?*' for c in part)
                or part.split('.')[0].upper() in reserved):
            raise ValueError('Ambiguous Windows runtime path: ' + name)
    return path


def plain_path(path):
    """Check before resolving: a junction must not silently become its target."""
    path = Path(os.path.abspath(path))
    if os.name == 'nt' and str(path).startswith('\\\\'):
        raise ValueError('Runtime must be on a local drive.')
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Runtime path contains a link/reparse point.')
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ValueError('Runtime contains a multiply linked file.')
    return path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    root = plain_path(root)
    result, pending, seen = [], [root], set()
    while pending:
        directory = pending.pop()
        for child in directory.iterdir():
            plain_path(child)
            name = child.relative_to(root).as_posix()
            safe_relative(name)
            key = name.casefold()
            if key in seen:
                raise ValueError('Case-insensitive runtime path collision.')
            seen.add(key)
            if child.is_dir():
                pending.append(child)
            elif child.is_file():
                if name != 'runtime.json':
                    result.append({'path': name, 'bytes': child.stat().st_size, 'sha256': digest(child)})
            else:
                raise ValueError('Runtime contains a special file.')
    return sorted(result, key=lambda item: item['path'])


def verify_inventory(root, entries):
    seen = set()
    for item in entries:
        name = str(safe_relative(item['path']))
        if name.casefold() in seen or name == 'runtime.json':
            raise ValueError('Duplicate/self-referencing runtime inventory entry.')
        seen.add(name.casefold())
    if entries != inventory(root):
        raise ValueError('Runtime files differ from the manifest; reinstall a new release.')


def unpack_support(archive, stage, expected_bytes):
    stage = plain_path(stage)
    total, seen = 0, set()
    with tarfile.open(archive, 'r:xz') as stream:
        for entry in stream:
            name = str(safe_relative(entry.name))
            if not entry.isfile() or name.casefold() in seen:
                raise ValueError('Archive contains a link, duplicate or special file.')
            if name != 'support-inventory.json' and not name.startswith(('tex/', 'format-sources/', 'licenses/texlive/')):
                raise ValueError('Unexpected support member.')
            seen.add(name.casefold())
            total += entry.size
            if total > expected_bytes:
                raise ValueError('Archive exceeds its unpacked budget.')
            target = plain_path(stage / name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with stream.extractfile(entry) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
    if total != expected_bytes:
        raise ValueError('Archive is incomplete.')
