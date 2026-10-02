"""Build a local M1 artifact from this Mac's tools, without editing global tools."""

import argparse
import fcntl
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import tarfile
from pathlib import Path

from experiments.m1.managed import digest, inventory
from experiments.m1.fonts import FONT_LICENSES
from experiments.m1.runtime import prepare_runtime
from scripts.check_contracts import ROOT, json_bytes


BUILD = ROOT / '.m1-build'
OUTPUT = ROOT / 'output/runtime'
VERSION = 'm2-inline-headings-20261001'


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def prepare_tex(destination):
    installed = prepare_runtime()
    source_root = Path(installed['tex_root'])
    seed = json.loads((ROOT / 'docs/m1/runtime-inputs.json').read_text())
    sources = []
    for item in seed['tex_inputs']:
        source = source_root / item['path']
        if digest(source) != item['sha256']:
            raise ValueError('TeX seed changed; rerun M1 baseline before packaging: ' + item['path'])
        if source.name == 'texmf.cnf':
            continue
        if source.suffix == '.fmt':
            target = destination / 'formats' / source.name
        else:
            target = destination / item['path']
        copy_file(source, target)
        sources.append(item)
    for name, original in [('xelatex', 'xetex'), ('xdvipdfmx', 'xdvipdfmx')]:
        source = Path(installed['engine']).parent / original
        target = destination / 'bin' / name
        copy_file(source, target)
        dependencies = subprocess.check_output(['/usr/bin/otool', '-L', str(target)], text=True)
        if any(not line.strip().startswith(('/usr/lib/', '/System/')) for line in dependencies.splitlines() if line.startswith('\t')):
            raise ValueError('engine has unbundled non-system dynamic dependencies')
        sources.append({'path': str(source.relative_to(source_root)), 'sha256': digest(source),
                        'bytes': source.stat().st_size, 'dynamic_dependencies': dependencies.replace(str(target), name)})
    for item in installed['fonts']:
        copy_file(ROOT / item['source'], destination / 'fonts' / item['name'])
    for name in FONT_LICENSES:
        copy_file(ROOT / 'assets/fonts' / name, destination / 'fonts' / name)
    # article.cls selects Latin Modern before fontspec installs our explicit fonts.
    for relative_name in ('texmf-dist/fonts/opentype/public/lm/lmroman10-regular.otf',
                          'texmf-dist/fonts/opentype/public/lm/lmroman10-bold.otf',
                          'texmf-dist/fonts/opentype/public/lm/lmroman10-italic.otf',
                          'texmf-dist/fonts/opentype/public/lm/lmroman10-bolditalic.otf',
                          'texmf-dist/fonts/misc/xetex/fontmapping/base/tex-text.tec'):
        source = source_root / relative_name
        relative = source.relative_to(source_root)
        copy_file(source, destination / relative)
        sources.append({'path': relative.as_posix(), 'sha256': digest(source), 'bytes': source.stat().st_size})
    copy_file(source_root / installed['cmap']['source'], destination / 'cmaps/Adobe-GB1-UCS2')
    # The system defaults are retained for memory constants; search roots are overridden.
    original = (source_root / 'texmf-dist/web2c/texmf.cnf').read_text()
    header = ('TEXMF = $TEXMFROOT/texmf-dist\nTEXMFDBS = $TEXMFROOT/texmf-dist\n'
              'TEXFORMATS = $TEXMFROOT/formats\nTEXMFLOCAL = $TEXMFROOT/empty\n'
              'TEXMFSYSVAR = $TEXMFROOT/empty\nTEXMFSYSCONFIG = $TEXMFROOT/empty\n'
              'shell_escape = f\nopenin_any = p\nopenout_any = p\n')
    (destination / 'web2c').mkdir(parents=True, exist_ok=True)
    (destination / 'web2c/texmf.cnf').write_text(header + original)
    (destination / 'texmf-dist/dvipdfmx').mkdir(parents=True, exist_ok=True)
    (destination / 'texmf-dist/dvipdfmx/dvipdfmx.cfg').write_text('%% Project fixed-font config; no external conversion.\nV 7\np a4\nI -2\n')
    # Retain original notices. Distribution/source obligations remain a separate release gate.
    for name in ('LICENSE.TL', 'LICENSE.CTAN'):
        copy_file(source_root / name, destination / 'licenses' / name)
    for name in (*FONT_LICENSES, 'README.md'):
        copy_file(ROOT / 'assets/fonts' / name, destination / 'licenses/fonts' / name)
    for name in ('GUST-FONT-LICENSE.TXT', 'MANIFEST-Latin-Modern.TXT', 'README-Latin-Modern.TXT'):
        copy_file(source_root / 'texmf-dist/doc/fonts/lm' / name, destination / 'licenses/latin-modern' / name)
    (destination / 'source-inventory.json').write_bytes(json_bytes({'tex': sources, 'fonts': installed['fonts'], 'cmap': installed['cmap']}))


def collect_python_notices(destination):
    packages = ['pyinstaller', 'markdown-it-py', 'mdurl', 'pypdf', 'Pillow', 'jsonschema',
                'jsonschema-specifications', 'attrs', 'referencing', 'rpds-py', 'typing-extensions']
    metadata = []
    for name in packages:
        package = importlib.metadata.distribution(name)
        notices = []
        for entry in package.files or []:
            if '..' in entry.parts:
                continue
            if any(part.lower() in ('licenses', 'license', 'copying') for part in entry.parts) or entry.name.lower().startswith(('license', 'copying', 'copyright')):
                source = Path(package.locate_file(entry))
                if source.is_file():
                    target = destination / name / str(entry)
                    copy_file(source, target)
                    notices.append(str(target.relative_to(destination)))
        metadata.append({'name': name, 'version': package.version, 'license': package.metadata.get('License-Expression') or package.metadata.get('License'), 'notices': notices})
    stdlib = Path(sysconfig.get_path('stdlib'))
    for candidate in (stdlib / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE.txt'):
        if candidate.is_file():
            copy_file(candidate, destination / 'python-LICENSE.txt')
            break
    (destination / 'packages.json').write_bytes(json_bytes(metadata))
    # The current Homebrew Python links these libraries; PyInstaller relocates them.
    for package, names in {'openssl@3': ['LICENSE.txt', 'AUTHORS.md'], 'zstd': ['LICENSE', 'COPYING'],
                           'mpdecimal': ['COPYRIGHT.txt']}.items():
        for name in names:
            copy_file(Path('/opt/homebrew/opt') / package / name, destination / 'native-libraries' / package / name)


def build(tex_only=False):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise SystemExit('This M1 build is verified only on macOS arm64.')
    stage = BUILD / 'package'
    if stage.exists():
        shutil.rmtree(stage)
    if not tex_only:
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
                   '--name', 'resume-runtime', '--distpath', str(BUILD / 'freeze'),
                   '--workpath', str(BUILD / 'pyinstaller'), '--specpath', str(BUILD),
                   '--paths', str(ROOT), '--add-data', str(ROOT / 'schemas') + ':schemas',
                   '--add-data', str(ROOT / 'fixtures') + ':fixtures',
                   '--add-data', str(ROOT / 'web/style-config.json') + ':web',
                   '--collect-data', 'jsonschema_specifications',
                   '--exclude-module', 'tkinter', '--exclude-module', 'matplotlib',
                   str(ROOT / 'experiments/m1/packaged_cli.py')]
        subprocess.run(command, check=True, env=os.environ | {'PYINSTALLER_CONFIG_DIR': str(BUILD / 'cache')})
        shutil.copytree(BUILD / 'freeze/resume-runtime', stage, symlinks=True)
    stage.mkdir(parents=True, exist_ok=True)
    prepare_tex(stage / 'tex')
    collect_python_notices(stage / 'licenses')
    manifest = {'schema': 1, 'version': VERSION, 'build_platform': platform.platform(),
                'python': platform.python_version(), 'clean_mac': 'skipped by explicit user decision',
                'distribution': 'local experimental artifact; no Developer ID/notarization or completed redistribution audit',
                'files': inventory(stage)}
    (stage / 'runtime.json').write_bytes(json_bytes(manifest))
    if tex_only:
        print(stage)
        return
    OUTPUT.mkdir(parents=True, exist_ok=True)
    archive = OUTPUT / 'resume-runtime-macos-arm64.tar.gz'
    with tarfile.open(archive, 'w:gz', dereference=False) as stream:
        stream.add(stage, arcname='runtime')
    info = {'version': VERSION, 'archive': archive.name, 'bytes': archive.stat().st_size,
            'sha256': digest(archive), 'unpacked_file_bytes': sum(item.get('bytes', 0) for item in manifest['files']),
            'file_count': len(manifest['files']), 'build_platform': platform.platform()}
    installer = (ROOT / 'scripts/install-runtime.sh.in').read_text()
    for key, value in {'SHA256': info['sha256'], 'BYTES': info['bytes'], 'VERSION': VERSION, 'ARCHIVE': archive.name}.items():
        installer = installer.replace('@' + key + '@', str(value))
    (OUTPUT / 'install-runtime.sh').write_text(installer)
    (OUTPUT / 'install-runtime.sh').chmod(0o755)
    (OUTPUT / 'artifact.json').write_bytes(json_bytes(info))
    (ROOT / 'docs/m1/managed-artifact.json').write_bytes(json_bytes(info))
    print(json.dumps(info))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tex-only', action='store_true')
    args = parser.parse_args()
    BUILD.mkdir(exist_ok=True)
    with (BUILD / '.build.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build(args.tex_only)


if __name__ == '__main__':
    main()
