import io
import re
import stat
import zipfile
import zlib

from backend.domain import AppError, validate
from scripts.check_contracts import json_bytes, make_manifest, read_json, validate_backup


MAX_ARCHIVE = 25 * 1024**2


def export_backup(document, assets):
    manifest, payloads = make_manifest(document, assets)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json_bytes(manifest))
        for name, content in payloads.items():
            archive.writestr(name, content)
    return stream.getvalue()


def import_backup(content):
    if len(content) > MAX_ARCHIVE:
        raise AppError(413, 'backup_too_large', '工程备份不能超过 25 MiB。')
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            if not 2 <= len(members) <= 3 or len(names) != len(set(names)):
                raise ValueError('invalid members')
            files = {}
            for item in members:
                mode = stat.S_IFMT(item.external_attr >> 16)
                if (item.is_dir() or mode not in (0, stat.S_IFREG) or item.flag_bits & 1
                        or item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)):
                    raise ValueError('unsupported member')
                if item.filename == 'manifest.json':
                    limit = 64 * 1024
                elif item.filename == 'resume.json':
                    limit = 2 * 1024**2
                elif re.fullmatch(r'assets/[a-z][a-z0-9_-]{0,63}\.(png|jpg)', item.filename):
                    limit = 5 * 1024**2
                else:
                    raise ValueError('unsafe path')
                if item.file_size > limit:
                    raise ValueError('oversized member')
                with archive.open(item) as source:
                    data = source.read(limit + 1)
                if len(data) > limit:
                    raise ValueError('oversized actual content')
                files[item.filename] = data
            manifest = read_json(files.pop('manifest.json'))
            if validate_backup(manifest, files):
                raise ValueError('invalid manifest')
            document = read_json(files.pop('resume.json'))
            validate(document, files)
            return document, files
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError, zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError) as error:
        raise AppError(422, 'invalid_backup', '备份结构、版本、附件或校验不正确，未导入任何内容。') from error
