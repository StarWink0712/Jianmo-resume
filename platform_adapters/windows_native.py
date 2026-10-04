"""Native Windows primitives for the D2 acceptance harness.

Not imported by the production adapter until the complete native acceptance
gate passes. No shell, global TeX, or unsandboxed process fallback is provided.
"""

import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager, ExitStack
import os
from pathlib import Path
import stat
import subprocess
import time
import uuid

from platform_adapters.contracts import LockBusy

if os.name != 'nt':
    raise ImportError('windows_native requires Windows')

P = C.c_void_p
SIZE = C.c_size_t
kernel = C.WinDLL('kernel32', use_last_error=True)
advapi = C.WinDLL('advapi32', use_last_error=True)
userenv = C.WinDLL('userenv', use_last_error=True)


def api(dll, name, result, *arguments):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = result, arguments
    return fn


class SecurityAttributes(C.Structure):
    _fields_ = [('length', W.DWORD), ('descriptor', P), ('inherit', W.BOOL)]


class StartupInfo(C.Structure):
    _fields_ = [('cb', W.DWORD), ('reserved', W.LPWSTR), ('desktop', W.LPWSTR),
                ('title', W.LPWSTR), ('x', W.DWORD), ('y', W.DWORD),
                ('width', W.DWORD), ('height', W.DWORD), ('chars_x', W.DWORD),
                ('chars_y', W.DWORD), ('fill', W.DWORD), ('flags', W.DWORD),
                ('show', W.WORD), ('reserved_size', W.WORD), ('reserved2', P),
                ('stdin', W.HANDLE), ('stdout', W.HANDLE), ('stderr', W.HANDLE)]


class StartupInfoEx(C.Structure):
    _fields_ = [('startup', StartupInfo), ('attributes', P)]


class ProcessInfo(C.Structure):
    _fields_ = [('process', W.HANDLE), ('thread', W.HANDLE),
                ('pid', W.DWORD), ('tid', W.DWORD)]


class SecurityCapabilities(C.Structure):
    _fields_ = [('sid', P), ('capabilities', P), ('count', W.DWORD), ('reserved', W.DWORD)]


class BasicLimits(C.Structure):
    _fields_ = [('process_time', C.c_longlong), ('job_time', C.c_longlong),
                ('flags', W.DWORD), ('min_working', SIZE), ('max_working', SIZE),
                ('active_processes', W.DWORD), ('affinity', SIZE),
                ('priority', W.DWORD), ('scheduling', W.DWORD)]


class IoCounters(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in
                ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class ExtendedLimits(C.Structure):
    _fields_ = [('basic', BasicLimits), ('io', IoCounters), ('process_memory', SIZE),
                ('job_memory', SIZE), ('peak_process', SIZE), ('peak_job', SIZE)]


class Accounting(C.Structure):
    _fields_ = [(name, C.c_longlong) for name in ('user', 'kernel', 'period_user', 'period_kernel')]
    _fields_ += [(name, W.DWORD) for name in ('faults', 'total', 'active', 'terminated')]


class FileInfo(C.Structure):
    _fields_ = [('attributes', W.DWORD), ('created', W.FILETIME), ('accessed', W.FILETIME),
                ('written', W.FILETIME), ('volume', W.DWORD), ('size_high', W.DWORD),
                ('size_low', W.DWORD), ('links', W.DWORD), ('index_high', W.DWORD), ('index_low', W.DWORD)]


class StandardFileInfo(C.Structure):
    _fields_ = [('allocated', C.c_longlong), ('size', C.c_longlong), ('links', W.DWORD),
                ('deleted', C.c_ubyte), ('directory', C.c_ubyte)]


CloseHandle = api(kernel, 'CloseHandle', W.BOOL, W.HANDLE)
LocalFree = api(kernel, 'LocalFree', P, P)
CreateFile = api(kernel, 'CreateFileW', W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD,
                 C.POINTER(SecurityAttributes), W.DWORD, W.DWORD, W.HANDLE)
CreateDirectory = api(kernel, 'CreateDirectoryW', W.BOOL, W.LPCWSTR, C.POINTER(SecurityAttributes))
ConvertSD = api(advapi, 'ConvertStringSecurityDescriptorToSecurityDescriptorW', W.BOOL,
                W.LPCWSTR, W.DWORD, C.POINTER(P), C.POINTER(W.DWORD))
SetFileSecurity = api(advapi, 'SetFileSecurityW', W.BOOL, W.LPCWSTR, W.DWORD, P)
GetFileSecurity = api(advapi, 'GetFileSecurityW', W.BOOL, W.LPCWSTR, W.DWORD, P, W.DWORD, C.POINTER(W.DWORD))
ConvertSDText = api(advapi, 'ConvertSecurityDescriptorToStringSecurityDescriptorW', W.BOOL,
                    P, W.DWORD, W.DWORD, C.POINTER(P), C.POINTER(W.DWORD))
OpenProcessToken = api(advapi, 'OpenProcessToken', W.BOOL, W.HANDLE, W.DWORD, C.POINTER(W.HANDLE))
GetTokenInformation = api(advapi, 'GetTokenInformation', W.BOOL, W.HANDLE, W.DWORD, P, W.DWORD, C.POINTER(W.DWORD))
ConvertSidText = api(advapi, 'ConvertSidToStringSidW', W.BOOL, P, C.POINTER(P))
GetCurrentProcess = api(kernel, 'GetCurrentProcess', W.HANDLE)
CreateProfile = api(userenv, 'CreateAppContainerProfile', C.c_long, W.LPCWSTR, W.LPCWSTR, W.LPCWSTR, P, W.DWORD, C.POINTER(P))
DeleteProfile = api(userenv, 'DeleteAppContainerProfile', C.c_long, W.LPCWSTR)
FreeSid = api(advapi, 'FreeSid', P, P)
CreateJob = api(kernel, 'CreateJobObjectW', W.HANDLE, P, W.LPCWSTR)
SetJob = api(kernel, 'SetInformationJobObject', W.BOOL, W.HANDLE, C.c_int, P, W.DWORD)
QueryJob = api(kernel, 'QueryInformationJobObject', W.BOOL, W.HANDLE, C.c_int, P, W.DWORD, P)
AssignJob = api(kernel, 'AssignProcessToJobObject', W.BOOL, W.HANDLE, W.HANDLE)
TerminateJob = api(kernel, 'TerminateJobObject', W.BOOL, W.HANDLE, W.UINT)
InitializeAttributes = api(kernel, 'InitializeProcThreadAttributeList', W.BOOL, P, W.DWORD, W.DWORD, C.POINTER(SIZE))
UpdateAttribute = api(kernel, 'UpdateProcThreadAttribute', W.BOOL, P, W.DWORD, SIZE, P, SIZE, P, P)
DeleteAttributes = api(kernel, 'DeleteProcThreadAttributeList', None, P)
CreateProcess = api(kernel, 'CreateProcessW', W.BOOL, W.LPCWSTR, W.LPWSTR, P, P, W.BOOL,
                    W.DWORD, P, W.LPCWSTR, C.POINTER(StartupInfoEx), C.POINTER(ProcessInfo))
ResumeThread = api(kernel, 'ResumeThread', W.DWORD, W.HANDLE)
Wait = api(kernel, 'WaitForSingleObject', W.DWORD, W.HANDLE, W.DWORD)
ExitCode = api(kernel, 'GetExitCodeProcess', W.BOOL, W.HANDLE, C.POINTER(W.DWORD))
TerminateProcess = api(kernel, 'TerminateProcess', W.BOOL, W.HANDLE, W.UINT)
GetFileInfo = api(kernel, 'GetFileInformationByHandle', W.BOOL, W.HANDLE, C.POINTER(FileInfo))
GetFileInfoEx = api(kernel, 'GetFileInformationByHandleEx', W.BOOL, W.HANDLE, C.c_int, P, W.DWORD)
SetHandleSecurity = api(advapi, 'SetKernelObjectSecurity', W.BOOL, W.HANDLE, W.DWORD, P)
FinalPath = api(kernel, 'GetFinalPathNameByHandleW', W.DWORD, W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD)


def checked(value):
    if not value:
        raise C.WinError(C.get_last_error())
    return value


def sid_text(sid):
    result = P()
    checked(ConvertSidText(sid, C.byref(result)))
    try:
        return C.wstring_at(result)
    finally:
        LocalFree(result)


def current_user_sid():
    token, size = W.HANDLE(), W.DWORD()
    checked(OpenProcessToken(GetCurrentProcess(), 8, C.byref(token)))
    try:
        GetTokenInformation(token, 1, None, 0, C.byref(size))
        data = C.create_string_buffer(size.value)
        checked(GetTokenInformation(token, 1, data, size, C.byref(size)))
        return sid_text(C.cast(data, C.POINTER(P))[0])
    finally:
        CloseHandle(token)


@contextmanager
def descriptor(sddl):
    result = P()
    checked(ConvertSD(sddl, 1, C.byref(result), None))
    try:
        yield result
    finally:
        LocalFree(result)


def local_path(path):
    """Reject reparse points before resolution; never follow a junction to an ACL target."""
    path = Path(os.path.abspath(path))
    if str(path).startswith('\\\\'):
        raise ValueError('Only local drive paths are supported.')
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError('Reparse points are not allowed: ' + str(part))
    return path


def private_sddl(directory=True, container=None, writable=False):
    inherit = 'OICI' if directory else ''
    sddl = f'D:P(A;{inherit};FA;;;{current_user_sid()})(A;{inherit};FA;;;SY)'
    if container:
        # Modify permits deletion, but never WRITE_DAC or WRITE_OWNER.
        rights = '0x1301bf' if writable else 'FRFX'
        sddl += f'(A;{inherit};{rights};;;{container})'
    return sddl


def set_private_acl(path, *, container=None, writable=False):
    with hold_path(path, access=0x60080) as (handle, info):
        with descriptor(private_sddl(bool(info.attributes & 0x10), container, writable)) as sd:
            # Handle-based update: never follow a swapped final path. Existing
            # children are explicitly migrated by grant_tree/private_tree.
            checked(SetHandleSecurity(handle, 0x80000004, sd))


def private_file(path):
    set_private_acl(path)


def path_from_handle(handle):
    buffer = C.create_unicode_buffer(32768)
    size = checked(FinalPath(handle, buffer, len(buffer), 0))
    if size >= len(buffer) or not buffer.value.startswith('\\\\?\\'):
        raise ValueError('Unresolvable local file path')
    path = buffer.value[4:]
    if path.startswith('UNC\\'):
        raise ValueError('Network files are not supported.')
    return Path(path)


def checked_file(handle):
    info = FileInfo()
    checked(GetFileInfo(handle, C.byref(info)))
    if info.attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT or info.links > 1:
        raise ValueError('Reparse points and multiply linked files are not allowed.')
    return info


@contextmanager
def hold_path(path, access=0x80, *, share=3):
    """Pin every existing ancestor against replacement; inspect the final handle."""
    path = local_path(path)
    with ExitStack() as held:
        for part in (*reversed(path.parents), path):
            handle = CreateFile(str(part), access if part == path else 0x80, share, None, 3, 0x02200000, None)
            if handle == P(-1).value:
                raise C.WinError(C.get_last_error())
            held.callback(CloseHandle, handle)
            info = checked_file(handle)
        yield handle, info


def plain_tree(root, *, missing_ok=False):
    """Do not recurse into a junction before inspecting it (Path.rglob can)."""
    root = local_path(root)
    yield root
    pending = [root]
    while pending:
        directory = pending.pop()
        with ExitStack() as held:
            try:
                handle, info = held.enter_context(hold_path(directory))
            except FileNotFoundError:
                if missing_ok and directory != root:
                    continue
                raise
            # The open directory cannot be replaced while it is enumerated.
            directory = path_from_handle(handle)
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        if missing_ok:
                            continue
                        raise
                    if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT or info.st_nlink > 1:
                        raise ValueError('Reparse points and multiply linked files are not allowed.')
                    path = Path(entry.path)
                    yield path
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(path)


def output_size(root):
    """Read directory metadata without blocking compiler temporary-file deletion.

    This is sampled usage, never an atomic snapshot or a hard disk quota. ACL
    mutations use the stricter plain_tree/hold_path functions instead.
    """
    root = local_path(root)
    total, pending = 0, [root]
    while pending:
        path = pending.pop()
        try:
            with hold_path(path, share=7) as (handle, _):
                info = StandardFileInfo()
                checked(GetFileInfoEx(handle, 1, C.byref(info), C.sizeof(info)))
                if info.deleted:
                    continue
                physical = path_from_handle(handle)
                if not physical.is_relative_to(root):
                    # Deleted directories can move into NTFS's $Extend/$Deleted
                    # between the two queries. Verify that state explicitly.
                    checked(GetFileInfoEx(handle, 1, C.byref(info), C.sizeof(info)))
                    if info.deleted:
                        continue
                    raise ValueError('Output path escaped the job root.')
                if info.directory:
                    with os.scandir(path) as entries:
                        pending.extend(Path(entry.path) for entry in entries)
                else:
                    # FindFirstFile/scandir sizes can stay stale while a writer
                    # keeps the file open; query the actual file handle instead.
                    total += info.size
        except FileNotFoundError:
            if path == root:
                raise
    return total


def private_tree(root):
    grant_tree(root, None)


def private_directory(path, exist_ok=True):
    path = local_path(path)
    if not path.parent.exists():
        private_directory(path.parent)
    with descriptor(private_sddl()) as sd:
        attributes = SecurityAttributes(C.sizeof(SecurityAttributes), sd, False)
        if not CreateDirectory(str(path), C.byref(attributes)):
            error = C.get_last_error()
            if error != 183 or not exist_ok or not path.is_dir():
                raise C.WinError(error)
            set_private_acl(path)


def security_text(path):
    size, result = W.DWORD(), P()
    GetFileSecurity(str(path), 4, None, 0, C.byref(size))
    buffer = C.create_string_buffer(size.value)
    checked(GetFileSecurity(str(path), 4, buffer, size, C.byref(size)))
    checked(ConvertSDText(buffer, 1, 4, C.byref(result), None))
    try:
        return C.wstring_at(result)
    finally:
        LocalFree(result)


class Lease:
    def __init__(self, handle):
        self.handle = handle

    def close(self):
        if self.handle is not None:
            checked(CloseHandle(self.handle))
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def acquire_lock(directory, name):
    reserved = {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$',
                *(f'{prefix}{n}' for prefix in ('COM', 'LPT') for n in '123456789¹²³')}
    if (not name or name in ('.', '..') or any(c in name for c in '/\\:<>"|?*')
            or any(ord(c) < 32 for c in name) or name[-1:] in (' ', '.')
            or name.split('.')[0].upper() in reserved):
        raise ValueError('Lock name must be a plain filename.')
    path = local_path(Path(directory) / name)
    with descriptor(private_sddl(False)) as sd:
        attributes = SecurityAttributes(C.sizeof(SecurityAttributes), sd, False)
        handle = CreateFile(str(path), 0xC0000000, 0, C.byref(attributes), 4, 0x00200080, None)
    if handle == P(-1).value:
        error = C.get_last_error()
        if error in (32, 33):
            raise LockBusy('Another process holds this directory lease.')
        raise C.WinError(error)
    try:
        checked_file(handle)
    except BaseException:
        CloseHandle(handle)
        raise
    return Lease(handle)


@contextmanager
def app_container():
    """Unique identity per task: no shared container access to another task's files."""
    name, sid = 'Jianmo.Probe.' + uuid.uuid4().hex, P()
    status = CreateProfile(name, name, 'Jianmo isolated compiler', None, 0, C.byref(sid))
    if status < 0:
        raise OSError(f'CreateAppContainerProfile failed: 0x{status & 0xffffffff:08x}')
    try:
        yield sid, sid_text(sid)
    finally:
        FreeSid(sid)
        status = DeleteProfile(name)
        if status < 0:
            raise OSError(f'DeleteAppContainerProfile failed: 0x{status & 0xffffffff:08x}')


def grant_tree(root, container, writable=False):
    """Only for dedicated private staging trees; never grant access to user directories."""
    root = local_path(root)
    paths = list(plain_tree(root))
    for path in paths:
        set_private_acl(path, container=container, writable=writable)


def system_directory():
    get = api(kernel, 'GetSystemDirectoryW', W.UINT, W.LPWSTR, W.UINT)
    buffer = C.create_unicode_buffer(32768)
    size = checked(get(buffer, len(buffer)))
    if size >= len(buffer):
        raise ValueError('System directory is too long.')
    return buffer.value


def environment(job, engine):
    system = str(Path(system_directory()).parent)
    return {'SystemRoot': system, 'WINDIR': system,
            'LOCALAPPDATA': os.environ['LOCALAPPDATA'],
            'PATH': str(Path(engine).parent) + os.pathsep + str(Path(system) / 'System32'),
            'TEMP': str(job), 'TMP': str(job), 'HOME': str(job), 'USERPROFILE': str(job)}


def run_in_container(command, cwd, env, sid, *, timeout=30, memory_limit_bytes=512 * 1024**2,
                     cpu_seconds=30, output_limit_bytes=64 * 1024**2, log_name='process.log', cancel=None,
                     image_policy=None):
    """Create suspended -> assign Job -> resume. Every exit path kills and drains the Job.

    Memory uses Windows Job commit accounting (not RSS). Output is sampled across
    the job tree. Caller must grant only this task and its dedicated runtime to sid.
    """
    started = time.monotonic()
    result = dict(returncode=None, timed_out=False, memory_exceeded=False, peak_job_memory_bytes=0,
                  memory_limit_bytes=memory_limit_bytes, cpu_seconds=0.0, seconds=0.0, reason='start_failed',
                  process_tree_cleanup='not_started')
    if timeout <= 0:
        return result | dict(timed_out=True, reason='wall_timeout')
    cwd = local_path(cwd)
    if not command or not Path(command[0]).is_absolute() or not sid:
        raise ValueError('An absolute executable and AppContainer SID are mandatory.')
    if Path(log_name).name != log_name or ':' in log_name:
        raise ValueError('Log name must be a filename.')
    job = checked(CreateJob(None, None))
    info, attribute_list, handles = ProcessInfo(), None, []
    attributes_ready = False
    audit = None
    if image_policy is not None:
        from platform_adapters.windows_images import ImageAudit
        audit = ImageAudit(image_policy, job)
    try:
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000 | 0x200 | 0x4 | 0x8  # kill-on-close, job memory, job time, process count
        limits.basic.job_time = int(cpu_seconds * 10_000_000)
        limits.basic.active_processes = 8
        limits.job_memory = memory_limit_bytes
        checked(SetJob(job, 9, C.byref(limits), C.sizeof(limits)))
        sa = SecurityAttributes(C.sizeof(SecurityAttributes), None, True)
        for path, access, disposition in [(str(cwd / log_name), 0x40000000, 2), ('NUL', 0x80000000, 3)]:
            handle = CreateFile(path, access, 3, C.byref(sa), disposition, 0x80, None)
            if handle == P(-1).value:
                raise C.WinError(C.get_last_error())
            handles.append(handle)
        size = SIZE()
        InitializeAttributes(None, 3, 0, C.byref(size))
        attribute_list = C.create_string_buffer(size.value)
        checked(InitializeAttributes(attribute_list, 3, 0, C.byref(size)))
        attributes_ready = True
        capabilities = SecurityCapabilities(sid, None, 0, 0)
        checked(UpdateAttribute(attribute_list, 0, 0x20009, C.byref(capabilities), C.sizeof(capabilities), None, None))
        inherited = (W.HANDLE * len(handles))(*handles)
        checked(UpdateAttribute(attribute_list, 0, 0x20002, inherited, C.sizeof(inherited), None, None))
        # Disable extension-point injection and remote image loads. Keep the
        # application-directory search order so pinned CRTs cannot be replaced
        # by a machine-global version; audit every actual loaded image below.
        mitigation = C.c_ulonglong((1 << 32) | (1 << 52))
        checked(UpdateAttribute(attribute_list, 0, 0x20007, C.byref(mitigation), C.sizeof(mitigation), None, None))
        startup = StartupInfoEx()
        startup.startup.cb = C.sizeof(startup)
        startup.startup.flags = 0x100
        startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = handles[1], handles[0], handles[0]
        startup.attributes = C.cast(attribute_list, P)
        block = C.create_unicode_buffer('\0'.join(f'{key}={value}' for key, value in sorted(env.items(), key=lambda item: item[0].upper())) + '\0\0')
        cmdline = C.create_unicode_buffer(subprocess.list2cmdline([str(arg) for arg in command]))
        checked(CreateProcess(str(command[0]), cmdline, None, None, True, 0x08080404 | (1 if audit else 0),
                              block, str(cwd), C.byref(startup), C.byref(info)))
        # Assignment failure must never resume the suspended child.
        checked(AssignJob(job, info.process))
        if ResumeThread(info.thread) == 0xffffffff:
            raise C.WinError(C.get_last_error())
        busy_samples = 0
        while True:
            if audit:
                audit.poll(25)
                if audit.error:
                    result.update(reason='image_policy', image_error=audit.error)
                    break
            waited = Wait(info.process, 0 if audit else 25)
            if waited == 0xffffffff:
                raise C.WinError(C.get_last_error())
            checked(QueryJob(job, 9, C.byref(limits), C.sizeof(limits), None))
            result['peak_job_memory_bytes'] = max(result['peak_job_memory_bytes'], limits.peak_job)
            accounting = Accounting()
            checked(QueryJob(job, 1, C.byref(accounting), C.sizeof(accounting), None))
            result['cpu_seconds'] = (accounting.user + accounting.kernel) / 10_000_000
            # Windows' job-time termination can be coarse. Sample aggregate CPU
            # as well, preserving the OS limit if the supervisor stops running.
            if result['cpu_seconds'] >= cpu_seconds:
                result['reason'] = 'cpu_limit'
                break
            try:
                size = output_size(cwd)
                busy_samples = 0
            except OSError as error:
                # Windows reports delete-pending files as ACCESS_DENIED. Retry
                # at most three consecutive samples, preserving all time/CPU
                # checks. Persistent unreadable output must fail closed.
                if error.winerror not in (5, 32, 303) or busy_samples >= 3:
                    raise
                busy_samples += 1
                size = 0
                if waited == 0:
                    raise
            if size > output_limit_bytes:
                result['reason'] = 'file_limit'
                break
            if waited == 0:
                code = W.DWORD()
                checked(ExitCode(info.process, C.byref(code)))
                result.update(returncode=code.value, reason='success' if code.value == 0 else 'exit_error')
                break
            if cancel is not None and cancel.is_set():
                result['reason'] = 'cancelled'
                break
            if time.monotonic() - started >= timeout:
                result.update(timed_out=True, reason='wall_timeout')
                break
    finally:
        try:
            if info.process:
                # Also handles failure before assignment.
                TerminateProcess(info.process, 1)
                checked(TerminateJob(job, 1))
                if audit:
                    # Consume the initial event even when Job assignment failed.
                    while audit.poll(0, terminating=True):
                        pass
                    audit.drain()
                if Wait(info.process, 5000) != 0:
                    raise OSError('Compiler process failed to terminate.')
                accounting = Accounting()
                deadline = time.monotonic() + 5
                while True:
                    checked(QueryJob(job, 1, C.byref(accounting), C.sizeof(accounting), None))
                    if not accounting.active:
                        break
                    if time.monotonic() >= deadline:
                        raise OSError('Compiler descendants failed to terminate.')
                    time.sleep(.01)
                result['process_tree_cleanup'] = 'terminated_and_drained'
        finally:
            for handle in (info.thread, info.process, *handles, job):
                if handle:
                    CloseHandle(handle)
            if attributes_ready:
                DeleteAttributes(attribute_list)
    result['seconds'] = round(time.monotonic() - started, 6)
    if audit:
        result['loaded_images'] = sorted(audit.images.values(), key=lambda item: (item['source'], item['name']))
    return result
