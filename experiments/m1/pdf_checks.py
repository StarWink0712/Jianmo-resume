"""PDF structure checks and explicit CJK ToUnicode normalization."""

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject
from core.tex_pipeline import RUNTIME


def ensure_unicode_maps(path, cmap=None):
    reader = PdfReader(path)
    writer = PdfWriter(clone_from=reader)
    repaired = 0
    mapping_ref = None
    for page in writer.pages:
        for reference in page.get('/Resources', {}).get('/Font', {}).values():
            font = reference.get_object()
            if font.get('/Subtype') != '/Type0' or '/ToUnicode' in font:
                continue
            descendant = font['/DescendantFonts'][0].get_object()
            info = descendant['/CIDSystemInfo']
            if str(info['/Registry']) != 'Adobe' or str(info['/Ordering']) != 'GB1' or font['/Encoding'] != '/Identity-H':
                raise ValueError('unmapped font requires a reviewed Unicode mapping')
            if mapping_ref is None:
                source = Path(cmap) if cmap else RUNTIME / 'cmaps' / 'Adobe-GB1-UCS2'
                stream = DecodedStreamObject()
                stream.set_data(source.read_bytes())
                mapping_ref = writer._add_object(stream.flate_encode())
            font[NameObject('/ToUnicode')] = mapping_ref
            repaired += 1
    if repaired:
        temporary = Path(path).with_suffix('.normalized.pdf')
        writer.write(temporary)
        temporary.replace(path)
    return repaired


def inspect_pdf(path):
    reader = PdfReader(path)
    texts = [page.extract_text() or '' for page in reader.pages]
    fonts = {}
    links = []
    for page in reader.pages:
        for reference in page.get('/Resources', {}).get('/Font', {}).values():
            font = reference.get_object()
            descendant = font['/DescendantFonts'][0].get_object() if '/DescendantFonts' in font else font
            descriptor = descendant.get('/FontDescriptor', {})
            descriptor = descriptor.get_object() if hasattr(descriptor, 'get_object') else descriptor
            fonts[str(font['/BaseFont'])] = {'embedded': any(key in descriptor for key in ('/FontFile', '/FontFile2', '/FontFile3')),
                                          'unicode_map': '/ToUnicode' in font}
        for reference in page.get('/Annots', []):
            annotation = reference.get_object()
            if annotation.get('/A', {}).get('/S') == '/URI':
                links.append(str(annotation['/A']['/URI']))
    return {'pages': len(reader.pages), 'text': '\n'.join(texts), 'fonts': fonts, 'links': links,
            'page_sizes_pt': [[float(page.mediabox.width), float(page.mediabox.height)] for page in reader.pages]}
