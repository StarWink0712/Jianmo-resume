"""Pinned redistributable fonts shared by the UI, renderer and installer."""

import hashlib
from pathlib import Path


FONT_VERSION = 'Noto Sans CJK SC 2.004 / Noto Sans 2.008'
FONT_FILES = {
    'NotoSansCJKsc-Regular.otf': (16437364, '2c76254f6fc379fddfce0a7e84fb5385bb135d3e399294f6eeb6680d0365b74b'),
    'NotoSansCJKsc-Bold.otf': (17002248, 'b5f0d1a190a7f9b43c310a8850630af12553df32c4c050543f9059732d9b4c0a'),
    'NotoSans-Regular.ttf': (569208, 'b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5'),
    'NotoSans-Bold.ttf': (575740, 'c976e4b1b99edc88775377fcc21692ca4bfa46b6d6ca6522bfda505b28ff9d6a'),
    'NotoSans-Italic.ttf': (552776, '36cff144df01309dab648bea71baff9bb074026914afe63aeacc8bc90b67a28b'),
    'NotoSans-BoldItalic.ttf': (555292, '6edf4227ef0fa846aca70e86a307804ca4401741830f5b3af0f2554abe2b8466'),
}
FONT_LICENSES = {
    'LICENSE': (4301, '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2'),
    'NotoSans-LICENSE': (4377, '0dab92d0544f7b233403f14b84a663bdbfa746982eda629e7f4f9ffe1b036feb'),
}
FONT_UPSTREAM = 'https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/'
LATIN_UPSTREAM = 'https://raw.githubusercontent.com/notofonts/noto-fonts/ffebf8c1ee449e544955a7e813c54f9b73848eac/'


def font_source_url(name):
    return ((FONT_UPSTREAM + 'Sans/OTF/SimplifiedChinese/') if name.endswith('.otf')
            else (LATIN_UPSTREAM + 'hinted/ttf/NotoSans/')) + name


def font_media_type(name):
    return 'font/otf' if name.endswith('.otf') else 'font/ttf'


def verify_fonts(root):
    root = Path(root)
    for name, (size, sha256) in (FONT_FILES | FONT_LICENSES).items():
        path = root / name
        if not path.is_file() or path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            raise ValueError('Bundled font missing or damaged: ' + name + '; rebuild/reinstall the matching runtime.')
    return root


def uses_bundled_fonts(fonts):
    names = tuple(Path(name).stem for name in FONT_FILES)
    # XeTeX appends synthetic italic features after the PostScript name.
    # A genuinely blank PDF has no fonts; separate expected-text checks ensure no content was lost.
    return all(any(name.split('+')[-1].lstrip('/').startswith(expected) for expected in names)
               and item['embedded'] and item['unicode_map'] for name, item in fonts.items())
