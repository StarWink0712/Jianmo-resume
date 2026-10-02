"""Fictional HTTP/PDF style regression: colors, units, fonts and simple sections."""

import copy
import json
from pathlib import Path
import tempfile

from pypdf import PdfReader

from scripts.check_backend import Harness, ROOT
from experiments.m1.style import STYLE_CONFIG
from scripts.check_contracts import json_bytes


def inspect_style(path, document):
    style = document['style']
    target = tuple(round(int(style['theme_color'][i:i + 2], 16) / 255, 3) for i in (1, 3, 5))
    reader = PdfReader(path)
    runs, rules, sizes = [], [], []
    for page in reader.pages:
        fill, stroke, start, end = (0, 0, 0), (0, 0, 0), None, None
        def operand(op, args, _cm, _tm):
            nonlocal fill, stroke, start, end
            if op == b'rg': fill = tuple(round(float(v), 3) for v in args)
            if op == b'RG': stroke = tuple(round(float(v), 3) for v in args)
            if op == b'g': fill = (float(args[0]),) * 3
            if op == b'G': stroke = (float(args[0]),) * 3
            if op == b'm': start = list(map(float, args))
            if op == b'l': end = list(map(float, args))
            if op == b'S' and start and end: rules.append((stroke, end[0] - start[0]))
            if op == b'Tf': sizes.append(float(args[1]))
        def text(value, _cm, _tm, _font, size):
            if value.strip(): runs.append((value.strip(), fill, size))
        page.extract_text(visitor_operand_before=operand, visitor_text=text)
    titles = {s['title'] for s in document['sections'] if s['visible'] and any(e['visible'] for e in s['entries'])}
    for title in titles:
        matching = [run for run in runs if run[0] == title]
        assert matching and all(run[1] == target for run in matching), ('heading color', title, matching)
        assert all(abs(run[2] - style['section_title_size_px'] * .75) < .01 for run in matching)
    assert len(rules) == len(titles) and all(color == target for color, _ in rules), rules
    expected_width = float(reader.pages[0].mediabox.width) - (style['margins_px']['left'] + style['margins_px']['right']) * .75
    assert all(abs(width - expected_width) < .02 for _, width in rules)
    assert any(abs(size - style['content_size_px'] * .75) < .01 for size in sizes)
    assert any(abs(size - style['name_size_px'] * .75) < .01 for size in sizes)
    assert all(color == (0, 0, 0) for text, color, _ in runs if 'Python' in text), runs
    extracted = ''.join(page.extract_text() for page in reader.pages)
    assert 'OMIT_SKILL_LABEL' not in extracted and 'OMIT_AWARD_HEADING' not in extracted
    assert '奖学金' in extracted
    return {'pages': len(reader.pages), 'colored_rules': len(rules), 'color': style['theme_color'],
            'heading_color_and_size': True, 'body_black': True, 'content_and_name_size': True,
            'margin_rule_width': True, 'simple_sections': True}


def main():
    root = ROOT / 'tmp/m2'
    root.mkdir(exist_ok=True, parents=True)
    report = []
    with tempfile.TemporaryDirectory(prefix='style-check-', dir=root) as temporary:
        h = Harness(Path(temporary), (ROOT / '.m1-build/local-install/current').resolve(), 8772)
        try:
            h.start()
            document = h.request('POST', '/api/resumes', 201, json={'title':'样式回归（虚构）', 'kind':'sample'}).json()['resume']
            document['sections'][3]['entries'][0]['label'] = 'OMIT_SKILL_LABEL'
            document['sections'][-1].update(type='awards', title='获奖经历')
            document['sections'][-1]['entries'][0].update(heading='OMIT_AWARD_HEADING', body='- 示例奖学金（虚构）\n- 示例竞赛奖励（虚构）')
            colors = [p['colors'][2] for p in STYLE_CONFIG['palettes']] + ['#406B5C']
            for index, color in enumerate(colors):
                document['style'].update(theme_color=color, name_size_px=[18, 20, 22, 24, 26, 28, 30][index],
                    section_title_size_px=[14, 15, 16, 17, 18, 20, 22][index], content_size_px=[13, 14, 15, 16, 17, 18, 20][index],
                    line_height=1.2 + index / 10, section_gap_px=index * 3)
                document['style']['margins_px'].update(top=25 + index, bottom=5, left=20 + index, right=20 + index)
                document = h.save(document)
                job = h.compile(document)
                pdf = Path(temporary) / f'variant-{index}.pdf'
                pdf.write_bytes(h.request('GET', f'/api/jobs/{job["id"]}/pdf').content)
                report.append(inspect_style(pdf, document))
            saved = copy.deepcopy(document)
            h.stop(); h.start()
            assert h.request('GET', '/api/resumes/' + document['id']).json()['resume'] == saved
        finally:
            h.stop(); h.client.close()
    result = {'variants':report, 'style_restart_roundtrip':True, 'passed':True}
    (ROOT / 'work-logs/evidence/m2-style-pdf.json').write_bytes(json_bytes(result))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
