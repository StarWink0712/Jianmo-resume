"""Immutable release transactions shared by platform-specific builders.

The builder must generate formats and run native PDF checks before returning.
Nothing is activated until the platform verifier accepts the staged manifest.
Old releases are never overwritten or garbage-collected by this module.
"""

import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

from core.runtime_manifest import plain_path, safe_relative


def replace(source, destination):
    for attempt in range(4):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 3:
                raise
            time.sleep(.05 * 2**attempt)


def current_release(prefix, platform):
    prefix = plain_path(prefix)
    pointer = plain_path(prefix / 'current.json')
    data = json.loads(pointer.read_text(encoding='utf-8'))
    if set(data) != {'schema', 'platform', 'release'} or data['schema'] != 1 or data['platform'] != platform:
        raise ValueError('Unsupported active runtime record.')
    relative = safe_relative(data['release'])
    if len(relative.parts) != 2 or relative.parts[0] != 'releases' or not re.fullmatch(r'[0-9a-f]{64}', relative.parts[1]):
        raise ValueError('Active runtime must name an immutable release.')
    root = plain_path(prefix / relative)
    if not root.is_dir():
        raise ValueError('Active runtime release is missing.')
    return root


def install_release(prefix, identity, platform, adapter, build, verify):
    if not re.fullmatch(r'[0-9a-f]{64}', identity):
        raise ValueError('Runtime identity must be SHA-256.')
    prefix = plain_path(prefix)
    if prefix == Path(prefix.anchor):
        raise ValueError('Refusing to install to a drive root.')
    adapter.private_directory(prefix)
    with adapter.acquire_lock(prefix, '.install.lock'):
        releases = plain_path(prefix / 'releases')
        adapter.private_directory(releases)
        destination = plain_path(releases / identity)
        current = plain_path(prefix / 'current.json')
        # A malformed existing pointer is evidence of damage, not permission to
        # silently overwrite it. Preserve the user's previous record verbatim.
        if current.exists():
            current_release(prefix, platform)
        if destination.exists():
            verify(destination)
        else:
            with tempfile.TemporaryDirectory(prefix='.stage-', dir=prefix) as temporary:
                stage = Path(temporary) / 'runtime'
                adapter.private_directory(stage, exist_ok=False)
                build(stage)
                verify(stage)
                # Windows can retain a loaded SEC_IMAGE's original filename
                # after all processes exit. Renaming the executed file then
                # produces debug events with no readable image handle. Copy
                # into new file identities, verify, and only rename that never-
                # executed tree. Do not overwrite any installed EXE/DLL.
                incoming = Path(temporary) / 'incoming'
                shutil.copytree(stage, incoming, copy_function=shutil.copyfile)
                verify(incoming)
                replace(incoming, destination)
                verify(destination)
        with tempfile.TemporaryDirectory(prefix='.activate-', dir=prefix) as temporary:
            pointer = Path(temporary) / 'current.json'
            payload = {'schema': 1, 'platform': platform, 'release': 'releases/' + identity}
            with pointer.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            adapter.private_file(pointer)
            replace(pointer, current)
        return destination
