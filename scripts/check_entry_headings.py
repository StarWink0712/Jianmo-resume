"""Verify actual PDF heading baselines, body gaps and long-field wrapping."""

import copy
from pathlib import Path
import tempfile

from pypdf import PdfReader

from experiments.m1.managed import compiler_manifest
from experiments.m1.render import render_resume
from core.resume_checks import compact
from core.tex_checks import compile_and_check

from experiments.m1.style import STYLE_CONFIG, effective_style
from scripts.check_contracts import ROOT, build_case, cases, json_bytes


def text_lines(path):
    lines = {}
    for index, page in enumerate(PdfReader(path).pages):
        def collect(text, cm, tm, _font, _size):
            if text.strip():
                key = (index, round(tm[5] + cm[5], 2))
                lines[key] = lines.get(key, '') + text
        page.extract_text(visitor_text=collect)
    return lines


def main():
    resume, _ = build_case(cases()[0])
    resume['style'] = copy.deepcopy(STYLE_CONFIG['defaults'])
    resume['style'].update(content_size_px=15, line_height=1.2)
    resume['sections'] = resume['sections'][1:3]
    work, project = [section['entries'][0] for section in resume['sections']]
    work.update(organization='ACME & Co', role='ROLE_ONE', location='Sample City',
                body='- BODY_WORK_FIRST\n- BODY_WORK_SECOND')
    project.update(name='PROJECT_ONE', role='ROLE_TWO', ongoing=False, end_date='2024-12',
                   url=None, body='BODY_PROJECT_FIRST\n\nBODY_PROJECT_SECOND')
    runtime = compiler_manifest(ROOT / '.m1-build/local-install/current')
    report = {'headers':[]}
    with tempfile.TemporaryDirectory(prefix='inline-heading-', dir=ROOT / 'tmp/pdfs') as temporary:
        root = Path(temporary)
        source, avatar = render_resume(resume)
        result = compile_and_check(source, avatar, resume, root / 'normal', runtime)
        assert result['ok'], result
        lines = text_lines(root / 'normal/main.pdf')
        for name, role, date, body in [('ACME & Co', 'ROLE_ONE', '2024-01 - 2024-05', 'BODY_WORK_FIRST'),
                                       ('PROJECT_ONE', 'ROLE_TWO', '2024-07 - 2024-12', 'BODY_PROJECT_FIRST')]:
            header = [key for key, text in lines.items() if all(compact(value) in compact(text) for value in (name, role, date))]
            first_body = [key for key, text in lines.items() if body in text]
            assert len(header) == len(first_body) == 1, 'Heading text must share one PDF baseline'
            assert header[0][0] == first_body[0][0], 'Heading must stay with its first body line'
            gap = header[0][1] - first_body[0][1]
            style = effective_style(resume['style'])
            extra = gap - style['content_size_px'] * .75 * style['line_height']
            assert abs(extra - 3) < .05, extra
            report['headers'].append({'same_baseline':True, 'first_body_same_page':True, 'extra_gap_bp':round(extra, 2)})
        work.update(organization='长公司名称' * 35, role='岗位职责说明' * 30)
        project.update(name='长项目名称' * 35, role='项目角色说明' * 30)
        source, avatar = render_resume(resume)
        result = compile_and_check(source, avatar, resume, root / 'long', runtime)
        assert result['ok'] and not result['overfull_boxes'], result
        report['long_headers_wrap_without_loss_or_overflow'] = True
    report['passed'] = True
    (ROOT / 'work-logs/evidence/m2-inline-headings.json').write_bytes(json_bytes(report))
    print(report)


if __name__ == '__main__':
    main()
