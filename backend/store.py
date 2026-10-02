"""Transactional snapshots; PDFs and immutable attachments live in the same SQLite DB."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading

from backend.domain import AppError, expected, now, validate
from scripts.check_contracts import attachment_path, json_bytes


class Store:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=5)
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise AppError(503, 'database_version', '数据版本高于当前程序，拒绝打开。')
        existing = self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='resumes'").fetchone()
        initial_examples = 'skipped-existing' if existing else 'pending'
        self.db.executescript(f'''
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS resumes(id TEXT PRIMARY KEY, revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS revisions(
                resume_id TEXT NOT NULL REFERENCES resumes(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL, document TEXT NOT NULL,
                PRIMARY KEY(resume_id,revision));
            CREATE TABLE IF NOT EXISTS blobs(sha256 TEXT PRIMARY KEY, content BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY, resume_id TEXT NOT NULL, revision INTEGER NOT NULL,
                build_key TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
                pages INTEGER, pdf BLOB, created_at TEXT NOT NULL,
                FOREIGN KEY(resume_id,revision) REFERENCES revisions(resume_id,revision) ON DELETE CASCADE);
            CREATE INDEX IF NOT EXISTS jobs_build ON jobs(build_key,status);
            CREATE TABLE IF NOT EXISTS app_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT OR IGNORE INTO app_metadata VALUES('bundled_examples', '{initial_examples}');
            PRAGMA user_version=1;
            COMMIT;
        ''')
        self.db.execute("UPDATE jobs SET status='failed',error='服务上次退出时任务未完成，请重新编译。' WHERE status IN ('queued','running')")

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise

    def get(self, resume_id, revision=None):
        with self.lock:
            if revision is None:
                row = self.db.execute('SELECT v.document FROM resumes r JOIN revisions v ON r.id=v.resume_id AND r.revision=v.revision WHERE r.id=?', (resume_id,)).fetchone()
            else:
                row = self.db.execute('SELECT document FROM revisions WHERE resume_id=? AND revision=?', (resume_id, revision)).fetchone()
            if row is None:
                raise AppError(404, 'not_found', '这份简历或修订不存在。')
            return json.loads(row['document'])

    def check_revision(self, resume_id, revision):
        document = self.get(resume_id)
        if document['revision'] != expected(revision):
            raise AppError(409, 'revision_conflict', '简历已在其他页面更新。本地输入已保留，请重新载入或创建副本。', current_revision=document['revision'])
        return document

    def assets(self, document):
        result = {}
        with self.lock:
            for item in document['attachments']:
                row = self.db.execute('SELECT content FROM blobs WHERE sha256=?', (item['sha256'],)).fetchone()
                if row is None:
                    raise AppError(422, 'missing_asset', '头像数据不存在，请重新上传。')
                result[attachment_path(item)] = bytes(row['content'])
        return result

    def put_blobs(self, document, assets):
        validate(document, assets)
        for item in document['attachments']:
            self.db.execute('INSERT OR IGNORE INTO blobs VALUES(?,?)', (item['sha256'], assets[attachment_path(item)]))

    def _insert(self, document, assets):
        self.put_blobs(document, assets)
        self.db.execute('INSERT INTO resumes VALUES(?,?)', (document['id'], document['revision']))
        self.db.execute('INSERT INTO revisions VALUES(?,?,?)', (document['id'], document['revision'], json_bytes(document).decode()))

    def initialize_examples(self, factory, enabled=True):
        with self.transaction():
            state = self.db.execute("SELECT value FROM app_metadata WHERE key='bundled_examples'").fetchone()[0]
            if state != 'pending':
                return
            # A durable marker, not an empty-list check, prevents deleted examples returning.
            if enabled and not self.db.execute('SELECT 1 FROM resumes LIMIT 1').fetchone():
                for document, assets in factory():
                    self._insert(document, assets)
            self.db.execute("UPDATE app_metadata SET value='complete' WHERE key='bundled_examples'")

    def insert(self, document, assets):
        with self.transaction():
            self._insert(document, assets)
        return document

    def save(self, resume_id, revision, document, added_assets=None):
        with self.transaction():
            old = self.check_revision(resume_id, revision)
            validate(document)
            if any(document[key] != old[key] for key in ('id', 'revision', 'created_at', 'updated_at')):
                raise AppError(422, 'immutable_fields', '标识、修订和时间由服务端管理。')
            assets = added_assets if added_assets is not None else self.assets(document)
            self.put_blobs(document, assets)
            if document == old:
                return old
            saved = dict(document, revision=old['revision'] + 1, updated_at=max(now(), old['updated_at']))
            self.db.execute('INSERT INTO revisions VALUES(?,?,?)', (resume_id, saved['revision'], json_bytes(saved).decode()))
            self.db.execute('UPDATE resumes SET revision=? WHERE id=?', (saved['revision'], resume_id))
        return saved

    def busy(self, resume_id):
        return self.db.execute("SELECT 1 FROM jobs WHERE resume_id=? AND status IN ('queued','running')", (resume_id,)).fetchone() is not None

    def delete(self, resume_id, revision):
        with self.transaction():
            self.check_revision(resume_id, revision)
            if self.busy(resume_id):
                raise AppError(409, 'busy', '请等待编译完成后再删除。')
            self.db.execute('DELETE FROM resumes WHERE id=?', (resume_id,))

    def documents(self):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute('SELECT v.document FROM resumes r JOIN revisions v ON r.id=v.resume_id AND r.revision=v.revision ORDER BY v.rowid DESC')]

    def job(self, job_id, with_pdf=False):
        with self.lock:
            columns = '*' if with_pdf else 'id,resume_id,revision,build_key,status,error,pages,created_at'
            row = self.db.execute('SELECT ' + columns + ' FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise AppError(404, 'job_not_found', '编译任务不存在。')
            return dict(row)

    def job_summary(self, resume_id, successful=False):
        with self.lock:
            condition = " AND status='succeeded'" if successful else ''
            order = 'revision DESC,rowid DESC' if successful else 'rowid DESC'
            row = self.db.execute('SELECT id FROM jobs WHERE resume_id=?' + condition + ' ORDER BY ' + order + ' LIMIT 1', (resume_id,)).fetchone()
            return self.job(row[0]) if row else None

    def close(self):
        with self.lock:
            self.db.close()
