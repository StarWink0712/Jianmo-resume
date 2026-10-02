import copy
import unittest

from experiments.m1.render import fixed_gap, render_markdown, render_resume
from experiments.m1.style import RHYTHM, STYLE_CONFIG, effective_style, px
from scripts.check_contracts import build_case, cases


class FixedSpacingTests(unittest.TestCase):
    def test_legacy_and_pixel_line_heights_render_identically_without_mutation(self):
        resume, _ = build_case(cases()[0])
        for style in (resume['style'], copy.deepcopy(STYLE_CONFIG['defaults'])):
            sources = []
            for value in (1.1, 1.35, 1.5):
                candidate = copy.deepcopy(resume)
                candidate['style'] = copy.deepcopy(style)
                candidate['style']['line_height'] = value
                before = copy.deepcopy(candidate)
                sources.append(render_resume(candidate)[0])
                self.assertEqual(candidate, before)
                self.assertEqual(effective_style(candidate['style'])['line_height'], 1.35)
            self.assertEqual(sources[0], sources[1])
            self.assertEqual(sources[1], sources[2])

    def test_header_has_fixed_gaps_only_between_populated_rows(self):
        resume, _ = build_case(cases()[0])
        header = render_resume(resume)[0].split(r'\par\endgroup')[0]
        self.assertEqual(header.count(fixed_gap('header_line_gap_px', keep=True)), 4)
        self.assertIn(r'\bfseries\strut ' + resume['basics']['name'] + r'\par}', header)
        resume['basics'].update(headline='', email='', phone='', location='', links=[])
        header = render_resume(resume)[0].split(r'\par\endgroup')[0]
        self.assertNotIn(fixed_gap('header_line_gap_px', keep=True), header)

    def test_block_spacing_does_not_add_space_before_first_paragraph_or_list(self):
        gap = r'\par\addvspace{' + px(RHYTHM['paragraph_gap_px']) + '}'
        self.assertEqual(render_markdown('ONE\n\nTWO\n\n- THREE\n- FOUR\n\nFIVE').count(gap), 3)
        self.assertTrue(render_markdown('ONE\n\nTWO').startswith('ONE'))
        self.assertTrue(render_markdown('- ONE\n- TWO').startswith(r'\begin{itemize}'))
        self.assertEqual(render_markdown('- ONE\n- TWO').count(gap), 0)
        self.assertEqual(render_markdown('- ONE\n\n  TWO\n- THREE').count(gap), 1)
        self.assertEqual(render_markdown('- ONE\n  - CHILD\n- TWO').count(gap), 1)

    def test_entry_spacing_is_fixed_while_module_spacing_is_independent(self):
        resume, _ = build_case(cases()[0])
        section = resume['sections'][1]
        second = copy.deepcopy(section['entries'][0])
        second['id'] = 'entry-second'
        section['entries'].append(second)
        resume['sections'] = [section]
        resume['style'] = copy.deepcopy(STYLE_CONFIG['defaults'])
        for gap in (0, 5, 20):
            resume['style']['section_gap_px'] = gap
            source, _ = render_resume(resume)
            self.assertIn(r'\addvspace{' + px(gap) + r'}\Needspace{4\baselineskip}', source)
            self.assertEqual(source.count(r'\addvspace{6.000000bp}\Needspace{2\baselineskip}'), 1)
        second['visible'] = False
        self.assertNotIn(r'\addvspace{6.000000bp}\Needspace{2\baselineskip}', render_resume(resume)[0])

    def test_lists_keep_tight_outer_spacing_and_fixed_item_spacing(self):
        resume, _ = build_case(cases()[0])
        source, _ = render_resume(resume)
        self.assertEqual(source.count(r'\setlist{'), 1)
        self.assertIn(r'\setlist{nosep,leftmargin=1.5em,topsep=0pt,partopsep=0pt,parsep=0pt,itemsep=1.500000bp}', source)
        self.assertIn(r'\raggedbottom', source)
