"""Import gate, runnable on both hosts without TeX or native compiler execution.

Blocking macOS-only APIs on a Mac catches transitive imports, but is not native
Windows acceptance. Run this script again with Windows Python during stage D.
"""

import importlib
import importlib.abc
from pathlib import Path
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {'fcntl', 'resource', 'platform_adapters.macos',
             'experiments.m1.run', 'experiments.m1.runtime',
             'experiments.m1.build_runtime', 'experiments.m1.validate_managed',
             'experiments.m1.packaged_cli'}
MODULES = ('backend.compiler', 'backend.service', 'backend.store', 'backend.app', 'backend.__main__',
           'scripts.light_runtime', 'core.resume_checks', 'core.tex_checks', 'core.tex_pipeline',
           'platform_adapters.contracts', 'platform_adapters.detect', 'platform_adapters.windows',
           'core.managed_runtime', 'core.runtime_install', 'core.runtime_manifest', 'scripts.bootstrap',
           'scripts.install_windows_runtime')


class ImportGate(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in FORBIDDEN:
            raise ModuleNotFoundError('Forbidden platform/experiment dependency: ' + fullname, name=fullname)
        return None


def main():
    sys.path.insert(0, str(ROOT))
    # On macOS, importlib's own stdlib dependencies may preload these. Remove
    # cached modules so subsequent application imports cannot bypass the gate.
    for name in ('fcntl', 'resource'):
        sys.modules.pop(name, None)
    gate = ImportGate()
    sys.meta_path.insert(0, gate)
    original_read_text = Path.read_text

    def non_utf8_default(path, encoding=None, errors=None, **kwargs):
        return original_read_text(path, encoding=encoding or 'ascii', errors=errors, **kwargs)

    try:
        with patch.object(Path, 'read_text', non_utf8_default):
            for name in MODULES:
                importlib.import_module(name)
        leaked = FORBIDDEN.intersection(sys.modules)
        if leaked:
            raise RuntimeError('Unexpected modules: ' + ', '.join(sorted(leaked)))
    finally:
        sys.meta_path.remove(gate)
    print(f'PASS: {len(MODULES)} production/shared modules imported with a non-UTF-8 default and without macOS APIs or experiment runners.')


if __name__ == '__main__':
    main()
