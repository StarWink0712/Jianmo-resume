import copy
import unittest

from experiments.m1.render import RenderError, render_entry_heading, render_resume
from experiments.m1.run import expected_text
from experiments.m1.style import RHYTHM, STYLE_CONFIG, content_only, effective_style, px
from scripts.check_contracts import RESUME_SCHEMA, build_case, cases, validate_resume


class StyleTests(unittest.TestCase):
    def setUp(self):
        self.resume, _ = build_case(cases()[0])

    def test_six_distinct_palettes_of_six_safe_colors(self):
        colors = [color for palette in STYLE_CONFIG['palettes'] for color in palette['colors']]
        self.assertEqual(len(STYLE_CONFIG['palettes']), 6)
        self.assertTrue(all(len(palette['colors']) == 6 for palette in STYLE_CONFIG['palettes']))
        self.assertEqual(len(set(colors)), 36)
        for color in colors:
            self.assertRegex(color, r'^#[0-9A-F]{6}$')

    def test_legacy_adapter_rounds_to_integer_controls_without_mutation(self):
        old = copy.deepcopy(self.resume['style'])
        style = effective_style(old)
        self.assertEqual(style['version'], 3)
        self.assertEqual(style['content_size_px'], 14)
        self.assertEqual(style['section_title_size_px'], 16)
        self.assertEqual(style['margins_px']['top'], 60)
        self.assertEqual(style['line_height'], RHYTHM['body_line_height'])
        self.assertEqual(self.resume['style'], old)
        self.assertEqual(style['name_size_px'], 22)
        self.resume['style'] = style
        self.assertFalse(validate_resume(self.resume))

    def test_old_decimal_pixel_settings_are_readable_and_render_as_integers(self):
        old = copy.deepcopy(STYLE_CONFIG['defaults'])
        old.update(version=2, section_title_size_px=15.94, content_size_px=15.94, section_gap_px=5.313)
        old['margins_px'].update(top=45.354, bottom=45.5)
        before = copy.deepcopy(old)
        self.resume['style'] = old
        self.assertFalse(validate_resume(self.resume))
        converted = effective_style(old)
        self.assertEqual(converted['section_title_size_px'], 16)
        self.assertEqual(converted['content_size_px'], 16)
        self.assertEqual(converted['section_gap_px'], 5)
        self.assertEqual(converted['margins_px']['top'], 45)
        self.assertEqual(converted['margins_px']['bottom'], 46)
        self.assertEqual(old, before)

    def test_integer_contract_matches_dropdowns_and_rejects_fractional_lengths(self):
        schema = RESUME_SCHEMA['$defs']['integerPixelStyle']['properties']
        for key, sizes in STYLE_CONFIG['sizes'].items():
            self.assertEqual(schema[key]['enum'], sizes)
            self.resume['style'] = copy.deepcopy(STYLE_CONFIG['defaults'])
            self.resume['style'][key] = 15.94
            self.assertTrue(validate_resume(self.resume))
        self.resume['style'] = copy.deepcopy(STYLE_CONFIG['defaults'])
        self.resume['style']['section_gap_px'] = 5.1
        self.assertTrue(validate_resume(self.resume))
        self.resume['style']['section_gap_px'] = 5
        for edge in ('top', 'bottom', 'left', 'right'):
            self.resume['style']['margins_px'][edge] = 30.5
            self.assertTrue(validate_resume(self.resume))
            self.resume['style']['margins_px'][edge] = 30
        self.resume['style']['line_height'] = 1.15
        self.assertFalse(validate_resume(self.resume))

    def test_pixel_style_is_independent_and_uses_correct_pdf_units(self):
        style = copy.deepcopy(STYLE_CONFIG['defaults'])
        self.assertEqual(effective_style(style), style)
        effective_style(style)['margins_px']['top'] = 100
        self.assertEqual(style['margins_px']['top'], 25)
        self.assertEqual(px(96), '72.000000bp')

    def test_pixel_ranges_and_hex_reject_injection(self):
        for key, value in [('theme_color', r'#000000}\input{x}'), ('theme_color', '#fff'),
                           ('theme_color', '#123456\n'), ('theme_color', '#GGGGGG'),
                           ('name_size_px', 40), ('content_size_px', 0), ('content_size_px', True),
                           ('section_title_size_px', 31), ('line_height', .5), ('section_gap_px', -1)]:
            with self.subTest(key=key, value=value):
                self.resume['style'] = copy.deepcopy(STYLE_CONFIG['defaults'])
                self.resume['style'][key] = value
                self.assertTrue(validate_resume(self.resume))
                with self.assertRaises(RenderError):
                    render_resume(self.resume)
        self.resume['style'] = copy.deepcopy(STYLE_CONFIG['defaults'])
        self.resume['style']['margins_px']['bottom'] = 5
        self.assertFalse(validate_resume(self.resume))
        self.resume['style']['margins_px']['left'] = 121
        self.assertTrue(validate_resume(self.resume))

    def test_title_and_rule_share_color_and_restore_body_black(self):
        self.resume['style'] = copy.deepcopy(STYLE_CONFIG['defaults'])
        self.resume['style'].update(theme_color='#804020', section_title_size_px=18, content_size_px=14, line_height=1.5, section_gap_px=5)
        source, _ = render_resume(self.resume)
        self.assertIn(r'\special{color push rgb 0.501961 0.250980 0.125490}', source)
        self.assertIn(r'\fontsize{13.500000bp}{16.875000bp}', source)
        self.assertIn(r'\fontsize{10.500000bp}{14.175000bp}', source)
        self.assertIn(r'\addvspace{3.750000bp}', source)
        self.assertEqual(source.count('color push'), source.count('color pop'))
        self.assertIn(r'\hrule height 0.5bp\special{color pop}\vspace{3bp}', source)
        self.assertNotIn(r'\small', source)

    def test_skills_and_awards_are_body_only_without_deleting_old_labels(self):
        skills = self.resume['sections'][3]
        awards = self.resume['sections'][4]
        awards['title'] = '获奖经历'
        before = copy.deepcopy(self.resume)
        for kind in ('custom', 'awards'):
            awards['type'] = kind
            self.assertFalse(validate_resume(self.resume))
            self.assertTrue(content_only(awards))
            source, _ = render_resume(self.resume)
            for value in (skills['entries'][0]['label'], awards['entries'][0]['heading']):
                self.assertNotIn(value, source)
                self.assertNotIn(value, expected_text(self.resume))
            self.assertNotIn(r'\textbf{}', source)
        self.assertEqual(skills, before['sections'][3])
        self.assertEqual(awards['entries'], before['sections'][4]['entries'])

    def test_unrelated_custom_title_is_not_suppressed(self):
        section = self.resume['sections'][4]
        self.assertFalse(content_only(section))
        source, _ = render_resume(self.resume)
        self.assertIn(section['entries'][0]['heading'], source)

    def test_work_and_project_headers_share_a_paragraph_and_have_body_gap(self):
        source, _ = render_resume(self.resume)
        for section in self.resume['sections'][1:3]:
            entry = section['entries'][0]
            title = entry['organization'] if section['type'] == 'employment' else entry['name']
            heading = source.split('\\textbf{' + title + '}')[1].split('\\par}')[0]
            self.assertIn(entry['role'], heading)
            self.assertIn(entry['start_date'], heading)
            self.assertIn(r'\hfill \mbox{', heading)
            self.assertNotIn(r'\par', heading)
        self.assertEqual(source.count(r'\par}' + '\n' + r'\nobreak\vspace{3.000000bp}\nobreak'), 2)

    def test_entry_heading_preserves_optional_fields_and_escapes_tex(self):
        self.assertEqual(render_entry_heading('', '', ''), '')
        title_only = render_entry_heading('A&B', '', '')
        self.assertIn(r'\textbf{A\&B}', title_only)
        self.assertNotIn(r'\textbar', title_only)
        self.assertNotIn(r'\hfill', title_only)
        date_only = render_entry_heading('', '', '2024-01 - 至今')
        self.assertIn(r'\mbox{2024-01 - 至今}', date_only)
        self.assertNotIn(r'\hfill', date_only)
        linked = render_entry_heading('Project', 'Role', '2024-01', 'https://example.com?a=1&b=2')
        self.assertIn(r'\href{https://example.com?a=1\&b=2}{项目链接}', linked)
        self.assertNotIn(r'\resizebox', linked)
