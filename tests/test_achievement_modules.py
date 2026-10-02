import copy
import json
import subprocess
import unittest

from experiments.m1.render import render_resume
from experiments.m1.run import expected_text
from experiments.m1.style import content_only
from scripts.check_contracts import ROOT, build_case, cases, validate_resume


class AchievementModuleTests(unittest.TestCase):
    def setUp(self):
        self.resume, _ = build_case(cases()[0])
        self.sections = json.loads((ROOT / 'fixtures/achievement-sections.json').read_text())
        self.resume['sections'].extend(self.sections)

    def test_new_modules_validate_without_mutation(self):
        before = copy.deepcopy(self.resume)
        self.assertEqual(validate_resume(self.resume), [])
        self.assertEqual(self.resume, before)

    def test_frontend_entry_defaults_match_backend_schema(self):
        generated = json.loads(subprocess.check_output(['node', '--input-type=module', '-e',
            "import {createEntry,sectionLabels} from './web/section-model.mjs'; console.log(JSON.stringify(Object.keys(sectionLabels).map(type => ({id:'section-'+type,type,title:sectionLabels[type],visible:true,entries:[createEntry(type,'entry-'+type)]}))));"], cwd=ROOT))
        self.resume['sections'] = generated
        self.assertEqual(validate_resume(self.resume), [])

    def test_new_types_require_explicit_fields_but_legacy_custom_remains_valid(self):
        for section in self.sections[:2]:
            for key in ('role', 'start_date', 'end_date', 'ongoing', 'url'):
                value = section['entries'][0].pop(key)
                self.assertTrue(validate_resume(self.resume), key)
                section['entries'][0][key] = value
        legacy = self.resume['sections'][4]['entries'][0]
        self.assertNotIn('role', legacy)
        for key, value in [('role', '贡献者'), ('end_date', '2025-09'), ('ongoing', True)]:
            candidate = copy.deepcopy(self.resume)
            candidate['sections'][4]['entries'][0][key] = value
            self.assertEqual(validate_resume(candidate), [])

    def test_date_role_url_and_unknown_field_validation(self):
        for index in (-3, -2, -1):
            for patch in ({'start_date':'2025-13'}, {'end_date':'2024-01'}, {'ongoing':True, 'end_date':'2025-12'},
                          {'role':'x'*201}, {'role':None}, {'url':'javascript:alert(1)'},
                          {'url':'https://user:pass@example.com'}, {'unknown':'value'}):
                with self.subTest(index=index, patch=patch):
                    bad = copy.deepcopy(self.resume)
                    bad['sections'][index]['entries'][0].update(patch)
                    self.assertTrue(validate_resume(bad))

    def test_new_headers_render_inline_with_gap_links_and_dates(self):
        source, _ = render_resume(self.resume)
        for section in self.sections:
            entry = section['entries'][0]
            self.assertIn(r'\textbf{' + entry['heading'] + r'} \enspace\textbar{}\enspace ' + entry['role'], source)
            self.assertIn(entry['start_date'], source)
            self.assertIn(entry['role'], expected_text(self.resume))
        self.assertIn(r'\mbox{2025-06 - 至今}', source)
        self.assertIn('}{成果链接}', source)
        self.assertIn('}{相关链接}', source)
        self.assertGreaterEqual(source.count(r'\nobreak\vspace{3.000000bp}\nobreak'), 5)

    def test_visibility_and_empty_optional_fields(self):
        self.sections[0]['visible'] = False
        self.sections[1]['entries'][0]['visible'] = False
        self.sections[2]['entries'][0].update(role='', start_date=None, end_date=None, ongoing=False, url=None)
        source, _ = render_resume(self.resume)
        self.assertNotIn('分布式系统研究', source)
        self.assertNotIn('软件设计竞赛', source)
        self.assertNotIn('维护者', source)
        self.assertIn(r'\textbf{示例开源工具（虚构）}\par}', source)

    def test_legacy_awards_and_new_custom_with_same_title_are_distinct(self):
        legacy = self.resume['sections'][4]
        legacy['title'] = '获奖经历'
        self.assertTrue(content_only(legacy))
        custom = self.sections[-1]
        custom['title'] = '获奖经历'
        self.assertFalse(content_only(custom))
        source, _ = render_resume(self.resume)
        self.assertIn(custom['entries'][0]['heading'], source)
        self.assertNotIn(legacy['entries'][0]['heading'], source)
