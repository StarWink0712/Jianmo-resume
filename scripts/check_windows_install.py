"""Exercise native offline installation, reuse and compilation after relocation."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=ROOT / '.m1-build/windows-install')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    from scripts.install_windows_runtime import install, runtime_identity, verify
    from scripts.probe_windows_engine import run
    from core.runtime_install import current_release
    from platform_adapters.windows_paths import runtime_alias
    from platform_adapters import windows_native as native
    parent = ROOT / '.m1-build'
    parent.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='windows-install-check-', dir=parent))
    cache = parent / 'engine-cache'
    report = {'schema': 1, 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'application_ready': False, 'passed': False, 'offline': args.offline}
    print('Installation report directory: ' + str(output), flush=True)
    try:
        identity = runtime_identity()
        release = install(args.prefix, cache, args.offline)
        manifest = verify(release, identity)
        if current_release(args.prefix, 'windows-x64') != release:
            raise ValueError('Active record did not select the verified release.')
        report['identity'] = identity
        report['inventory_files'] = len(manifest['files'])
        report['inventory_bytes'] = sum(item['bytes'] for item in manifest['files'])
        report['installed'] = True
        (output / 'build-acceptance.json').write_bytes((release / 'acceptance.json').read_bytes())
        before = (release / 'tex/formats/xelatex.fmt').stat().st_mtime_ns
        with patch('scripts.probe_windows_engine.run', side_effect=AssertionError('Unnecessary rebuild')):
            reused = install(args.prefix, cache, True)
        if reused != release or before != (release / 'tex/formats/xelatex.fmt').stat().st_mtime_ns:
            raise ValueError('Offline reuse changed the installed runtime.')
        report['offline_reuse_without_rebuild'] = True
        print('PASS installed manifest and offline reuse', flush=True)
        # Occupy the preferred free letter with an unrelated private directory.
        # Compilation must use a different alias than the fresh build did.
        occupied = output / 'occupied'
        native.private_directory(occupied)
        relocated_output = output / 'relocated'
        native.private_directory(relocated_output)
        with runtime_alias(occupied) as other:
            relocated = run(relocated_output, cache, True, installed_runtime=release)
            if relocated['runtime_alias_drive'] == str(other):
                raise ValueError('Runtime alias overwrote an occupied drive.')
        verify(release, identity)
        report['relocated_compile'] = relocated['prototype_passed']
        report['runtime_unchanged_after_compile'] = True
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        print('FAIL installation acceptance: ' + str(error), flush=True)
    finally:
        (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('Report: ' + str(output / 'summary.json'), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
