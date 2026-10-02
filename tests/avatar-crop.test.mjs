import test from 'node:test';
import assert from 'node:assert/strict';
import {CROP_WIDTH, CROP_HEIGHT, cropFrame, cropTransform, isAvatarImage, avatarDimensions} from '../web/avatar-crop-model.mjs';

function assertCovered(state) {
  const angle = state.rotation * Math.PI / 180, c = Math.cos(angle), s = Math.sin(angle);
  for (const x of [-CROP_WIDTH / 2, CROP_WIDTH / 2]) {
    for (const y of [-CROP_HEIGHT / 2, CROP_HEIGHT / 2]) {
      const dx = x - state.x, dy = y - state.y;
      assert.ok(Math.abs((dx * c + dy * s) / state.scale) <= state.width / 2 + 1e-7);
      assert.ok(Math.abs((-dx * s + dy * c) / state.scale) <= state.height / 2 + 1e-7);
    }
  }
}

test('initial 3:4 crop covers the frame without stretching the photo', () => {
  assert.equal(CROP_WIDTH / CROP_HEIGHT, .75);
  const state = cropTransform({width: 1200, height: 800});
  assert.equal(state.scale, 1);
  assert.equal(state.x, 0);
  assert.equal(state.y, 0);
  assertCovered(state);
});

test('landscape, portrait, tiny and elongated photos stay covered at all rotations', () => {
  for (const [width, height] of [[1200, 800], [300, 400], [800, 800], [8, 70], [5000, 1000]]) {
    for (let rotation = -180; rotation <= 180; rotation += 3) {
      for (const zoom of [1, 1.5, 4]) {
        for (const [x, y] of [[0, 0], [-100000, 100000], [100000, -100000]]) {
          assertCovered(cropTransform({width, height, rotation, zoom, x, y}));
        }
      }
    }
  }
});

test('panning is clamped and cannot expose empty corners', () => {
  const state = cropTransform({width: 1200, height: 800, x: 9999, y: -9999});
  assert.equal(state.x, 300); assert.equal(state.y, 0);
  assertCovered(state);
});

test('zoom and rotation are bounded without mutating the input', () => {
  const input = {width: 600, height: 800, zoom: 100, rotation: 450, x: 1, y: 2};
  const before = structuredClone(input), result = cropTransform(input);
  assert.deepEqual(input, before); assert.equal(result.zoom, 4); assert.equal(result.rotation, 90);
  assert.equal(cropTransform({...input, zoom: 0, rotation: -450}).rotation, -90);
  assert.equal(cropTransform({...input, zoom: 0}).zoom, 1);
});

test('invalid dimensions or non-finite transforms are rejected', () => {
  for (const patch of [{width: 0}, {height: -1}, {width: Infinity}, {zoom: NaN}, {rotation: Infinity}, {x: NaN}]) {
    assert.throws(() => cropTransform({width: 600, height: 800, ...patch}));
  }
});

test('desktop and narrow crop frames retain their ratio within the canvas', () => {
  for (const [width, height] of [[710, 440], [324, 362], [100, 200]]) {
    const frame = cropFrame(width, height);
    assert.ok(Math.abs(frame.width / frame.height - .75) < 1e-10);
    assert.ok(frame.x > 0 && frame.y > 0);
    assert.ok(frame.x + frame.width < width && frame.y + frame.height < height);
  }
});

test('PNG/JPEG signatures are checked before decoding and re-encoding', async () => {
  for (const header of [[137,80,78,71,13,10,26,10], [255,216,255,224]]) {
    assert.equal(await isAvatarImage(new Blob([new Uint8Array(header)])), true);
  }
  for (const input of ['', 'GIF89a', '<svg/>', 'RIFFfakeWEBP']) {
    assert.equal(await isAvatarImage(new Blob([input], {type: 'image/png'})), false);
  }
});

test('PNG dimensions are bounded before bitmap decoding without an aspect restriction', async () => {
  const buffer = new ArrayBuffer(24), header = new DataView(buffer);
  [0x89504e47, 0x0d0a1a0a, 13, 0x49484452, 5000, 1000].forEach((value, i) => header.setUint32(i * 4, value));
  assert.deepEqual(await avatarDimensions(new Blob([buffer])), {width: 5000, height: 1000});
  header.setUint32(20, 5000);
  await assert.rejects(avatarDimensions(new Blob([buffer])), /像素占用过大/);
  header.setUint32(16, 0);
  await assert.rejects(avatarDimensions(new Blob([buffer])), /尺寸无效/);
});

test('baseline and progressive JPEG dimensions skip metadata and reject truncated segments', async () => {
  for (const marker of [0xc0, 0xc2]) {
    const bytes = new Uint8Array([255,216,255,224,0,4,0,0,255,marker,0,11,8,3,32,2,88,1,1,17,0]);
    assert.deepEqual(await avatarDimensions(new Blob([bytes])), {width: 600, height: 800});
    await assert.rejects(avatarDimensions(new Blob([bytes.slice(0, 13)])), /无法读取/);
    bytes[13] = bytes[14] = 255;
    await assert.rejects(avatarDimensions(new Blob([bytes])), /像素占用过大/);
  }
  for (const content of ['', 'GIF89a', '\xff\xd8']) await assert.rejects(avatarDimensions(new Blob([content])));
});
