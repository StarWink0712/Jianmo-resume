from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import threading

from backend import backup
from backend.compiler import Compiler
from backend.domain import AppError, clone_resume, decode_avatar, expected, identifier, new_resume, now, title, validate
from backend.store import Store
from scripts.check_contracts import attachment_path


class Service:
    def __init__(self, directory, runtime=None, compiler=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lease = (self.directory / '.instance-lock').open('a')
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.lease.close()
            raise AppError(409, 'already_running', '这个数据目录已有服务运行。') from error
        try:
            self.compiler = compiler or Compiler(runtime)
            self.store = Store(self.directory / 'resumes.sqlite3')
        except BaseException:
            self.lease.close()
            raise
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='resume-compile')
        self.closed = False
        self.submit_lock = threading.Lock()

    def key(self, document):
        value = [document['id'], document['revision'], document['template'], self.compiler.fingerprint]
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def detail(self, resume_id):
        with self.store.lock:
            document = self.store.get(resume_id)
            return {'resume': document, 'latest_job': self.store.job_summary(resume_id),
                    'pdf': self.store.job_summary(resume_id, True), 'build_key': self.key(document)}

    def list(self):
        with self.store.lock:
            return [{'id': doc['id'], 'title': doc['title'], 'revision': doc['revision'],
                     'headline': doc['basics']['headline'], 'name': doc['basics']['name'], 'updated_at': doc['updated_at']}
                    for doc in self.store.documents()]

    def create(self, name, kind):
        document, assets = new_resume(name, kind)
        with self.store.lock:
            self.store.insert(document, assets)
            return self.detail(document['id'])

    def save(self, resume_id, revision, document):
        # The acknowledgment must describe this write, not a later concurrent writer.
        with self.store.lock:
            saved = self.store.save(resume_id, revision, document)
            return self.detail(saved['id'])

    def copy(self, resume_id, revision, name, version='saved', draft=None):
        with self.store.lock:
            document = self.store.check_revision(resume_id, revision)
            if self.store.busy(resume_id):
                raise AppError(409, 'busy', '请等待源简历编译完成后再创建副本。')
            if version == 'draft':
                validate(draft)
                if draft['id'] != resume_id or draft['revision'] != revision:
                    raise AppError(422, 'invalid_draft', '草稿必须属于当前简历和已知修订。')
                document = draft
            elif version != 'saved' or draft is not None:
                raise AppError(422, 'invalid_copy', '请明确选择已保存版本或当前草稿。')
            copied, assets = clone_resume(document, self.store.assets(document), name)
            self.store.insert(copied, assets)
            return self.detail(copied['id'])

    def rename(self, resume_id, revision, name):
        with self.store.lock:
            document = self.store.check_revision(resume_id, revision)
            if self.store.busy(resume_id):
                raise AppError(409, 'busy', '请等待编译完成后再重命名。')
            document['title'] = title(name)
            self.store.save(resume_id, revision, document)
            return self.detail(resume_id)

    def read_avatar(self, resume_id, attachment_id):
        with self.store.lock:
            document = self.store.get(resume_id)
            if not document['attachments']:
                raise AppError(404, 'no_avatar', '这份简历尚未设置头像。')
            item = document['attachments'][0]
            if item['id'] != attachment_id:
                raise AppError(409, 'avatar_changed', '头像已在其他页面修改，请重新载入简历后再调整。')
            return self.store.assets(document)[attachment_path(item)], item['media_type']

    def avatar(self, resume_id, revision, content):
        metadata, data = decode_avatar(content)
        with self.store.lock:
            document = self.store.check_revision(resume_id, revision)
            document['attachments'] = [metadata]
            document['basics'].update(avatar_attachment_id=metadata['id'], avatar_visible=True)
            self.store.save(resume_id, revision, document, {attachment_path(metadata): data})
            return self.detail(resume_id)

    def export(self, resume_id, revision):
        with self.store.lock:
            document = self.store.check_revision(resume_id, revision)
            return backup.export_backup(document, self.store.assets(document))

    def import_file(self, content):
        document, assets = backup.import_backup(content)
        copied, assets = clone_resume(document, assets, document['title'][:76] + '（导入）')
        with self.store.lock:
            self.store.insert(copied, assets)
            return self.detail(copied['id'])

    def enqueue(self, resume_id, revision):
        with self.submit_lock, self.store.transaction():
            if self.closed:
                raise AppError(503, 'stopping', '服务正在退出。')
            document = self.store.check_revision(resume_id, revision)
            key = self.key(document)
            found = self.store.db.execute("SELECT id FROM jobs WHERE build_key=? AND status IN ('queued','running','succeeded') ORDER BY rowid DESC LIMIT 1", (key,)).fetchone()
            if found:
                return self.store.job(found[0])
            pending = self.store.db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
            if pending >= 32:
                raise AppError(429, 'queue_full', '编译队列已满，请稍后重试。')
            job_id = identifier('job')
            self.store.db.execute('INSERT INTO jobs(id,resume_id,revision,build_key,status,created_at) VALUES(?,?,?,?,?,?)',
                                  (job_id, resume_id, expected(revision), key, 'queued', now()))
            self.executor.submit(self._compile, job_id)
            return self.store.job(job_id)

    def _compile(self, job_id):
        work = self.directory / 'jobs' / job_id
        try:
            with self.store.transaction():
                job = self.store.job(job_id)
                if job['status'] != 'queued':
                    return
                self.store.db.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
                document = self.store.get(job['resume_id'], job['revision'])
                assets = self.store.assets(document)
            work.mkdir(parents=True, exist_ok=False, mode=0o700)
            pdf, pages = self.compiler(document, assets, work)
            if not pdf.startswith(b'%PDF-') or len(pdf) > 64 * 1024**2:
                raise AppError(422, 'invalid_pdf', '生成的 PDF 无效或过大。')
            with self.store.transaction():
                self.store.db.execute("UPDATE jobs SET status='succeeded',pdf=?,pages=?,error=NULL WHERE id=? AND status='running'", (pdf, pages, job_id))
        except Exception as error:
            message = error.message if isinstance(error, AppError) else '编译失败。保存内容保留，可重试；若持续发生请执行自检。'
            status = 'timed_out' if isinstance(error, AppError) and error.code == 'timed_out' else 'failed'
            with self.store.transaction():
                self.store.db.execute('UPDATE jobs SET status=?,error=? WHERE id=?', (status, message, job_id))
        finally:
            # TeX logs contain user content: do not retain them as normal service logs.
            shutil.rmtree(work, ignore_errors=True)

    def pdf(self, job_id):
        job = self.store.job(job_id, True)
        if job['status'] != 'succeeded' or job['pdf'] is None:
            raise AppError(409, 'pdf_unavailable', '这次任务还没有成功的 PDF。')
        return job

    def close(self):
        with self.submit_lock:
            if self.closed:
                return
            self.closed = True
            with self.store.transaction():
                self.store.db.execute("UPDATE jobs SET status='cancelled',error='服务退出，排队任务已取消。' WHERE status='queued'")
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.store.close()
        self.lease.close()
