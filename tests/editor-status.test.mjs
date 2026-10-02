import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../web/app.js', import.meta.url), 'utf8');
// Exercise the shipped status renderer without booting the app or making API requests.
const start = source.indexOf('function renderStatus() {');
const end = source.indexOf('\nasync function preview(', start);
assert.ok(start >= 0 && end > start);
const guards = ['busy', 'dirty'].map((name) => {
  const declaration = source.match(new RegExp(`^const ${name} = .*;$`, 'm'));
  assert.ok(declaration);
  return declaration[0];
}).join('\n');
const script = new vm.Script(`${guards}\n${source.slice(start, end)}\nrenderStatus();`);

function render(overrides = {}) {
  const record = {epoch: 0, savedEpoch: 0, saved: {revision: 23}, error: '', conflict: false,
    saving: null, uploading: false, job: {status: 'succeeded', revision: 23},
    pdf: {build_key: 'current-key', pages: 2, revision: 23}, buildKey: 'current-key', ...overrides};
  const before = structuredClone(record), nodes = new Map();
  script.runInNewContext({active: 'resume', records: new Map([['resume', record]]),
    $: (id) => {
      if (!nodes.has(id)) nodes.set(id, {textContent: '', dataset: {}, hidden: false, disabled: false});
      return nodes.get(id);
    }});
  assert.deepEqual(record, before);
  for (const id of ['save-status', 'preview-status']) {
    assert.doesNotMatch(nodes.get(id).textContent, /r\d+|编译|服务端|数据库/);
  }
  return Object.fromEntries(nodes);
}

test('saved content and current PDF use user-facing labels without revision numbers', () => {
  const nodes = render();
  assert.equal(nodes['save-status'].textContent, '已保存到本机');
  assert.equal(nodes['preview-status'].textContent, '预览已更新 · 2 页');
  assert.equal(nodes.export.disabled, false);
  assert.equal(nodes['editor-error'].hidden, true);
});

test('unsaved changes retain the stale-preview warning and block latest export', () => {
  const nodes = render({epoch: 1});
  assert.equal(nodes['save-status'].textContent, '有未保存修改');
  assert.equal(nodes['save-status'].dataset.state, 'dirty');
  assert.equal(nodes['preview-status'].textContent, '预览待更新 · 2 页');
  assert.equal(nodes.export.disabled, true);
  assert.equal(nodes['old-export'].disabled, false);
});

test('saved but unpreviewed changes still require a preview update', () => {
  const nodes = render({buildKey: 'new-key'});
  assert.equal(nodes['save-status'].textContent, '已保存到本机');
  assert.equal(nodes['preview-status'].textContent, '预览待更新 · 2 页');
  assert.equal(nodes.export.disabled, true);
});

test('save failure remains visible and never claims unsaved inputs are saved', () => {
  const nodes = render({epoch: 1, error: '无法保存，请重试。'});
  assert.equal(nodes['save-status'].textContent, '保存未确认 · 请重试');
  assert.equal(nodes['save-status'].dataset.state, 'failed');
  assert.equal(nodes['editor-error'].hidden, false);
  assert.equal(nodes['editor-error'].textContent, '无法保存，请重试。');
  assert.equal(nodes.export.disabled, true);
  assert.equal(nodes.save.disabled, false);
});

test('conflicts keep recovery actions visible and block save, backup and latest export', () => {
  const nodes = render({conflict: true, error: '这份简历已有其他修改。'});
  assert.equal(nodes['save-status'].textContent, '内容有冲突 · 本页草稿保留');
  assert.equal(nodes['conflict-actions'].hidden, false);
  assert.equal(nodes.save.disabled, true);
  assert.equal(nodes.backup.disabled, true);
  assert.equal(nodes.export.disabled, true);
  assert.equal(nodes['old-export'].disabled, false);
});

for (const operation of ['saving', 'uploading']) {
  test(`${operation} is still shown as in progress`, () => {
    const nodes = render({epoch: 1, [operation]: true});
    assert.equal(nodes['save-status'].textContent, '正在保存…');
    for (const id of ['save', 'rename', 'copy', 'backup']) assert.equal(nodes[id].disabled, true);
  });
}

for (const [status, label] of [['queued', '等待生成 PDF…'], ['running', '正在生成 PDF…']]) {
  test(`${status} distinguishes in-progress output from the last preview`, () => {
    const nodes = render({job: {status, revision: 24}});
    assert.equal(nodes['preview-status'].textContent, `${label} · 暂显示上次预览`);
    assert.equal(nodes.save.disabled, true);
    assert.equal(nodes.export.disabled, true);
    assert.equal(nodes['old-export'].disabled, false);
    const empty = render({job: {status, revision: 24}, pdf: null});
    assert.equal(empty['preview-status'].textContent, label);
    assert.equal(empty['old-export'].disabled, true);
  });
}

for (const status of ['failed', 'timed_out']) {
  test(`${status} preserves failure warnings with and without a previous PDF`, () => {
    const job = {status, revision: 24}, error = 'PDF 生成失败，请重试。';
    const nodes = render({job, error, buildKey: 'new-key'});
    assert.equal(nodes['preview-status'].textContent, '更新失败 · 显示上次预览 · 2 页');
    assert.equal(nodes['editor-error'].hidden, false);
    assert.equal(nodes.export.disabled, true);
    assert.equal(nodes['old-export'].disabled, false);
    const empty = render({job, error, pdf: null});
    assert.equal(empty['preview-status'].textContent, 'PDF 生成失败，请点击“保存并预览”重试');
    assert.equal(empty['old-export'].disabled, true);
  });
}

test('first preview has a clear call to action without enabling either export', () => {
  const nodes = render({pdf: null, job: null});
  assert.equal(nodes['preview-status'].textContent, '点击“保存并预览”生成 PDF');
  assert.equal(nodes.export.disabled, true);
  assert.equal(nodes['old-export'].disabled, true);
});

test('removing revision labels does not remove old-version export confirmation', () => {
  assert.match(source, /if \(confirm\(`导出“\$\{r.saved.title\}”上次成功生成的 PDF？不包含之后的修改。`\)\)/);
  assert.match(source, /el\('h2', item.title\)/);
});
