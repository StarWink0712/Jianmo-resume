"""Compile toolbar-generated Markdown and verify PDF text, font runs and lists."""

import json
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

from experiments.m1.managed import compiler_manifest
from experiments.m1.pdf_checks import inspect_pdf
from experiments.m1.render import render_resume
from experiments.m1.run import compile_and_check, compact
from scripts.check_contracts import ROOT, build_case, cases, json_bytes


def main():
    generated = subprocess.check_output(['node', '--input-type=module', '-e', r'''
import {formatMarkdown as f} from './web/markdown-model.mjs';
const source = '熟悉 Redis 和 MySQL\n掌握 Java 服务端开发';
const bold = f(source, 0, source.length, 'bold');
const bullet = f(bold.text, bold.start, bold.end, 'bullet');
const extra = 'Italic proof\nNumbered proof';
const italic = f(extra, 0, extra.length, 'italic');
const ordered = f(italic.text, italic.start, italic.end, 'ordered');
console.log(JSON.stringify({bullet:bullet.text, ordered:ordered.text}));
'''], cwd=ROOT, text=True)
    values = json.loads(generated)
    resume, _ = build_case(cases()[0])
    resume['basics']['name'] = '格式工具栏验证（虚构）'
    resume['sections'] = [
        {'id':'section-toolbar-skills', 'type':'skills', 'title':'黑点与加粗', 'visible':True,
         'entries':[{'id':'entry-toolbar-skills', 'visible':True, 'label':'', 'body':values['bullet']}]},
        {'id':'section-toolbar-custom', 'type':'custom', 'title':'编号与斜体', 'visible':True,
         'entries':[{'id':'entry-toolbar-custom', 'visible':True, 'heading':'', 'body':values['ordered']}]},
    ]
    with tempfile.TemporaryDirectory(prefix='markdown-toolbar-', dir=ROOT / 'tmp/pdfs') as temporary:
        root = Path(temporary)
        source, avatar = render_resume(resume)
        result = compile_and_check(source, avatar, resume, root,
                                   compiler_manifest(ROOT / '.m1-build/local-install/current'))
        assert result['ok'] and result['pages'] == 1, result
        runs = []
        reader = PdfReader(root / 'main.pdf')
        for page in reader.pages:
            page.extract_text(visitor_text=lambda text, _cm, _tm, font, _size:
                              runs.append((text, str(font.get('/BaseFont', '')) if font else '')))
        bold = compact(''.join(text for text, font in runs if 'Bold' in font))
        italic = compact(''.join(text for text, font in runs if 'Italic' in font))
        info = inspect_pdf(root / 'main.pdf')
        assert all(compact(word) in bold for word in ('熟悉', 'Redis', 'MySQL', '掌握', 'Java'))
        assert all(compact(word) in italic for word in ('Italic proof', 'Numbered proof'))
        assert info['text'].count('•') == 2
        assert '1.' in info['text'] and '2.' in info['text']
        assert '**' not in info['text'] and '*Italic' not in info['text']
        assert all(font['embedded'] for font in info['fonts'].values())
    report = {'passed':True, 'pages':1, 'toolbar_markdown_compiles':True,
              'chinese_and_latin_bold_runs':True, 'latin_italic_runs':True,
              'bullet_count':2, 'numbered_items':2, 'markdown_markers_hidden':True,
              'fonts_embedded':True}
    (ROOT / 'work-logs/evidence/m2-markdown-toolbar-pdf.json').write_bytes(json_bytes(report))
    print(report)


if __name__ == '__main__':
    main()
