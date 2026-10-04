"""Measure fixed row/paragraph/item rhythm in actual PDFs, independent of module gap."""

import copy
from pathlib import Path
import tempfile

from experiments.m1.managed import compiler_manifest
from experiments.m1.render import render_resume
from core.tex_checks import compile_and_check

from experiments.m1.style import RHYTHM, STYLE_CONFIG
from scripts.check_contracts import ROOT, build_case, cases, json_bytes
from scripts.check_entry_headings import text_lines


def metrics(path):
    lines = text_lines(path)
    def y(fragment):
        found = [position for position, text in lines.items() if fragment in text]
        assert len(found) == 1, (fragment, found)
        assert found[0][0] == 0
        return found[0][1]
    leading = 15 * .75 * RHYTHM['body_line_height']
    return {
        'header_extra_bp':round(y('JOB_INTENT') - y('CITY_LINE') - leading, 2),
        'heading_extra_bp':round(y('ENTRY_ONE') - y('BULLET_ONE') - leading, 2),
        'list_item_extra_bp':round(y('BULLET_ONE') - y('BULLET_TWO') - leading, 2),
        'list_to_paragraph_extra_bp':round(y('BULLET_TWO') - y('PARA_ONE') - leading, 2),
        'paragraph_extra_bp':round(y('PARA_ONE') - y('PARA_TWO') - leading, 2),
        'entry_extra_bp':round(y('PARA_TWO') - y('ENTRY_TWO') - leading, 2),
        'section_distance_bp':round(y('SECOND_BODY') - y('NEXT_SECTION'), 2),
    }


def main():
    resume, _ = build_case(cases()[0])
    resume['style'] = copy.deepcopy(STYLE_CONFIG['defaults'])
    resume['style'].update(content_size_px=15, section_gap_px=5)
    resume['basics'].update(name='NAME', headline='JOB_INTENT', location='CITY_LINE', email='', phone='', links=[])
    resume['sections'] = [{
        'id':'section-work', 'type':'employment', 'title':'FIRST_SECTION', 'visible':True,
        'entries':[
            {'id':'entry-one', 'visible':True, 'organization':'ENTRY_ONE', 'role':'ROLE_ONE', 'location':'',
             'employment_type':'internship', 'start_date':None, 'end_date':None, 'ongoing':False,
             'body':'- BULLET_ONE\n- BULLET_TWO\n\nPARA_ONE\n\nPARA_TWO'},
            {'id':'entry-two', 'visible':True, 'organization':'ENTRY_TWO', 'role':'ROLE_TWO', 'location':'',
             'employment_type':'internship', 'start_date':None, 'end_date':None, 'ongoing':False,
             'body':'SECOND_BODY'},
        ]}, {'id':'section-next', 'type':'skills', 'title':'NEXT_SECTION', 'visible':True,
              'entries':[{'id':'entry-next', 'label':'', 'body':'NEXT_BODY', 'visible':True}]}]
    runtime = compiler_manifest(ROOT / '.m1-build/local-install/current')
    reports = []
    with tempfile.TemporaryDirectory(prefix='fixed-spacing-', dir=ROOT / 'tmp/pdfs') as temporary:
        for index, (height, gap) in enumerate([(1.1, 5), (2, 5), (1.1, 13)]):
            resume['style'].update(line_height=height, section_gap_px=gap)
            source, avatar = render_resume(resume)
            job = Path(temporary) / str(index)
            result = compile_and_check(source, avatar, resume, job, runtime)
            assert result['ok'] and result['pages'] == 1, result
            reports.append(metrics(job / 'main.pdf'))
    for key, expected in [('header_extra_bp', 2.25), ('heading_extra_bp', 3), ('list_item_extra_bp', 1.5),
                          ('list_to_paragraph_extra_bp', 3), ('paragraph_extra_bp', 3), ('entry_extra_bp', 6)]:
        assert abs(reports[0][key] - expected) < .05, (key, reports[0][key], expected)
    assert reports[0] == reports[1], 'Saved legacy line height must not alter fixed rhythm'
    assert abs(reports[2]['section_distance_bp'] - reports[0]['section_distance_bp'] - 6) < .05
    for key in reports[0].keys() - {'section_distance_bp'}:
        assert abs(reports[0][key] - reports[2][key]) < .05
    report = {'passed':True, 'measured':reports[0], 'legacy_line_height_ignored':True,
              'module_gap_adjusts_independently':True, 'no_extra_list_top_spacing':True}
    (ROOT / 'work-logs/evidence/m2-fixed-spacing.json').write_bytes(json_bytes(report))
    print(report)


if __name__ == '__main__':
    main()
