"""Observe every executable/DLL load through Win32 debug events, including children.

Unlike module snapshots, load events include transient LoadLibrary calls. Policy
errors terminate the job before the suspended load event is continued. This is
additional enforcement inside AppContainer, not a replacement for its sandbox.
"""

import ctypes as C
from ctypes import wintypes as W
import hashlib
import os
from pathlib import Path
import time

from platform_adapters import windows_native as n


class ExceptionRecord(C.Structure):
    _fields_ = [('code', W.DWORD), ('flags', W.DWORD), ('record', n.P), ('address', n.P),
                ('count', W.DWORD), ('information', n.SIZE * 15)]


class ExceptionInfo(C.Structure):
    _fields_ = [('record', ExceptionRecord), ('first_chance', W.DWORD)]


class CreateInfo(C.Structure):
    _fields_ = [('file', W.HANDLE), ('process', W.HANDLE), ('thread', W.HANDLE), ('base', n.P),
                ('offset', W.DWORD), ('size', W.DWORD), ('tls', n.P), ('start', n.P),
                ('name', n.P), ('unicode', W.WORD)]


class LoadInfo(C.Structure):
    _fields_ = [('file', W.HANDLE), ('base', n.P), ('offset', W.DWORD), ('size', W.DWORD),
                ('name', n.P), ('unicode', W.WORD)]


class EventData(C.Union):
    _fields_ = [('exception', ExceptionInfo), ('create', CreateInfo), ('load', LoadInfo), ('exit_code', W.DWORD)]


class DebugEvent(C.Structure):
    _fields_ = [('code', W.DWORD), ('pid', W.DWORD), ('tid', W.DWORD), ('data', EventData)]


WaitEvent = n.api(n.kernel, 'WaitForDebugEvent', W.BOOL, C.POINTER(DebugEvent), W.DWORD)
ContinueEvent = n.api(n.kernel, 'ContinueDebugEvent', W.BOOL, W.DWORD, W.DWORD, W.DWORD)
DuplicateHandle = n.api(n.kernel, 'DuplicateHandle', W.BOOL, W.HANDLE, W.HANDLE, W.HANDLE,
                        C.POINTER(W.HANDLE), W.DWORD, W.BOOL, W.DWORD)


def image_path(handle):
    return n.path_from_handle(handle)


def image_hash(handle):
    import msvcrt
    duplicate = W.HANDLE()
    process = n.GetCurrentProcess()
    n.checked(DuplicateHandle(process, handle, process, C.byref(duplicate), 0, False, 2))
    try:
        fd = msvcrt.open_osfhandle(duplicate.value, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        n.CloseHandle(duplicate)
        raise
    with os.fdopen(fd, 'rb') as stream:
        stream.seek(0)
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class ImagePolicy:
    def __init__(self, pinned):
        """pinned maps actual local paths (not aliases) to approved SHA-256 values."""
        self.pinned = {os.path.normcase(str(n.local_path(path))): digest for path, digest in pinned.items()}
        self.locked_names = {Path(path).name.lower() for path in self.pinned}
        self.system = Path(n.system_directory())

    def verify(self, handle):
        if not handle:
            raise ValueError('Windows supplied no verifiable image handle')
        path = image_path(handle)
        key = os.path.normcase(str(path))
        digest = image_hash(handle)
        if key in self.pinned:
            if digest != self.pinned[key]:
                raise ValueError('Loaded image hash differs from lock: ' + path.name)
            return {'source': 'runtime', 'name': path.name.lower(), 'sha256': digest}
        if path.name.lower() not in self.locked_names and path.is_relative_to(self.system):
            return {'source': 'windows', 'name': path.relative_to(self.system).as_posix().lower(), 'sha256': digest}
        raise ValueError('Loaded image outside pinned runtime and Windows System32: ' + path.name)


class ImageAudit:
    def __init__(self, policy, job):
        self.policy, self.job = policy, job
        self.active = set()
        self.images = {}
        self.error = None

    def poll(self, timeout=25, terminating=False):
        event = DebugEvent()
        if not WaitEvent(C.byref(event), timeout):
            error = C.get_last_error()
            if error in (121, 258):
                return False
            raise C.WinError(error)
        status = 0x10002  # DBG_CONTINUE
        handle = None
        try:
            if event.code == 3:
                self.active.add(event.pid)
                handle = event.data.create.file
            elif event.code == 6:
                handle = event.data.load.file
            elif event.code == 5:
                self.active.discard(event.pid)
            elif event.code == 1:
                record = event.data.exception
                if record.record.code != 0x80000003 or not record.first_chance:
                    status = 0x80010001  # pass real exceptions to application/OS
            if event.code in (3, 6) and not terminating and not self.error:
                image = self.policy.verify(handle)
                self.images[(image['source'], image['name'], image['sha256'])] = image
        except (OSError, ValueError) as error:
            self.error = str(error)
            n.checked(n.TerminateJob(self.job, 1))
        finally:
            if handle:
                n.CloseHandle(handle)
            n.checked(ContinueEvent(event.pid, event.tid, status))
        return True

    def drain(self):
        deadline = time.monotonic() + 5
        while self.active:
            self.poll(25, terminating=True)
            if time.monotonic() >= deadline:
                raise OSError('Debugged process tree failed to terminate.')
