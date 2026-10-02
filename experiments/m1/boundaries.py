"""Executable boundary experiments, not the production FastAPI service/installer."""

from contextlib import contextmanager
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


def authorize(method, headers, origin, token):
    if hasattr(headers, 'get_all') and any(len(headers.get_all(name, [])) > 1 for name in ('Host', 'Origin', 'X-Resume-Token', 'Content-Type')):
        return 400
    expected_host = urlsplit(origin).netloc
    if headers.get('Host') != expected_host:
        return 403
    supplied_origin = headers.get('Origin')
    if supplied_origin is not None and supplied_origin != origin:
        return 403
    if method != 'GET' and supplied_origin != origin:
        return 403
    if not hmac.compare_digest(headers.get('X-Resume-Token', '').encode('utf-8'), token.encode('utf-8')):
        return 403
    if method == 'POST' and headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
        return 415
    return 200


@contextmanager
def boundary_server():
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(2)

        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def respond(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            code = authorize(self.command, self.headers, origin, token)
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(b'{"probe":true}' if code == 200 else b'{"error":"request_rejected"}')

        def log_message(self, _format, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', token
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def fetch_verified(url, target, expected_sha256, expected_size, opener=urlopen):
    """Download validation/atomic-promotion spike; no archive extraction or execution."""
    if urlsplit(url).scheme != 'https':
        raise ValueError('HTTPS required')
    if not re.fullmatch('[0-9a-f]{64}', expected_sha256) or not 0 < expected_size <= 4 * 1024 ** 3:
        raise ValueError('invalid pinned artifact metadata')
    target = Path(target)
    if target.is_file() and target.stat().st_size == expected_size:
        with target.open('rb') as existing:
            if hashlib.file_digest(existing, 'sha256').hexdigest() == expected_sha256:
                return 'cached'
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.download-', dir=target.parent)
    try:
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(fd, 'wb') as output, opener(Request(url), timeout=15) as response:
            if urlsplit(response.geturl()).scheme != 'https':
                raise ValueError('insecure redirect')
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > expected_size:
                    raise ValueError('download exceeds pinned size')
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if total != expected_size or digest.hexdigest() != expected_sha256:
            raise ValueError('download size or SHA-256 mismatch')
        os.replace(temporary, target)
        return 'downloaded'
    finally:
        Path(temporary).unlink(missing_ok=True)
