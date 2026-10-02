import copy
import json
from pathlib import Path
import re
import unittest

from backend.backup import export_backup, import_backup
from experiments.m1.render import render_resume
from scripts.check_contracts import validate_resume

ROOT = Path(__file__).resolve().parents[1]


class EnglishResumeTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads((ROOT / 'fixtures/resumes/english.json').read_text())

    def test_english_fixture_and_backup_roundtrip(self):
        self.assertEqual(validate_resume(self.document), [])
        restored, assets = import_backup(export_backup(self.document, {}))
        self.assertEqual(restored, self.document)
        self.assertEqual(assets, {})

    def test_literal_punctuation_and_word_boundaries(self):
        source, _ = render_resume(self.document)
        self.assertIn(r'\defaultfontfeatures[\rmfamily,\sffamily]{Ligatures=TeXOff}', source)
        self.assertIn(r'\hyphenpenalty=10000', source)
        self.assertIn(r'\setlength{\emergencystretch}{.1\linewidth}', source)
        self.assertIn('"double quotes", \'single quotes\', --double-hyphens, ---triple-hyphens', source)
        self.assertIn(r'12.5\%', source)
        self.assertIn(r'R\&D', source)
        self.assertIn(r'\$4,200', source)

    def test_english_content_does_not_acquire_unrelated_labels(self):
        original = copy.deepcopy(self.document)
        source, avatar = render_resume(self.document)
        self.assertIsNone(avatar)
        self.assertIsNone(re.search(r'[\u4e00-\u9fff]', source))
        self.assertIn(r'\textbf{bold}', source)
        self.assertIn(r'\textit{italic}', source)
        self.assertIn('2025-01 - 2026-06', source)
        self.assertIn(r'\href{https://example.com/projects/toolkit}{Project}', source)
        self.assertEqual(self.document, original)


if __name__ == '__main__':
    unittest.main()
