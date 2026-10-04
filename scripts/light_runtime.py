"""Install the small, pinned TeX subset. No system TeX or package manager needed."""

import argparse
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

import certifi

from experiments.m1.fonts import FONT_FILES, FONT_LICENSES, verify_fonts
from experiments.m1.managed import digest, inventory, verify
from core.tex_checks import check_cases
from core.tex_pipeline import generate_format_at, resource_manifest, tex_config
from platform_adapters.contracts import LockBusy, PlatformUnavailable
from platform_adapters.detect import get_adapter
from experiments.m1.tex_baseline import implementation_hash
from experiments.m1.tex_baseline import load_approved
from scripts.check_contracts import ROOT, json_bytes


class HTTPSOnlyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.startswith('https://'):
            raise ValueError('Runtime download refused a non-HTTPS redirect.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_name(name):
    path = PurePosixPath(name)
    if not name or name == '.' or path.is_absolute() or '..' in path.parts or path.as_posix() != name:
        raise ValueError('Unsafe archive path: ' + name)
    return path


def check_archive(path, size, expected, algorithm='sha256'):
    if not path.is_file() or path.stat().st_size != size:
        raise ValueError('Runtime archive size mismatch: ' + path.name)
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, algorithm).hexdigest()
    if actual != expected:
        raise ValueError('Runtime archive hash mismatch: ' + path.name)


def download(package, cache, offline=False):
    target = cache / (package['archive_sha512'] + '.tar.xz')
    if target.exists():
        check_archive(target, package['archive_bytes'], package['archive_sha512'], 'sha512')
        return target
    if offline:
        raise ValueError('Offline engine cache is missing: ' + package['name'])
    if not package['urls'] or any(not url.startswith('https://') for url in package['urls']):
        raise ValueError('Runtime download must use HTTPS.')
    print('Downloading ' + package['name'] + ' (pinned TeX Live archive)...', flush=True)
    opener = urllib.request.build_opener(HTTPSOnlyRedirect,
                                        urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
    # A failed download never becomes a reusable cache entry.
    with tempfile.TemporaryDirectory(prefix='.download-', dir=cache) as temporary:
        partial = Path(temporary) / 'archive.tar.xz'
        errors = []
        for url in package['urls']:
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'Jianmo-Resume/1'})
                started = time.monotonic()
                with opener.open(request, timeout=30) as response, partial.open('wb') as output:
                    received = 0
                    while chunk := response.read(64 * 1024):
                        received += len(chunk)
                        if received > package['archive_bytes']:
                            raise ValueError('Runtime download exceeds the pinned size.')
                        if time.monotonic() - started > 300:
                            raise ValueError('Runtime download time limit exceeded.')
                        output.write(chunk)
                check_archive(partial, package['archive_bytes'], package['archive_sha512'], 'sha512')
                os.replace(partial, target)
                break
            except (OSError, ValueError, http.client.HTTPException, urllib.error.URLError) as error:
                errors.append(str(error))
                print('Mirror unavailable or version changed; trying the next pinned source.', flush=True)
        else:
            raise ValueError('Engine download failed. Rerun to retry; no MacTeX installation is needed. ' + '; '.join(errors))
    return target


def unpack_support(archive, stage, expected_bytes):
    total, seen = 0, set()
    with tarfile.open(archive, 'r:xz') as stream:
        for entry in stream:
            safe_name(entry.name)
            if not entry.isfile() or entry.name in seen:
                raise ValueError('Support archive contains a link, duplicate or special file.')
            if entry.name != 'support-inventory.json' and not entry.name.startswith(('tex/', 'format-sources/', 'licenses/texlive/')):
                raise ValueError('Unexpected support archive member.')
            total += entry.size
            if total > expected_bytes:
                raise ValueError('Support archive exceeds its unpacked size.')
            seen.add(entry.name)
            target = stage / entry.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with stream.extractfile(entry) as source, target.open('xb') as output:
                shutil.copyfileobj(source, output)
            target.chmod(0o644)
    if total != expected_bytes:
        raise ValueError('Support archive is incomplete.')


def unpack_engine(archive, package, stage):
    with tarfile.open(archive, 'r:xz') as stream:
        members = [entry for entry in stream.getmembers() if entry.name == package['member']]
        if len(members) != 1 or not members[0].isfile() or members[0].size != package['bytes']:
            raise ValueError('Engine archive does not contain the expected regular file.')
        safe_name(package['target'])
        target = stage / package['target']
        target.parent.mkdir(parents=True, exist_ok=True)
        with stream.extractfile(members[0]) as source, target.open('xb') as output:
            shutil.copyfileobj(source, output)
        if digest(target) != package['sha256']:
            raise ValueError('Engine file differs from the approved baseline.')
        target.chmod(0o755)


def make_format(stage, seed):
    tex = stage / 'tex'
    temporary_inputs = []
    for item in seed['format_inputs']:
        target = tex / item['path']
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / 'format-sources' / item['path'], target)
            temporary_inputs.append(target)
    formats = tex / 'formats'
    formats.mkdir()
    (tex / 'web2c').mkdir()
    (tex / 'web2c/texmf.cnf').write_text(tex_config(tex), encoding='utf-8')
    (tex / 'texmf-dist/dvipdfmx').mkdir(exist_ok=True)
    (tex / 'texmf-dist/dvipdfmx/dvipdfmx.cfg').write_text('%% No external conversion.\nV 7\np a4\nI -2\n')
    with tempfile.TemporaryDirectory(prefix='.format-', dir=stage) as temporary:
        job = Path(temporary)
        result = generate_format_at(job, tex, tex / 'bin/xelatex', fonts_root=tex / 'fonts')
        if result['returncode'] != 0 or not (job / 'xelatex.fmt').is_file():
            raise ValueError('Private TeX format generation failed: ' + (job / 'process.log').read_text(encoding='utf-8', errors='replace')[-2500:])
        observed = {item['path']: item for item in resource_manifest(job, tex, recorder='xelatex.fls')}
        expected = {item['path']: item for item in seed['format_inputs']}
        if observed != expected:
            delta = {'added': sorted(observed.keys() - expected.keys()),
                     'missing': sorted(expected.keys() - observed.keys()),
                     'changed': sorted(name for name in observed.keys() & expected.keys() if observed[name] != expected[name])}
            raise ValueError('Generated format source closure differs from baseline: ' + json.dumps(delta))
        shutil.copyfile(job / 'xelatex.fmt', formats / 'xelatex.fmt')
    # Keep format-only sources available for provenance, but out of Kpathsea's
    # runtime search tree. Normal compilation needs only the document closure.
    for path in temporary_inputs:
        path.unlink()
        parent = path.parent
        while parent != tex:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent


@contextmanager
def install_lock(prefix):
    adapter = get_adapter()
    adapter.private_directory(prefix)
    try:
        lease = adapter.acquire_lock(prefix, '.light-install.lock')
    except LockBusy as error:
        raise ValueError('Another lightweight runtime installation is active.') from error
    try:
        yield
    finally:
        lease.close()


def verify_install(root, identity, lock):
    manifest = verify(root)
    if manifest.get('light_runtime_id') != identity:
        raise ValueError('Runtime was built for another source lock or installer.')
    verify_fonts(root / 'tex/fonts')
    for package in lock['engines']:
        if digest(root / package['target']) != package['sha256']:
            raise ValueError('Installed engine has changed.')
    support = json.loads((root / 'support-inventory.json').read_text(encoding='utf-8'))
    if digest(root / 'support-inventory.json') != lock['support']['inventory_sha256']:
        raise ValueError('Installed support inventory has changed.')
    for item in support['files']:
        if digest(root / item['path']) != item['sha256']:
            raise ValueError('Installed TeX source has changed: ' + item['path'])
    return manifest


def install(prefix, cache, offline=False, root=ROOT):
    adapter = get_adapter()
    if adapter.KEY != 'darwin-arm64':
        raise PlatformUnavailable('Use scripts/bootstrap.py for the native Windows runtime.')
    adapter.CAPABILITIES.require_compilation()
    seed = load_approved()
    lock_path = root / 'runtime/tex.lock.json'
    lock = json.loads(lock_path.read_text(encoding='utf-8'))
    if lock.get('schema') != 1 or lock.get('platform') != adapter.KEY:
        raise ValueError('Unsupported TeX lock.')
    if lock['baseline_sha256'] != digest(root / 'docs/m1/runtime-inputs.json'):
        raise ValueError('TeX lock differs from the approved baseline; rebuild the support bundle.')
    identity = hashlib.sha256((digest(lock_path) + implementation_hash()).encode()).hexdigest()
    archive = root / 'runtime' / safe_name(lock['support']['archive'])
    check_archive(archive, lock['support']['bytes'], lock['support']['sha256'])
    prefix, cache = prefix.resolve(), cache.resolve()
    if prefix == Path('/'):
        raise ValueError('Refusing the filesystem root as an installation prefix.')
    with install_lock(prefix):
        releases = prefix / 'releases'
        if releases.is_symlink():
            raise ValueError('Refusing a symlinked releases directory.')
        releases.mkdir(exist_ok=True)
        current = prefix / 'current'
        if current.exists() and not current.is_symlink():
            raise ValueError('Refusing to replace a non-symlink current directory.')
        destination = releases / ('light-' + identity)
        if destination.is_symlink():
            raise ValueError('Refusing a symlinked release.')
        if destination.exists():
            verify_install(destination, identity, lock)
        else:
            cache.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.light-stage-', dir=prefix) as temporary:
                stage = Path(temporary) / 'runtime'
                stage.mkdir()
                unpack_support(archive, stage, lock['support']['unpacked_bytes'])
                fonts = stage / 'tex/fonts'
                fonts.mkdir()
                verify_fonts(root / 'assets/fonts')
                for name in (*FONT_FILES, *FONT_LICENSES):
                    shutil.copyfile(root / 'assets/fonts' / name, fonts / name)
                for package in lock['engines']:
                    unpack_engine(download(package, cache, offline), package, stage)
                make_format(stage, seed)
                cmap = stage / 'tex/cmaps'
                cmap.mkdir()
                shutil.copyfile(stage / 'tex' / seed['cmap']['source'], cmap / 'Adobe-GB1-UCS2')
                manifest = {'schema': 1, 'version': lock['version'], 'light_runtime_id': identity,
                            'platform': adapter.KEY, 'lock_sha256': digest(lock_path),
                            'baseline_sha256': lock['baseline_sha256'], 'files': inventory(stage)}
                (stage / 'runtime.json').write_bytes(json_bytes(manifest))
                verify_install(stage, identity, lock)
                print('Checking local PDF compilation and bundled fonts...', flush=True)
                result = check_cases(stage, Path(temporary) / 'self-test')
                if result['failures']:
                    raise ValueError('Runtime PDF self-test failed: ' + ', '.join(result['failures']))
                os.replace(stage, destination)
        with tempfile.TemporaryDirectory(prefix='.activate-', dir=prefix) as temporary:
            link = Path(temporary) / 'current'
            link.symlink_to(destination.relative_to(prefix))
            os.replace(link, current)
    print('Lightweight TeX runtime ready (no system TeX required).', flush=True)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, default=ROOT / '.m1-build/local-install')
    parser.add_argument('--cache-dir', type=Path, default=ROOT / '.m1-build/engine-cache')
    parser.add_argument('--offline', action='store_true', help='Use only installed files or verified engine cache.')
    args = parser.parse_args()
    try:
        install(args.prefix, args.cache_dir, args.offline)
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, 'Lightweight TeX setup stopped: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
