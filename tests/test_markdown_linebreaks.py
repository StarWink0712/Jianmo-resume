import unittest

from experiments.m1.render import RenderError, render_markdown


class MarkdownLinebreakTests(unittest.TestCase):
    def test_two_spaces_and_backslash_newlines_are_explicit_linebreaks(self):
        for source in ('First  \nSecond', 'First\\\nSecond'):
            self.assertEqual(render_markdown(source), 'First\\newline{}\nSecond\\par\n')

    def test_numbered_citations_are_text_not_bullets_or_tex_length_arguments(self):
        rendered = render_markdown('[1] **Alex Example**. First paper.  \n[2] *Second paper*.')
        self.assertIn('First paper.\\newline{}\n[2]', rendered)
        self.assertNotIn(r'\begin{itemize}', rendered)
        self.assertNotIn(r'\begin{enumerate}', rendered)
        self.assertNotIn(r'\\[2]', rendered)

    def test_soft_newlines_and_blank_paragraphs_keep_existing_behavior(self):
        self.assertEqual(render_markdown('First\nSecond'), 'First Second\\par\n')
        self.assertNotIn(r'\newline', render_markdown('First\n\nSecond'))
        self.assertIn(r'\addvspace', render_markdown('First\n\nSecond'))

    def test_hardbreaks_work_inside_emphasis_links_and_list_items(self):
        for source in ('**First  \nSecond**', '*First  \nSecond*', '[First  \nSecond](https://example.com)'):
            self.assertIn('First\\newline{}\nSecond', render_markdown(source))
        rendered = render_markdown('- First  \n  Second\n- Third')
        self.assertEqual(rendered.count(r'\item '), 2)
        self.assertEqual(rendered.count(r'\newline{}'), 1)

    def test_explicit_linebreak_does_not_enable_html_or_raw_tex(self):
        with self.assertRaises(RenderError):
            render_markdown('First<br>Second')
        rendered = render_markdown('First  \n\\input{secret}')
        self.assertIn(r'\textbackslash{}input\{secret\}', rendered)
        self.assertNotIn(r'\input{secret}', rendered)


if __name__ == '__main__':
    unittest.main()
