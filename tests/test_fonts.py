import tempfile
import unittest
from pathlib import Path

from experiments.m1.fonts import FONT_FILES, FONT_LICENSES, uses_bundled_fonts, verify_fonts
from experiments.m1.render import PREAMBLE
from experiments.m1.runtime import profile
from scripts.check_contracts import ROOT


class BundledFontTests(unittest.TestCase):
    def test_vendored_fonts_and_original_license_match_pins(self):
        verify_fonts(ROOT / 'assets/fonts')

    def test_missing_corrupt_or_missing_license_cannot_fall_back(self):
        for name in [*FONT_FILES, *FONT_LICENSES]:
            for corrupt in (True, False):
                with self.subTest(name=name, corrupt=corrupt), tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    for entry in [*FONT_FILES, *FONT_LICENSES]:
                        if entry != name:
                            (root / entry).symlink_to(ROOT / 'assets/fonts' / entry)
                    if corrupt:
                        (root / name).write_bytes(b'corrupted font resource')
                    with self.assertRaisesRegex(ValueError, 'Bundled font missing or damaged'):
                        verify_fonts(root)

    def test_renderer_uses_explicit_files_for_all_styles(self):
        self.assertEqual(PREAMBLE.count('Path=fonts/'), 2)
        for name in FONT_FILES:
            self.assertIn(name, PREAMBLE)
        for name in ('Fandol', 'Termes', 'PingFang', 'Avenir'):
            self.assertNotIn(name, PREAMBLE)
        self.assertEqual(PREAMBLE.count('FakeSlant=0.2'), 2)

    def test_ui_has_no_system_or_remote_font_source(self):
        css = (ROOT / 'web/app.css').read_text()
        for name in FONT_FILES:
            self.assertIn(f'url("/assets/{name}")', css)
        self.assertIn('body { font-family: "Resume Latin", "Resume Sans", sans-serif;', css)
        self.assertNotIn('local(', css)
        self.assertNotIn('https://', css)
        self.assertIn("$('font-warning').hidden = false", (ROOT / 'web/app.js').read_text())

    def test_pdf_font_check_rejects_fallback_and_unembedded_fonts(self):
        info = {'embedded': True, 'unicode_map': True}
        self.assertTrue(uses_bundled_fonts({'/ABCDEF+NotoSansCJKsc-Regular-Identity-H': info}))
        self.assertTrue(uses_bundled_fonts({}))
        self.assertFalse(uses_bundled_fonts({'/ABCDEF+FandolSong-Regular': info}))
        self.assertFalse(uses_bundled_fonts({'/ABCDEF+NotoSansCJKsc-Bold': info | {'embedded': False}}))
        self.assertFalse(uses_bundled_fonts({'/ABCDEF+NotoSansCJKsc-Bold': info | {'unicode_map': False}}))

    def test_sandbox_denies_system_font_files_even_under_system_allow(self):
        policy = profile(Path('/tmp/job'), Path('/tmp/runtime'))
        self.assertIn('(deny file-read* (subpath "/System/Library/Fonts")', policy)
        self.assertIn('^/System/.*[.](otf|ttf|ttc|otc|dfont)$', policy)
