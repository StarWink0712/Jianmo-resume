"""Measure right-aligned dates in PDFs for every structured timeline module."""
import copy
import json
from pathlib import Path
import re
import tempfile

from PIL import ImageFont
from pypdf import PdfReader

from experiments.m1.managed import compiler_manifest
from experiments.m1.render import render_resume
from experiments.m1.run import compact, compile_and_check
from experiments.m1.style import STYLE_CONFIG
from scripts.check_contracts import ROOT, build_case, cases, json_bytes


def fixture():
    document, _ = build_case(cases()[0])
    document['basics'].update(name='日期右对齐验证（虚构）', headline='', location='', email='', phone='', links=[])
    document['style'] = copy.deepcopy(STYLE_CONFIG['defaults'])
    document['style'].update(content_size_px=15)
    document['style']['margins_px'].update(top=30, bottom=30, left=36, right=48)
    document['sections'] = []
    for index, kind in enumerate(('education', 'employment', 'project', 'academic', 'competition', 'custom')):
        entry = {'id':f'entry-{kind}', 'visible':True, 'body':f'BODY_{kind.upper()}',
                 'start_date':f'{2020 + index}-01', 'end_date':f'{2020 + index}-12', 'ongoing':False}
        if kind == 'education':
            entry.update(school='Example University (Fictional)', degree='Master of Science', field_of_study='Computer Science', location='Example City')
        elif kind == 'employment':
            entry.update(organization='Example Laboratory', role='Research Assistant', location='Example City', employment_type='internship')
        elif kind == 'project':
            entry.update(name='Example Project', role='Developer', url='https://example.com/project')
        else:
            entry.update(heading=f'Example {kind.title()}', role='Contributor', url=None)
        document['sections'].append({'id':f'section-{kind}', 'type':kind, 'title':kind.upper(), 'visible':True, 'entries':[entry]})
    chinese = copy.deepcopy(document['sections'][0]['entries'][0])
    chinese.update(id='entry-education-cn', school='示例大学（虚构）', degree='硕士', field_of_study='计算机科学',
                   location='示例市', start_date='2026-09', end_date=None, ongoing=True, body='BODY_EDUCATION_CN')
    document['sections'][0]['entries'].append(chinese)
    return document


def text_runs(path, directory):
    runs = []
    reader = PdfReader(path)
    for index, page in enumerate(reader.pages):
        debug = directory / f'layout-{index}'
        debug.mkdir()
        page.extract_text(extraction_mode='layout', layout_mode_debug_path=debug)
        runs.extend(dict(run, page=index, page_width=float(page.mediabox.width))
                    for run in json.loads((debug / 'tjs.json').read_text()))
    return runs


def measure_dates(document, runs, fonts, same_row):
    errors = []
    for section in document['sections']:
        for entry in section['entries']:
            parts = [value for value in (entry['start_date'], '至今' if entry['ongoing'] else entry['end_date']) if value]
            date = ' - '.join(parts)
            matching = [run for run in runs if run['txt'] == parts[0]]
            assert len(matching) == 1, (section['type'], parts[0], len(matching))
            run = matching[0]
            # PDF text-run origins are exact; use bundled font advances because pypdf's
            # inferred CID widths can be wrong even when the glyph origins are correct.
            advance = sum(fonts['cjk' if re.match(r'[\u4e00-\u9fff]', segment) else 'latin'].getlength(segment)
                          for segment in re.findall(r'[\u4e00-\u9fff]+|[^\u4e00-\u9fff]+', date))
            right = run['tx'] + advance * run['font_size'] / 1000
            target = run['page_width'] - document['style']['margins_px']['right'] * .75
            error = abs(right - target)
            assert error < .1, (section['type'], date, right, target)
            if same_row:
                title = next(entry[key] for key in ('school', 'organization', 'name', 'heading') if key in entry)
                row = ''.join(item['txt'] for item in sorted(runs, key=lambda item:item['tx'])
                              if item['page'] == run['page'] and abs(item['ty'] - run['ty']) < .05)
                assert compact(title) in compact(row), (title, row)
            errors.append(error)
    return {'dates':len(errors), 'max_right_edge_error_bp':round(max(errors), 4)}


def main():
    base = fixture()
    fonts = {key:ImageFont.truetype(str(ROOT / 'assets/fonts' / filename), size=1000)
             for key, filename in [('latin', 'NotoSans-Regular.ttf'), ('cjk', 'NotoSansCJKsc-Regular.otf')]}
    runtime = compiler_manifest(ROOT / '.m1-build/local-install/current')
    report = {'checks':{}}
    with tempfile.TemporaryDirectory(prefix='date-alignment-', dir=ROOT / 'tmp/pdfs') as temporary:
        for scenario in ('normal', 'long_titles', 'date_only', 'partial_dates'):
            document = copy.deepcopy(base)
            for section in document['sections']:
                for index, entry in enumerate(section['entries']):
                    if scenario in ('long_titles', 'date_only'):
                        for key in ('school', 'organization', 'name', 'heading'):
                            if key in entry:
                                entry[key] = ('长学校名称' * 32 if index else 'Long institution title ' * 8).strip() if scenario == 'long_titles' else ''
                        if scenario == 'date_only':
                            for key in ('degree', 'field_of_study', 'location', 'role'):
                                if key in entry:
                                    entry[key] = ''
                            if 'url' in entry:
                                entry['url'] = None
                    if scenario == 'partial_dates':
                        if section['type'] in ('education', 'project', 'competition'):
                            entry.update(end_date=None, ongoing=False)
                        else:
                            entry.update(start_date=None, ongoing=False)
            if scenario == 'long_titles':
                document['style']['margins_px'].update(left=96, right=96)
            elif scenario == 'partial_dates':
                document['style'].update(content_size_px=12)
                document['style']['margins_px']['right'] = 20
            directory = Path(temporary) / scenario
            source, avatar = render_resume(document)
            result = compile_and_check(source, avatar, document, directory, runtime)
            assert result['ok'] and result['overfull_boxes'] == 0, result
            report['checks'][scenario] = measure_dates(document, text_runs(directory / 'main.pdf', directory), fonts, scenario == 'normal')
            if scenario == 'normal':
                output = ROOT / 'output/pdf/date-alignment.pdf'
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes((directory / 'main.pdf').read_bytes())
    report.update(passed=True, timeline_types=6, scenarios=4)
    (ROOT / 'work-logs/evidence/m2-date-alignment.json').write_bytes(json_bytes(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
