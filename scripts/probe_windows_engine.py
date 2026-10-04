"""D1 experiment: pinned Windows TeX inside AppContainer + Job Object.

This is NOT an installer or application launcher. Use scripts/bootstrap.py for
the locally validated Windows application. A handle-owned temporary drive alias works around
Kpathsea enumerating inaccessible ancestor directories. Debug events audit actual
EXE/DLL loads; wider platform and application acceptance is still required.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pe_imports(path):
    """Read PE32+ regular and delay imports without loading executable code."""
    data = Path(path).read_bytes()
    if data[:2] != b'MZ':
        raise ValueError('Not a PE file: ' + str(path))
    pe = struct.unpack_from('<I', data, 60)[0]
    if data[pe:pe+4] != b'PE\0\0':
        raise ValueError('Invalid PE signature')
    machine, count = struct.unpack_from('<HH', data, pe + 4)
    optional = pe + 24
    optional_size = struct.unpack_from('<H', data, pe + 20)[0]
    if machine != 0x8664 or struct.unpack_from('<H', data, optional)[0] != 0x20b:
        raise ValueError('Only native x64 PE32+ engines are accepted.')
    sections = []
    for index in range(count):
        size, address, raw_size, offset = struct.unpack_from('<IIII', data, optional + optional_size + index * 40 + 8)
        sections.append((address, max(size, raw_size), offset))

    def offset(rva):
        for address, size, raw in sections:
            if address <= rva < address + size:
                result = raw + rva - address
                if result < len(data):
                    return result
        raise ValueError('Invalid PE RVA')

    def string(rva):
        start = offset(rva)
        return data[start:data.index(b'\0', start)].decode('ascii').lower()

    imports, delayed = [], []
    for index, width, name_offset, output in [(1, 20, 12, imports), (13, 32, 4, delayed)]:
        rva, length = struct.unpack_from('<II', data, optional + 112 + 8 * index)
        if not rva:
            continue
        start = offset(rva)
        end = min(len(data), start + length)
        while start + width <= end and any(data[start:start + width]):
            if index == 13 and struct.unpack_from('<I', data, start)[0] != 1:
                raise ValueError('Unsupported delay import addressing')
            output.append(string(struct.unpack_from('<I', data, start + name_offset)[0]))
            start += width
    return {'machine': 'AMD64', 'imports': imports, 'delay_imports': delayed}


def prototype_drive(root):
    """Compatibility name for old developer callers; aliases are now handle-owned."""
    from platform_adapters.windows_paths import runtime_alias
    return runtime_alias(root)


def prepare(root, cache, offline):
    from scripts.light_runtime import check_archive, download
    from core.runtime_manifest import safe_relative, unpack_support
    from experiments.m1.fonts import FONT_FILES, FONT_LICENSES, verify_fonts
    from core.tex_pipeline import tex_config
    lock = json.loads((ROOT / 'runtime/locks/windows-x64.prototype.json').read_text(encoding='utf-8'))
    support = json.loads((ROOT / 'runtime/tex.lock.json').read_text(encoding='utf-8'))['support']
    archive = ROOT / 'runtime' / support['archive']
    check_archive(archive, support['bytes'], support['sha256'])
    unpack_support(archive, root, support['unpacked_bytes'])
    selected = {}
    for package in lock['packages']:
        archive = download(package, cache, offline)
        with tarfile.open(archive, 'r:xz') as stream:
            for item in package['files']:
                members = [m for m in stream.getmembers() if m.name == item['member']]
                if len(members) != 1 or not members[0].isfile() or members[0].size != item['bytes']:
                    raise ValueError('Unexpected engine member')
                target = root / item['target']
                # Lock is source-controlled; still reject platform path ambiguity.
                safe_relative(item['target'])
                target.parent.mkdir(parents=True, exist_ok=True)
                data = stream.extractfile(members[0]).read()
                if hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise ValueError('Engine member hash mismatch')
                target.write_bytes(data)
                selected[target.name.lower()] = pe_imports(target)
    available = set(selected) | set(lock['system_imports'])
    for name, metadata in selected.items():
        missing = (set(metadata['imports']) | set(metadata['delay_imports'])) - available
        if missing:
            raise ValueError(f'Unpinned DLL dependency for {name}: {sorted(missing)}')
    tex = root / 'tex'
    for source in (root / 'format-sources').rglob('*'):
        if source.is_file():
            target = tex / source.relative_to(root / 'format-sources')
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != source.read_bytes():
                raise ValueError('Conflicting format input')
            target.write_bytes(source.read_bytes())
    for name in ('formats', 'web2c', 'fonts', 'empty', 'cmaps'):
        (tex / name).mkdir(exist_ok=True)
    (tex / 'web2c/texmf.cnf').write_text(tex_config(tex), encoding='utf-8')
    (tex / 'texmf-dist/dvipdfmx').mkdir(exist_ok=True)
    (tex / 'texmf-dist/dvipdfmx/dvipdfmx.cfg').write_text('%% No external conversion.\nV 7\np a4\nI -2\n', encoding='utf-8')
    verify_fonts(ROOT / 'assets/fonts')
    for name in (*FONT_FILES, *FONT_LICENSES):
        shutil.copyfile(ROOT / 'assets/fonts' / name, tex / 'fonts' / name)
    seed = json.loads((ROOT / 'docs/m1/runtime-inputs.json').read_text(encoding='utf-8'))
    shutil.copyfile(tex / seed['cmap']['source'], tex / 'cmaps/Adobe-GB1-UCS2')
    return selected


def run(output, cache, offline=False, *, installed_runtime=None):
    from platform_adapters import windows_native as native
    from core.resume_checks import case_passes, compact, expected_text
    from experiments.m1.pdf_checks import ensure_unicode_maps, inspect_pdf
    from experiments.m1.fonts import uses_bundled_fonts
    from experiments.m1.render import RenderError, render_resume
    from scripts.check_contracts import build_case, cases
    from backend.examples import example_document
    runtime = native.local_path(installed_runtime) if installed_runtime else output / 'runtime'
    if not installed_runtime:
        native.private_directory(runtime, exist_ok=False)
    cache.mkdir(parents=True, exist_ok=True)
    report = {'schema': 1, 'application_ready': False, 'scope': 'Windows engine prototype, not release acceptance',
              'stages': {}, 'image_audit': 'debug events, pinned runtime hashes and Windows System32',
              'runtime_alias': 'temporary NT object, lifetime owned by host handle',
              'unverified': ['ordinary non-administrator account', 'long paths and wider Windows versions',
                  'external network and DNS (separate acceptance)', 'complete visual PDF review',
                  'production installer integration', 'application UI', 'third-party redistribution approval']}
    try:
        if installed_runtime:
            report['installed_runtime_check'] = True
        else:
            report['pe'] = prepare(runtime, cache, offline)
        from platform_adapters.windows_images import ImagePolicy
        lock = json.loads((ROOT / 'runtime/locks/windows-x64.prototype.json').read_text(encoding='utf-8'))
        image_policy = ImagePolicy({runtime / item['target']: item['sha256'] for package in lock['packages'] for item in package['files']})
        with prototype_drive(runtime) as mapped:
            report['runtime_alias_drive'] = str(mapped)
            tex = mapped / 'tex'

            def execute(job, executable, args, log_name, timeout=30, format_mode=False):
                (job / 'cache').mkdir(exist_ok=True)
                (job / 'fonts/cache').mkdir(parents=True, exist_ok=True)
                (job / 'fonts.conf').write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
                    '<fontconfig><dir prefix="cwd">fonts</dir><cachedir prefix="cwd">cache</cachedir></fontconfig>', encoding='utf-8')
                with native.app_container() as (sid, text):
                    native.grant_tree(runtime, text)
                    native.grant_tree(job, text, True)
                    engine = tex / 'bin' / executable
                    env = native.environment(job, engine) | {
                        'TEXMFROOT': str(tex), 'TEXMFCNF': str(tex / 'web2c'),
                        'TEXMF': str(tex / 'texmf-dist'), 'TEXFORMATS': '.' if format_mode else str(tex / 'formats'),
                        'TEXMFHOME': str(tex / 'empty'), 'TEXMFVAR': '.', 'TEXMFCONFIG': '.', 'TEXMFCACHE': '.',
                        'OSFONTDIR': str(tex / 'empty'), 'MKTEXFMT': '0', 'MKTEXPK': '0', 'MKTEXTFM': '0', 'MKTEXTEX': '0',
                        'FONTCONFIG_FILE': 'fonts.conf', 'FONTCONFIG_PATH': '.',
                        'XE_FONTCONFIG_PATH': '.', 'XE_FC_CACHEDIR': './cache',
                        'openin_any': 'p', 'openout_any': 'p', 'shell_escape': 'f',
                        'SOURCE_DATE_EPOCH': '1790812800', 'FORCE_SOURCE_DATE': '1'}
                    result = native.run_in_container([str(engine), *args], job, env, sid, timeout=timeout,
                                                     log_name=log_name, image_policy=image_policy)
                    report['stages'][job.name + '/' + log_name] = result
                    if result['reason'] != 'success':
                        raise ValueError('Native TeX stage failed: ' + job.name + '/' + log_name)
                    return result

            if not installed_runtime:
                job = output / 'format'
                native.private_directory(job)
                execute(job, 'xetex.exe', ['-ini', '-etex', '-no-shell-escape', '-interaction=nonstopmode',
                        '-halt-on-error', '-recorder', '-jobname=xelatex', '-progname=xelatex', 'xelatex.ini'], 'format.log', format_mode=True)
                shutil.copyfile(job / 'xelatex.fmt', runtime / 'tex/formats/xelatex.fmt')
            def compile_document(kind, document, assets):
                job = output / kind
                native.private_directory(job)
                source, avatar = render_resume(document, assets)
                (job / 'main.tex').write_text(source, encoding='utf-8')
                if avatar:
                    (job / 'avatar.png').write_bytes(avatar)
                shutil.copytree(runtime / 'tex/fonts', job / 'fonts')
                started = time.monotonic()
                execute(job, 'xelatex.exe', ['-no-shell-escape', '-no-pdf', '-interaction=nonstopmode',
                        '-halt-on-error', '-file-line-error', '-recorder', 'main.tex'], 'engine.log')
                execute(job, 'xdvipdfmx.exe', ['-q', '-E', '-o', 'main.pdf', 'main.xdv'], 'driver.log',
                        timeout=max(0, 30 - (time.monotonic() - started)))
                ensure_unicode_maps(job / 'main.pdf', runtime / 'tex/cmaps/Adobe-GB1-UCS2')
                inspected = inspect_pdf(job / 'main.pdf')
                text = compact(inspected.pop('text'))
                inspected['missing_text_fragments'] = sum(compact(value) not in text for value in expected_text(document))
                inspected['bundled_fonts'] = uses_bundled_fonts(inspected['fonts'])
                log = (job / 'main.log').read_text(encoding='utf-8', errors='replace')
                inspected['overfull_boxes'] = log.count('Overfull \\hbox')
                inspected['missing_glyphs'] = 'Missing character:' in log
                inspected['ok'] = not (inspected['missing_text_fragments'] or not inspected['bundled_fonts'] or inspected['overfull_boxes'] or inspected['missing_glyphs'])
                if not inspected['ok']:
                    raise ValueError('PDF semantic checks failed: ' + kind)
                print('PASS native PDF: ' + kind, flush=True)
                return inspected

            for kind in ('java', 'algorithm', 'testing'):
                report[kind] = compile_document(kind, example_document(kind), {})
            report['fixtures'] = {}
            for case in cases():
                document, assets = build_case(case)
                try:
                    render_resume(document, assets)
                except RenderError:
                    result = {'rejected': True}
                else:
                    if not case['valid'] or case.get('render_expectation'):
                        raise ValueError('Unexpected acceptance: ' + case['id'])
                    result = compile_document(case['id'], document, assets)
                report['fixtures'][case['id']] = result
                if not case_passes(case, result):
                    raise ValueError('Fixture expectation failed: ' + case['id'])
        report['prototype_passed'] = True
    except BaseException as error:
        report['prototype_passed'] = False
        report['error'] = str(error)
        raise
    finally:
        if installed_runtime:
            native.private_tree(runtime)
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / '.m1-build/engine-cache')
    args = parser.parse_args()
    if sys.platform != 'win32':
        parser.error('Native Windows required')
    parent = ROOT / '.m1-build'
    parent.mkdir(exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix='windows-probe-', dir=parent))
    print('Prototype output: ' + str(output), flush=True)
    run(output, args.cache_dir.resolve(), args.offline)
    print('Reference PDFs and fixture suite passed. Launch the application with scripts/bootstrap.py.', flush=True)


if __name__ == '__main__':
    main()
