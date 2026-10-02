"""Isolated developer-machine compiler experiment; not a distributable runtime."""

import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import time

from scripts.check_contracts import ROOT, json_bytes
from experiments.m1.fonts import FONT_FILES, FONT_LICENSES, font_source_url, verify_fonts


RUNTIME = ROOT / '.m1-runtime'
FONT_NAMES = tuple(FONT_FILES)


def query_kpse(argument):
    return Path(subprocess.check_output(['kpsewhich', argument], text=True).strip()).resolve(strict=True)


def prepare_runtime():
    root = query_kpse('-var-value=TEXMFROOT')
    engine = Path(shutil.which('xelatex')).resolve(strict=True)
    # xelatex is commonly a symlink to xetex; preserve its invocation name to load the format.
    engine = engine.parent / 'xelatex'
    (RUNTIME / 'fonts').mkdir(parents=True, exist_ok=True)
    (RUNTIME / 'licenses').mkdir(exist_ok=True)
    (RUNTIME / 'cmaps').mkdir(exist_ok=True)
    cmap_source = Path(subprocess.check_output(['kpsewhich', '-format=cmap', 'Adobe-GB1-UCS2'], text=True).strip()).resolve(strict=True)
    cmap_bytes = cmap_source.read_bytes()
    (RUNTIME / 'cmaps' / 'Adobe-GB1-UCS2').write_bytes(cmap_bytes)
    cmap = {'name': 'Adobe-GB1-UCS2', 'source': str(cmap_source.relative_to(root)), 'bytes': len(cmap_bytes),
            'sha256': hashlib.sha256(cmap_bytes).hexdigest(), 'license': 'BSD-3-Clause; notice retained in CMap header'}
    fonts = []
    font_source = verify_fonts(ROOT / 'assets/fonts')
    for name in FONT_NAMES:
        source = font_source / name
        target = RUNTIME / 'fonts' / name
        content = source.read_bytes()
        target.write_bytes(content)
        fonts.append({'name': name, 'origin': 'project', 'source': 'assets/fonts/' + name,
                      'upstream': font_source_url(name),
                      'license': 'OFL-1.1', 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
    for name in FONT_LICENSES:
        shutil.copyfile(font_source / name, RUNTIME / 'fonts' / name)
    for name in (*FONT_LICENSES, 'README.md'):
        shutil.copyfile(font_source / name, RUNTIME / 'licenses' / ('noto-sans-cjk-' + name))
    manifest = {'mode': 'developer-installed-texlive', 'tex_root': str(root), 'engine': str(engine), 'fonts': fonts, 'cmap': cmap,
                'font_bytes': sum(item['bytes'] for item in fonts), 'engine_version': subprocess.check_output([str(engine), '--version'], text=True).splitlines()[0]}
    (RUNTIME / 'manifest.json').write_bytes(json_bytes(manifest))
    return manifest


def profile(job, tex_root, extra_read=(), network=False, fonts_root=None):
    def literal(path):
        return '(literal ' + json.dumps(str(path), ensure_ascii=False) + ')'

    fonts_root = Path(fonts_root or RUNTIME / 'fonts')
    roots = ['/System', '/usr/lib', '/usr/share', '/private/var/db/dyld', tex_root, fonts_root, job]
    readable = '\n'.join('(subpath ' + json.dumps(str(Path(path).resolve()), ensure_ascii=False) + ')' for path in roots)
    literals = ['/', '/dev/null', '/dev/random', '/dev/urandom', '/bin/sh', '/usr/bin/curl', '/private/etc/localtime', '/private/var/select/sh']
    readable += '\n' + ' '.join(literal(path) for path in [*literals, *extra_read])
    ancestors = {parent for path in [Path(job), Path(tex_root), fonts_root] for parent in path.parents}
    return '\n'.join([
        '(version 1)', '(deny default)', '(allow process-fork)', '(allow process-exec)',
        '(allow sysctl-read)', '(allow mach-lookup (global-name "com.apple.system.logger"))',
        '(allow file-read* ' + readable + ')',
        # macOS libraries remain readable, but fonts must come from the package.
        '(deny file-read* (subpath "/System/Library/Fonts") (subpath "/Library/Fonts") '
        '(regex #"^/System/.*[.](otf|ttf|ttc|otc|dfont)$"))',
        '(allow file-read-metadata ' + ' '.join(literal(path) for path in sorted(ancestors)) + ')',
        '(allow file-write* (subpath ' + json.dumps(str(job), ensure_ascii=False) + ') (literal "/dev/null"))',
        '(allow network*)' if network else '',
    ])


def group_rss_bytes(pgid):
    result = subprocess.run(['/bin/ps', '-axo', 'pgid=,rss='], capture_output=True, text=True, timeout=2)
    if result.returncode:
        raise RuntimeError('cannot inspect compiler process-group memory')
    return sum(int(parts[1]) * 1024 for line in result.stdout.splitlines()
               if len(parts := line.split()) == 2 and int(parts[0]) == pgid)


def run_bounded(command, cwd, env, timeout=30, memory_limit_bytes=512 * 1024 * 1024, process_group=True,
                log_name='process.log', limit_wrapper=None):
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))

    started = time.perf_counter()
    if limit_wrapper is not None:
        command = [sys.executable, str(limit_wrapper), *command]
    with (cwd / log_name).open('wb') as output:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=process_group, preexec_fn=None if limit_wrapper else limits)
        timed_out = False
        memory_exceeded = False
        peak_rss = 0
        try:
            while process.poll() is None:
                if time.perf_counter() - started >= timeout:
                    timed_out = True
                    break
                if memory_limit_bytes is not None:
                    peak_rss = max(peak_rss, group_rss_bytes(process.pid))
                    if peak_rss > memory_limit_bytes:
                        memory_exceeded = True
                        break
                time.sleep(0.05)
            code = None if timed_out or memory_exceeded else process.returncode
        finally:
            # Also remove descendants left behind after the direct process exits.
            try:
                if process_group:
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()
    return {'returncode': code, 'timed_out': timed_out, 'memory_exceeded': memory_exceeded,
            'peak_group_rss_bytes': peak_rss, 'memory_limit_bytes': memory_limit_bytes,
            'seconds': round(time.perf_counter() - started, 6)}


def compile_tex(source, job, manifest, avatar=None, timeout=30, extra_read=(), openin='p', verbose=False,
                fixture_outer_sandbox=False, limit_wrapper=None):
    job = Path(job).resolve()
    job.mkdir(parents=True, exist_ok=True)
    # Remove only this experiment's own known output before a repeat compile.
    for name in ('main.pdf', 'main.xdv', 'main.log', 'main.fls', 'main.aux', 'main.out'):
        (job / name).unlink(missing_ok=True)
    (job / 'main.tex').write_text(source, encoding='utf-8')
    fonts_root = Path(manifest.get('fonts_root', RUNTIME / 'fonts')).resolve()
    verify_fonts(fonts_root)
    link = job / 'fonts'
    if link.is_symlink():
        link.unlink()
    if link.exists():
        raise ValueError('job fonts path must not contain user files')
    link.symlink_to(fonts_root, target_is_directory=True)
    if avatar is not None:
        (job / 'avatar.png').write_bytes(avatar)
    for name in ('home', 'empty', 'var', 'config', 'cache'):
        (job / name).mkdir(exist_ok=True)
    sandbox = job / 'compile.sb'
    sandbox.write_text(profile(job, manifest['tex_root'], extra_read, fonts_root=fonts_root), encoding='utf-8')
    env = {
        'PATH': str(Path(manifest['engine']).parent) + ':/usr/bin:/bin',
        'HOME': str(job / 'home'), 'TMPDIR': str(job), 'LANG': 'en_US.UTF-8',
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
    # Run the PDF driver directly: XeTeX's internal shell invocation breaks with spaces
    # in its executable path, even when a relative output-driver is explicitly supplied.
    prefix = [] if fixture_outer_sandbox else ['/usr/bin/sandbox-exec', '-f', str(sandbox)]
    command = prefix + [manifest['engine'], '-no-shell-escape', '-no-pdf',
               '-interaction=nonstopmode', '-halt-on-error', '-file-line-error', '-recorder', 'main.tex']
    # Only the fixed-fixture harness uses this: its outer OS sandbox/supervisor covers
    # the frozen Python process and all descendants. macOS disallows nested sandbox_apply.
    supervision = {'memory_limit_bytes': None, 'process_group': False} if fixture_outer_sandbox else {}
    if limit_wrapper is not None:
        supervision['limit_wrapper'] = limit_wrapper
    result = run_bounded(command, job, env, timeout, **supervision)
    if result['returncode'] == 0 and (job / 'main.xdv').exists():
        driver = prefix + [str(Path(manifest['engine']).parent / 'xdvipdfmx'), '-vv' if verbose else '-q',
                           '-E', '-o', 'main.pdf', 'main.xdv']
        conversion = run_bounded(driver, job, env, max(0, timeout - result['seconds']),
                                 log_name='driver-process.log', **supervision)
        engine_seconds = result['seconds']
        peak_rss = max(result['peak_group_rss_bytes'], conversion['peak_group_rss_bytes'])
        result.update(conversion)
        result.update({'engine_seconds': engine_seconds, 'driver_seconds': conversion['seconds'],
                       'seconds': round(engine_seconds + conversion['seconds'], 6), 'peak_group_rss_bytes': peak_rss})
    log = (job / 'main.log').read_text(errors='replace') if (job / 'main.log').exists() else ''
    result.update({'pdf_exists': (job / 'main.pdf').exists(), 'missing_glyphs': 'Missing character:' in log,
                   'overfull_boxes': log.count('Overfull \\hbox'), 'underfull_boxes': log.count('Underfull \\hbox')})
    result['ok'] = result['returncode'] == 0 and result['pdf_exists'] and not result['missing_glyphs']
    return result


def resource_manifest(job, tex_root):
    files = set()
    for line in (Path(job) / 'main.fls').read_text().splitlines():
        if not line.startswith('INPUT '):
            continue
        path = Path(line[6:])
        path = (Path(job) / path).resolve() if not path.is_absolute() else path.resolve()
        if path.is_file() and path.is_relative_to(tex_root):
            files.add(path)
    return [{'path': str(path.relative_to(tex_root)), 'bytes': path.stat().st_size,
             'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(files)]
