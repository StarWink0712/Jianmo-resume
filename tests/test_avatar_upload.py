import hashlib
import io
import json
import subprocess
import unittest

from PIL import Image

from backend.domain import AppError, AVATAR_STORED_MAX_EDGE, MAX_AVATAR_UPLOAD_BYTES, MAX_AVATAR_DECODE_PIXELS, decode_avatar
from backend.backup import export_backup, import_backup
from experiments.m1.render import normalized_avatar
from scripts.check_contracts import ROOT, build_case, cases, attachment_path


def picture(fmt='PNG', size=(80, 120), mode='RGB', color='red', **kwargs):
    stream = io.BytesIO()
    Image.new(mode, size, color).save(stream, format=fmt, **kwargs)
    return stream.getvalue()


class AvatarUploadTests(unittest.TestCase):
    def test_frontend_and_backend_share_one_mb_boundary(self):
        limit = json.loads(subprocess.check_output(['node', '--input-type=module', '-e',
            "import {MAX_AVATAR_UPLOAD_BYTES} from './web/avatar-model.mjs'; console.log(JSON.stringify(MAX_AVATAR_UPLOAD_BYTES));"], cwd=ROOT))
        self.assertEqual(limit, MAX_AVATAR_UPLOAD_BYTES)
        pixels = json.loads(subprocess.check_output(['node', '--input-type=module', '-e',
            "import {MAX_AVATAR_DECODE_PIXELS} from './web/avatar-crop-model.mjs'; console.log(JSON.stringify(MAX_AVATAR_DECODE_PIXELS));"], cwd=ROOT))
        self.assertEqual(pixels, MAX_AVATAR_DECODE_PIXELS)

    def test_jpeg_png_and_exact_limit_are_supported(self):
        for fmt in ('JPEG', 'PNG'):
            content = picture(fmt)
            content += b'\0' * (MAX_AVATAR_UPLOAD_BYTES - len(content))
            metadata, data = decode_avatar(content)
            self.assertEqual((metadata['width_px'], metadata['height_px']), (80, 120))
            self.assertEqual(metadata['sha256'], hashlib.sha256(data).hexdigest())
            self.assertEqual(metadata['media_type'], 'image/png')
            self.assertEqual(metadata['byte_size'], len(data))

    def test_one_byte_over_the_limit_is_rejected(self):
        with self.assertRaises(AppError) as raised:
            decode_avatar(b'x' * (MAX_AVATAR_UPLOAD_BYTES + 1))
        self.assertEqual(raised.exception.code, 'avatar_too_large')
        self.assertEqual(raised.exception.status, 413)

    def test_large_dimensions_are_resized_not_rejected(self):
        for size in [(5000, 1000), (1000, 5000)]:
            metadata, data = decode_avatar(picture(size=size))
            self.assertEqual(max(metadata['width_px'], metadata['height_px']), AVATAR_STORED_MAX_EDGE)
            self.assertAlmostEqual(metadata['width_px'] / metadata['height_px'], size[0] / size[1], delta=.01)
            self.assertLess(len(data), 5 * 1024**2)
        metadata, _ = decode_avatar(picture(size=(8, 70)))
        self.assertEqual((metadata['width_px'], metadata['height_px']), (8, 70))

    def test_exif_orientation_and_transparency_are_normalized(self):
        exif = Image.Exif()
        exif[274] = 6
        metadata, data = decode_avatar(picture('JPEG', size=(80, 120), exif=exif))
        self.assertEqual((metadata['width_px'], metadata['height_px']), (120, 80))
        with Image.open(io.BytesIO(data)) as clean:
            self.assertFalse(clean.getexif())
        _, data = decode_avatar(picture(mode='RGBA', color=(255, 0, 0, 0)))
        with Image.open(io.BytesIO(data)) as clean:
            self.assertEqual(clean.getpixel((0, 0)), (255, 255, 255))

    def test_malformed_and_disguised_formats_are_rejected(self):
        for content in (b'', b'not a picture', picture('GIF'), picture()[:40]):
            with self.subTest(size=len(content)), self.assertRaises(AppError) as raised:
                decode_avatar(content)
            self.assertEqual(raised.exception.status, 422)

    def test_tiny_compressed_file_cannot_trigger_unbounded_decode(self):
        # PNG header dimensions are inspected before pixel allocation/decoding.
        import struct
        import zlib
        content = bytearray(picture())
        content[16:24] = struct.pack('!II', 6000, 4000)
        content[29:33] = struct.pack('!I', zlib.crc32(content[12:29]) & 0xffffffff)
        with self.assertRaises(AppError) as raised:
            decode_avatar(bytes(content))
        self.assertEqual(raised.exception.code, 'avatar_decode_limit')

    def test_old_stored_avatar_over_one_mb_still_imports_and_renders(self):
        document, assets = build_case(next(case for case in cases() if case['id'] == 'avatar'))
        metadata = document['attachments'][0]
        path = attachment_path(metadata)
        assets[path] += b'\0' * (MAX_AVATAR_UPLOAD_BYTES + 100 - len(assets[path]))
        metadata.update(byte_size=len(assets[path]), sha256=hashlib.sha256(assets[path]).hexdigest())
        self.assertTrue(normalized_avatar(document, assets))
        self.assertEqual(import_backup(export_backup(document, assets)), (document, assets))
