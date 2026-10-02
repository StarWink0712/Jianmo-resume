import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {effectiveStyle, normalizeHex, contentOnly} from '../web/style-model.mjs';

const config = JSON.parse(readFileSync(new URL('../web/style-config.json', import.meta.url)));
test('six families provide 36 distinct colors', () => {
  assert.equal(config.palettes.length, 6);
  for (const palette of config.palettes) assert.equal(palette.colors.length, 6);
  assert.equal(new Set(config.palettes.flatMap(p => p.colors)).size, 36);
});
test('HEX accepts six digits with optional hash and rejects malformed/injected values', () => {
  assert.equal(normalizeHex('  a1b2c3 '), '#A1B2C3');
  assert.equal(normalizeHex('#123ABC'), '#123ABC');
  for (const value of ['', '#fff', '#1234567', 'red', '#xx0000', 'url(x)', '#000000}']) assert.equal(normalizeHex(value), null);
});
test('legacy measurements migrate to integer controls without mutating the source', () => {
  const old = {paper:'a4', font_size_pt:10, line_height:1.1, section_gap_pt:4, entry_gap_pt:2,
    margins_mm:{top:12, bottom:12, left:12, right:12}};
  const copy = structuredClone(old), migrated = effectiveStyle(old, config);
  assert.deepEqual(old, copy);
  assert.equal(migrated.version, 3);
  assert.equal(migrated.content_size_px, 13);
  assert.equal(migrated.section_gap_px, 5);
  assert.equal(migrated.margins_px.left, 45);
  assert.equal(migrated.name_size_px, 22);
});
test('old decimal pixel settings snap to preset sizes and integer spacing', () => {
  const old = {...structuredClone(config.defaults), version:2, section_title_size_px:15.94,
    content_size_px:15.94, section_gap_px:5.313};
  old.margins_px.top = 45.354; old.margins_px.bottom = 45.5;
  const copy = structuredClone(old), converted = effectiveStyle(old, config);
  assert.equal(converted.section_title_size_px, 16);
  assert.equal(converted.content_size_px, 16);
  assert.equal(converted.section_gap_px, 5);
  assert.equal(converted.margins_px.top, 45);
  assert.equal(converted.margins_px.bottom, 46);
  assert.deepEqual(old, copy);
});
test('modern settings return an independent deep copy', () => {
  const copy = effectiveStyle(config.defaults, config);
  assert.deepEqual(copy, config.defaults);
  copy.margins_px.top = 110;
  assert.equal(config.defaults.margins_px.top, 25);
});
test('only skills, awards and old award headings use the simple editor', () => {
  for (const type of ['skills', 'awards']) assert.ok(contentOnly({type, title:'renamed'}, config));
  assert.ok(contentOnly({type:'custom', title:'获奖经历'}, config));
  assert.equal(contentOnly({type:'custom', title:'补充说明'}, config), false);
});
test('line rhythm is fixed without mutating saved styles or the adjustable module gap', () => {
  for (const height of [1, 1.1, 1.35, 2]) {
    const saved = {...structuredClone(config.defaults), line_height:height, section_gap_px:17};
    const result = effectiveStyle(saved, config);
    assert.equal(result.line_height, config.rhythm.body_line_height);
    assert.equal(result.section_gap_px, 17);
    assert.equal(saved.line_height, height);
  }
  assert.equal(config.defaults.line_height, config.rhythm.body_line_height);
});
