"""Compile toolbar-generated Markdown and verify PDF text, font runs and lists."""

import json
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

from experiments.m1.managed import compiler_manifest
from experiments.m1.pdf_checks import inspect_pdf
from experiments.m1.render import render_resume
from core.resume_checks import compact
from core.tex_checks import compile_and_check

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
let references = '[1] **Alex Example**. First paper. [Paper](https://example.com/paper)\n[2] *Second paper*.\n[3] 第三条内容';
for (const label of ['[2]', '[3]']) {
  const caret = references.indexOf(label);
  references = f(references, caret, caret, 'linebreak').text;
}
console.log(JSON.stringify({bullet:bullet.text, ordered:ordered.text, references}));
'''], cwd=ROOT, text=True)
    values = json.loads(generated)
    resume, _ = build_case(cases()[0])
    resume['basics']['name'] = '格式工具栏验证（虚构）'
    resume['sections'] = [
        {'id':'section-toolbar-skills', 'type':'skills', 'title':'黑点与加粗', 'visible':True,
         'entries':[{'id':'entry-toolbar-skills', 'visible':True, 'label':'', 'body':values['bullet']}]},
        {'id':'section-toolbar-custom', 'type':'custom', 'title':'编号与斜体', 'visible':True,
         'entries':[{'id':'entry-toolbar-custom', 'visible':True, 'heading':'', 'body':values['ordered']}]},
        {'id':'section-toolbar-references', 'type':'academic', 'title':'同一条目内的无黑点换行', 'visible':True,
         'entries':[{'id':'entry-toolbar-references', 'visible':True, 'heading':'', 'role':'', 'url':None,
                     'start_date':None, 'end_date':None, 'ongoing':False, 'body':values['references']}]},
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
        lines = [line.strip() for page in reader.pages for line in page.extract_text(extraction_mode='layout').splitlines()]
        for marker, content in [('[1]', 'First paper.'), ('[2]', 'Second paper.'), ('[3]', '第三条内容')]:
            matching = [line for line in lines if line.startswith(marker)]
            assert len(matching) == 1 and compact(content) in compact(matching[0]), matching
            assert not any(other in matching[0] for other in ('[1]', '[2]', '[3]') if other != marker)
        assert 'https://example.com/paper' in info['links']
        assert '  \n' in values['references']
        output = ROOT / 'output/pdf/markdown-toolbar.pdf'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes((root / 'main.pdf').read_bytes())
    report = {'passed':True, 'pages':1, 'toolbar_markdown_compiles':True,
              'chinese_and_latin_bold_runs':True, 'latin_italic_runs':True,
              'bullet_count':2, 'numbered_items':2, 'markdown_markers_hidden':True,
              'fonts_embedded':True, 'explicit_linebreaks_in_one_entry':True,
              'reference_labels_are_not_bullets':True, 'linebreak_link_preserved':True}
    (ROOT / 'work-logs/evidence/m2-markdown-toolbar-pdf.json').write_bytes(json_bytes(report))
    print(report)


if __name__ == '__main__':
    main()
