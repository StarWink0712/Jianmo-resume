import test from 'node:test';
import assert from 'node:assert/strict';
import {EditHistory, formatMarkdown} from '../web/markdown-model.mjs';

const format = (text, action, start = 0, end = text.length) => formatMarkdown(text, start, end, action);
test('bold wraps a Chinese selection without changing surrounding text', () => {
  const text = '熟悉 Redis 与 MySQL';
  assert.deepEqual(format(text, 'bold', 3, 8), {text:'熟悉 **Redis** 与 MySQL', start:3, end:12});
});
test('inline formats toggle both inside and inclusive marker selections', () => {
  for (const [action, marker] of [['bold', '**'], ['italic', '*']]) {
    const first = format('开发', action);
    assert.equal(format(first.text, action).text, '开发');
    assert.equal(format(first.text, action, marker.length, marker.length + 2).text, '开发');
  }
});
test('bold and italic combine and can be removed independently', () => {
  assert.equal(format('**开发**', 'italic', 2, 4).text, '***开发***');
  assert.equal(format('***开发***', 'italic', 3, 5).text, '**开发**');
  assert.equal(format('***开发***', 'bold', 3, 5).text, '*开发*');
});
test('empty selection inserts and selects a placeholder', () => {
  for (const action of ['bold', 'italic']) {
    const result = format('前后', action, 1, 1);
    assert.equal(result.text.slice(result.start, result.end), action === 'bold' ? '加粗文字' : '斜体文字');
    assert.ok(result.text.startsWith('前')); assert.ok(result.text.endsWith('后'));
  }
});
test('multi-line bold preserves list prefixes, empty lines and edge whitespace', () => {
  const value = '- 一项\n- 第二项\n\n  正文  ';
  const result = format(value, 'bold');
  assert.equal(result.text, '- **一项**\n- **第二项**\n\n  **正文**  ');
  assert.equal(format(result.text, 'bold').text, value);
});
test('whitespace-only inline selections are unchanged', () => {
  assert.equal(format(' \n  ', 'bold').text, ' \n  ');
});
test('partial UTF-16 selection leaves emoji and neighboring text intact', () => {
  assert.equal(format('🙂中文', 'bold', 2, 4).text, '🙂**中文**');
});
test('bullet adds and removes markers across selected lines', () => {
  const first = format('第一项\n第二项', 'bullet');
  assert.equal(first.text, '- 第一项\n- 第二项');
  assert.equal(format(first.text, 'bullet').text, '第一项\n第二项');
});
test('list with only a caret acts on the current line and retains caret in the text', () => {
  const first = format('第一项\n第二项', 'bullet', 6, 6);
  assert.equal(first.text, '第一项\n\n- 第二项');
  assert.equal(first.text.slice(first.start - 1, first.start), '二');
});
test('selecting up to next line start excludes the next line', () => {
  assert.equal(format('一\n二', 'bullet', 0, 2).text, '- 一\n\n二');
});
test('empty body and first blank line accept list prefixes', () => {
  assert.deepEqual(format('', 'bullet', 0, 0), {text:'- ', start:2, end:2});
  assert.equal(format('\n后文', 'bullet', 0, 0).text, '- \n\n后文');
});
test('empty selected lines remain blank, not extra list items', () => {
  assert.equal(format('一\n\n二\n', 'bullet').text, '- 一\n\n- 二\n');
});
test('ordered list converts existing markers rather than stacking them', () => {
  assert.equal(format('- 一\n+ 二\n3) 三', 'ordered').text, '1. 一\n2. 二\n3. 三');
  assert.equal(format('1. 一\n2. 二', 'bullet').text, '- 一\n- 二');
});
test('repeating ordered command removes list markers', () => {
  assert.equal(format('1. 一\n2. 二', 'ordered').text, '一\n二');
});
test('matching adjacent lists stay connected while paragraphs are separated', () => {
  assert.equal(format('- 一\n二\n- 三', 'bullet', 4, 5).text, '- 一\n- 二\n- 三');
  assert.equal(format('前段\n中段\n后段', 'bullet', 3, 5).text, '前段\n\n- 中段\n\n后段');
  assert.equal(format('- 一\n- 二\n- 三', 'bullet', 4, 7).text, '- 一\n\n二\n\n- 三');
});
test('nested bullet indentation is preserved', () => {
  assert.equal(format('- 父项\n  - 子项', 'bold').text, '- **父项**\n  - **子项**');
});
test('linebreak inserts a CommonMark hard break at the caret without bullets', () => {
  assert.deepEqual(format('第一条第二条', 'linebreak', 3, 3), {text:'第一条  \n第二条', start:6, end:6});
  assert.deepEqual(format('🙂Next', 'linebreak', 2, 2), {text:'🙂  \nNext', start:5, end:5});
});
test('linebreak preserves selected text and inserts after it', () => {
  assert.deepEqual(format('FirstSecond', 'linebreak', 0, 5), {text:'First  \nSecond', start:8, end:8});
});
test('linebreak upgrades either side of a soft newline between references', () => {
  const text = '[1] First\n[2] Second', newline = text.indexOf('\n');
  for (const caret of [newline, newline + 1]) {
    const result = format(text, 'linebreak', caret, caret);
    assert.equal(result.text, '[1] First  \n[2] Second');
    assert.equal(result.start, result.text.indexOf('[2]'));
    assert.equal(result.end, result.start);
  }
});
test('linebreak reuses existing hard breaks and normalizes trailing whitespace', () => {
  for (const text of ['First  \nSecond', 'First\\\nSecond']) {
    const result = format(text, 'linebreak', text.indexOf('\n'), text.indexOf('\n'));
    assert.equal(result.text, text);
    assert.equal(result.start, text.indexOf('Second'));
  }
  assert.equal(format('First \t \nSecond', 'linebreak', 8, 8).text, 'First  \nSecond');
});
test('linebreak on blank lines does not add Markdown indentation or placeholders', () => {
  assert.deepEqual(format('', 'linebreak', 0, 0), {text:'\n', start:1, end:1});
  assert.equal(format('  ', 'linebreak', 2, 2).text, '\n');
  assert.equal(format('First  \n', 'linebreak', 8, 8).text, 'First  \n\n');
  assert.equal(format('\nNext', 'linebreak', 0, 0).text, '\nNext');
});
test('linebreak is reversible without changing inline formatting or list markers', () => {
  const text = '**First**Next', history = new EditHistory(text);
  history.selection({text, start:9, end:9});
  const result = format(text, 'linebreak', 9, 9);
  history.push(result);
  assert.equal(result.text, '**First**  \nNext');
  assert.equal(history.undo().text, text);
  assert.deepEqual(history.redo(), result);
  assert.equal(format('- FirstNext', 'linebreak', 7, 7).text, '- First  \nNext');
});
test('history stores formatting and typing, selection, undo and redo', () => {
  const history = new EditHistory('原文');
  history.selection({text:'原文', start:0, end:2});
  const bold = format('原文', 'bold'); history.push(bold);
  history.push({text:bold.text + '新', start:7, end:7});
  assert.deepEqual(history.undo(), bold);
  assert.deepEqual(history.undo(), {text:'原文', start:0, end:2});
  assert.deepEqual(history.redo(), bold);
  assert.ok(history.canRedo);
  history.push({text:'新分支', start:3, end:3}); assert.equal(history.canRedo, false);
});
test('history is bounded, independent, and no-op selections do not add entries', () => {
  const history = new EditHistory('', 2), other = new EditHistory('另一个正文');
  for (const text of ['1', '2', '3']) history.push({text, start:1, end:1});
  history.push({text:'3', start:0, end:1});
  assert.equal(history.states.length, 3); assert.equal(history.undo().text, '2');
  assert.equal(history.undo().text, '1'); assert.equal(history.canUndo, false);
  assert.equal(other.current.text, '另一个正文'); assert.equal(other.canUndo, false);
});
