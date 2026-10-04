"""macOS isolation, process supervision, filesystem permissions and leases."""

import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import time

from platform_adapters.contracts import Capabilities, ExecutionResult, LockBusy


KEY = 'darwin-arm64'
CAPABILITIES = Capabilities(True, True, 'process-group', 'sampled-group-rss', 'rlimit', 'rlimit-per-file')
LIMIT_WRAPPER = Path(__file__).with_name('macos_exec.py')


def initialize_process():
    os.umask(0o077)


def private_directory(path, exist_ok=True):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=exist_ok, mode=0o700)
    path.chmod(0o700)


def private_file(path):
    Path(path).chmod(0o600)


def acquire_lock(directory, name):
    directory = Path(directory).resolve(strict=True)
    if Path(name).name != name or name in ('', '.', '..'):
        raise ValueError('Lock name must be a filename.')
    fd = os.open(directory / name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    handle = os.fdopen(fd, 'a')
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Lock must be a regular file.')
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        handle.close()
        raise LockBusy('Another process holds this directory lease.') from error
    except BaseException:
        handle.close()
        raise
    return handle


def configure_listener(listener):
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


def process_environment(job, engine):
    return {'PATH': os.pathsep.join((str(Path(engine).parent), '/usr/bin', '/bin')),
            'HOME': str(job / 'home'), 'TMPDIR': str(job), 'LANG': 'en_US.UTF-8'}


def prepare_fonts(job, fonts_root):
    link = job / 'fonts'
    if link.is_symlink():
        link.unlink()
    if link.exists():
        raise ValueError('job fonts path must not contain user files')
    link.symlink_to(fonts_root, target_is_directory=True)


def profile(job, tex_root, extra_read=(), network=False, fonts_root=None):
    def literal(path):
        return '(literal ' + json.dumps(str(path), ensure_ascii=False) + ')'

    if fonts_root is None:
        fonts_root = Path(__file__).resolve().parents[1] / '.m1-runtime/fonts'
    fonts_root = Path(fonts_root)
    roots = ['/System', '/usr/lib', '/usr/share', '/private/var/db/dyld', tex_root, fonts_root, job]
    readable = '\n'.join('(subpath ' + json.dumps(str(Path(path).resolve()), ensure_ascii=False) + ')' for path in roots)
    literals = ['/', '/dev/null', '/dev/random', '/dev/urandom', '/bin/sh', '/usr/bin/curl', '/private/etc/localtime', '/private/var/select/sh']
    readable += '\n' + ' '.join(literal(path) for path in [*literals, *extra_read])
    ancestors = {parent for path in [Path(job), Path(tex_root), fonts_root] for parent in path.parents}
    return '\n'.join([
        '(version 1)', '(deny default)', '(allow process-fork)', '(allow process-exec)',
        '(allow sysctl-read)', '(allow mach-lookup (global-name "com.apple.system.logger"))',
        '(allow file-read* ' + readable + ')',
        '(deny file-read* (subpath "/System/Library/Fonts") (subpath "/Library/Fonts") '
        '(regex #"^/System/.*[.](otf|ttf|ttc|otc|dfont)$"))',
        '(allow file-read-metadata ' + ' '.join(literal(path) for path in sorted(ancestors)) + ')',
        '(allow file-write* (subpath ' + json.dumps(str(job), ensure_ascii=False) + ') (literal "/dev/null"))',
        '(allow network*)' if network else '',
    ])


def sandbox_prefix(job, tex_root, extra_read=(), fonts_root=None, name='compile.sb'):
    sandbox = job / name
    sandbox.write_text(profile(job, tex_root, extra_read, fonts_root=fonts_root), encoding='utf-8')
    return ['/usr/bin/sandbox-exec', '-f', str(sandbox)]


def group_rss_bytes(pgid):
    result = subprocess.run(['/bin/ps', '-axo', 'pgid=,rss='], capture_output=True, text=True, timeout=2)
    if result.returncode:
        raise RuntimeError('cannot inspect compiler process-group memory')
    return sum(int(parts[1]) * 1024 for line in result.stdout.splitlines()
               if len(parts := line.split()) == 2 and int(parts[0]) == pgid)


def run_bounded(command, cwd, env, timeout=30, memory_limit_bytes=512 * 1024**2, process_group=True,
                log_name='process.log', limit_wrapper=None) -> ExecutionResult:
    started = time.monotonic()
    result = {'returncode': None, 'timed_out': False, 'memory_exceeded': False,
              'peak_group_rss_bytes': 0, 'memory_limit_bytes': memory_limit_bytes,
              'seconds': 0.0, 'reason': 'start_failed', 'process_tree_cleanup': 'not_started'}
    if timeout <= 0:
        return result | {'timed_out': True, 'reason': 'wall_timeout'}
    # The frozen fixture harness is already enclosed by an outer supervisor.
    # Every normal production/developer compile uses a fresh Python launcher.
    if process_group or limit_wrapper is not None:
        command = [sys.executable, str(limit_wrapper or LIMIT_WRAPPER), *command]
    with (Path(cwd) / log_name).open('wb') as output:
        try:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=process_group)
        except OSError as error:
            output.write(str(error).encode('utf-8', errors='replace'))
            result['seconds'] = round(time.monotonic() - started, 6)
            return result
        try:
            while process.poll() is None:
                if time.monotonic() - started >= timeout:
                    result.update(timed_out=True, reason='wall_timeout')
                    break
                if memory_limit_bytes is not None:
                    result['peak_group_rss_bytes'] = max(result['peak_group_rss_bytes'], group_rss_bytes(process.pid))
                    if result['peak_group_rss_bytes'] > memory_limit_bytes:
                        result.update(memory_exceeded=True, reason='memory_limit')
                        break
                time.sleep(0.05)
            if not (result['timed_out'] or result['memory_exceeded']):
                code = process.returncode
                reason = {0: 'success', -signal.SIGXCPU: 'cpu_limit', -signal.SIGXFSZ: 'file_limit'}.get(code, 'exit_error')
                result.update(returncode=code, reason=reason)
        finally:
            # Clean descendants even when the parent exited or supervision raised.
            try:
                if process_group:
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                result['process_tree_cleanup'] = 'signalled'
            except ProcessLookupError:
                result['process_tree_cleanup'] = 'already_exited'
            except OSError:
                result['process_tree_cleanup'] = 'failed'
                raise
            finally:
                process.wait()
    result['seconds'] = round(time.monotonic() - started, 6)
    return result
