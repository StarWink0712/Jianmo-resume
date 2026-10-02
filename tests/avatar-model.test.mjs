import test from 'node:test';
import assert from 'node:assert/strict';
import {AVATAR_ACCEPT, avatarFileError, MAX_AVATAR_UPLOAD_BYTES} from '../web/avatar-model.mjs';

test('JPG, JPEG and PNG extensions accept mixed case and empty browser MIME', () => {
  for (const name of ['photo.jpg', 'photo.JPEG', 'photo.PnG']) {
    assert.equal(avatarFileError({name, size:100, type:''}), '');
  }
  for (const extension of ['.jpg', '.jpeg', '.png']) assert.ok(AVATAR_ACCEPT.split(',').includes(extension));
});
test('one MB is inclusive and a single excess byte is rejected', () => {
  assert.equal(MAX_AVATAR_UPLOAD_BYTES, 1_000_000);
  assert.equal(avatarFileError({name:'a.png', size:MAX_AVATAR_UPLOAD_BYTES}), '');
  assert.match(avatarFileError({name:'a.png', size:MAX_AVATAR_UPLOAD_BYTES + 1}), /1 MB/);
});
test('unsupported extensions and empty files are rejected before upload', () => {
  for (const name of ['a.gif', 'a.webp', 'a.svg', 'a.jpg.exe', 'a']) assert.ok(avatarFileError({name,size:100}));
  for (const size of [0, -1, NaN]) assert.ok(avatarFileError({name:'a.jpg',size}));
});
