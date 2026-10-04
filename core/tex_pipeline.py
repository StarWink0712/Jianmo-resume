"""Shared TeX -> XDV -> PDF pipeline; all native execution is delegated."""

import hashlib
from pathlib import Path
import time

from experiments.m1.fonts import verify_fonts
from platform_adapters.detect import get_adapter
from scripts.check_contracts import ROOT


RUNTIME = ROOT / '.m1-runtime'


def tex_config(root):
    # Ignore machine-local texmf.cnf; keep upstream memory constants and fixed roots.
    header = ('TEXMF = $TEXMFROOT/texmf-dist\nTEXMFDBS = $TEXMFROOT/texmf-dist\n'
              'TEXFORMATS = $TEXMFROOT/formats\nTEXMFLOCAL = $TEXMFROOT/empty\n'
              'TEXMFSYSVAR = $TEXMFROOT/empty\nTEXMFSYSCONFIG = $TEXMFROOT/empty\n'
              'shell_escape = f\nopenin_any = p\nopenout_any = p\n')
    return header + (Path(root) / 'texmf-dist/web2c/texmf.cnf').read_text(encoding='utf-8')


def generate_format_at(job, tex_root, engine, fonts_root=None, adapter=None):
    adapter = adapter or get_adapter()
    adapter.CAPABILITIES.require_compilation()
    job, tex_root = Path(job).resolve(), Path(tex_root).resolve()
    adapter.private_directory(job)
    for name in ('home', 'empty', 'var', 'config', 'cache'):
        (job / name).mkdir(exist_ok=True)
    (job / 'config/texmf.cnf').write_text(tex_config(tex_root), encoding='utf-8')
    (job / 'xelatex.fmt').unlink(missing_ok=True)
    env = adapter.process_environment(job, engine) | {
        'TEXMFROOT': str(tex_root), 'TEXMFCNF': str(job / 'config'),
        'TEXMF': str(tex_root / 'texmf-dist'),
        'TEXMFHOME': str(job / 'empty'), 'TEXMFVAR': str(job / 'var'),
        'TEXMFCONFIG': str(job / 'config'), 'TEXMFCACHE': str(job / 'cache'),
        'TEXFORMATS': str(job), 'OSFONTDIR': str(job / 'empty'),
        'MKTEXFMT': '0', 'MKTEXPK': '0', 'MKTEXTFM': '0', 'MKTEXTEX': '0',
        'SOURCE_DATE_EPOCH': '1790812800', 'FORCE_SOURCE_DATE': '1',
        'openin_any': 'p', 'openout_any': 'p', 'shell_escape': 'f',
    }
    command = adapter.sandbox_prefix(job, tex_root, fonts_root=fonts_root, name='format.sb')
    command += [str(engine), '-ini', '-etex', '-no-shell-escape', '-interaction=nonstopmode',
                '-halt-on-error', '-recorder', '-jobname=xelatex', '-progname=xelatex', 'xelatex.ini']
    return adapter.run_bounded(command, job, env, timeout=30)


def compile_tex(source, job, manifest, avatar=None, timeout=30, extra_read=(), openin='p', verbose=False,
                fixture_outer_sandbox=False, limit_wrapper=None, adapter=None):
    adapter = adapter or get_adapter()
    adapter.CAPABILITIES.require_compilation()
    if manifest.get('platform', adapter.KEY) != adapter.KEY:
        raise ValueError('Runtime platform does not match the compiler executor.')
    options = dict(avatar=avatar, timeout=timeout, extra_read=extra_read, openin=openin, verbose=verbose,
                   fixture_outer_sandbox=fixture_outer_sandbox, limit_wrapper=limit_wrapper, adapter=adapter)
    if adapter.KEY == 'windows-x64':
        with adapter.compilation(manifest, job) as prepared:
            return _compile_tex(source, job, prepared, **options)
    return _compile_tex(source, job, manifest, **options)


def _compile_tex(source, job, manifest, avatar=None, timeout=30, extra_read=(), openin='p', verbose=False,
                 fixture_outer_sandbox=False, limit_wrapper=None, adapter=None):
    job = Path(job).resolve()
    adapter.private_directory(job)
    # Remove only this experiment's own known output before a repeat compile.
    for name in ('main.pdf', 'main.xdv', 'main.log', 'main.fls', 'main.aux', 'main.out'):
        (job / name).unlink(missing_ok=True)
    (job / 'main.tex').write_text(source, encoding='utf-8')
    fonts_root = Path(manifest.get('fonts_root', RUNTIME / 'fonts')).resolve()
    verify_fonts(fonts_root)
    adapter.prepare_fonts(job, fonts_root)
    if avatar is not None:
        (job / 'avatar.png').write_bytes(avatar)
    for name in ('home', 'empty', 'var', 'config', 'cache'):
        (job / name).mkdir(exist_ok=True)
    format_reads = (manifest['formats_root'], Path(manifest['formats_root']) / 'xelatex.fmt') if manifest.get('formats_root') else ()
    prefix = adapter.sandbox_prefix(job, manifest['tex_root'], (*extra_read, *format_reads), fonts_root=fonts_root)
    env = adapter.process_environment(job, manifest['engine']) | {
        'TEXMFHOME': str(job / 'empty'), 'TEXMFVAR': str(job / 'var'), 'TEXMFCONFIG': str(job / 'config'),
        'TEXMFCACHE': str(job / 'cache'), 'openin_any': openin, 'openout_any': 'p',
        'shell_escape': 'f', 'SOURCE_DATE_EPOCH': '1790812800', 'FORCE_SOURCE_DATE': '1',
    }
    if manifest.get('isolated'):
        root = Path(manifest['tex_root'])
        env.update({'TEXMFCNF': str(root / 'web2c'), 'TEXMFROOT': str(root),
                    'TEXMF': str(root / 'texmf-dist'), 'TEXFORMATS': str(root / 'formats'),
                    'OSFONTDIR': str(job / 'empty'), 'MKTEXFMT': '0', 'MKTEXPK': '0',
                    'MKTEXTFM': '0', 'MKTEXTEX': '0'})
    elif manifest.get('formats_root'):
        config = job / 'config'
        (config / 'texmf.cnf').write_text(tex_config(manifest['tex_root']), encoding='utf-8')
        env.update({'TEXMFCNF': str(config), 'TEXMFROOT': manifest['tex_root'],
                    'TEXMF': '!!' + str(Path(manifest['tex_root']) / 'texmf-dist'),
                    'TEXFORMATS': manifest['formats_root'], 'MKTEXFMT': '0', 'OSFONTDIR': str(job / 'empty')})
    # Run the PDF driver directly: XeTeX's internal shell invocation breaks with spaces
    # in its executable path, even when a relative output-driver is explicitly supplied.
    if fixture_outer_sandbox:
        if adapter.KEY != 'darwin-arm64':
            raise ValueError('Outer sandbox is only supported by the frozen macOS fixture harness.')
        prefix = []
    command = prefix + [manifest['engine'], '-no-shell-escape', '-no-pdf',
               '-interaction=nonstopmode', '-halt-on-error', '-file-line-error', '-recorder', 'main.tex']
    # Only the fixed-fixture harness uses this: its outer OS sandbox/supervisor covers
    # the frozen Python process and all descendants. macOS disallows nested sandbox_apply.
    supervision = {'memory_limit_bytes': None, 'process_group': False} if fixture_outer_sandbox else {}
    if limit_wrapper is not None:
        supervision['limit_wrapper'] = limit_wrapper
    started = time.monotonic()
    result = adapter.run_bounded(command, job, env, timeout, **supervision)
    if result['returncode'] == 0 and (job / 'main.xdv').exists():
        driver = prefix + [manifest.get('driver', str(Path(manifest['engine']).parent / 'xdvipdfmx')), '-vv' if verbose else '-q',
                           '-E', '-o', 'main.pdf', 'main.xdv']
        conversion = adapter.run_bounded(driver, job, env, max(0, timeout - (time.monotonic() - started)),
                                 log_name='driver-process.log', **supervision)
        engine_seconds = result['seconds']
        memory_key = 'peak_job_memory_bytes' if adapter.KEY == 'windows-x64' else 'peak_group_rss_bytes'
        peak_memory = max(result[memory_key], conversion[memory_key])
        result.update(conversion)
        result.update({'engine_seconds': engine_seconds, 'driver_seconds': conversion['seconds'],
                       'seconds': round(engine_seconds + conversion['seconds'], 6), memory_key: peak_memory})
    log = (job / 'main.log').read_text(encoding='utf-8', errors='replace') if (job / 'main.log').exists() else ''
    result.update({'pdf_exists': (job / 'main.pdf').exists(), 'missing_glyphs': 'Missing character:' in log,
                   'overfull_boxes': log.count('Overfull \\hbox'), 'underfull_boxes': log.count('Underfull \\hbox')})
    result['ok'] = result['returncode'] == 0 and result['pdf_exists'] and not result['missing_glyphs']
    return result


def resource_manifest(job, tex_root, recorder='main.fls'):
    files = set()
    for line in (Path(job) / recorder).read_text(encoding='utf-8').splitlines():
        if not line.startswith('INPUT '):
            continue
        path = Path(line[6:])
        path = (Path(job) / path).resolve() if not path.is_absolute() else path.resolve()
        if path.is_file() and path.is_relative_to(tex_root):
            files.add(path)
    return [{'path': path.relative_to(tex_root).as_posix(), 'bytes': path.stat().st_size,
             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(files)]
