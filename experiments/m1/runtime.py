"""Developer runtime discovery and compatibility exports for the M1 harness."""

import hashlib
from pathlib import Path
import shutil
import subprocess

from core.tex_pipeline import RUNTIME, compile_tex, generate_format_at, resource_manifest, tex_config
from experiments.m1.fonts import FONT_FILES, FONT_LICENSES, font_source_url, verify_fonts
from platform_adapters.detect import get_adapter
from scripts.check_contracts import ROOT, json_bytes


FONT_NAMES = tuple(FONT_FILES)


def profile(*args, **kwargs):
    return get_adapter().profile(*args, **kwargs)


def group_rss_bytes(*args, **kwargs):
    return get_adapter().group_rss_bytes(*args, **kwargs)


def run_bounded(*args, **kwargs):
    return get_adapter().run_bounded(*args, **kwargs)


def generate_format(tex_root, engine):
    job = (RUNTIME / 'format-build').resolve()
    result = generate_format_at(job, tex_root, engine)
    if result['returncode'] != 0 or not (job / 'xelatex.fmt').is_file():
        raise ValueError('Project-local format generation failed; inspect .m1-runtime/format-build/process.log')
    inputs = resource_manifest(job, Path(tex_root), recorder='xelatex.fls')
    formats = (RUNTIME / 'formats').resolve()
    formats.mkdir(exist_ok=True)
    shutil.copyfile(job / 'xelatex.fmt', formats / 'xelatex.fmt')
    return formats, inputs


def query_kpse(argument):
    return Path(subprocess.check_output(['kpsewhich', argument], text=True).strip()).resolve(strict=True)


def prepare_runtime():
    root = query_kpse('-var-value=TEXMFROOT')
    engine = Path(shutil.which('xelatex')).resolve(strict=True)
    # xelatex is commonly a symlink to xetex; preserve its invocation name to load the format.
    engine = engine.parent / 'xelatex'
    if not engine.resolve().is_relative_to(root):
        raise ValueError('xelatex and kpsewhich resolve to different TeX installations; fix PATH before building.')
    (RUNTIME / 'fonts').mkdir(parents=True, exist_ok=True)
    (RUNTIME / 'licenses').mkdir(exist_ok=True)
    (RUNTIME / 'cmaps').mkdir(exist_ok=True)
    cmap_source = Path(subprocess.check_output(['kpsewhich', '-format=cmap', 'Adobe-GB1-UCS2'], text=True).strip()).resolve(strict=True)
    cmap_bytes = cmap_source.read_bytes()
    (RUNTIME / 'cmaps' / 'Adobe-GB1-UCS2').write_bytes(cmap_bytes)
    cmap = {'name': 'Adobe-GB1-UCS2', 'source': cmap_source.relative_to(root).as_posix(), 'bytes': len(cmap_bytes),
            'sha256': hashlib.sha256(cmap_bytes).hexdigest(), 'license': 'BSD-3-Clause; notice retained in CMap header'}
    fonts = []
    font_source = verify_fonts(ROOT / 'assets/fonts')
    for name in FONT_NAMES:
        source = font_source / name
        target = RUNTIME / 'fonts' / name
        content = source.read_bytes()
        target.write_bytes(content)
        fonts.append({'name': name, 'origin': 'project', 'source': 'assets/fonts/' + name,
                      'upstream': font_source_url(name),
                      'license': 'OFL-1.1', 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
    for name in FONT_LICENSES:
        shutil.copyfile(font_source / name, RUNTIME / 'fonts' / name)
    for name in (*FONT_LICENSES, 'README.md'):
        shutil.copyfile(font_source / name, RUNTIME / 'licenses' / ('noto-sans-cjk-' + name))
    formats, format_inputs = generate_format(root, engine)
    manifest = {'mode': 'developer-texlive-project-format', 'tex_root': str(root), 'engine': str(engine), 'fonts': fonts, 'cmap': cmap,
                'formats_root': str(formats), 'format_inputs': format_inputs,
                'font_bytes': sum(item['bytes'] for item in fonts), 'engine_version': subprocess.check_output([str(engine), '--version'], text=True).splitlines()[0]}
    (RUNTIME / 'manifest.json').write_bytes(json_bytes(manifest))
    return manifest
