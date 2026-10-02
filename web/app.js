import {clearPdf, showPdf} from '/assets/viewer.js';
import {contentOnly} from '/assets/style-model.mjs';
import {mountStyleEditor} from '/assets/style-editor.mjs';
import {mountMarkdownEditor} from '/assets/markdown-editor.mjs';
import {EditHistory} from '/assets/markdown-model.mjs';
import {sectionLabels as labels, entryFields, hasTimeline, createEntry} from '/assets/section-model.mjs';
import {AVATAR_ACCEPT, AVATAR_HINT, avatarFileError} from '/assets/avatar-model.mjs';
const $ = (id) => document.getElementById(id);
const clone = (value) => structuredClone(value);
const uid = (prefix) => `${prefix}-${crypto.randomUUID()}`;
const records = new Map();
const bodyHistories = new WeakMap();
const avatarRequests = new Set();
let summaries = [], active = null, token = '', manage = null, toastTimer, opening = 0, sessionTask, styleConfig;
const busy = (r) => r?.saving || r?.uploading || ['queued', 'running'].includes(r?.job?.status);
const dirty = (r) => r.epoch !== r.savedEpoch;

function el(tag, text = '', className = '') {
  const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
}
function button(text, action, className = 'button') {
  const node = el('button', text, className); node.type = 'button'; node.addEventListener('click', () => Promise.resolve().then(action).catch(showError)); return node;
}
function notify(text) { $('toast').textContent = text; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 5500); }
function showError(error) { notify(error.message || '操作未完成，请重试。'); }

async function session() {
  if (!sessionTask) sessionTask = (async () => {
    const response = await fetch('/api/session', {headers:{'X-Resume-Bootstrap':'1'}, cache:'no-store'});
    if (!response.ok) throw new Error('会话初始化失败，请从本地服务地址重新打开。');
    token = (await response.json()).token;
  })().finally(() => { sessionTask = null; });
  return sessionTask;
}
async function api(path, {method = 'GET', data, raw, type} = {}, retry = true) {
  const headers = {'X-Resume-Token': token};
  if (data !== undefined) headers['Content-Type'] = 'application/json';
  if (type) headers['Content-Type'] = type;
  let response;
  try { response = await fetch(path, {method, headers, body: data === undefined ? raw : JSON.stringify(data), cache: 'no-store'}); }
  catch { throw new Error('无法连接本地服务。输入仍在本页，请启动后端后重试。'); }
  if (response.status === 403 && retry) { await session(); return api(path, {method, data, raw, type}, false); }
  if (!response.ok) {
    const info = await response.json().catch(() => ({}));
    const error = new Error(info.message || `请求失败（${response.status}）`); Object.assign(error, info, {status: response.status}); throw error;
  }
  return response;
}
async function json(path, options) { return (await api(path, options)).json(); }

function record(detail) {
  return {id: detail.resume.id, draft: clone(detail.resume), saved: detail.resume, epoch:0, savedEpoch:0,
    selected:'basics', error:'', conflict:false, saving:null, uploading:false, timer:null,
    job:detail.latest_job, pdf:detail.pdf, buildKey:detail.build_key, blob:null, blobJob:null, pdfSequence:0};
}
function metadata(r, detail) { r.job = detail.latest_job; r.pdf = detail.pdf; r.buildKey = detail.build_key; }
function serverFields(r, document) { for (const key of ['id','revision','created_at','updated_at']) r.draft[key] = document[key]; }
async function refreshList() { summaries = await json('/api/resumes'); renderList(); renderSwitcher(); }
function renderList() {
  const query = $('search').value.trim().toLowerCase();
  $('count').textContent = summaries.length;
  const visible = summaries.filter((item) => `${item.title} ${item.headline}`.toLowerCase().includes(query));
  $('empty').hidden = summaries.length !== 0;
  const cards = visible.map((item) => {
    const r = records.get(item.id), card = el('article', '', 'resume-card');
    const thumb = button('', () => open(item.id), 'resume-thumbnail'); thumb.setAttribute('aria-label', `编辑 ${item.title}`);
    const paper = el('div', '', 'thumbnail-sheet'); paper.append(el('h3', item.name || '你的姓名'), el('p', item.headline || '开始填写你的简历'));
    for (const name of ['教育经历', '工作与项目', '技能']) { const part = el('div', '', 'thumbnail-section'); part.append(el('strong', name), el('div', '', 'thumbnail-line'), el('div', '', 'thumbnail-line short')); paper.append(part); }
    thumb.append(paper, el('span', '内容示意', 'resume-type'));
    const content = el('div', '', 'resume-card-content'), heading = el('div', '', 'resume-card-heading');
    heading.append(el('h2', item.title), el('span', r && dirty(r) ? '本页有草稿' : `已保存 r${item.revision}`, 'resume-card-status'));
    content.append(heading, el('p', item.headline || '未填写求职方向', 'resume-role'), el('p', `更新于 ${new Date(item.updated_at).toLocaleString()}`, 'resume-provenance'));
    const actions = el('div', '', 'resume-card-actions');
    actions.append(button('编辑', () => open(item.id), 'button primary'), button('创建副本', () => dialog('copy', item.id), 'text-button'), button('重命名', () => dialog('rename', item.id), 'text-button muted'), button('删除', () => remove(item.id), 'text-button muted delete-action'));
    for (const child of [...actions.children].slice(1)) child.disabled = Boolean(busy(r));
    content.append(actions); card.append(thumb, content); return card;
  });
  if (summaries.length && !visible.length) cards.push(el('p', '没有匹配的简历。'));
  $('cards').replaceChildren(...cards);
}
function renderSwitcher() {
  $('switcher').replaceChildren(...summaries.map((item) => { const option = el('option', item.title); option.value = item.id; return option; }));
  $('switcher').value = active || '';
}
async function load(id) { if (!records.has(id)) records.set(id, record(await json(`/api/resumes/${id}`))); return records.get(id); }
async function open(id) {
  const sequence = ++opening, r = await load(id);
  if (sequence !== opening) return;
  active = id; document.body.dataset.view = 'editor'; $('library').hidden = true; $('context').hidden = $('context-actions').hidden = $('editor').hidden = false;
  renderSwitcher(); renderForm(); renderStatus(); await preview(r);
}
function home() { ++opening; active = null; document.body.dataset.view = 'library'; $('library').hidden = false; $('context').hidden = $('context-actions').hidden = $('editor').hidden = true; refreshList().catch(showError); }

function changed(r) {
  r.epoch++; r.error = r.conflict ? r.error : ''; clearTimeout(r.timer);
  if (!r.conflict) r.timer = setTimeout(() => save(r).catch(() => {}), 1000);
  renderStatus();
}
async function save(r, compile = false) {
  clearTimeout(r.timer);
  if (r.uploading) throw new Error('请等待头像上传完成。');
  if (r.saving) { await r.saving; return save(r, compile); }
  if (r.conflict) throw new Error(r.error);
  const epoch = r.epoch, snapshot = clone(r.draft);
  r.error = '';
  r.saving = (async () => {
    try {
      if (dirty(r)) {
        const result = await json(`/api/resumes/${r.id}`, {method:'PUT', data:{expected_revision:r.saved.revision, resume:snapshot}});
        r.saved = result.resume; r.savedEpoch = epoch; serverFields(r, result.resume); metadata(r, result);
      }
      if (compile && r.epoch === epoch) r.job = await json(`/api/resumes/${r.id}/compile`, {method:'POST', data:{expected_revision:r.saved.revision}});
      await refreshList();
    } catch (error) {
      r.error = error.message; if (error.code === 'revision_conflict') r.conflict = true; throw error;
    } finally {
      r.saving = null; renderStatus();
      if (r.epoch !== epoch && !r.conflict) { clearTimeout(r.timer); r.timer = setTimeout(() => save(r).catch(() => {}), 1000); }
    }
  })();
  renderStatus(); await r.saving;
  if (compile && r.job?.status === 'succeeded') { const detail = await json(`/api/resumes/${r.id}`); metadata(r, detail); await preview(r); renderStatus(); }
  else await preview(r);
  if (compile && dirty(r)) return save(r, true);
}

function renderStatus() {
  const r = records.get(active); if (!r) return;
  $('save-status').textContent = r.conflict ? '版本冲突 · 本页草稿保留' : r.error && dirty(r) ? '保存未确认 · 请重试' : r.saving || r.uploading ? '正在保存…' : dirty(r) ? '有未保存修改' : `已保存到本地 r${r.saved.revision}`;
  $('save-status').dataset.state = r.error ? 'failed' : dirty(r) ? 'dirty' : 'saved';
  $('editor-error').hidden = !r.error; $('editor-error').textContent = r.error;
  $('conflict-actions').hidden = !r.conflict;
  const running = ['queued','running'].includes(r.job?.status);
  const current = r.pdf && r.pdf.build_key === r.buildKey && !dirty(r) && !r.conflict;
  $('preview-status').textContent = running ? `${r.job.status === 'queued' ? '等待编译' : '正在生成 PDF'} r${r.job.revision}${r.pdf ? ` · 保留上次成功 r${r.pdf.revision}` : ''}` : r.pdf ? `${current ? '当前版本' : '旧版预览'} r${r.pdf.revision} · ${r.pdf.pages} 页${r.job?.status === 'failed' || r.job?.status === 'timed_out' ? ' · 最新编译未成功' : ''}` : '尚无成功的 PDF，请点击保存并预览';
  $('save').disabled = Boolean(r.saving || r.uploading || r.conflict || running);
  $('rename').disabled = $('copy').disabled = Boolean(busy(r));
  $('export').disabled = !current || Boolean(r.saving || running);
  $('old-export').disabled = !r.pdf || Boolean(r.uploading);
  $('backup').disabled = Boolean(r.saving || r.uploading || r.conflict);
}
async function preview(r) {
  if (!r.pdf) { if (active === r.id) { clearPdf(); $('open-pdf').hidden = true; } return; }
  const job = r.pdf.id, sequence = ++r.pdfSequence;
  if (r.blobJob !== job) {
    const blob = await (await api(`/api/jobs/${job}/pdf`)).blob();
    if (r.pdf?.id !== job || r.pdfSequence !== sequence) return;
    if (r.blob) URL.revokeObjectURL(r.blob);
    r.blob = URL.createObjectURL(blob); r.blobJob = job;
  }
  if (active === r.id) {
    $('open-pdf').hidden = false; $('open-pdf').href = r.blob;
    await showPdf(job, r.blob);
  }
}
let polling = false;
setInterval(async () => {
  if (polling) return; polling = true;
  try {
    for (const r of records.values()) {
      if (!['queued','running'].includes(r.job?.status)) continue;
      const jobId = r.job.id, result = await json(`/api/jobs/${jobId}`);
      if (r.job?.id !== jobId) continue;
      if (!['queued','running'].includes(result.status)) {
        const detail = await json(`/api/resumes/${r.id}`);
        if (r.job?.id !== jobId || r.saving || r.uploading || detail.resume.revision < r.saved.revision) continue;
        metadata(r, detail);
        if (detail.resume.revision !== r.saved.revision && !r.saving) { r.conflict = true; r.error = '服务端版本已变化。本页输入保留，请重新载入或创建副本。'; }
        if (result.error) r.error = result.error;
        await preview(r);
      } else r.job = result;
    }
    renderStatus();
  } catch (error) { const r = records.get(active); if (r) { r.error = error.message; renderStatus(); } }
  finally { polling = false; }
}, 650);

function field(label, object, key, r, {type = 'text', max = 200, nullable = false, min, step, maxValue, placeholder} = {}) {
  const node = el('label', '', 'field'), input = document.createElement('input');
  node.append(el('span', label), input); input.type = type; input.value = object[key] ?? ''; input.maxLength = max;
  if (placeholder) input.placeholder = placeholder;
  if (min !== undefined) input.min = min; if (maxValue !== undefined) input.max = maxValue; if (step !== undefined) input.step = step;
  input.addEventListener('input', () => { object[key] = nullable && !input.value ? null : type === 'number' ? Number(input.value) : input.value; changed(r); });
  return node;
}
function check(label, object, key, r, after) {
  const node = el('label', '', 'check-field'), input = document.createElement('input'); input.type = 'checkbox'; input.checked = object[key];
  input.addEventListener('change', () => { object[key] = input.checked; after?.(); changed(r); }); node.append(input, document.createTextNode(label)); return node;
}
function tabs(r) {
  const items = [{id:'basics', title:'基本信息'}, ...r.draft.sections];
  $('tabs').replaceChildren(...items.map((item) => {
    const tab = button(item.title, () => { r.selected = item.id; renderForm(); }, ''); tab.setAttribute('role', 'tab'); tab.setAttribute('aria-selected', String(item.id === r.selected)); return tab;
  }));
  requestAnimationFrame(revealSelectedTab);
}
function revealSelectedTab() {
  const list = $('tabs'), selected = list.querySelector('[aria-selected="true"]');
  if (!selected || !list.clientWidth) return;
  const frame = list.getBoundingClientRect(), item = selected.getBoundingClientRect();
  if (item.left < frame.left) list.scrollLeft += item.left - frame.left - 12;
  else if (item.right > frame.right) list.scrollLeft += item.right - frame.right + 12;
}
window.addEventListener('resize', () => requestAnimationFrame(revealSelectedTab));
function renderForm() {
  const r = records.get(active); if (!r) return;
  if (r.selected !== 'basics' && !r.draft.sections.some((s) => s.id === r.selected)) r.selected = 'basics';
  tabs(r); const content = $('form-content'); content.replaceChildren();
  const intro = el('div', '', 'section-intro'); content.append(intro);
  if (r.selected === 'basics') {
    intro.append(el('h2', '基本信息'), el('p', '停下输入约 1 秒自动保存。点击“保存并预览”生成真实 PDF。'));
    const grid = el('div', '', 'form-grid basic-grid'), data = r.draft.basics;
    grid.append(field('姓名', data, 'name', r), field('求职意向', data, 'headline', r));
    grid.append(field('性别', data, 'gender', r, {max:20, placeholder:'选填'}), field('年龄（岁）', data, 'age', r, {type:'number', min:0, maxValue:150, step:1, nullable:true, placeholder:'选填，留空不显示'}));
    for (const [key, label, max] of [['email','邮箱',254],['phone','电话',80],['location','所在城市',200]]) grid.append(field(label, data, key, r, {max}));
    content.append(grid, el('h3', '个人链接', 'body-label'));
    content.append(el('p', '显示文字选填；留空时直接显示网址，不添加名称。', 'field-hint'));
    data.links.forEach((link) => { const row = el('div', '', 'link-row'); row.append(field('显示文字（选填）', link, 'label', r, {placeholder:'留空则显示网址'}), field('网址（HTTP/HTTPS）', link, 'url', r, {max:2048}), button('移除', () => { data.links = data.links.filter((x) => x.id !== link.id); changed(r); renderForm(); })); content.append(row); });
    const addLink = button('＋ 添加链接', () => { data.links.push({id:uid('link'), label:'', url:'https://example.com'}); changed(r); renderForm(); }); addLink.disabled = data.links.length >= 6; content.append(addLink);
    const avatar = el('div', '', 'avatar-controls');
    avatar.append(button(data.avatar_attachment_id ? '更换头像' : '上传头像', () => $('avatar-file').click()), check('在 PDF 中显示头像', data, 'avatar_visible', r), el('p', AVATAR_HINT));
    if (data.avatar_attachment_id) avatar.append(button('移除头像', () => { if (!confirm('确认移除这份简历的头像？')) return; data.avatar_attachment_id = null; r.draft.attachments = []; changed(r); renderForm(); }));
    content.append(avatar);
  } else {
    const section = r.draft.sections.find((s) => s.id === r.selected);
    const simple = contentOnly(section, styleConfig);
    intro.append(el('h2', section.title), el('p', '使用正文框上方按钮设置格式，停下输入后自动保存；点击“保存并预览”查看 PDF 效果。'));
    content.append(check('显示这个模块', section, 'visible', r));
    section.entries.forEach((entry, index) => {
      const box = el('div', '', 'entry-box'), caption = el('div', '', 'entry-caption'), actions = el('div', '', 'entry-actions');
      caption.append(el('span', `条目 ${index + 1}`), check('显示', entry, 'visible', r));
      for (const [offset,label] of [[-1,'上移'],[1,'下移']]) { const move = button(label, () => { section.entries.splice(index,1); section.entries.splice(index+offset,0,entry); changed(r); renderForm(); }, ''); move.disabled = index+offset < 0 || index+offset >= section.entries.length; actions.append(move); }
      actions.append(button('删除条目', () => { if (!confirm('确认删除这个条目？')) return; section.entries.splice(index,1); changed(r); renderForm(); }, ''));
      const grid = el('div', '', 'form-grid');
      const spec = simple ? [] : entryFields(section.type), timeline = !simple && hasTimeline(section.type);
      for (const [key,label] of spec) grid.append(field(label, entry, key, r, {max:key==='url'?2048:200, nullable:key==='url'}));
      if (timeline) {
        const end = field('结束月份',entry,'end_date',r,{type:'month',nullable:true});
        end.querySelector('input').disabled = Boolean(entry.ongoing);
        grid.append(field('开始月份',entry,'start_date',r,{type:'month',nullable:true}), end);
      }
      if (!simple || section.entries.length > 1) box.append(caption);
      else box.append(check('显示内容', entry, 'visible', r));
      if (spec.length) box.append(grid);
      if (simple) box.classList.add('content-only-entry');
      if (timeline) box.append(check('至今', entry, 'ongoing', r, () => { if (entry.ongoing) entry.end_date = null; renderForm(); }));
      if (!bodyHistories.has(entry)) bodyHistories.set(entry, new EditHistory(entry.body));
      box.append(mountMarkdownEditor({id:`body-${entry.id}`, label:simple ? `${section.title}内容（Markdown）` : '详细描述（Markdown）',
        value:entry.body, history:bodyHistories.get(entry), onChange:(value) => { entry.body = value; changed(r); }}), actions);
      content.append(box);
    });
    const add = button('＋ 新增条目', () => {
      if (section.type === 'custom' && contentOnly(section, styleConfig)) section.type = 'awards';
      section.entries.push(newEntry(section.type)); changed(r); renderForm();
    }); add.disabled = section.entries.length >= 100; content.append(add);
  }
}
function newEntry(type) {
  return createEntry(type, uid('entry'));
}
function moduleList() {
  const r = records.get(active); $('module-list').replaceChildren(...r.draft.sections.map((section,index) => {
    const row = el('div', '', 'module-row'), name = document.createElement('input'); name.type = 'text'; name.maxLength = 80; name.value = section.title; name.setAttribute('aria-label', '模块标题');
    name.addEventListener('input', () => { if (section.type === 'custom' && contentOnly(section, styleConfig)) section.type = 'awards'; section.title = name.value; changed(r); tabs(r); }); row.append(name, check('显示',section,'visible',r));
    const actions = el('div', '', 'module-order'); for (const [offset,label] of [[-1,'上移'],[1,'下移']]) { const b = button(label, () => { r.draft.sections.splice(index,1); r.draft.sections.splice(index+offset,0,section); changed(r); moduleList(); renderForm(); }, 'text-button'); b.disabled = index+offset<0 || index+offset>=r.draft.sections.length; actions.append(b); }
    actions.append(button('删除', () => { if (!confirm(`删除“${section.title}”及其条目？`)) return; r.draft.sections.splice(index,1); changed(r); moduleList(); renderForm(); }, 'text-button muted')); row.append(actions); return row;
  })); $('add-module').disabled = r.draft.sections.length >= 20;
}

async function dialog(mode, id = active) {
  const r = mode === 'create' ? null : await load(id); if (busy(r)) throw new Error('请等待保存或编译完成。');
  manage = {mode,id}; $('manage-title').textContent = {create:'新建简历',copy:'创建独立副本',rename:'重命名简历'}[mode];
  $('manage-name').value = mode === 'create' ? '未命名简历' : mode === 'copy' ? [...r.draft.title].slice(0,76).join('')+'（副本）' : r.draft.title;
  $('kind-field').hidden = mode !== 'create'; $('version-field').hidden = mode !== 'copy'; $('version').value = r?.conflict ? 'draft' : 'saved'; $('manage-error').textContent = ''; $('manage-dialog').showModal();
}
$('manage-form').addEventListener('submit', async (event) => {
  event.preventDefault(); if (!manage) return; const action = {...manage}; $('manage-submit').disabled = true;
  try {
    let result;
    if (action.mode === 'create') result = await json('/api/resumes',{method:'POST',data:{title:$('manage-name').value,kind:$('kind').value}});
    else {
      const r = await load(action.id);
      if (action.mode === 'rename') { await save(r); result = await json(`/api/resumes/${r.id}`,{method:'PATCH',data:{expected_revision:r.saved.revision,title:$('manage-name').value}}); }
      else {
        const current = await json(`/api/resumes/${r.id}`), version = $('version').value;
        const data = {expected_revision:current.resume.revision,title:$('manage-name').value,version};
        if (version === 'draft') { data.draft = clone(r.draft); for (const key of ['id','revision','created_at','updated_at']) data.draft[key] = current.resume[key]; }
        result = await json(`/api/resumes/${r.id}/copy`,{method:'POST',data});
      }
    }
    if (action.mode === 'rename') {
      const r = records.get(action.id); r.saved = result.resume; r.draft.title = result.resume.title; serverFields(r,result.resume); metadata(r,result);
    } else records.set(result.resume.id,record(result));
    $('manage-dialog').close(); await refreshList(); await open(result.resume.id); notify(action.mode === 'copy' ? '副本已保存，源简历保持不变。' : '已保存到本地。');
  } catch (error) { $('manage-error').textContent = error.message; }
  finally { $('manage-submit').disabled = false; }
});
async function remove(id) {
  const r = await load(id); if (busy(r)) throw new Error('请等待保存或编译完成。');
  if (!confirm(`删除“${r.draft.title}”？${dirty(r)?'本页未保存草稿也会丢弃。':''}其他简历和副本不受影响，此操作不可撤销。`)) return;
  await json(`/api/resumes/${id}`,{method:'DELETE',data:{expected_revision:r.saved.revision}}); clearTimeout(r.timer); if (r.blob) URL.revokeObjectURL(r.blob); records.delete(id); await refreshList();
}
async function download(path, name) {
  const blob = await (await api(path)).blob(), url = URL.createObjectURL(blob), link = document.createElement('a');
  link.href = url; link.download = name; link.hidden = true; document.body.append(link); link.click();
  setTimeout(() => { link.remove(); URL.revokeObjectURL(url); }, 30000);
  notify('已向浏览器请求下载。若没有出现文件，请在独立浏览器打开本机地址后重试。');
}
const act = (id, action) => $(id).addEventListener('click', () => Promise.resolve().then(action).catch(showError));
for (const id of ['home','nav-library','back']) act(id, home);
for (const id of ['create','empty-create']) act(id, () => dialog('create'));
act('copy', () => dialog('copy')); act('conflict-copy', () => dialog('copy')); act('rename', () => dialog('rename'));
$('search').addEventListener('input',renderList); $('switcher').addEventListener('change', () => open($('switcher').value).catch(showError));
act('save', () => save(records.get(active),true));
act('reload', async () => { const r = records.get(active); if (!confirm('丢弃本页未保存输入，载入服务端最新版本？')) return; clearTimeout(r.timer); if (r.blob) URL.revokeObjectURL(r.blob); records.delete(active); await open(active); });
act('export', async () => { const r = records.get(active); if (dirty(r) || r.pdf?.build_key !== r.buildKey) throw new Error('请先保存并生成最新版 PDF。'); await download(`/api/jobs/${r.pdf.id}/pdf?download=true`,`${r.saved.title}-r${r.pdf.revision}.pdf`); });
act('old-export', async () => { const r = records.get(active), pdf = r.pdf; if (!pdf) return; if (confirm(`导出“${r.saved.title}”上次成功版本 r${pdf.revision}？不包含之后的修改。`)) await download(`/api/jobs/${pdf.id}/pdf?download=true`,`${r.saved.title}-旧版-r${pdf.revision}.pdf`); });
act('backup', async () => { const r = records.get(active); await save(r); if (dirty(r)) throw new Error('请等待当前修改保存后再备份。'); await download(`/api/resumes/${r.id}/backup?expected_revision=${r.saved.revision}`,`${r.saved.title}-r${r.saved.revision}.resume.zip`); });
act('import', () => $('import-file').click());
$('import-file').addEventListener('change', async () => { const file = $('import-file').files[0]; if (!file) return; try { const result = await json('/api/import',{method:'POST',raw:file,type:'application/zip'}); records.set(result.resume.id,record(result)); await refreshList(); await open(result.resume.id); notify('工程已导入为新副本，没有覆盖任何原简历。'); } catch(error){showError(error);} finally{$('import-file').value='';} });
$('avatar-file').accept = AVATAR_ACCEPT;
$('avatar-file').addEventListener('change', async () => {
  const file = $('avatar-file').files[0], r = records.get(active); if (!file || !r) return;
  const validationError = avatarFileError(file);
  if (validationError || r.uploading || avatarRequests.has(r.id)) { notify(validationError || '请等待当前头像上传完成。'); $('avatar-file').value=''; return; }
  avatarRequests.add(r.id);
  try {
    await save(r); r.uploading = true; renderStatus();
    const result = await json(`/api/resumes/${r.id}/avatar?expected_revision=${r.saved.revision}`,{method:'PUT',raw:file,type:'application/octet-stream'});
    r.saved = result.resume; serverFields(r,result.resume); r.draft.attachments = clone(result.resume.attachments); r.draft.basics.avatar_attachment_id = result.resume.basics.avatar_attachment_id; r.draft.basics.avatar_visible = true; metadata(r,result);
    if (active === r.id) renderForm(); notify('头像已保存到本地。');
  } catch(error){r.error=error.message;showError(error);} finally {avatarRequests.delete(r.id);r.uploading=false;$('avatar-file').value='';renderStatus();if(dirty(r)){clearTimeout(r.timer);r.timer=setTimeout(()=>save(r).catch(()=>{}),1000);}}
});
act('modules', () => {moduleList();$('modules-dialog').showModal();});
act('add-module', () => { const r=records.get(active),type=$('module-kind').value; const section={id:uid('section'),type,title:labels[type],visible:true,entries:[newEntry(type)]}; r.draft.sections.push(section);r.selected=section.id;changed(r);moduleList();renderForm(); });
// Keep the module picker and entry factory on the same supported type list.
$('module-kind').replaceChildren(...Object.entries(labels).map(([type, label]) => { const option = el('option', label); option.value = type; return option; }));
act('settings', () => {
  const r = records.get(active);
  mountStyleEditor($('style-fields'), r.draft.style, styleConfig,
    (style) => { r.draft.style = style; changed(r); },
    (valid) => { $('style-preview').disabled = !valid; });
  $('settings-dialog').showModal();
});
act('style-preview', async () => { await save(records.get(active), true); $('settings-dialog').close(); });
act('guide', () => $('guide-dialog').showModal());
document.querySelectorAll('[data-close]').forEach((node)=>node.addEventListener('click',()=>$(node.dataset.close).close()));
window.addEventListener('beforeunload',(event)=>{if([...records.values()].some((r)=>dirty(r)||r.saving||r.uploading)){event.preventDefault();event.returnValue='';}});

try {
  await session(); styleConfig = await json('/assets/style-config.json'); await refreshList(); $('connection').textContent='本地服务已连接 · 自动保存到本机 · 点击“保存并预览”更新 PDF';
} catch(error){$('connection').textContent=error.message;showError(error);}

document.documentElement.dataset.fontStatus = 'loading';
try {
  const faces = await Promise.all(['400 14px "Resume Sans"', '700 14px "Resume Sans"',
    '400 14px "Resume Latin"', '700 14px "Resume Latin"',
    'italic 400 14px "Resume Latin"', 'italic 700 14px "Resume Latin"'].map((font) => document.fonts.load(font, '简历 Resume')));
  if (faces.some((loaded) => !loaded.length || loaded.some((font) => font.status !== 'loaded'))) throw new Error('Font unavailable');
  document.documentElement.dataset.fontStatus = 'loaded';
  document.documentElement.dataset.fontFaces = String(faces.flat().length);
} catch {
  document.documentElement.dataset.fontStatus = 'failed';
  $('font-warning').hidden = false;
}
