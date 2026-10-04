"""Pure semantic checks shared by the backend, installer and experiments."""

import unicodedata

from markdown_it import MarkdownIt

from experiments.m1.render import contact_link_text
from experiments.m1.style import content_only


PAGE_TARGETS = {'standard-one-page-target': 1, 'two-page-target': 2}


def case_passes(case, result):
    if not case['valid'] or bool(case.get('render_expectation')):
        return result.get('rejected', False)
    return bool(result.get('ok')) and (case['id'] not in PAGE_TARGETS or result.get('pages') == PAGE_TARGETS[case['id']])


def benchmark_passes(benchmark):
    if benchmark['iterations'] < 30:
        return None
    return benchmark['pages'] == 2 and benchmark['p95_seconds'] <= benchmark['p95_target_seconds']


def compact(text):
    return ''.join(unicodedata.normalize('NFC', text).split())


def expected_text(resume):
    expected = [resume['basics'][key] for key in ('name', 'headline', 'email', 'phone', 'location') if resume['basics'][key]]
    if resume['basics'].get('gender'):
        expected.append(resume['basics']['gender'])
    if resume['basics'].get('age') is not None:
        expected.append(f"{int(resume['basics']['age'])}岁")
    expected += [contact_link_text(item) for item in resume['basics']['links']]
    parser = MarkdownIt('commonmark')
    names = {'education': ['school', 'degree', 'field_of_study', 'location'],
             'employment': ['organization', 'role', 'location'], 'project': ['name', 'role'],
             'skills': ['label'], 'custom': ['heading', 'role'],
             'academic': ['heading', 'role'], 'competition': ['heading', 'role']}
    for section in resume['sections']:
        visible = [entry for entry in section['entries'] if entry['visible']]
        if not section['visible'] or not visible:
            continue
        expected.append(section['title'])
        for entry in visible:
            if not content_only(section):
                expected.extend(entry[key] for key in names[section['type']] if entry.get(key))
                expected.extend(value for value in (entry.get('start_date'), '至今' if entry.get('ongoing') else entry.get('end_date')) if value)
            for token in parser.parse(entry['body']):
                if token.type == 'inline':
                    expected.extend(child.content for child in token.children or [] if child.type == 'text' and child.content.strip())
    return expected
