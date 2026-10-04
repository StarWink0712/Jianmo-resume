"""Platform identification is safe to import, including on unsupported hosts."""

import importlib
import platform
import struct

from platform_adapters.contracts import PlatformUnavailable


def platform_key(system=None, machine=None, bits=None):
    system = platform.system() if system is None else system
    machine = (platform.machine() if machine is None else machine).lower()
    bits = struct.calcsize('P') * 8 if bits is None else bits
    if bits == 64 and system == 'Darwin' and machine == 'arm64':
        return 'darwin-arm64'
    if bits == 64 and system == 'Windows' and machine in ('amd64', 'x86_64'):
        return 'windows-x64'
    raise PlatformUnavailable(f'Unsupported platform: {system}/{machine}/{bits}-bit. Targets: macOS Apple Silicon and Windows x64 (not yet enabled).')


def get_adapter():
    key = platform_key()
    return importlib.import_module('platform_adapters.' + {'darwin-arm64': 'macos', 'windows-x64': 'windows'}[key])
