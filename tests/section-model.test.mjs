import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createEntry, entryFields, hasTimeline, sectionLabels} from '../web/section-model.mjs';
import {contentOnly} from '../web/style-model.mjs';

const config = JSON.parse(readFileSync(new URL('../web/style-config.json', import.meta.url)));
test('all picker types have entry factories and fields', () => {
  for (const type of Object.keys(sectionLabels)) {
    assert.ok(Array.isArray(entryFields(type)));
    assert.equal(createEntry(type, 'entry-test').id, 'entry-test');
  }
  for (const type of ['unknown', 'toString']) assert.throws(() => createEntry(type, 'entry-test'));
});
test('academic, competition and new custom entries have title, role and complete timeline', () => {
  for (const type of ['academic', 'competition', 'custom']) {
    assert.deepEqual(createEntry(type, 'entry-test'), {id:'entry-test', visible:true, body:'', heading:'', role:'', url:null, start_date:null, end_date:null, ongoing:false});
    assert.ok(hasTimeline(type));
    assert.deepEqual(entryFields(type).map(([key]) => key), ['heading','role','url']);
  }
});
test('entry defaults are independent and plain awards/skills stay body only', () => {
  const first = createEntry('academic', 'entry-one'), second = createEntry('academic', 'entry-two');
  first.role = '作者'; assert.equal(second.role, '');
  for (const type of ['skills', 'awards']) {
    assert.equal(hasTimeline(type), false);
    assert.equal('start_date' in createEntry(type, 'entry-test'), false);
  }
});
test('new custom modules retain structured fields even if renamed to an award title', () => {
  assert.equal(contentOnly({type:'custom', title:'获奖经历', entries:[createEntry('custom', 'entry-test')]}, config), false);
  assert.equal(contentOnly({type:'custom', title:'获奖经历', entries:[{id:'entry-old', heading:'旧标题', body:'旧内容', visible:true}]}, config), true);
  for (const type of ['academic', 'competition']) assert.equal(contentOnly({type, title:'获奖经历'}, config), false);
});
