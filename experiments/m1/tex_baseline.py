"""Reviewable source pins; generated host formats are deliberately not source pins."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil

from experiments.m1.fonts import verify_fonts
from experiments.m1.managed import digest
from platform_adapters.detect import platform_key
from scripts.check_contracts import ROOT, json_bytes


BASELINE = ROOT / 'docs/m1'
ISOLATION_CHECKS = {'file-read-denied', 'file-read-allowed-control', 'file-write-outside-denied',
                    'file-write-inside-allowed', 'shell-escape-disabled', 'network-allowed-control', 'network-denied'}
TIMEOUT_CHECKS = {'engine_timeout', 'next_compile_succeeds', 'process_group_timeout', 'child_not_running'}
EXTRA_TEX_FILES = (
    'texmf-dist/fonts/opentype/public/lm/lmroman10-regular.otf',
    'texmf-dist/fonts/opentype/public/lm/lmroman10-bold.otf',
    'texmf-dist/fonts/opentype/public/lm/lmroman10-italic.otf',
    'texmf-dist/fonts/opentype/public/lm/lmroman10-bolditalic.otf',
    'texmf-dist/fonts/misc/xetex/fontmapping/base/tex-text.tec',
    'texmf-dist/web2c/texmf.cnf', 'LICENSE.TL', 'LICENSE.CTAN',
    'texmf-dist/doc/fonts/lm/GUST-FONT-LICENSE.TXT',
    'texmf-dist/doc/fonts/lm/MANIFEST-Latin-Modern.TXT',
    'texmf-dist/doc/fonts/lm/README-Latin-Modern.TXT',
)


def implementation_hash():
    paths = [*sorted((ROOT / 'experiments/m1').glob('*.py')),
             *sorted((ROOT / 'core').rglob('*.py')),
             *sorted((ROOT / 'platform_adapters').rglob('*.py')),
             *sorted((ROOT / 'backend').glob('*.py')),
             ROOT / 'scripts/check_contracts.py', ROOT / 'scripts/light_runtime.py',
             ROOT / 'scripts/build_light_runtime.py', ROOT / 'web/style-config.json',
             *sorted((ROOT / 'fixtures').rglob('*.json')), *sorted((ROOT / 'schemas').glob('*.json'))]
    return hashlib.sha256(json_bytes([{p.relative_to(ROOT).as_posix(): digest(p)} for p in paths])).hexdigest()


def collect_inputs(runtime, observed):
    root = Path(runtime['tex_root'])
    paths = {item['path'] for item in observed}
    paths.update(EXTRA_TEX_FILES)
    paths.add(runtime['cmap']['source'])
    engine = Path(runtime['engine']).resolve()
    paths.update(p.relative_to(root).as_posix() for p in (engine, engine.parent / 'xdvipdfmx'))
    inputs = [{'path': name, 'bytes': (root / name).stat().st_size, 'sha256': digest(root / name)} for name in sorted(paths)]
    return {'schema': 2, 'engine_version': runtime['engine_version'], 'tex_inputs': inputs,
            'format_inputs': runtime['format_inputs'], 'fonts': runtime['fonts'], 'cmap': runtime['cmap'],
            'format_policy': 'Generate xelatex.fmt locally from pinned format_inputs; never copy a host .fmt.',
            'warning': 'Source inventory plus verified package closure; not a complete redistribution/SBOM audit.'}


def all_inputs(seed):
    result = {}
    for item in [*seed['tex_inputs'], *seed.get('format_inputs', [])]:
        name = item['path']
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or path.as_posix() != name or path.suffix == '.fmt':
            raise ValueError('Invalid source baseline path: ' + name)
        if name in result and result[name] != item:
            raise ValueError('Conflicting source pins: ' + name)
        result[name] = item
    return result


def verify_sources(seed, tex_root):
    if seed.get('schema') != 2:
        raise ValueError('Legacy machine-specific TeX baseline; use the documented baseline update workflow.')
    root = Path(tex_root).resolve()
    mismatches = []
    for name, item in all_inputs(seed).items():
        path = (root / name).resolve()
        if (not path.is_relative_to(root) or not path.is_file() or
                path.stat().st_size != item['bytes'] or digest(path) != item['sha256']):
            mismatches.append(name)
    if mismatches:
        raise ValueError('TeX source baseline mismatch (not a host .fmt): ' + ', '.join(mismatches[:6]) +
                         '. See docs/m1/tex-baseline-update.md; do not edit individual hashes.')
    verify_fonts(ROOT / 'assets/fonts')


def verify_evidence(directory):
    from core.resume_checks import benchmark_passes, case_passes
    from scripts.check_contracts import cases
    directory = Path(directory)
    seed = json.loads((directory / 'runtime-inputs.json').read_text(encoding='utf-8'))
    report = json.loads((directory / 'results.json').read_text(encoding='utf-8'))
    proof = json.loads((directory / 'baseline-evidence.json').read_text(encoding='utf-8'))
    if (proof['inputs_sha256'] != digest(directory / 'runtime-inputs.json') or
            proof['results_sha256'] != digest(directory / 'results.json') or
            proof['implementation_sha256'] != implementation_hash()):
        raise ValueError('Baseline evidence is stale or modified; rerun the complete M1 experiment.')
    if (proof.get('platform_key') != platform_key() or report.get('platform_key') != platform_key()
            or proof.get('implementation_policy') != 'platform-v1'):
        raise ValueError('Baseline execution evidence belongs to another platform or digest policy.')
    if (seed.get('schema') != 2 or report.get('failures') != [] or
            benchmark_passes(report['benchmark']) is not True or
            report['benchmark']['iterations'] != len(report['benchmark']['samples_seconds']) or
            any(not case_passes(c, report['cases'].get(c['id'], {})) for c in cases()) or
            set(report.get('isolation_probes', {})) != ISOLATION_CHECKS or not all(report['isolation_probes'].values()) or
            set(report.get('timeout_probes', {})) != TIMEOUT_CHECKS or not all(report['timeout_probes'].values())):
        raise ValueError('Baseline requires all cases, isolation/timeout checks and >=30 timing samples to pass.')
    all_inputs(seed)
    return seed


def load_approved(directory=BASELINE):
    directory = Path(directory)
    seed = verify_evidence(directory)
    approval = json.loads((directory / 'baseline-approval.json').read_text(encoding='utf-8'))
    note = (ROOT / approval['review']).resolve()
    if (not note.is_relative_to(ROOT) or approval['inputs_sha256'] != digest(directory / 'runtime-inputs.json') or
            approval['review_sha256'] != digest(note)):
        raise ValueError('Baseline review does not match the current source inventory.')
    return seed


def compare(old, new):
    # Legacy .fmt pins remain visible in the diff, but cannot enter a new source baseline.
    before = {i['path']: i for i in [*old['tex_inputs'], *old.get('format_inputs', [])]}
    after = all_inputs(new)
    return {'added': [after[p] for p in sorted(after.keys() - before.keys())],
            'removed': [before[p] for p in sorted(before.keys() - after.keys())],
            'changed': [{'before': before[p], 'after': after[p]} for p in sorted(before.keys() & after.keys()) if before[p] != after[p]],
            'unchanged_count': sum(before[p] == after[p] for p in before.keys() & after.keys()),
            'fonts_before': old.get('fonts', []), 'fonts_after': new['fonts']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('diff', 'approve'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--candidate', type=Path, required=True)
        if name == 'approve':
            cmd.add_argument('--review', type=Path, required=True)
            cmd.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    seed = verify_evidence(candidate)
    delta = compare(json.loads((BASELINE / 'runtime-inputs.json').read_text(encoding='utf-8')), seed)
    if args.command == 'diff':
        (candidate / 'dependency-diff.json').write_bytes(json_bytes(delta))
        print(json.dumps({'inputs_sha256': digest(candidate / 'runtime-inputs.json'),
                          'added': len(delta['added']), 'removed': len(delta['removed']),
                          'changed': len(delta['changed']), 'diff': str(candidate / 'dependency-diff.json')}))
        return
    review = args.review.resolve()
    if (candidate == BASELINE.resolve() or not review.is_relative_to(ROOT) or
            not review.is_file() or len(review.read_text(encoding='utf-8').strip()) < 80 or
            args.expected_sha256 != digest(candidate / 'runtime-inputs.json')):
        parser.error('Review a separate candidate and provide its exact inventory digest plus a substantive project review note.')
    previous = json.loads((BASELINE / 'baseline-evidence.json').read_text(encoding='utf-8'))
    previous_platform = previous.get('platform_key', 'darwin-arm64')
    if previous_platform not in ('darwin-arm64', 'windows-x64'):
        parser.error('Invalid platform in previous baseline evidence.')
    # Bind both digests without nesting two long components on Windows paths.
    archive_key = hashlib.sha256(json_bytes([
        digest(BASELINE / 'runtime-inputs.json'), previous['implementation_sha256']])).hexdigest()
    archive = BASELINE / 'baseline-history' / previous_platform / archive_key
    archive.mkdir(parents=True, exist_ok=True)
    for name in ('runtime-inputs.json', 'results.json', 'baseline-evidence.json', 'baseline-approval.json'):
        if (BASELINE / name).is_file() and not (archive / name).exists():
            shutil.copyfile(BASELINE / name, archive / name)
    for name in ('runtime-inputs.json', 'results.json', 'baseline-evidence.json'):
        shutil.copyfile(candidate / name, BASELINE / name)
    (BASELINE / 'baseline-approval.json').write_bytes(json_bytes({
        'inputs_sha256': args.expected_sha256, 'review': review.relative_to(ROOT).as_posix(), 'review_sha256': digest(review)}))
    print('Approved source baseline; next build and validate the packaged runtime. No host .fmt was approved.')


if __name__ == '__main__':
    main()
