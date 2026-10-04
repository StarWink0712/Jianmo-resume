"""Platform-specific runtime validation, with no eager native imports."""

from pathlib import Path

from core.runtime_manifest import digest, plain_path
from platform_adapters.detect import platform_key


def verify_runtime(root):
    if platform_key() == 'windows-x64':
        from scripts.install_windows_runtime import runtime_identity, verify
        return verify(plain_path(root), runtime_identity())
    from experiments.m1.managed import verify
    return verify(root)


def compiler_manifest(root):
    if platform_key() == 'windows-x64':
        root = plain_path(root)
        return {'platform': 'windows-x64', 'runtime_root': str(root), 'tex_root': str(root / 'tex'),
                'engine': str(root / 'tex/bin/xelatex.exe'), 'driver': str(root / 'tex/bin/xdvipdfmx.exe'),
                'fonts_root': str(root / 'tex/fonts'), 'isolated': True}
    from experiments.m1.managed import compiler_manifest as macos_manifest
    return macos_manifest(root)


def default_runtime():
    root = Path(__file__).resolve().parents[1]
    if platform_key() == 'windows-x64':
        from core.runtime_install import current_release
        return current_release(root / '.m1-build/windows-install', 'windows-x64')
    return root / '.m1-build/local-install/current'
