"""Handle-owned drive aliases; no permanent links or recovery journal.

The alias is an NT object-manager symbolic link, not a filesystem reparse point.
Creation is atomic and fails on collision. Its non-inherited handle owns its
lifetime, including supervisor crashes. Lack of native API support fails closed.
"""

from contextlib import contextmanager
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path

from platform_adapters import windows_native as native


class UnicodeString(C.Structure):
    _fields_ = [('length', W.USHORT), ('maximum_length', W.USHORT), ('buffer', W.LPWSTR)]


class ObjectAttributes(C.Structure):
    _fields_ = [('length', W.ULONG), ('root', W.HANDLE), ('name', C.POINTER(UnicodeString)),
                ('flags', W.ULONG), ('security', native.P), ('qos', native.P)]


ntdll = C.WinDLL('ntdll')
CreateSymbolicLink = native.api(ntdll, 'NtCreateSymbolicLinkObject', C.c_long,
    C.POINTER(W.HANDLE), W.DWORD, C.POINTER(ObjectAttributes), C.POINTER(UnicodeString))
StatusToError = native.api(ntdll, 'RtlNtStatusToDosError', W.ULONG, C.c_long)
QueryDevice = native.api(native.kernel, 'QueryDosDeviceW', W.DWORD, W.LPCWSTR, W.LPWSTR, W.DWORD)


def unicode_string(text):
    buffer = C.create_unicode_buffer(text)
    size = len(text.encode('utf-16-le'))
    if size > 65532:
        raise ValueError('Native alias target is too long.')
    return UnicodeString(size, size + 2, C.cast(buffer, W.LPWSTR)), buffer


@contextmanager
def runtime_alias(root):
    root = native.local_path(root)
    if not root.is_dir():
        raise ValueError('Alias target must be an existing local directory.')
    target, target_buffer = unicode_string('\\??\\' + str(root))
    handle = W.HANDLE()
    query_buffer = C.create_unicode_buffer(32768)
    # Neither OBJ_PERMANENT nor OBJ_OPENIF nor OBJ_INHERIT is set. A collision
    # cannot replace an existing object, and children cannot keep the link alive.
    with native.descriptor(native.private_sddl(False)) as security:
        for letter in 'ZYXWVUTSRQPONMLKJIHGFED':
            name = letter + ':'
            # Also respect global volume letters. Atomic creation below handles
            # local namespace races after this read; never open or replace a link.
            if QueryDevice(name, query_buffer, len(query_buffer)):
                continue
            if C.get_last_error() != 2:
                raise C.WinError(C.get_last_error())
            object_name, name_buffer = unicode_string('\\??\\' + name)
            attributes = ObjectAttributes(C.sizeof(ObjectAttributes), None, C.pointer(object_name), 0x40, security, None)
            status = CreateSymbolicLink(C.byref(handle), 0xF0001, C.byref(attributes), C.byref(target))
            if status & 0xffffffff != 0xc0000035:  # STATUS_OBJECT_NAME_COLLISION
                break
        else:
            raise ValueError('No free drive name for the private runtime alias.')
    if status < 0:
        raise C.WinError(StatusToError(status))
    try:
        yield Path(name + '\\')
    finally:
        native.checked(native.CloseHandle(handle))
