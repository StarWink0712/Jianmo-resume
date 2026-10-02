from html.parser import HTMLParser
from pathlib import Path
import unittest


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes, self.stack = [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = {'tag': tag, 'attrs': dict(attrs), 'parent': self.stack[-1] if self.stack else None}
        self.nodes.append(node)
        if tag not in ('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'):
            self.stack.append(node)

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()['tag'] == tag:
                break

    def by_id(self, identifier):
        return next(node for node in self.nodes if node['attrs'].get('id') == identifier)


class EditorLayoutTests(unittest.TestCase):
    def setUp(self):
        self.page = Elements((Path(__file__).resolve().parents[1] / 'web/index.html').read_text())

    def test_status_and_editor_controls_share_one_bar(self):
        status = self.page.by_id('connection')['parent']
        context = self.page.by_id('context')
        actions = self.page.by_id('context-actions')
        self.assertIs(status['parent'], context['parent'])
        self.assertIs(actions['parent'], context['parent'])
        self.assertEqual(status['attrs'].get('role'), 'status')
        self.assertIn('workspace-context', context['parent']['attrs']['class'])
        self.assertFalse(any('prototype-note' in node['attrs'].get('class', '').split() for node in self.page.nodes))

    def test_library_keeps_connection_visible_without_editor_controls(self):
        for identifier in ('context', 'context-actions'):
            self.assertIn('hidden', self.page.by_id(identifier)['attrs'])
        node = self.page.by_id('connection')
        while node:
            self.assertNotIn('hidden', node['attrs'])
            node = node['parent']
        identifiers = [node['attrs']['id'] for node in self.page.nodes if 'id' in node['attrs']]
        self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_user_interface_has_no_development_badge_or_validation_copy(self):
        root = Path(__file__).resolve().parents[1]
        for filename in ('index.html', 'app.js', 'style-editor.mjs', 'viewer.js'):
            source = (root / 'web' / filename).read_text()
            for phrase in ('M2', '开发版', '数据库', '服务端', '真实 PDF', '编译', '96 px/英寸'):
                with self.subTest(filename=filename, phrase=phrase):
                    self.assertNotIn(phrase, source)
        self.assertFalse(any('prototype-badge' in node['attrs'].get('class', '').split()
                             for node in self.page.nodes))

    def test_safety_warnings_and_accessible_statuses_are_retained(self):
        self.assertEqual(self.page.by_id('connection')['parent']['attrs'].get('role'), 'status')
        for identifier in ('save-status', 'preview-status', 'toast'):
            self.assertEqual(self.page.by_id(identifier)['attrs'].get('role'), 'status')
        for identifier in ('font-warning', 'editor-error', 'pdf-render-error', 'manage-error'):
            self.assertEqual(self.page.by_id(identifier)['attrs'].get('role'), 'alert')
        source = (Path(__file__).resolve().parents[1] / 'web/index.html').read_text()
        for phrase in ('数据仅在本机', '工程备份', '不包含之后的修改', '退出服务后无法保存',
                       '使用虚构示例', 'Markdown', '草稿'):
            self.assertIn(phrase, source)


if __name__ == '__main__':
    unittest.main()
