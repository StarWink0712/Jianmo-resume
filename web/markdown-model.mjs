// Selection offsets follow textarea's UTF-16 indexing, including Chinese and emoji.
const listPattern = /^([ \t]*)([-+*]|\d+[.)])([ \t]+|$)/;
const listKind = (line) => {
  const match = line.match(listPattern);
  return match ? (/\d/.test(match[2]) ? 'ordered' : 'bullet') : null;
};

function replace(text, start, end, value, selectionStart = start, selectionEnd = start + value.length) {
  return {text:text.slice(0, start) + value + text.slice(end), start:selectionStart, end:selectionEnd};
}

function inline(text, start, end, action) {
  const marker = action === 'bold' ? '**' : '*', size = marker.length;
  const selected = text.slice(start, end);
  const hasMark = (left, right) => size === 2 ? left >= 2 && right >= 2 : left % 2 === 1 && right % 2 === 1;
  const before = text.slice(0, start).match(/\*+$/)?.[0].length || 0;
  const after = text.slice(end).match(/^\*+/)?.[0].length || 0;
  if (selected && hasMark(before, after)) {
    return replace(text, start - size, end + size, selected, start - size, end - size);
  }
  if (!selected) {
    const placeholder = action === 'bold' ? '加粗文字' : '斜体文字';
    return replace(text, start, end, marker + placeholder + marker, start + size, start + size + placeholder.length);
  }
  // Format each selected line independently, never swallowing a list marker or blank line.
  const selectedLines = selected.split('\n');
  const chunks = selectedLines.map((line, index) => {
    const atLineStart = index > 0 || start === 0 || text[start - 1] === '\n';
    const prefix = atLineStart ? line.match(listPattern)?.[0] || '' : '';
    const body = line.slice(prefix.length), leading = body.match(/^\s*/)[0], trailing = body.match(/\s*$/)[0];
    const core = body.trim();
    const left = core.match(/^\*+/)?.[0].length || 0, right = core.match(/\*+$/)?.[0].length || 0;
    return {prefix, leading, trailing, core, marked:hasMark(left, right) && core.length > 2 * size};
  });
  const nonempty = chunks.filter((part) => part.core), remove = nonempty.length > 0 && nonempty.every((part) => part.marked);
  const result = chunks.map((part, index) => !part.core ? selectedLines[index] :
    part.prefix + part.leading + (remove ? part.core.slice(size, -size) : part.marked ? part.core : marker + part.core + marker) + part.trailing).join('\n');
  return replace(text, start, end, result);
}

function list(text, start, end, kind) {
  const from = start === 0 ? 0 : text.lastIndexOf('\n', start - 1) + 1;
  const last = end > start && text[end - 1] === '\n' ? end - 1 : end;
  let to = text.indexOf('\n', last);
  if (to < 0) to = text.length;
  const lines = text.slice(from, to).split('\n'), nonempty = lines.filter((line) => line.trim());
  const remove = nonempty.length > 0 && nonempty.every((line) => listKind(line) === kind);
  let number = 0;
  const formatted = lines.map((line) => {
    if (!line.trim() && lines.length > 1) return line;
    const match = line.match(listPattern), indent = match?.[1] ?? line.match(/^[ \t]*/)[0];
    const body = match ? line.slice(match[0].length) : line.slice(indent.length);
    if (remove) return indent + body;
    const prefix = kind === 'bullet' ? '- ' : `${++number}. `;
    return indent + prefix + body;
  }).join('\n');
  // Separate neighboring paragraphs to avoid CommonMark's lazy list continuation.
  const previous = text.slice(0, Math.max(0, from - 1)).split('\n').at(-1);
  const next = text.slice(to + 1).split('\n')[0];
  const leading = from > 0 && previous.trim() && (remove || listKind(previous) !== kind) ? '\n' : '';
  const trailing = to < text.length && next.trim() && (remove || listKind(next) !== kind) ? '\n' : '';
  const result = replace(text, from, to, leading + formatted + trailing, from + leading.length, from + leading.length + formatted.length);
  if (start === end && lines.length === 1) {
    const oldPrefix = lines[0].match(listPattern)?.[0].length || 0;
    const newPrefix = formatted.match(listPattern)?.[0].length || 0;
    result.start = result.end = Math.min(result.end, from + leading.length + Math.max(newPrefix, start - from + newPrefix - oldPrefix));
  }
  return result;
}

export function formatMarkdown(text, start, end, action) {
  start = Math.max(0, Math.min(text.length, start));
  end = Math.max(start, Math.min(text.length, end));
  if (action === 'bold' || action === 'italic') return inline(text, start, end, action);
  if (action === 'bullet' || action === 'ordered') return list(text, start, end, action);
  throw new Error('Unknown Markdown action');
}

export class EditHistory {
  constructor(text, limit = 100) { this.states = [{text, start:0, end:0}]; this.index = 0; this.limit = limit; }
  get current() { return {...this.states[this.index]}; }
  get canUndo() { return this.index > 0; }
  get canRedo() { return this.index < this.states.length - 1; }
  selection(state) { if (state.text === this.current.text) this.states[this.index] = {...state}; }
  push(state) {
    if (state.text === this.current.text) { this.selection(state); return; }
    this.states.splice(this.index + 1);
    this.states.push({...state});
    if (this.states.length > this.limit + 1) this.states.shift();
    this.index = this.states.length - 1;
  }
  undo() { if (this.canUndo) this.index--; return this.current; }
  redo() { if (this.canRedo) this.index++; return this.current; }
}
