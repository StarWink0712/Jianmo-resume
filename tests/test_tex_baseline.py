import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.m1.managed import digest
from experiments.m1.tex_baseline import all_inputs, compare, verify_evidence, verify_sources


class SourceBaselineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / 'texmf-dist/tex/latex/base/latex.ltx'
        source.parent.mkdir(parents=True)
        source.write_bytes(b'reviewed format source')
        self.item = {'path': str(source.relative_to(self.root)), 'bytes': source.stat().st_size, 'sha256': digest(source)}
        self.seed = {'schema': 2, 'tex_inputs': [dict(self.item)], 'format_inputs': [dict(self.item)]}

    def test_machine_generated_format_is_not_a_portability_pin(self):
        host = self.root / 'texmf-var/web2c/xetex/xelatex.fmt'
        host.parent.mkdir(parents=True)
        for content in (b'old host format', b'new machine format', b'broken host cache'):
            host.write_bytes(content)
            verify_sources(self.seed, self.root)
        host.unlink()
        verify_sources(self.seed, self.root)

    def test_actual_source_change_is_still_rejected(self):
        (self.root / self.item['path']).write_bytes(b'changed source')
        with self.assertRaisesRegex(ValueError, 'source baseline mismatch'):
            verify_sources(self.seed, self.root)

    def test_baseline_is_relative_to_discovered_installation(self):
        moved = self.root / 'another install with spaces'
        path = moved / self.item['path']
        path.parent.mkdir(parents=True)
        path.write_bytes((self.root / self.item['path']).read_bytes())
        verify_sources(self.seed, moved)

    def test_unreviewed_legacy_and_unsafe_source_pins_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Legacy'):
            verify_sources({'tex_inputs': [self.item]}, self.root)
        for name in ('/outside', '../outside', 'texmf-var/xelatex.fmt'):
            bad = copy.deepcopy(self.seed)
            bad['tex_inputs'][0]['path'] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                all_inputs(bad)

    def test_external_source_symlink_is_rejected(self):
        (self.root / self.item['path']).unlink()
        (self.root / self.item['path']).symlink_to('/etc/hosts')
        with self.assertRaises(ValueError):
            verify_sources(self.seed, self.root)

    def test_conflicting_duplicate_pins_rejected(self):
        bad = copy.deepcopy(self.seed)
        bad['format_inputs'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            all_inputs(bad)

    def test_diff_keeps_removed_host_format_visible_for_review(self):
        before = {'tex_inputs': [self.item, {'path': 'texmf-var/xelatex.fmt', 'bytes': 1, 'sha256': 'old'}]}
        result = compare(before, dict(self.seed, fonts=[]))
        self.assertEqual(result['unchanged_count'], 1)
        self.assertEqual(result['removed'][0]['path'], 'texmf-var/xelatex.fmt')
        self.assertEqual(result['changed'], [])

    def test_modified_or_stale_experiment_evidence_is_rejected(self):
        (self.root / 'runtime-inputs.json').write_text(json.dumps(self.seed))
        (self.root / 'results.json').write_text('{}')
        (self.root / 'baseline-evidence.json').write_text(json.dumps({
            'inputs_sha256': digest(self.root / 'runtime-inputs.json'),
            'results_sha256': digest(self.root / 'results.json'), 'implementation_sha256': 'previous'}))
        with patch('experiments.m1.tex_baseline.implementation_hash', return_value='changed'):
            with self.assertRaisesRegex(ValueError, 'stale or modified'):
                verify_evidence(self.root)
        (self.root / 'runtime-inputs.json').write_text('{}')
        with patch('experiments.m1.tex_baseline.implementation_hash', return_value='previous'):
            with self.assertRaisesRegex(ValueError, 'stale or modified'):
                verify_evidence(self.root)


if __name__ == '__main__':
    unittest.main()
