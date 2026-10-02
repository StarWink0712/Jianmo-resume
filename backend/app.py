from contextlib import asynccontextmanager
import hmac
import secrets
import sqlite3
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from backend.domain import AppError, MAX_AVATAR_UPLOAD_BYTES
from backend.service import Service
from scripts.check_contracts import ROOT, read_json


class Boundary:
    def __init__(self, app, origin, token):
        self.app, self.origin, self.token = app, origin, token

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = scope['headers']
        get = lambda key: next((v.decode('latin1') for k, v in headers if k == key), None)
        duplicates = any(sum(k == name for k, _ in headers) > 1 for name in (b'host', b'origin', b'x-resume-token', b'content-type', b'content-length'))
        code = 400 if duplicates else None
        if get(b'host') != urlsplit(self.origin).netloc or get(b'origin') not in (None, self.origin):
            code = 403
        if scope['path'].startswith('/api/') and scope['path'] != '/api/health':
            if scope['path'] == '/api/session' and scope['method'] == 'GET':
                if get(b'x-resume-bootstrap') != '1' or get(b'sec-fetch-site') not in (None, 'same-origin', 'none'):
                    code = 403
            else:
                if not hmac.compare_digest((get(b'x-resume-token') or '').encode(), self.token.encode()):
                    code = 403
            if scope['method'] not in ('GET', 'HEAD') and get(b'origin') != self.origin:
                code = 403
        if code:
            return await JSONResponse({'code': 'request_rejected', 'message': '请求来源或访问令牌不正确，请从本机服务页面重新打开。'}, status_code=code)(scope, receive, send)

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                message.setdefault('headers', []).extend([
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer'), (b'x-frame-options', b'SAMEORIGIN'),
                    (b'content-security-policy', b"default-src 'self'; script-src 'self'; worker-src 'self'; style-src 'self'; connect-src 'self' blob:; font-src 'self' blob:; img-src 'self' blob: data:; frame-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")])
            await send(message)
        await self.app(scope, receive, secure_send)


async def body(request, content_type='application/json', limit=2 * 1024**2):
    if request.headers.get('content-type', '').split(';')[0].strip() != content_type:
        raise AppError(415, 'content_type', '请求内容类型不正确。')
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > limit:
            raise AppError(413, 'request_too_large', '请求超过大小限制。')
        data.extend(chunk)
    return bytes(data)


async def fields(request, required, optional=()):
    try:
        value = read_json(await body(request))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise AppError(422, 'invalid_json', 'JSON 不合法，不能包含重复字段或非有限数值。') from error
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise AppError(422, 'invalid_request', '请求字段不正确。')
    return value


def create_app(directory, runtime=None, origin='http://127.0.0.1:8770', compiler=None):
    from experiments.m1.fonts import FONT_FILES, font_media_type, verify_fonts

    service = Service(directory, runtime, compiler)
    fonts_root = verify_fonts(getattr(service.compiler, 'fonts_root', ROOT / 'assets/fonts'))
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        await run_in_threadpool(service.close)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    app.add_middleware(Boundary, origin=origin, token=token)

    @app.exception_handler(AppError)
    async def app_error(_request, error):
        return JSONResponse({'code': error.code, 'message': error.message, **error.details}, status_code=error.status)

    @app.exception_handler(sqlite3.Error)
    async def database_error(_request, _error):
        return JSONResponse({'code': 'storage_failed', 'message': '本地写入失败，未确认保存；请检查磁盘空间和目录权限后重试。'}, status_code=503)

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'web/index.html')

    assets = {'app.js': ROOT / 'web/app.js', 'viewer.js': ROOT / 'web/viewer.js',
              'style-model.mjs': ROOT / 'web/style-model.mjs', 'style-editor.mjs': ROOT / 'web/style-editor.mjs',
              'markdown-model.mjs': ROOT / 'web/markdown-model.mjs', 'markdown-editor.mjs': ROOT / 'web/markdown-editor.mjs',
              'section-model.mjs': ROOT / 'web/section-model.mjs',
              'avatar-model.mjs': ROOT / 'web/avatar-model.mjs',
              'style-config.json': ROOT / 'web/style-config.json',
              'app.css': ROOT / 'web/app.css', 'editor.css': ROOT / 'docs/m0/editor-wireframe.css',
              'pdf.min.mjs': ROOT / 'web/vendor/pdfjs/pdf.min.mjs',
              'pdf.worker.min.mjs': ROOT / 'web/vendor/pdfjs/pdf.worker.min.mjs'}
    assets.update({name: fonts_root / name for name in FONT_FILES})

    @app.get('/assets/{name}')
    def static(name):
        if name not in assets:
            raise AppError(404, 'not_found', '文件不存在。')
        media_type = font_media_type(name) if name in FONT_FILES else ('text/javascript' if name.endswith(('.js', '.mjs')) else 'text/css')
        if name == 'style-config.json':
            media_type = 'application/json'
        return FileResponse(assets[name], media_type=media_type)

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'stage': 'M2', 'runtime_fingerprint': service.compiler.fingerprint}

    @app.get('/api/session')
    def session():
        return {'token': token}

    @app.get('/api/resumes')
    def list_resumes():
        return service.list()

    @app.post('/api/resumes', status_code=201)
    async def create(request: Request):
        value = await fields(request, ('title', 'kind'))
        return await run_in_threadpool(service.create, value['title'], value['kind'])

    @app.get('/api/resumes/{resume_id}')
    def detail(resume_id: str):
        return service.detail(resume_id)

    @app.put('/api/resumes/{resume_id}')
    async def save(resume_id: str, request: Request):
        value = await fields(request, ('expected_revision', 'resume'))
        return await run_in_threadpool(service.save, resume_id, value['expected_revision'], value['resume'])

    @app.patch('/api/resumes/{resume_id}')
    async def rename(resume_id: str, request: Request):
        value = await fields(request, ('expected_revision', 'title'))
        return await run_in_threadpool(service.rename, resume_id, value['expected_revision'], value['title'])

    @app.delete('/api/resumes/{resume_id}')
    async def delete(resume_id: str, request: Request):
        value = await fields(request, ('expected_revision',))
        await run_in_threadpool(service.store.delete, resume_id, value['expected_revision'])
        return {'deleted': True}

    @app.post('/api/resumes/{resume_id}/copy', status_code=201)
    async def duplicate(resume_id: str, request: Request):
        value = await fields(request, ('expected_revision', 'title', 'version'), ('draft',))
        return await run_in_threadpool(service.copy, resume_id, value['expected_revision'], value['title'], value['version'], value.get('draft'))

    @app.post('/api/resumes/{resume_id}/compile', status_code=202)
    async def compile_resume(resume_id: str, request: Request):
        value = await fields(request, ('expected_revision',))
        return await run_in_threadpool(service.enqueue, resume_id, value['expected_revision'])

    @app.get('/api/jobs/{job_id}')
    def job(job_id: str):
        return service.store.job(job_id)

    @app.get('/api/jobs/{job_id}/pdf')
    def pdf(job_id: str, download: bool = False):
        job = service.pdf(job_id)
        disposition = 'attachment' if download else 'inline'
        return Response(bytes(job['pdf']), media_type='application/pdf', headers={
            'Content-Disposition': f'{disposition}; filename="{job["resume_id"]}-r{job["revision"]}.pdf"',
            'X-Resume-Revision': str(job['revision']), 'X-Build-Key': job['build_key']})

    @app.put('/api/resumes/{resume_id}/avatar')
    async def avatar(resume_id: str, request: Request, expected_revision: int):
        try:
            content = await body(request, 'application/octet-stream', MAX_AVATAR_UPLOAD_BYTES)
        except AppError as error:
            if error.code == 'request_too_large':
                raise AppError(413, 'avatar_too_large', '头像文件不能超过 1 MB。') from error
            raise
        return await run_in_threadpool(service.avatar, resume_id, expected_revision, content)

    @app.get('/api/resumes/{resume_id}/backup')
    def export(resume_id: str, expected_revision: int):
        content = service.export(resume_id, expected_revision)
        return Response(content, media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="{resume_id}-r{expected_revision}.resume.zip"'})

    @app.post('/api/import', status_code=201)
    async def import_file(request: Request):
        content = await body(request, 'application/zip', 25 * 1024**2)
        return await run_in_threadpool(service.import_file, content)

    return app
