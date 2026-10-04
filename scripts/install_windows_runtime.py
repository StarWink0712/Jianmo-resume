"""Install the pinned Windows runtime transactionally.

Native PDF fixtures pass before activation; failed/occupied upgrades preserve
current.json. Broader distribution approval is independent of local installation.
"""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.runtime_install import install_release
from core.runtime_manifest import digest, inventory, plain_path, verify_inventory


def runtime_identity():
    sources = [ROOT / 'runtime/locks/windows-x64.prototype.json', ROOT / 'runtime/tex.lock.json',
               ROOT / 'runtime/tex-support.tar.xz', ROOT / 'docs/m1/runtime-inputs.json',
               ROOT / 'scripts/probe_windows_engine.py', Path(__file__),
               ROOT / 'scripts/light_runtime.py', ROOT / 'scripts/check_contracts.py',
               ROOT / 'backend/examples.py', *sorted(ROOT.glob('requirements-*.txt')),
               *sorted((ROOT / 'core').glob('*.py')), *sorted((ROOT / 'platform_adapters').glob('*.py')),
               *sorted((ROOT / 'experiments/m1').glob('*.py')), ROOT / 'web/style-config.json',
               *sorted((ROOT / 'fixtures').rglob('*.json')), *sorted((ROOT / 'schemas').glob('*.json')),
               *sorted((ROOT / 'examples/resumes').glob('*.json'))]
    return hashlib.sha256(json.dumps([(p.relative_to(ROOT).as_posix(), digest(p)) for p in sources],
                                     separators=(',', ':')).encode()).hexdigest()


def verify(root, identity):
    root = plain_path(root)
    manifest = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
    if (manifest.get('schema') != 2 or manifest.get('platform') != 'windows-x64'
            or manifest.get('identity') != identity or manifest.get('status') != 'development-validated'):
        raise ValueError('Windows runtime manifest is not valid for this build.')
    verify_inventory(root, manifest['files'])
    lock = json.loads((ROOT / 'runtime/locks/windows-x64.prototype.json').read_text(encoding='utf-8'))
    for package in lock['packages']:
        for item in package['files']:
            if digest(root / item['target']) != item['sha256']:
                raise ValueError('Installed Windows engine differs from source lock.')
    report = json.loads((root / 'acceptance.json').read_text(encoding='utf-8'))
    from scripts.check_contracts import cases
    from core.resume_checks import case_passes
    fixtures = cases()
    if (not report.get('prototype_passed') or not all(report.get(kind, {}).get('ok') for kind in ('java', 'algorithm', 'testing'))
            or set(report.get('fixtures', {})) != {case['id'] for case in fixtures}
            or any(not case_passes(case, report['fixtures'][case['id']]) for case in fixtures)
            or not report.get('stages')
            or any(stage['reason'] != 'success' or not stage.get('loaded_images')
                   or stage['process_tree_cleanup'] != 'terminated_and_drained' for stage in report['stages'].values())):
        raise ValueError('Windows runtime lacks passing native fixture results.')
    from experiments.m1.fonts import verify_fonts
    verify_fonts(root / 'tex/fonts')
    return manifest


def install(prefix, cache, offline=False):
    from platform_adapters import windows_native as native
    from scripts.probe_windows_engine import run
    identity = runtime_identity()

    def verify_build(root):
        if runtime_identity() != identity:
            raise ValueError('Source changed during installation; repeat after edits are complete.')
        return verify(root, identity)

    def build(stage):
        with tempfile.TemporaryDirectory(prefix='.native-check-', dir=stage.parent) as temporary:
            output = Path(temporary)
            report = run(output, cache, offline)
            for path in (output / 'runtime').iterdir():
                path.rename(stage / path.name)
            (stage / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        native.private_tree(stage)
        manifest = {'schema': 2, 'platform': 'windows-x64', 'identity': identity,
                    'status': 'development-validated', 'files': inventory(stage)}
        (stage / 'runtime.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        native.private_file(stage / 'runtime.json')

    return install_release(prefix, identity, 'windows-x64', native, build, verify_build)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=ROOT / '.m1-build/windows-install')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / '.m1-build/engine-cache')
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    try:
        from platform_adapters.detect import platform_key
        if platform_key() != 'windows-x64':
            raise ValueError('Native Windows x64 is required.')
        root = install(args.prefix, args.cache_dir, args.offline)
    except (OSError, ValueError) as error:
        parser.exit(1, 'Windows runtime installation stopped: ' + str(error) + '\n')
    print('Verified Windows runtime: ' + str(root), flush=True)
    print('Start with scripts/bootstrap.py or python -m backend.', flush=True)


if __name__ == '__main__':
    main()
