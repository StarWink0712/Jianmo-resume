import {CROP_WIDTH, CROP_HEIGHT, MAX_AVATAR_DECODE_PIXELS, cropFrame, cropTransform, isAvatarImage, avatarDimensions} from './avatar-crop-model.mjs';
import {MAX_AVATAR_UPLOAD_BYTES} from './avatar-model.mjs';

const $ = (id) => document.getElementById(id);

function paintPhoto(ctx, image, state) {
  ctx.translate(CROP_WIDTH / 2 + state.x, CROP_HEIGHT / 2 + state.y);
  ctx.rotate(state.rotation * Math.PI / 180);
  ctx.scale(state.scale, state.scale);
  ctx.drawImage(image, -state.width / 2, -state.height / 2);
}

async function cropBlob(image, state) {
  const canvas = document.createElement('canvas');
  canvas.width = CROP_WIDTH; canvas.height = CROP_HEIGHT;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  paintPhoto(ctx, image, state);
  for (const quality of [.92, .82, .72]) {
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality));
    if (blob && blob.size <= MAX_AVATAR_UPLOAD_BYTES) return blob;
  }
  throw new Error('裁剪图片生成失败，请重试或选择另一张图片。');
}

export function cropAvatar(blob) {
  const dialog = $('avatar-crop-dialog');
  if (dialog.open) return Promise.reject(new Error('请先完成当前头像裁剪。'));
  return new Promise((resolve) => {
    const canvas = $('crop-canvas'), zoom = $('crop-zoom'), rotation = $('crop-rotation');
    const confirm = $('crop-confirm'), controls = $('crop-controls'), status = $('crop-status');
    const image = new Image(), controller = new AbortController(), options = {signal: controller.signal};
    let state, pointer, frame, url, finished = false, working = false;
    controls.disabled = confirm.disabled = true; confirm.textContent = '确认裁剪';
    status.textContent = '正在读取图片…'; status.removeAttribute('data-error');
    zoom.value = '1'; rotation.value = '0';
    $('crop-zoom-value').textContent = '100%'; $('crop-rotation-value').textContent = '0°';

    function draw() {
      const rect = canvas.getBoundingClientRect();
      if (!rect.width || !rect.height || finished) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(rect.width * ratio); canvas.height = Math.round(rect.height * ratio);
      const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio);
      ctx.fillStyle = '#edf0f5'; ctx.fillRect(0, 0, rect.width, rect.height);
      if (!state) return;
      frame = cropFrame(rect.width, rect.height);
      ctx.fillStyle = '#fff'; ctx.fillRect(frame.x, frame.y, frame.width, frame.height);
      ctx.save(); ctx.translate(frame.x, frame.y); ctx.scale(frame.scale, frame.scale);
      paintPhoto(ctx, image, state); ctx.restore();
      ctx.fillStyle = '#111b2b99';
      ctx.fillRect(0, 0, rect.width, frame.y);
      ctx.fillRect(0, frame.y + frame.height, rect.width, rect.height - frame.y - frame.height);
      ctx.fillRect(0, frame.y, frame.x, frame.height);
      ctx.fillRect(frame.x + frame.width, frame.y, rect.width - frame.x - frame.width, frame.height);
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 2;
      ctx.strokeRect(frame.x, frame.y, frame.width, frame.height);
      ctx.strokeStyle = '#ffffff70'; ctx.lineWidth = 1;
      for (const part of [1 / 3, 2 / 3]) {
        ctx.beginPath(); ctx.moveTo(frame.x + frame.width * part, frame.y);
        ctx.lineTo(frame.x + frame.width * part, frame.y + frame.height);
        ctx.moveTo(frame.x, frame.y + frame.height * part);
        ctx.lineTo(frame.x + frame.width, frame.y + frame.height * part); ctx.stroke();
      }
    }
    function change(update) {
      if (!state || working) return;
      state = cropTransform({...state, ...update});
      zoom.value = String(state.zoom); rotation.value = String(state.rotation);
      $('crop-zoom-value').textContent = `${Math.round(state.zoom * 100)}%`;
      $('crop-rotation-value').textContent = `${Math.round(state.rotation)}°`;
      draw();
    }
    function finish(result) {
      if (finished) return;
      finished = true; observer.disconnect(); controller.abort();
      if (url) URL.revokeObjectURL(url);
      image.src = ''; canvas.width = canvas.height = 1;
      dialog.close(); resolve(result);
    }
    const observer = new ResizeObserver(draw);
    observer.observe(canvas);
    dialog.addEventListener('cancel', (event) => { event.preventDefault(); finish(null); }, options);
    dialog.addEventListener('close', () => finish(null), options);
    for (const id of ['crop-close', 'crop-cancel']) $(id).addEventListener('click', () => finish(null), options);
    zoom.addEventListener('input', () => change({zoom: Number(zoom.value)}), options);
    rotation.addEventListener('input', () => change({rotation: Number(rotation.value)}), options);
    for (const [id, delta] of [['crop-zoom-out', -.1], ['crop-zoom-in', .1]]) {
      $(id).addEventListener('click', () => change({zoom: state.zoom + delta}), options);
    }
    for (const [id, delta] of [['crop-left', -90], ['crop-right', 90]]) {
      $(id).addEventListener('click', () => change({rotation: state.rotation + delta}), options);
    }
    $('crop-reset').addEventListener('click', () => change({zoom: 1, rotation: 0, x: 0, y: 0}), options);
    canvas.addEventListener('pointerdown', (event) => {
      if (!state || working || pointer || event.button !== 0) return;
      pointer = {id: event.pointerId, x: event.clientX, y: event.clientY};
      canvas.setPointerCapture(event.pointerId); canvas.focus(); event.preventDefault();
    }, options);
    canvas.addEventListener('pointermove', (event) => {
      if (pointer?.id !== event.pointerId || !frame) return;
      change({x: state.x + (event.clientX - pointer.x) / frame.scale,
        y: state.y + (event.clientY - pointer.y) / frame.scale});
      pointer.x = event.clientX; pointer.y = event.clientY;
    }, options);
    for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
      canvas.addEventListener(name, (event) => { if (pointer?.id === event.pointerId) pointer = null; }, options);
    }
    canvas.addEventListener('keydown', (event) => {
      const direction = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[event.key];
      if (!direction || !state) return;
      event.preventDefault(); const step = event.shiftKey ? 40 : 10;
      change({x: state.x + direction[0] * step, y: state.y + direction[1] * step});
    }, options);
    confirm.addEventListener('click', async () => {
      if (!state || working) return;
      working = true; controls.disabled = confirm.disabled = true; confirm.textContent = '正在处理…';
      try { const result = await cropBlob(image, state); if (!finished) finish(result); }
      catch (error) {
        if (!finished) { status.textContent = error.message; status.dataset.error = 'true'; }
      } finally {
        if (!finished) { working = false; controls.disabled = confirm.disabled = false; confirm.textContent = '确认裁剪'; }
      }
    }, options);
    dialog.showModal(); draw();
    (async () => {
      try {
        if (!await isAvatarImage(blob)) throw new Error('请选择有效的 JPG、JPEG 或 PNG 图片。');
        await avatarDimensions(blob);
        if (finished) return;
        url = URL.createObjectURL(blob); image.src = url;
        try { await image.decode(); }
        catch { throw new Error('图片无法读取，请选择有效的 JPG、JPEG 或 PNG 图片。'); }
        if (finished) return;
        if (image.naturalWidth * image.naturalHeight > MAX_AVATAR_DECODE_PIXELS) throw new Error('图片解码后的像素占用过大，请压缩图片后重试。');
        state = cropTransform({width: image.naturalWidth, height: image.naturalHeight});
        controls.disabled = confirm.disabled = false;
        status.textContent = '只保留框内画面；确认后保存，取消不改变原头像。'; draw();
      } catch (error) {
        if (!finished) { status.textContent = error.message || '图片无法读取，请选择另一张图片。'; status.dataset.error = 'true'; }
      }
    })();
  });
}
