"""Native Windows compiler boundary. Win32 imports remain lazy on other hosts."""

from contextlib import contextmanager
from contextvars import ContextVar
import json
from pathlib import Path
import shutil
import socket
import time

from platform_adapters.contracts import Capabilities, LockBusy, PlatformUnavailable

KEY = 'windows-x64'
CAPABILITIES = Capabilities(True, True, 'job-object', 'job-commit-hard-limit', 'job-and-sampled-cpu', 'sampled-job-bytes')
_active = ContextVar('windows_compilation', default=None)


def initialize_process():
    from platform_adapters.detect import platform_key
    if platform_key() != KEY:
        raise PlatformUnavailable('Native Windows x64 is required.')


def private_directory(path, exist_ok=True):
    from platform_adapters import windows_native as native
    native.private_directory(path, exist_ok=exist_ok)


def private_file(path):
    from platform_adapters import windows_native as native
    native.private_file(path)


def acquire_lock(directory, name):
    from platform_adapters import windows_native as native
    return native.acquire_lock(directory, name)


def configure_listener(listener):
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)


def process_environment(job, engine):
    from platform_adapters import windows_native as native
    return native.environment(job, engine)


def prepare_fonts(job, fonts_root):
    shutil.copytree(fonts_root, job / 'fonts')
    (job / 'fonts.conf').write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
        '<fontconfig><dir prefix="cwd">fonts</dir><cachedir prefix="cwd">cache</cachedir></fontconfig>', encoding='utf-8')


def sandbox_prefix(job, tex_root, extra_read=(), fonts_root=None, name=None):
    context = _active.get()
    if context is None or Path(tex_root) != context['tex'] or Path(job) != context['job']:
        raise PlatformUnavailable('Windows compiler requires a verified runtime and an active isolated scope.')
    if any(not Path(path).is_relative_to(context['tex']) for path in extra_read):
        raise ValueError('Additional Windows compiler read access is not allowed.')
    return []  # Isolation is a CreateProcess attribute, never a shell prefix.


@contextmanager
def compilation(manifest, job):
    from platform_adapters import windows_native as native
    from platform_adapters.windows_images import ImagePolicy
    from platform_adapters.windows_paths import runtime_alias
    from core.managed_runtime import verify_runtime
    if _active.get() is not None:
        raise ValueError('Nested Windows compilation is not supported.')
    if 'runtime_root' not in manifest:
        raise PlatformUnavailable('A verified Windows runtime manifest is required.')
    root = native.local_path(manifest['runtime_root'])
    job = native.local_path(job)
    if len(str(job)) > 220:
        raise ValueError('作业路径过长，请用 --data-dir 选择较短的本地目录。')
    if job.is_relative_to(root) or root.is_relative_to(job):
        raise ValueError('Runtime and writable job directories must be separate.')
    deadline = time.monotonic() + 60
    while True:
        try:
            lease = native.acquire_lock(root.parent, '.' + root.name + '-compile.lock')
            break
        except LockBusy:
            if time.monotonic() >= deadline:
                raise
            time.sleep(.1)
    with lease:
        verify_runtime(root)
        native.private_directory(job)
        lock = json.loads((Path(__file__).resolve().parents[1] / 'runtime/locks/windows-x64.prototype.json').read_text(encoding='utf-8'))
        policy = ImagePolicy({root / item['target']: item['sha256'] for package in lock['packages'] for item in package['files']})
        try:
            with runtime_alias(root) as mapped, native.app_container() as (sid, text):
                tex = mapped / 'tex'
                native.grant_tree(root, text)
                context = {'root': root, 'tex': tex, 'job': job, 'sid': sid, 'sid_text': text, 'images': policy}
                token = _active.set(context)
                try:
                    yield manifest | {'tex_root': str(tex), 'engine': str(tex / 'bin/xelatex.exe'),
                                      'driver': str(tex / 'bin/xdvipdfmx.exe')}
                finally:
                    _active.reset(token)
        finally:
            native.private_tree(root)
            native.private_tree(job)


def run_bounded(command, cwd, env, timeout=30, *, log_name='process.log', **unsupported):
    from platform_adapters import windows_native as native
    context = _active.get()
    if context is None:
        raise PlatformUnavailable('Windows execution outside an isolated compilation is forbidden.')
    if unsupported or Path(cwd) != context['job']:
        raise ValueError('Unsupported Windows execution options or job path.')
    if Path(command[0]) not in (context['tex'] / 'bin/xelatex.exe', context['tex'] / 'bin/xdvipdfmx.exe'):
        raise ValueError('Only pinned Windows TeX entry points are allowed.')
    native.grant_tree(cwd, context['sid_text'], True)
    env = env | {'FONTCONFIG_FILE': 'fonts.conf', 'FONTCONFIG_PATH': '.', 'XE_FONTCONFIG_PATH': '.',
                 'XE_FC_CACHEDIR': './cache', 'TEXMFVAR': '.', 'TEXMFCONFIG': '.', 'TEXMFCACHE': '.',
                 'openin_any': 'p', 'openout_any': 'p', 'shell_escape': 'f'}
    return native.run_in_container(command, cwd, env, context['sid'], timeout=timeout,
                                   log_name=log_name, image_policy=context['images'])
