"""Fictional avatar fixtures and real HTTP/PDF checks for the enlarged photo box."""
import argparse
import io
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw
from pypdf import PdfReader
from backend.backup import import_backup
from scripts.check_backend import Harness
from scripts.check_contracts import json_bytes


def fixtures(directory):
    directory.mkdir(parents=True, exist_ok=True)
    image = Image.new('RGB', (1200, 900), '#edf3f6')
    draw = ImageDraw.Draw(image)
    for x, color in [(0, '#df8a72'), (400, '#7bb5c5'), (800, '#b8c69a')]:
        draw.rectangle((x, 0, x + 399, 899), fill=color)
    draw.rectangle((0, 0, 1199, 90), fill='#203953')
    draw.ellipse((490, 205, 710, 425), fill='#f5dab9')
    draw.rounded_rectangle((405, 440, 795, 930), radius=95, fill='#f4f6ed')
    draw.rectangle((570, 485, 630, 810), fill='#203953')
    image.save(directory / 'portrait-source.jpg', quality=92)
    image.save(directory / 'portrait-source.png')
    exif = Image.Exif(); exif[274] = 6
    image.rotate(90, expand=True).save(directory / 'portrait-oriented.jpeg', quality=92, exif=exif)
    transparent = Image.new('RGBA', (600, 800), (0, 0, 0, 0))
    ImageDraw.Draw(transparent).ellipse((180, 150, 420, 500), fill='#2457a7')
    transparent.save(directory / 'portrait-transparent.png')
    image.save(directory / 'invalid-format.png', format='GIF')
    (directory / 'oversized.png').write_bytes(b'x' * 1_000_001)
    return image


def image_placements(page):
    stack, matrix, result = [], [1, 0, 0, 1, 0, 0], []
    def before(operator, arguments, _cm, _tm):
        nonlocal matrix
        if operator == b'q':
            stack.append(matrix[:])
        elif operator == b'Q':
            matrix = stack.pop()
        elif operator == b'cm':
            a, b, c, d, e, f = map(float, arguments)
            A, B, C, D, E, F = matrix
            matrix = [a*A+b*C, a*B+b*D, c*A+d*C, c*B+d*D, e*A+f*C+E, e*B+f*D+F]
        elif operator == b'Do':
            asset = page['/Resources']['/XObject'][arguments[0]].get_object()
            if asset.get('/Subtype') == '/Image':
                result.append(matrix[:])
    page.extract_text(visitor_operand_before=before)
    return result


def run(h, directory):
    h.start()
    source = fixtures(directory).crop((263, 0, 938, 900)).resize((600, 800))
    buffer = io.BytesIO(); source.save(buffer, format='JPEG', quality=92)
    document = h.request('POST', '/api/resumes', 201, json={'title': 'Avatar crop check', 'kind': 'sample'}).json()['resume']
    document = h.request('PUT', f'/api/resumes/{document["id"]}/avatar?expected_revision=1',
                         content=buffer.getvalue(), headers={'Content-Type': 'application/octet-stream'}).json()['resume']
    image = h.request('GET', f'/api/resumes/{document["id"]}/avatar',
                      params={'attachment_id': document['attachments'][0]['id']}).content
    with Image.open(io.BytesIO(image)) as stored:
        assert stored.size == (600, 800) and not stored.getexif()
    archive = h.request('GET', f'/api/resumes/{document["id"]}/backup?expected_revision={document["revision"]}').content
    restored, assets = import_backup(archive)
    assert restored == document and list(assets.values()) == [image]
    placements = []
    for margin in (24, 120):
        document['style']['margins_px'].update(left=margin, right=margin)
        document = h.save(document)
        job = h.compile(document)
        data = h.request('GET', f'/api/jobs/{job["id"]}/pdf').content
        path = directory / f'avatar-{margin}px-margin.pdf'; path.write_bytes(data)
        page = PdfReader(path).pages[0]
        boxes = image_placements(page)
        assert len(boxes) == 1
        a, b, c, d, x, y = boxes[0]
        assert abs(a - 24 * 72 / 25.4) < .02 and abs(d - 32 * 72 / 25.4) < .02
        assert abs(b) + abs(c) < .001
        assert x >= margin * .75 and x + a <= float(page.mediabox.width) - margin * .75 + .02
        assert 0 < y < float(page.mediabox.height) - d
        placements.append({'margin_px': margin, 'width_mm': round(a * 25.4 / 72, 3),
                           'height_mm': round(d * 25.4 / 72, 3), 'pages': job['pages']})
    return {'passed': True, 'stored_size': [600, 800], 'backup_preserves_image': True, 'placements': placements}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixtures-only', action='store_true')
    args = parser.parse_args()
    directory = ROOT / 'tmp/m2/avatar-crop-check'
    if args.fixtures_only:
        fixtures(directory)
        print('Fictional image fixtures prepared in tmp/m2/avatar-crop-check')
        return
    with tempfile.TemporaryDirectory(prefix='avatar-crop-', dir=ROOT / 'tmp/m2') as temporary:
        h = Harness(Path(temporary), (ROOT / '.m1-build/local-install/current').resolve(), 8774)
        try:
            report = run(h, directory)
        finally:
            h.stop(); h.client.close()
    (ROOT / 'work-logs/evidence/m2-avatar-crop.json').write_bytes(json_bytes(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
