const $ = (id) => document.getElementById(id);
let library, documentTask, pdf, job, renderTask, generation = 0, rendering = 0, page = 1, resizeTimer;

function failure() {
  $('pdf-render-error').textContent = '浏览器未能渲染这份 PDF。文件已生成，可点击“导出 PDF”下载查看。';
  $('pdf-render-error').hidden = false;
}
function reset() {
  generation++; rendering++;
  renderTask?.cancel(); renderTask = null;
  documentTask?.destroy(); documentTask = null;
  pdf = null; job = null; page = 1;
  $('pdf-pages').replaceChildren(); $('pdf-pages').hidden = true;
  $('pdf-toolbar').hidden = true; $('pdf-render-error').hidden = true;
}
export function clearPdf() { reset(); $('pdf-empty').hidden = false; }

async function draw() {
  if (!pdf || $('editor').hidden) return;
  const version = ++rendering, source = pdf, target = page;
  renderTask?.cancel();
  try {
    const sheet = await source.getPage(target);
    if (version !== rendering) return;
    const zoom = Number($('pdf-zoom').value), width = Math.max(200, $('pdf-container').clientWidth - 32);
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const viewport = sheet.getViewport({scale: width / sheet.getViewport({scale: 1}).width * zoom});
    const canvas = document.createElement('canvas');
    canvas.width = Math.ceil(viewport.width * ratio); canvas.height = Math.ceil(viewport.height * ratio);
    canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`;
    canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', `PDF 第 ${target} 页`);
    const task = sheet.render({canvasContext: canvas.getContext('2d'), viewport, transform: [ratio, 0, 0, ratio, 0, 0]});
    renderTask = task;
    await task.promise;
    const content = await sheet.getTextContent();
    if (version !== rendering || pdf !== source) return;
    const text = document.createElement('p'); text.className = 'sr-only'; text.textContent = content.items.map((item) => item.str || '').join(' ');
    $('pdf-pages').replaceChildren(canvas, text); $('pdf-pages').hidden = false;
    $('pdf-page').textContent = `${target} / ${source.numPages} 页`;
    $('pdf-prev').disabled = target <= 1; $('pdf-next').disabled = target >= source.numPages;
    $('pdf-toolbar').hidden = false; $('pdf-render-error').hidden = true;
  } catch (error) {
    if (version === rendering && error.name !== 'RenderingCancelledException') failure();
  }
}

export async function showPdf(id, url) {
  if (job === id && pdf) { await draw(); return; }
  reset(); job = id;
  const version = generation;
  $('pdf-empty').hidden = true;
  try {
    library ||= await import('/assets/pdf.min.mjs');
    if (version !== generation) return;
    library.GlobalWorkerOptions.workerSrc = '/assets/pdf.worker.min.mjs';
    const task = library.getDocument({url, isEvalSupported: false, useWasm: false, useSystemFonts: false});
    documentTask = task;
    const loaded = await task.promise;
    if (version !== generation) { await loaded.destroy(); return; }
    pdf = loaded; await draw();
  } catch {
    if (version === generation) failure();
  }
}

$('pdf-prev').addEventListener('click', () => { if (pdf && page > 1) { page--; draw(); } });
$('pdf-next').addEventListener('click', () => { if (pdf && page < pdf.numPages) { page++; draw(); } });
$('pdf-zoom').addEventListener('change', () => draw());
new ResizeObserver(() => { clearTimeout(resizeTimer); resizeTimer = setTimeout(draw, 120); }).observe($('pdf-container'));
