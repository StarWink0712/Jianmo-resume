"""Trusted-template renderer for the M1 experiment; never accepts raw TeX."""

import hashlib
import io
import unicodedata
from urllib.parse import quote

from markdown_it import MarkdownIt
from PIL import Image

from scripts.check_contracts import safe_url, validate_resume
from experiments.m1.style import RHYTHM, color_rgb, content_only, effective_style, px


class RenderError(ValueError):
    pass


ESCAPES = {
    '\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
    '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}',
    '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
}


def escape_text(value):
    if any(unicodedata.category(char).startswith('C') and char not in '\n\t' for char in value):
        raise RenderError('unsupported control character')
    return ''.join(ESCAPES.get(char, ' ' if char in '\n\t' else char) for char in value)


def link_target(url):
    if not safe_url(url):
        raise RenderError('unsafe link target')
    return escape_text(quote(url, safe=':/?&=#%+@,;~.-_'))


def contact_link_text(item):
    return item['label'].strip() or item['url']


def render_contact_link(item):
    if item['label'].strip():
        display = escape_text(contact_link_text(item))
    else:
        # Break long bare URLs only at separators, without changing their text or target.
        display = ''.join(escape_text(char) + (r'\allowbreak{}' if char in '/.?&=-_' else '') for char in item['url'])
    return r'\href{' + link_target(item['url']) + '}{' + display + '}'


def render_entry_heading(title, detail, date, url=None, link_label='项目链接', *, body_gap=True):
    parts = [r'\textbf{' + escape_text(title) + '}'] if title else []
    if detail:
        parts.append(escape_text(detail))
    if url:
        parts.append(r'\href{' + link_target(url) + '}{' + escape_text(link_label) + '}')
    line = r' \enspace\textbar{}\enspace '.join(parts)
    if date:
        # Starred fill survives a line break and also right-aligns date-only entries.
        line += (' ' if line else '') + r'\hspace*{\fill}\mbox{' + escape_text(date) + '}'
    if not line:
        return ''
    # Keep the date together, while allowing long names/roles to wrap without shrinking.
    # The explicit gap also applies to Markdown lists, whose topsep is zero.
    return r'{\raggedright ' + line + '\\par}\n' + (fixed_gap('entry_heading_gap_px', keep=True) if body_gap else '')


def fixed_gap(key, keep=False):
    gap = '\\vspace{' + px(RHYTHM[key]) + '}'
    return ('\\nobreak' + gap + '\\nobreak\n') if keep else gap + '\n'


def render_markdown(source):
    parser = MarkdownIt('commonmark', {'html': True})
    # Parse unsafe targets too, so our allowlist rejects rather than silently literalizes them.
    parser.validateLink = lambda _url: True
    tokens = parser.parse(source)
    output = []
    depth = 0
    blocks = [0]

    def begin_block():
        # Keep the first block flush with its heading; space only sibling blocks.
        if blocks[-1]:
            output.append('\\par\\addvspace{' + px(RHYTHM['paragraph_gap_px']) + '}\n')
        blocks[-1] += 1

    def inline(children):
        parts = []
        for token in children:
            if token.type == 'text':
                parts.append(escape_text(token.content))
            elif token.type == 'softbreak':
                parts.append(' ')
            elif token.type == 'hardbreak':
                # Unlike \\\\, newline cannot interpret a following [2] as a length.
                parts.append('\\newline{}\n')
            elif token.type in ('strong_open', 'em_open'):
                parts.append(r'\textbf{' if token.type == 'strong_open' else r'\textit{')
            elif token.type in ('strong_close', 'em_close', 'link_close'):
                parts.append('}')
            elif token.type == 'link_open':
                if token.info == 'auto':
                    raise RenderError('autolinks are outside the declared Markdown subset')
                parts.append(r'\href{' + link_target(token.attrGet('href')) + '}{')
            else:
                raise RenderError('unsupported inline node: ' + token.type)
        return ''.join(parts)

    for token in tokens:
        if token.type == 'inline':
            output.append(inline(token.children or []))
        elif token.type == 'paragraph_open':
            begin_block()
        elif token.type == 'paragraph_close':
            output.append('\n' if token.hidden else '\\par\n')
        elif token.type in ('bullet_list_open', 'ordered_list_open'):
            begin_block()
            depth += 1
            if depth > 2:
                raise RenderError('list nesting exceeds 2')
            if token.type == 'bullet_list_open':
                output.append('\\begin{itemize}\n')
            else:
                start = int(token.attrGet('start') or 1)
                output.append('\\begin{enumerate}[start=' + str(start) + ']\n')
        elif token.type in ('bullet_list_close', 'ordered_list_close'):
            depth -= 1
            output.append('\\end{' + ('itemize' if token.type == 'bullet_list_close' else 'enumerate') + '}\n')
        elif token.type == 'list_item_open':
            output.append('\\item ')
            blocks.append(0)
        elif token.type == 'list_item_close':
            output.append('\n')
            blocks.pop()
        else:
            raise RenderError('unsupported block node: ' + token.type)
    return ''.join(output)


def normalized_avatar(resume, assets):
    if not resume['attachments']:
        return None
    item = resume['attachments'][0]
    extension = 'png' if item['media_type'] == 'image/png' else 'jpg'
    content = assets.get(f"assets/{item['id']}.{extension}")
    if content is None or len(content) != item['byte_size'] or hashlib.sha256(content).hexdigest() != item['sha256']:
        raise RenderError('avatar payload mismatch')
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in ('PNG', 'JPEG') or image.format != ('PNG' if extension == 'png' else 'JPEG'):
                raise RenderError('unsupported avatar format')
            if image.size != (item['width_px'], item['height_px']) or max(image.size) > 4096:
                raise RenderError('avatar dimensions mismatch')
            image.load()
            clean = Image.new('RGB', image.size, 'white')
            rgba = image.convert('RGBA')
            clean.paste(rgba, mask=rgba.getchannel('A'))
            stream = io.BytesIO()
            clean.save(stream, format='PNG')
            return stream.getvalue()
    except (OSError, Image.DecompressionBombError) as error:
        raise RenderError('invalid avatar bytes') from error


PREAMBLE = r'''\documentclass[a4paper]{article}
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{geometry}
\usepackage{enumitem}
\usepackage{needspace}
\usepackage{graphicx}
\usepackage[unicode,hidelinks]{hyperref}
% User text is literal: do not turn quotes or repeated hyphens into TeX punctuation.
\defaultfontfeatures[\rmfamily,\sffamily]{Ligatures=TeXOff}
\setmainfont[Path=fonts/,BoldFont=NotoSans-Bold.ttf,ItalicFont=NotoSans-Italic.ttf,BoldItalicFont=NotoSans-BoldItalic.ttf]{NotoSans-Regular.ttf}
\setCJKmainfont[Path=fonts/,BoldFont=NotoSansCJKsc-Bold.otf,ItalicFont=NotoSansCJKsc-Regular.otf,ItalicFeatures={FakeSlant=0.2},BoldItalicFont=NotoSansCJKsc-Bold.otf,BoldItalicFeatures={FakeSlant=0.2}]{NotoSansCJKsc-Regular.otf}
\xeCJKDeclareCharClass{CJK}{"2190 -> "2BFF}
% CJK shares the middle-dot glyph with U+30FB; use Latin to preserve U+00B7.
\xeCJKDeclareCharClass{Default}{"00B7}
\pagestyle{empty}
\raggedbottom
\setlength{\parindent}{0pt}
\setlength{\parskip}{0pt}
% Keep words intact so PDF text extraction matches the saved content.
\hyphenpenalty=10000
\tracinglostchars=3
\clubpenalty=10000
\widowpenalty=10000
'''


def render_resume(resume, assets=None):
    errors = validate_resume(resume)
    if errors:
        raise RenderError('invalid resume contract: ' + '; '.join(errors[:3]))
    assets = assets or {}
    avatar = normalized_avatar(resume, assets)
    # Validate all content, including hidden sections, before generating a trusted template.
    bodies = {entry['id']: render_markdown(entry['body']) for section in resume['sections'] for entry in section['entries']}
    style = effective_style(resume['style'])
    margins = style['margins_px']
    result = [PREAMBLE, '\\geometry{' + ','.join(f'{key}={px(value)}' for key, value in margins.items()) + '}\n']
    result.append('\\setlist{nosep,leftmargin=1.5em,topsep=0pt,partopsep=0pt,parsep=0pt,itemsep=' + px(RHYTHM['list_item_gap_px']) + '}\n')
    result.append('\\begin{document}\n')
    result.append('\\setlength{\\emergencystretch}{.1\\linewidth}\n')
    size, leading = style['content_size_px'], style['content_size_px'] * style['line_height']
    result.append(f"\\fontsize{{{px(size)}}}{{{px(leading)}}}\\selectfont\n")
    basics = resume['basics']
    with_avatar = avatar is not None and basics['avatar_visible']
    if with_avatar:
        # Symmetric side columns keep the text centered on the page, not beside the photo.
        result.append('\\noindent\\begin{minipage}[t]{26mm}\\vspace{0pt}\\mbox{}\\end{minipage}%\n'
                      '\\begin{minipage}[t]{\\dimexpr\\linewidth-52mm\\relax}\\vspace{0pt}\n')
    result.append('\\begingroup\\centering\n')
    header_rows = []
    if basics['name']:
        header_rows.append('{\\fontsize{' + px(style['name_size_px']) + '}{' + px(style['name_size_px'] * 1.2) + '}\\selectfont\\bfseries\\strut ' + escape_text(basics['name']) + '\\par}\n')
    if basics['headline']:
        header_rows.append('{\\strut ' + escape_text(basics['headline']) + '\\par}\n')
    demographics = [basics.get('gender', '')]
    if basics.get('age') is not None:
        demographics.append(f"{int(basics['age'])}岁")
    demographics.append(basics['location'])
    if any(demographics):
        header_rows.append('{\\strut ' + ' \\textbar{} '.join(escape_text(value) for value in demographics if value) + '\\par}\n')
    contacts = [escape_text(basics[key]) for key in ('phone', 'email') if basics[key]]
    if contacts:
        header_rows.append('{\\strut ' + ' \\textbar{} '.join(contacts) + '\\par}\n')
    if basics['links']:
        header_rows.append('{\\strut ' + ' \\textbar{} '.join(render_contact_link(item) for item in basics['links']) + '\\par}\n')
    result.append(fixed_gap('header_line_gap_px', keep=True).join(header_rows))
    result.append('\\par\\endgroup\n')
    if with_avatar:
        result.append('\\end{minipage}%\n\\begin{minipage}[t]{26mm}\\vspace{0pt}\\raggedleft\\includegraphics[width=24mm,height=32mm,keepaspectratio]{avatar.png}\\end{minipage}\\par\n')
    for section in resume['sections']:
        entries = [entry for entry in section['entries'] if entry['visible']]
        if not section['visible'] or not entries:
            continue
        result.append(f"\\par\\addvspace{{{px(style['section_gap_px'])}}}\\Needspace{{4\\baselineskip}}\n")
        # Driver color specials avoid adding a host-only TeX package dependency.
        result.append('\\special{color push rgb ' + color_rgb(style['theme_color']) + '}\n')
        title_size = style['section_title_size_px']
        result.append('{\\fontsize{' + px(title_size) + '}{' + px(title_size * 1.25) + '}\\selectfont\\bfseries\\strut '
                      + escape_text(section['title']) + '}\\par\\vspace{2bp}\\hrule height 0.5bp\\special{color pop}\\vspace{3bp}\n')
        for index, entry in enumerate(entries):
            if index:
                result.append('\\par\\addvspace{' + px(RHYTHM['entry_gap_px']) + '}\\Needspace{2\\baselineskip}\n')
            kind = section['type']
            if kind == 'education':
                title, detail = entry['school'], ' / '.join(filter(None, (entry['degree'], entry['field_of_study'], entry['location'])))
            elif kind == 'employment':
                title, detail = entry['organization'], ' / '.join(filter(None, (entry['role'], entry['location'])))
            elif kind == 'project':
                title, detail = entry['name'], entry['role']
            elif kind in ('academic', 'competition', 'custom') and not content_only(section):
                title, detail = entry['heading'], entry.get('role', '')
            else:
                title, detail = entry['label'] if kind == 'skills' else entry['heading'], ''
            date = ''
            if not content_only(section):
                date = ' - '.join(filter(None, (entry.get('start_date'), '至今' if entry.get('ongoing') else entry.get('end_date'))))
            detailed_custom = kind == 'custom' and not content_only(section) and any(
                key in entry for key in ('role', 'start_date', 'end_date', 'ongoing', 'url'))
            if kind == 'education':
                heading = render_entry_heading(title, '', date, body_gap=False)
                result.append(heading)
                if detail:
                    if heading:
                        result.append(fixed_gap('education_detail_gap_px', keep=True))
                    result.append(escape_text(detail) + '\\par\n')
                if (heading or detail) and bodies[entry['id']].strip():
                    result.append(fixed_gap('entry_heading_gap_px', keep=True))
            elif kind in ('employment', 'project', 'academic', 'competition') or detailed_custom:
                link_label = {'academic':'成果链接', 'competition':'成果链接', 'custom':'相关链接'}.get(kind, '项目链接')
                result.append(render_entry_heading(title, detail, date, entry.get('url'), link_label))
            else:
                has_heading = False
                if title and not content_only(section):
                    result.append('\\textbf{' + escape_text(title) + '}\\par\n')
                    has_heading = True
                parts = [escape_text(detail)] if detail else []
                if date:
                    parts.append(escape_text(date))
                if parts:
                    if has_heading:
                        result.append(fixed_gap('education_detail_gap_px', keep=True))
                    result.append(' \\textbar{} '.join(parts) + '\\par\n')
                    has_heading = True
                if has_heading and bodies[entry['id']].strip():
                    result.append(fixed_gap('entry_heading_gap_px', keep=True))
            result.append(bodies[entry['id']])
    # An empty document must still produce a one-page PDF for the blank fixture.
    result.append('\\mbox{}\n\\end{document}\n')
    return ''.join(result), avatar
