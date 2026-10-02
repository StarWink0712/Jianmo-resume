import {EditHistory, formatMarkdown} from './markdown-model.mjs';

export function mountMarkdownEditor({id, label, value, history = new EditHistory(value), onChange}) {
  const root = document.createElement('div'); root.className = 'markdown-editor body-label';
  const heading = document.createElement('label'); heading.htmlFor = id; heading.textContent = label;
  const toolbar = document.createElement('div'); toolbar.className = 'markdown-toolbar';
  toolbar.setAttribute('role', 'group'); toolbar.setAttribute('aria-label', `${label}格式工具`);
  const area = document.createElement('textarea'); area.id = id; area.value = value; area.maxLength = 10000;
  const hint = document.createElement('p'); hint.id = `${id}-hint`; hint.className = 'markdown-hint';
  hint.textContent = '选中文字设置加粗/斜体；点击“换行”或按 Shift+Enter 可在同一条目内换行，不加黑点。普通 Enter 是 Markdown 软换行，空一行可分段；列表按钮再点可取消。';
  area.setAttribute('aria-describedby', hint.id);
  const status = document.createElement('p'); status.className = 'markdown-status'; status.setAttribute('role', 'status');
  root.append(heading, toolbar, area, hint, status);
  let composing = false, announced = value;
  const snapshot = () => ({text:area.value, start:area.selectionStart, end:area.selectionEnd});
  const controls = new Map();
  function emitChange() { if (area.value !== announced) { announced = area.value; onChange(announced); } }
  function sync() {
    for (const [action, control] of controls) control.disabled = composing || (action === 'undo' && !history.canUndo) || (action === 'redo' && !history.canRedo);
  }
  function apply(state) {
    const scroll = area.scrollTop;
    area.value = state.text; area.focus({preventScroll:true}); area.setSelectionRange(state.start, state.end); area.scrollTop = scroll;
    emitChange(); sync();
  }
  function run(action) {
    if (composing) return;
    history.selection(snapshot()); status.textContent = '';
    if (action === 'undo' || action === 'redo') {
      if (!(action === 'undo' ? history.canUndo : history.canRedo)) return;
      apply(history[action]()); return;
    }
    const result = formatMarkdown(area.value, area.selectionStart, area.selectionEnd, action);
    if (result.text.length > area.maxLength) { status.textContent = '添加格式后超过 10000 字符，请先缩短正文。原文未改动。'; return; }
    if (result.text === area.value) { if (action === 'linebreak') apply(result); return; }
    history.push(result); apply(result);
  }
  const definitions = [
    ['bold', 'B', '加粗', '选中文字后加粗或取消（⌘/Ctrl+B）'],
    ['italic', 'I', '斜体', '选中文字后倾斜或取消（⌘/Ctrl+I）'],
    ['linebreak', '↵', '换行', '光标处换行，不添加黑点；有选区时在选区后换行（Shift+Enter）'],
    ['bullet', '•', '黑点列表', '当前行或选中多行添加/取消黑点列表'],
    ['ordered', '1.', '编号列表', '当前行或选中多行添加/取消编号列表'],
    ['undo', '↶', '撤销', '撤销本正文框的编辑（⌘/Ctrl+Z）'],
    ['redo', '↷', '重做', '重做本正文框的编辑（⌘/Ctrl+Shift+Z）'],
  ];
  const historyControls = document.createElement('div'); historyControls.className = 'markdown-history';
  for (const [action, symbol, name, title] of definitions) {
    const control = document.createElement('button'); control.type = 'button'; control.dataset.action = action;
    control.title = title; control.setAttribute('aria-label', name); control.setAttribute('aria-controls', id);
    const icon = document.createElement('span'); icon.textContent = symbol; icon.className = 'markdown-icon'; icon.setAttribute('aria-hidden', 'true');
    control.append(icon, document.createTextNode(name));
    control.addEventListener('pointerdown', (event) => { if (event.pointerType === 'mouse' && event.button === 0) event.preventDefault(); });
    control.addEventListener('click', () => run(action)); controls.set(action, control);
    (action === 'undo' || action === 'redo' ? historyControls : toolbar).append(control);
  }
  toolbar.append(historyControls);
  area.addEventListener('beforeinput', (event) => {
    if (composing || event.isComposing) return;
    if (['historyUndo', 'historyRedo'].includes(event.inputType)) { event.preventDefault(); run(event.inputType === 'historyUndo' ? 'undo' : 'redo'); }
    else history.selection(snapshot());
  });
  area.addEventListener('input', (event) => {
    if (composing || event.isComposing) return;
    history.push(snapshot()); status.textContent = ''; emitChange(); sync();
  });
  area.addEventListener('compositionstart', () => { history.selection(snapshot()); composing = true; sync(); });
  area.addEventListener('compositionend', () => { composing = false; history.push(snapshot()); emitChange(); sync(); });
  area.addEventListener('select', () => { if (!composing) history.selection(snapshot()); });
  area.addEventListener('keydown', (event) => {
    if (composing || event.isComposing || event.altKey) return;
    if (event.key === 'Enter' && event.shiftKey && !event.metaKey && !event.ctrlKey) {
      event.preventDefault(); run('linebreak'); return;
    }
    if (!(event.metaKey || event.ctrlKey)) return;
    const key = event.key.toLowerCase();
    const action = key === 'z' ? (event.shiftKey ? 'redo' : 'undo') : key === 'y' ? 'redo' : !event.shiftKey ? {b:'bold', i:'italic'}[key] : null;
    if (action) { event.preventDefault(); run(action); }
  });
  sync(); return root;
}
