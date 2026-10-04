import hashlib
from pathlib import Path

from backend.domain import AppError
from core.resume_checks import compact, expected_text
from core.tex_pipeline import compile_tex
from experiments.m1.fonts import uses_bundled_fonts, verify_fonts
from core.managed_runtime import compiler_manifest, digest, verify_runtime
from experiments.m1.pdf_checks import ensure_unicode_maps, inspect_pdf
from experiments.m1.render import render_resume, RenderError
from platform_adapters.detect import get_adapter
from scripts.check_contracts import ROOT


class Compiler:
    def __init__(self, runtime, adapter=None):
        self.adapter = adapter or get_adapter()
        self.adapter.CAPABILITIES.require_compilation()
        verify_runtime(runtime)
        self.root = Path(runtime).resolve()
        self.fonts_root = verify_fonts(self.root / 'tex/fonts')
        inputs = [self.root / 'runtime.json', Path(__file__),
                  ROOT / 'experiments/m1/render.py', ROOT / 'experiments/m1/managed.py',
                  ROOT / 'experiments/m1/pdf_checks.py', ROOT / 'experiments/m1/fonts.py',
                  ROOT / 'experiments/m1/style.py', ROOT / 'web/style-config.json',
                  *sorted((ROOT / 'core').rglob('*.py')),
                  *sorted((ROOT / 'platform_adapters').rglob('*.py'))]
        self.fingerprint = hashlib.sha256((self.adapter.KEY + ''.join(digest(path) for path in inputs)).encode()).hexdigest()
        self.manifest = compiler_manifest(self.root)

    def __call__(self, document, assets, job):
        try:
            source, avatar = render_resume(document, assets)
        except RenderError as error:
            raise AppError(422, 'unsupported_markdown', '内容已保存，但含不支持的 Markdown。请检查 HTML、代码、图片、链接或过深列表。') from error
        result = compile_tex(source, job, self.manifest, avatar, adapter=self.adapter)
        if result['timed_out']:
            raise AppError(422, 'timed_out', '编译超时，已停止任务。保存内容不受影响。')
        if result['memory_exceeded']:
            raise AppError(422, 'memory_limit', '编译超过内存保护阈值，已停止任务。')
        if not result['ok']:
            raise AppError(422, 'compile_failed', 'PDF 编译失败，可能含字体不支持的字符；内容已保存。')
        pdf = job / 'main.pdf'
        ensure_unicode_maps(pdf, self.root / 'tex/cmaps/Adobe-GB1-UCS2')
        checked = inspect_pdf(pdf)
        text = compact(checked['text'])
        if (result['overfull_boxes'] or any(compact(fragment) not in text for fragment in expected_text(document))
                or not uses_bundled_fonts(checked['fonts'])):
            raise AppError(422, 'pdf_validation_failed', 'PDF 内容或版面检查未通过。请缩短过长字段，或调整排版。')
        return pdf.read_bytes(), checked['pages']
