"""Pixel-based style contract, with a non-mutating legacy adapter."""

import copy
import json
import math

from scripts.check_contracts import ROOT


STYLE_CONFIG = json.loads((ROOT / 'web/style-config.json').read_text(encoding='utf-8'))
RHYTHM = STYLE_CONFIG['rhythm']


def effective_style(style):
    if style.get('version', 1) >= 2:
        result = copy.deepcopy(style)
    else:
        result = copy.deepcopy(STYLE_CONFIG['defaults'])
        result.update(content_size_px=style['font_size_pt'] * 96 / 72.27,
                      section_title_size_px=12 * 96 / 72.27,
                      line_height=style['line_height'], section_gap_px=style['section_gap_pt'] * 96 / 72.27,
                      margins_px={key: value * 96 / 25.4 for key, value in style['margins_mm'].items()})
    for key, choices in STYLE_CONFIG['sizes'].items():
        result[key] = min(choices, key=lambda value: (abs(value - result[key]), value))
    result['version'] = 3
    # Preserve stored legacy settings; only the effective template rhythm is fixed.
    result['line_height'] = RHYTHM['body_line_height']
    # Match JavaScript Math.round for these non-negative lengths, including .5 ties.
    result['section_gap_px'] = math.floor(result['section_gap_px'] + .5)
    result['margins_px'] = {key: math.floor(value + .5) for key, value in result['margins_px'].items()}
    return result


def content_only(section):
    return section['type'] in ('skills', 'awards') or (
        section['type'] == 'custom' and section['title'].strip() in STYLE_CONFIG['award_titles']
        and not any(key in entry for entry in section.get('entries', [])
                    for key in ('role', 'start_date', 'end_date', 'ongoing', 'url')))


def px(value):
    # CSS 96 px/in, PDF 72 bp/in; do not confuse TeX pt (72.27/in) with PDF points.
    return f'{value * 0.75:.6f}bp'


def color_rgb(hex_color):
    return ' '.join(f'{int(hex_color[offset:offset + 2], 16) / 255:.6f}' for offset in (1, 3, 5))
