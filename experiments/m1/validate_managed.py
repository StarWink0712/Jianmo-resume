"""Real local install, relocation, offline and failure tests for the built artifact."""

from contextlib import contextmanager
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import time

from experiments.m1.managed import digest
from experiments.m1.runtime import profile, run_bounded
from scripts.check_contracts import ROOT, json_bytes


OUTPUT = ROOT / 'output/runtime'


def redact_evidence(value, work):
    if isinstance(value, str):
        for source, label in ((str(work), '<test-root>'), (str(ROOT), '<project>'), (str(Path.home()), '<home>')):
            value = value.replace(source, label).replace(json.dumps(source)[1:-1], label)
        return value
    if isinstance(value, dict):
        return {key: redact_evidence(item, work) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_evidence(item, work) for item in value]
    return value


@contextmanager
def download_server(work, archive):
    key, cert = work / 'key.pem', work / 'cert.pem'
    subprocess.run(['/usr/bin/openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                    '-keyout', str(key), '-out', str(cert), '-days', '1', '-subj', '/CN=localhost',
                    '-addext', 'subjectAltName=DNS:localhost'], check=True, capture_output=True)
    state = {'requests': 0, 'truncate': False, 'downgrade': False}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state['requests'] += 1
            if self.path == '/probe':
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'M1PROBE')
                return
            if state['downgrade']:
                self.send_response(302)
                self.send_header('Location', 'http://localhost:1/not-allowed')
                self.end_headers()
                return
            self.send_response(200)
            self.send_header('Content-Length', str(archive.stat().st_size))
            self.end_headers()
            with archive.open('rb') as stream:
                if state['truncate']:
                    self.wfile.write(stream.read(1024))
                    self.close_connection = True
                else:
                    shutil.copyfileobj(stream, self.wfile)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'https://localhost:{server.server_port}/runtime.tar.gz', cert, state
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def main():
    report = {'clean_mac': 'skipped by explicit user decision; not passed', 'checks': {}}
    evidence = []
    installer = OUTPUT / 'install-runtime.sh'
    archive = OUTPUT / 'resume-runtime-macos-arm64.tar.gz'
    report['artifact_sha256'] = digest(archive)
    report['archive_bytes'] = archive.stat().st_size

    def record(name, passed):
        report['checks'][name] = bool(passed)
        print(name, 'PASS' if passed else 'FAIL', flush=True)

    with tempfile.TemporaryDirectory(prefix='managed-test-', dir=ROOT / '.m1-build') as temporary:
        work = Path(temporary).resolve()
        home = work / 'home'
        home.mkdir()
        env = {'HOME': str(home), 'PATH': '/usr/bin:/bin', 'TMPDIR': str(work), 'LC_ALL': 'C'}

        def install(prefix, *args, extra_env=None):
            started = time.perf_counter()
            result = subprocess.run(['/bin/sh', str(installer), '--prefix', str(prefix), *map(str, args)],
                                    env=env | (extra_env or {}), capture_output=True, text=True, timeout=120)
            evidence.append({'command': 'install ' + prefix.name, 'exit': result.returncode,
                             'seconds': round(time.perf_counter() - started, 4),
                             'stdout': result.stdout.replace(str(work), '<test-root>'),
                             'stderr': result.stderr.replace(str(work), '<test-root>')})
            return result

        prefix = work / 'install space 中文'
        result = install(prefix)
        record('fresh-local-install', result.returncode == 0)
        if result.returncode:
            raise RuntimeError(result.stderr)
        release = (prefix / 'current').readlink()
        record('repeat-install', install(prefix).returncode == 0 and (prefix / 'current').readlink() == release)
        record('no-profile-or-user-data-written', list(home.iterdir()) == [])
        normal = subprocess.run([str(prefix / 'current/resume-runtime'), 'self-test', '--output', str(work / 'normal-samples')],
                                env=env, capture_output=True, text=True, timeout=90)
        evidence.append({'command': 'normal frozen self-test', 'exit': normal.returncode,
                         'stdout': normal.stdout.replace(str(work), '<test-root>'),
                         'stderr': normal.stderr.replace(str(work), '<test-root>')})
        record('normal-frozen-self-test', normal.returncode == 0)
        if (work / 'normal-samples/results.json').exists():
            report['normal_self_test'] = json.loads((work / 'normal-samples/results.json').read_text())
        if normal.returncode:
            evidence.append({'normal_first_compile_log': (work / 'normal-samples/standard-one-page-target/process.log').read_text()[-2000:].replace(str(work), '<test-root>')})

        locked = work / 'locked'
        (locked / '.install-lock').mkdir(parents=True)
        record('concurrent-install-rejected', install(locked).returncode != 0 and not (locked / 'current').exists())

        malformed = work / 'bad.tar.gz'
        content = bytearray(archive.read_bytes())
        content[len(content) // 2] ^= 1
        malformed.write_bytes(content)
        bad_prefix = work / 'bad-archive'
        (bad_prefix / 'releases/old').mkdir(parents=True)
        (bad_prefix / 'releases/old/sentinel').write_text('old runtime')
        (bad_prefix / 'current').symlink_to('releases/old')
        result = install(bad_prefix, '--archive', malformed)
        record('hash-mismatch-preserves-current', result.returncode != 0 and (bad_prefix / 'current').readlink() == Path('releases/old'))
        malformed.write_bytes(b'truncated')
        record('truncated-archive-rejected', install(bad_prefix, '--archive', malformed).returncode != 0)
        record('failed-install-cleaned', not (bad_prefix / '.install-lock').exists() and not list(bad_prefix.glob('.install-*')))
        record('retry-after-bad-archive', install(bad_prefix).returncode == 0)
        record('previous-release-retained', (bad_prefix / 'releases/old/sentinel').read_text() == 'old runtime')
        installed_resource = bad_prefix / 'current/tex/cmaps/Adobe-GB1-UCS2'
        installed_resource.write_bytes(b'corrupt')
        record('damaged-installed-runtime-rejected', install(bad_prefix).returncode != 0)

        with download_server(work, archive) as (url, cert, state):
            download_prefix = work / 'https-install'
            state['truncate'] = True
            result = install(download_prefix, '--url', url, extra_env={'CURL_CA_BUNDLE': str(cert)})
            record('https-interruption-rejected', result.returncode != 0 and state['requests'] > 0 and not (download_prefix / 'current').exists())
            state['truncate'] = False
            record('real-loopback-https-retry', install(download_prefix, '--url', url, extra_env={'CURL_CA_BUNDLE': str(cert)}).returncode == 0)
            state['downgrade'] = True
            record('https-downgrade-rejected', install(work / 'downgrade', '--url', url, extra_env={'CURL_CA_BUNDLE': str(cert)}).returncode != 0)
            for allowed in (True, False):
                probe = work / ('network-' + str(allowed))
                probe.mkdir()
                bundle = (prefix / 'current').resolve()
                sb = probe / 'network.sb'
                sb.write_text(profile(probe, bundle, extra_read=(cert, '/private/etc/ssl/openssl.cnf'),
                                      network=allowed, fonts_root=bundle / 'tex/fonts'))
                result = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(sb), '/usr/bin/curl', '--noproxy', '*',
                                         '--max-time', '3', '-fsS', '--cacert', str(cert), url.rsplit('/', 1)[0] + '/probe'],
                                        env=env, capture_output=True, text=True, timeout=5)
                record('network-allowed-control' if allowed else 'network-denied',
                       result.returncode == 0 and result.stdout == 'M1PROBE' if allowed
                       else result.returncode != 0 and ('Operation not permitted' in result.stderr or 'Failed to connect' in result.stderr))
        record('plain-http-rejected', install(work / 'http', '--url', 'http://localhost:1/unused').returncode != 0)

        moved = work / 'relocated runtime 中文'
        prefix.rename(moved)
        bundle = (moved / 'current').resolve()
        binaries = []
        for item in bundle.rglob('*'):
            if item.is_file() and not item.is_symlink():
                with item.open('rb') as stream:
                    if stream.read(4) in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
                        binaries.append(item)
        dependencies = subprocess.check_output(['/usr/bin/otool', '-L', *map(str, binaries)], text=True)
        unexpected = [line.strip() for line in dependencies.splitlines() if line.startswith('\t') and
                      not line.strip().startswith(('/usr/lib/', '/System/', '@rpath/', '@loader_path/', '@executable_path/'))]
        record('no-absolute-third-party-dylib-paths', not unexpected)
        report['mach_o_binary_count'] = len(binaries)
        job = work / 'offline'
        job.mkdir()
        sandbox = job / 'outer.sb'
        policy = profile(job, bundle, extra_read=('/bin/cat',), fonts_root=bundle / 'tex/fonts')
        policy += '\n(allow signal (target same-sandbox))\n'
        sandbox.write_text(policy)
        command = ['/usr/bin/sandbox-exec', '-f', str(sandbox), str(bundle / 'resume-runtime'),
                   'self-test', '--outer-sandbox', '--output', str(job / 'samples')]
        attempt = run_bounded(command, job, env | {'HOME': str(job), 'TMPDIR': str(job), 'M1_DEBUG': '1'}, timeout=90, memory_limit_bytes=1024**3)
        evidence.append({'command': 'relocated full-program offline self-test', 'result': attempt,
                         'log': (job / 'process.log').read_text().replace(str(work), '<test-root>')})
        record('relocated-frozen-offline-self-test', attempt['returncode'] == 0)
        if attempt['returncode'] == 0:
            details = json.loads((job / 'samples/results.json').read_text())
            report['self_test'] = details
            report['supervisor'] = attempt
            copied_outputs = {}
            for case, name in [('standard-one-page-target', 'm1-managed-standard.pdf'), ('two-page-target', 'm1-managed-long.pdf')]:
                shutil.copyfile(job / 'samples' / case / 'main.pdf', ROOT / 'output/pdf' / name)
                copied_outputs[name] = digest(ROOT / 'output/pdf' / name)
            report['pdf_sha256'] = copied_outputs

        original_engine = Path(shutil.which('xelatex')).resolve()
        original_python = Path(shutil.which('python3')).resolve()
        targets = [('bundle-file-readable', bundle / 'tex/licenses/LICENSE.TL', True),
                   ('global-tex-unreadable', original_engine, False),
                   ('global-python-unreadable', original_python, False),
                   ('development-fonts-unreadable', ROOT / '.m1-runtime/fonts/NotoSansCJKsc-Regular.otf', False),
                   ('source-fonts-unreadable', ROOT / 'assets/fonts/NotoSansCJKsc-Regular.otf', False),
                   ('system-fonts-unreadable', Path('/System/Library/Fonts/Helvetica.ttc'), False)]
        for name, target, allowed in targets:
            if not target.is_file():
                raise RuntimeError('Font isolation probe needs an existing file: ' + str(target))
            probe = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(sandbox), '/bin/cat', str(target)], env=env, capture_output=True)
            record(name, (probe.returncode == 0) == allowed)

    report['limitations'] = ['Not a clean macOS install; user skipped', 'No public CDN/download availability test',
                             'No Developer ID signing/notarization', 'RSS watchdog is not a hard memory cap',
                             'Only current macOS arm64 validated; no browser acceptance or complete redistribution audit']
    report['failures'] = [name for name, passed in report['checks'].items() if not passed]
    (ROOT / 'docs/m1/managed-results.json').write_bytes(json_bytes(report))
    (ROOT / 'work-logs/evidence/m1-managed-install.json').write_bytes(json_bytes(redact_evidence(evidence, work)))
    return int(bool(report['failures']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe-bundle', type=Path, help='quick outer-sandbox diagnosis without reinstalling')
    args = parser.parse_args()
    if args.probe_bundle:
        bundle = args.probe_bundle.resolve()
        with tempfile.TemporaryDirectory(prefix='offline-probe-', dir=ROOT / '.m1-build') as temporary:
            job = Path(temporary).resolve()
            sandbox = job / 'outer.sb'
            sandbox.write_text(profile(job, bundle, extra_read=('/bin/cat',), fonts_root=bundle / 'tex/fonts') + '\n(allow signal (target same-sandbox))\n')
            command = ['/usr/bin/sandbox-exec', '-f', str(sandbox), str(bundle / 'resume-runtime'), 'self-test', '--outer-sandbox', '--output', str(job / 'samples')]
            result = run_bounded(command, job, {'HOME': str(job), 'TMPDIR': str(job), 'PATH': '/usr/bin:/bin', 'M1_DEBUG': '1'}, timeout=90)
            print((job / 'process.log').read_text())
            for log in job.glob('samples/*/process.log'):
                print(log.parent.name, log.read_text()[-1500:])
            raise SystemExit(0 if result['returncode'] == 0 else 1)
    raise SystemExit(main())
