"""Maintainer tool: collect pinned TeX data and source notices, without binaries."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile

from experiments.m1.managed import digest
from experiments.m1.runtime import query_kpse
from experiments.m1.tex_baseline import all_inputs, load_approved, verify_sources
from scripts.check_contracts import ROOT, json_bytes

SNAPSHOT = 'https://texlive.info/tlnet-archive/2026/03/23/tlnet/archive/'


def package_metadata(path):
    fields, files = {}, {'runfiles': [], 'srcfiles': [], 'docfiles': [], 'binfiles': []}
    section = None
    for line in path.read_text().splitlines():
        if line.startswith(' '):
            if section in files:
                files[section].append(line.strip().split()[0])
        elif line:
            key, _, value = line.partition(' ')
            fields[key] = value
            section = key
    return fields, files


def build(destination):
    seed = load_approved()
    root = query_kpse('-var-value=TEXMFROOT')
    verify_sources(seed, root)
    pins = all_inputs(seed)
    runtime_files = {item['path'] for item in seed['tex_inputs'] if not item['path'].startswith('bin/')}
    format_files = {item['path'] for item in seed['format_inputs']}
    selected = {name for name in pins if not name.startswith('bin/')}
    packages = []
    for path in sorted((root / 'tlpkg/tlpobj').glob('*.tlpobj')):
        fields, files = package_metadata(path)
        used = selected.intersection(files['runfiles'])
        if not used:
            continue
        packages.append({'name': fields['name'], 'revision': fields['revision'],
                         'license': fields.get('catalogue-license', 'see upstream files'),
                         'used_files': sorted(used)})
        selected.update(files['srcfiles'])
        for name in files['docfiles']:
            leaf = Path(name).name.lower()
            if leaf.startswith(('readme', 'license', 'copying', 'notice', 'manifest', 'legal', 'lppl')) and not leaf.endswith('.pdf'):
                selected.add(name)
        selected.add(str(path.relative_to(root)))
    # Format inputs retain their original names and headers. Include their sources
    # and notices as well, rather than claiming a derived format is source code.
    payload = {}
    for name in sorted(selected):
        source = (root / name).resolve(strict=True)
        if not source.is_relative_to(root):
            raise ValueError('Source escapes TeX tree: ' + name)
        prefix = 'tex/' if name in runtime_files else 'format-sources/' if name in format_files else 'licenses/texlive/'
        payload[prefix + name] = source.read_bytes()
    files = [{'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
             for name, data in sorted(payload.items())]
    metadata = {'schema': 1, 'baseline_sha256': digest(ROOT / 'docs/m1/runtime-inputs.json'),
                'packages': packages, 'files': files}
    payload['support-inventory.json'] = json_bytes(metadata)
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / 'tex-support.tar.xz'
    with tempfile.TemporaryDirectory(prefix='.build-', dir=destination) as temporary:
        candidate = Path(temporary) / archive.name
        with tarfile.open(candidate, 'w:xz', preset=6) as stream:
            for name, data in sorted(payload.items()):
                entry = tarfile.TarInfo(name)
                entry.size, entry.mode, entry.mtime = len(data), 0o644, 1790812800
                stream.addfile(entry, io.BytesIO(data))
        candidate.replace(archive)
    engines = []
    for package, member, installed in (
        ('xetex', 'bin/universal-darwin/xetex', 'xelatex'),
        ('dvipdfmx', 'bin/universal-darwin/xdvipdfmx', 'xdvipdfmx'),
    ):
        name = package + '.universal-darwin'
        fields, _ = package_metadata(root / 'tlpkg/tlpobj' / (name + '.tlpobj'))
        source = root / 'bin/universal-darwin' / installed
        engines.append({'name': name, 'revision': fields['revision'],
                        'urls': ['https://mirrors.ustc.edu.cn/CTAN/systems/texlive/tlnet/archive/' + name + '.tar.xz',
                                 'https://ctan.math.illinois.edu/systems/texlive/tlnet/archive/' + name + '.tar.xz',
                                 'https://mirrors.ibiblio.org/CTAN/systems/texlive/tlnet/archive/' + name + '.tar.xz',
                                 SNAPSHOT + name + '.tar.xz'],
                        'archive_bytes': int(fields['containersize']),
                        'archive_sha512': fields['containerchecksum'],
                        'member': member, 'target': 'tex/bin/' + installed,
                        'bytes': source.stat().st_size, 'sha256': digest(source)})
    lock = {'schema': 1, 'version': 'texlive-2026-light-1', 'platform': 'darwin-arm64',
            'baseline_sha256': metadata['baseline_sha256'],
            'support': {'archive': archive.name, 'bytes': archive.stat().st_size,
                        'sha256': digest(archive), 'unpacked_bytes': sum(map(len, payload.values())),
                        'inventory_sha256': hashlib.sha256(payload['support-inventory.json']).hexdigest()},
            'engines': engines}
    (destination / 'tex.lock.json').write_bytes(json_bytes(lock))
    (destination / 'support-inventory.json').write_bytes(json_bytes(metadata))
    print(json.dumps({'support_bytes': archive.stat().st_size, 'support_files': len(files),
                      'engine_download_bytes': sum(i['archive_bytes'] for i in engines),
                      'packages': len(packages)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'runtime')
    build(parser.parse_args().output)
