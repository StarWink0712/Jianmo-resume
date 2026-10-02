import copy
from datetime import datetime, timezone
import hashlib
import io
import uuid
import warnings

from PIL import Image, ImageOps

from backend.examples import EXAMPLES, example_document
from experiments.m1.render import normalized_avatar, RenderError
from experiments.m1.style import STYLE_CONFIG
from scripts.check_contracts import attachment_path, build_case, cases, validate_resume


MAX_AVATAR_UPLOAD_BYTES = 1_000_000
MAX_AVATAR_DECODE_PIXELS = 4096 * 4096
AVATAR_STORED_MAX_EDGE = 1024


class AppError(Exception):
    def __init__(self, status, code, message, **details):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def identifier(kind):
    return kind + '-' + uuid.uuid4().hex


def validate(document, assets=None):
    try:
        errors = validate_resume(document)
    except (TypeError, ValueError, UnicodeError):
        errors = ['invalid JSON data']
    if errors:
        raise AppError(422, 'invalid_resume', '简历数据不符合约定，请检查字段。', fields=errors[:8])
    if assets is not None:
        try:
            normalized_avatar(document, assets)
        except (RenderError, ValueError) as error:
            raise AppError(422, 'invalid_avatar', '头像内容、尺寸或校验信息不正确。') from error


def title(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
        raise AppError(422, 'invalid_title', '简历名称不能为空，且最多 80 个字符。')
    return value.strip()


def expected(value):
    if type(value) is not int or value < 1:
        raise AppError(422, 'invalid_revision', '需要有效的 expected_revision。')
    return value


def clone_resume(document, assets, name):
    validate(document, assets)
    result = copy.deepcopy(document)
    result.update(id=identifier('resume'), revision=1, title=title(name), created_at=now(), updated_at=now())
    for link in result['basics']['links']:
        link['id'] = identifier('link')
    for section in result['sections']:
        section['id'] = identifier('section')
        for entry in section['entries']:
            entry['id'] = identifier('entry')
    copied = {}
    for item in result['attachments']:
        content = assets[attachment_path(item)]
        item['id'] = identifier('asset')
        result['basics']['avatar_attachment_id'] = item['id']
        copied[attachment_path(item)] = content
    return result, copied


def new_resume(name, kind):
    if isinstance(kind, str) and kind in EXAMPLES:
        return clone_resume(example_document(kind), {}, name)
    if kind not in ('blank', 'sample'):
        raise AppError(422, 'invalid_kind', '请选择空白简历或受支持的参考简历。')
    case_id = 'blank' if kind == 'blank' else 'standard-one-page-target'
    document, assets = build_case(next(item for item in cases() if item['id'] == case_id))
    document['basics'].update(gender='', age=None)
    document['style'] = copy.deepcopy(STYLE_CONFIG['defaults'])
    return clone_resume(document, assets, name)


def decode_avatar(content):
    if len(content) > MAX_AVATAR_UPLOAD_BYTES:
        raise AppError(413, 'avatar_too_large', '头像文件不能超过 1 MB。')
    try:
        with warnings.catch_warnings(action='error', category=Image.DecompressionBombWarning), Image.open(io.BytesIO(content)) as image:
            if image.format not in ('PNG', 'JPEG') or min(image.size) < 1:
                raise ValueError('unsupported image')
            if image.width * image.height > MAX_AVATAR_DECODE_PIXELS:
                raise AppError(422, 'avatar_decode_limit', '图片解码后的像素占用过大，请压缩图片后重试。')
            image.load()
            oriented = ImageOps.exif_transpose(image)
            oriented.thumbnail((AVATAR_STORED_MAX_EDGE, AVATAR_STORED_MAX_EDGE), Image.Resampling.LANCZOS)
            rgba = oriented.convert('RGBA')
            clean = Image.new('RGB', oriented.size, 'white')
            clean.paste(rgba, mask=rgba.getchannel('A'))
            out = io.BytesIO()
            clean.save(out, format='PNG')
            data = out.getvalue()
            # Bound the stored artifact without imposing another upload size/dimension rule.
            # A metadata-free 1024x1024 RGB PNG fits the existing 5 MiB backup contract.
            return {'id': identifier('asset'), 'media_type': 'image/png', 'byte_size': len(data),
                    'sha256': hashlib.sha256(data).hexdigest(), 'width_px': clean.width, 'height_px': clean.height}, data
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise AppError(422, 'invalid_avatar', '图片无法安全读取，请使用有效的 JPG、JPEG 或 PNG 文件。') from error
