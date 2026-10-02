"use strict";

const byId = (id) => document.getElementById(id);
const basicFields = ["name", "phone", "email", "location", "headline", "portfolio"];
let sections = {
  education: { label: "教育经历", title: "示例理工大学（虚构）", subtitle: "软件工程 · 学士", date: "2020.09 - 2024.06", body: "主修数据结构、数据库系统、计算机网络与软件测试。", visible: true, entryVisible: true },
  employment: { label: "工作与实习", title: "示例软件工作室（虚构）", subtitle: "开发实习生", date: "2024.01 - 2024.05", body: "• 参与内部任务管理工具开发，负责页面交互与数据接口对接。\n• 编写 API 自动化测试，覆盖输入校验、错误反馈与恢复场景。", visible: true, entryVisible: true },
  project: { label: "项目经历", title: "离线阅读清单（虚构）", subtitle: "独立开发 · TypeScript / SQLite", date: "2024.07 - 至今", body: "• 使用 TypeScript 与 SQLite 组织本地阅读记录。\n• 实现全文搜索、标签管理及工程备份，支持离线使用。\n• 对异常输入与恢复流程进行测试，并记录测试环境和已知限制。", visible: true, entryVisible: true },
  skills: { label: "专业技能", title: "语言与工具", subtitle: "", date: "", body: "• 编程语言：Python、TypeScript、SQL。\n• 开发工具：Git、SQLite、浏览器开发者工具。\n• 工程实践：结构化数据建模、接口测试与版本管理。", visible: true, entryVisible: true },
  custom: { label: "补充说明", title: "关于此示例", subtitle: "", date: "", body: "本简历的姓名、学校、单位与经历均为虚构，仅用于开发和排版测试，不代表真实个人经历。", visible: true, entryVisible: true },
};
const sectionFields = {
  education: ["学校名称", "专业与学历", "填写教育经历，展示学校、专业及学习成果。"],
  employment: ["公司 / 单位", "职位", "描述您的工作职责、具体行动与取得的成果。"],
  project: ["项目名称", "项目角色与技术", "突出项目背景、个人贡献与可验证的结果。"],
  skills: ["技能分组", "", "按类别整理技能，让招聘者快速了解您的能力。"],
  custom: ["条目标题", "", "补充证书、奖项、个人简介或其他有价值的信息。"],
};
let order = Object.keys(sections);
let selected = "basics";
let avatarVisible = false;
let pendingOldExport = null;
let activeId;
let view = "library";
let resumeAction = null;
let deleteId = null;
let feedbackTimer;

function snapshot() {
  return {
    basics: Object.fromEntries(basicFields.map((id) => [id, byId(id).value])),
    sections: structuredClone(sections), order: [...order], avatarVisible,
    fontSize: Number(byId("font-size").value), lineHeight: Number(byId("line-height").value),
  };
}
const exampleData = snapshot();
const library = new ResumeLibrary();
activeId = library.create("软件工程师 · 通用版（示例）", exampleData).id;

function current() {
  const record = library.get(activeId);
  return !!record && record.preview !== null && record.preview.resumeId === activeId
    && record.preview.revision === record.revision && record.editEpoch === record.savedEpoch;
}
function feedback(message) {
  clearTimeout(feedbackTimer);
  byId("feedback").textContent = message;
  byId("feedback").hidden = false;
  feedbackTimer = setTimeout(() => { byId("feedback").hidden = true; }, 6500);
}
function error(message = "") {
  byId("error").textContent = message;
  byId("error").hidden = !message;
}
function textElement(tag, className, value) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = value;
  return element;
}
function fitPaper() {
  if (byId("editor-view").hidden) return;
  const container = byId("preview-scroll");
  const padding = getComputedStyle(container);
  const available = container.clientWidth - parseFloat(padding.paddingLeft) - parseFloat(padding.paddingRight);
  const zoom = byId("zoom").value;
  const scale = zoom === "fit" ? Math.min(1, Math.max(1, available) / 794) : Number(zoom) / 100;
  const paper = byId("resume-paper");
  paper.style.transform = `scale(${scale})`;
  byId("paper-frame").style.width = `${794 * scale}px`;
  byId("paper-frame").style.height = `${paper.offsetHeight * scale}px`;
}
function renderPaper() {
  // Keep the initial illustration or last compiled snapshot separate from the draft.
  const record = library.get(activeId);
  const preview = record.preview;
  const data = preview ? preview.data : record.initialData;
  byId("preview-name").textContent = data.basics.name || "（空白姓名）";
  const contacts = [data.basics.phone, data.basics.email, data.basics.location, data.basics.portfolio].filter((value) => value.trim());
  byId("preview-contacts").textContent = contacts.join("  |  ");
  byId("preview-contacts").hidden = contacts.length === 0;
  byId("preview-headline").textContent = data.basics.headline ? `求职意向：${data.basics.headline}` : "";
  byId("preview-avatar").hidden = !data.avatarVisible;
  byId("resume-paper").style.fontSize = `${data.fontSize * 4 / 3}px`;
  byId("resume-paper").style.lineHeight = String(data.lineHeight * 1.3);
  const fragment = document.createDocumentFragment();
  for (const key of data.order) {
    const entry = data.sections[key];
    if (!entry.visible || !entry.entryVisible) continue;
    const section = textElement("section", "resume-section", "");
    section.append(textElement("h4", "", entry.label));
    const heading = textElement("div", "resume-entry-heading", "");
    heading.append(textElement("span", "", entry.title), textElement("span", "", entry.date));
    section.append(heading);
    if (entry.subtitle) section.append(textElement("p", "resume-subtitle", entry.subtitle));
    section.append(textElement("p", "resume-body", entry.body));
    fragment.append(section);
  }
  byId("preview-sections").replaceChildren(fragment);
  byId("revision-label").textContent = preview ? `模拟快照 r${preview.revision}` : "初始示意 · 未编译";
  fitPaper();
}
function render() {
  updateNavigation();
  if (view === "library") { renderLibrary(); return; }
  const { editEpoch, savedEpoch, revision, preview, phase, saveFailed, compileFailed, error: message } = library.get(activeId);
  const dirty = editEpoch !== savedEpoch;
  error(message);
  byId("save-status").textContent = saveFailed ? "保存失败 · 输入已保留"
    : phase === "saving" ? "正在模拟保存…"
    : dirty ? "有未保存的修改" : `模拟已保存 r${revision}`;
  byId("save-indicator").dataset.state = saveFailed ? "failed" : dirty ? "dirty" : "saved";
  byId("simulate").disabled = phase !== "idle";
  byId("save-button-label").textContent = phase === "saving" ? "保存中…" : phase === "compiling" ? "预览生成中…" : "保存并预览";
  byId("export").disabled = !current() || phase !== "idle" || compileFailed;
  byId("old-export").disabled = !preview || (current() && !compileFailed);
  let status = preview ? `上次成功 r${preview.revision}` : "当前简历尚未编译";
  if (phase === "compiling") status += ` · 正在模拟编译 r${revision}`;
  else if (compileFailed) status += " · 编译失败，可重试";
  else if (current()) status = `当前快照 r${preview.revision} · 与已保存内容一致`;
  if (preview && !current()) status += " · 预览已过期";
  if (!preview) status += " · 排版示意";
  byId("preview-status").textContent = status;
  byId("preview-dot").dataset.state = current() ? "current" : preview ? "stale" : "initial";
  byId("avatar-placeholder").classList.toggle("is-visible", avatarVisible);
  byId("avatar-show").disabled = avatarVisible;
  byId("avatar-hide").disabled = !avatarVisible;
  if (selected !== "basics") byId("character-count").textContent = `${sections[selected].body.length} / 10000`;
  renderPaper();
}
function edited() {
  library.updateDraft(activeId, snapshot());
  byId("feedback").hidden = true;
  render();
}
function selectSection(key) {
  selected = key;
  library.setView(activeId, { selected: key });
  for (const button of document.querySelectorAll("[data-section]")) {
    const active = button.dataset.section === key;
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  }
  byId("editor-panel").setAttribute("aria-labelledby", `tab-${key}`);
  byId("basics-form").hidden = key !== "basics";
  byId("section-form").hidden = key === "basics";
  byId("section-icon").setAttribute("href", key === "basics" ? "#i-user" : "#i-file");
  byId("editor-title").textContent = key === "basics" ? "基本信息" : sections[key].label;
  byId("editor-description").textContent = key === "basics" ? "填写您的基本个人信息，这些信息将显示在简历顶部。" : sectionFields[key][2];
  if (key !== "basics") {
    byId("title-label").textContent = sectionFields[key][0];
    byId("subtitle-label").textContent = sectionFields[key][1];
    byId("subtitle-field").hidden = !sectionFields[key][1];
    byId("section-title").value = sections[key].title;
    byId("section-subtitle").value = sections[key].subtitle;
    byId("body").value = sections[key].body;
    byId("entry-visible").checked = sections[key].entryVisible;
  }
  byId("editor-panel").scrollTop = 0;
  render();
}

function blankData() {
  const data = structuredClone(exampleData);
  for (const key of Object.keys(data.basics)) data.basics[key] = "";
  for (const entry of Object.values(data.sections)) {
    entry.title = ""; entry.subtitle = ""; entry.date = ""; entry.body = "";
  }
  data.avatarVisible = false;
  return data;
}

function updateNavigation() {
  const record = library.get(activeId);
  for (const [id, target] of [["nav-library", "library"], ["nav-editor", "editor"]]) {
    byId(id).classList.toggle("active", view === target);
    if (view === target) byId(id).setAttribute("aria-current", "page");
    else byId(id).removeAttribute("aria-current");
  }
  byId("nav-editor").disabled = !record;
  byId("rename-active").disabled = !record || record.phase !== "idle";
  byId("copy-active").disabled = !record || record.phase !== "idle";
  byId("draft-context").textContent = record && record.editEpoch !== record.savedEpoch ? "本次草稿已保留 · 未保存" : "独立内容与预览";
  const options = library.list().map((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.title;
    option.selected = item.id === activeId;
    return option;
  });
  byId("resume-switcher").replaceChildren(...options);
}

function showLibrary() {
  view = "library";
  document.body.dataset.view = view;
  byId("library-view").hidden = false;
  byId("editor-view").hidden = true;
  byId("editor-context").hidden = true;
  byId("feedback").hidden = true;
  render();
  window.scrollTo(0, 0);
  byId("library-heading").focus({ preventScroll: true });
}

function openResume(id) {
  const record = library.get(id);
  if (!record) return;
  activeId = id;
  view = "editor";
  document.body.dataset.view = view;
  byId("library-view").hidden = true;
  byId("editor-view").hidden = false;
  byId("editor-context").hidden = false;
  const data = record.draft;
  sections = structuredClone(data.sections);
  order = [...data.order];
  avatarVisible = data.avatarVisible;
  for (const field of basicFields) byId(field).value = data.basics[field];
  byId("font-size").value = String(data.fontSize);
  byId("line-height").value = String(data.lineHeight);
  byId("zoom").value = record.zoom;
  byId("scenario").value = "success";
  byId("feedback").hidden = true;
  byId("preview-scroll").scrollTop = 0;
  selectSection(record.selected);
  window.scrollTo(0, 0);
  byId(`tab-${record.selected}`).focus({ preventScroll: true });
}

function actionButton(label, className, callback, accessibleLabel = label) {
  const button = textElement("button", className, label);
  button.type = "button";
  button.setAttribute("aria-label", accessibleLabel);
  button.addEventListener("click", callback);
  return button;
}

function renderLibrary() {
  const records = library.list();
  const query = byId("resume-search").value.trim().toLocaleLowerCase();
  const matching = records.filter((record) => `${record.title} ${record.draft.basics.headline}`.toLocaleLowerCase().includes(query));
  byId("resume-count").textContent = records.length;
  byId("library-empty").hidden = matching.length !== 0;
  byId("empty-title").textContent = records.length ? "没有找到匹配的简历" : "还没有简历";
  byId("empty-description").textContent = records.length ? "试试其他名称或求职方向，您的简历没有被删除。" : "从空白开始，或使用虚构示例熟悉编辑流程。";
  byId("empty-create").hidden = records.length > 0;
  const fragment = document.createDocumentFragment();
  for (const record of matching) {
    const card = textElement("article", "resume-card", "");
    card.dataset.resumeId = record.id;
    card.setAttribute("aria-label", `简历：${record.title}`);
    const thumbnail = actionButton("", "resume-thumbnail", () => openResume(record.id), `打开简历：${record.title}`);
    const paper = textElement("div", "thumbnail-sheet", "");
    paper.append(textElement("h3", "", record.draft.basics.name || "您的姓名"));
    paper.append(textElement("p", "", record.draft.basics.headline || "填写您的求职方向"));
    for (const key of record.draft.order.filter((key) => record.draft.sections[key].visible && record.draft.sections[key].entryVisible).slice(0, 3)) {
      const section = textElement("div", "thumbnail-section", "");
      section.append(textElement("strong", "", record.draft.sections[key].label), textElement("div", "thumbnail-line", ""), textElement("div", "thumbnail-line short", ""));
      paper.append(section);
    }
    thumbnail.append(paper, textElement("span", "resume-type", record.sourceTitle ? "独立副本" : "中文单栏"));
    const content = textElement("div", "resume-card-content", "");
    const heading = textElement("div", "resume-card-heading", "");
    const title = textElement("h2", "", record.title);
    title.title = record.title;
    const dirty = record.editEpoch !== record.savedEpoch;
    const busy = record.phase !== "idle";
    const status = record.saveFailed ? "保存失败" : busy ? "处理中" : dirty ? "未保存草稿" : "已模拟保存";
    heading.append(title, textElement("span", `resume-card-status ${busy ? "busy" : dirty || record.saveFailed ? "dirty" : ""}`, status));
    const role = textElement("p", "resume-role", record.draft.basics.headline || "尚未填写求职方向");
    role.title = role.textContent;
    const time = new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(record.updatedAt));
    const provenance = textElement("p", "resume-provenance", `更新于 ${time} · r${record.revision}${record.sourceTitle ? " · 复制自 " + record.sourceTitle : ""}`);
    provenance.title = provenance.textContent;
    const actions = textElement("div", "resume-card-actions", "");
    const edit = actionButton("编辑", "button primary", () => openResume(record.id), `编辑：${record.title}`);
    const copy = actionButton("创建副本", "button", () => openResumeDialog("copy", record.id), `创建副本：${record.title}`);
    const rename = actionButton("重命名", "text-button muted", () => openResumeDialog("rename", record.id), `重命名：${record.title}`);
    const remove = actionButton("删除", "text-button muted delete-action", () => openDeleteDialog(record.id), `删除：${record.title}`);
    for (const button of [copy, rename, remove]) button.disabled = busy;
    actions.append(edit, copy, rename, remove);
    content.append(heading, role, provenance, actions);
    card.append(thumbnail, content);
    fragment.append(card);
  }
  if (matching.length && !query) {
    const tile = actionButton("", "new-resume-tile", () => openResumeDialog("create"), "新建另一份简历");
    tile.append(textElement("strong", "", "+ 新建另一份简历"), textElement("span", "", "空白开始，或使用虚构示例"));
    fragment.append(tile);
  }
  byId("resume-grid").replaceChildren(fragment);
}

function openResumeDialog(mode, id = null) {
  const record = id ? library.get(id) : null;
  if (id && (!record || record.phase !== "idle")) return;
  resumeAction = { mode, id };
  byId("resume-dialog-title").textContent = { create: "新建简历", copy: "创建简历副本", rename: "重命名简历" }[mode];
  byId("resume-dialog-description").textContent = mode === "copy"
    ? `复制“${record.title}”的内容和排版设置。原简历保持不变，副本独立编辑，并需重新生成预览。`
    : mode === "rename" ? "名称仅用于管理，不显示在简历正文中。不会改变其他简历。" : "给这份简历起一个容易区分的名字，例如岗位或投递场景。";
  byId("resume-title-input").value = mode === "create" ? "" : mode === "copy" ? library.suggestCopyTitle(id) : record.title;
  byId("create-kind-field").hidden = mode !== "create";
  byId("create-kind").value = "blank";
  byId("copy-version-field").hidden = mode !== "copy" || record.editEpoch === record.savedEpoch;
  byId("copy-version").value = "saved";
  byId("resume-submit").textContent = mode === "rename" ? "保存名称" : mode === "copy" ? "创建副本并编辑" : "创建并编辑";
  byId("resume-form-error").hidden = true;
  byId("resume-dialog").showModal();
  byId("resume-title-input").focus();
  byId("resume-title-input").select();
}

function openDeleteDialog(id) {
  const record = library.get(id);
  if (!record || record.phase !== "idle") return;
  deleteId = id;
  const dirty = record.editEpoch !== record.savedEpoch;
  byId("delete-description").textContent = `即将删除“${record.title}”。${dirty ? "这份简历还有未保存草稿，确认后也将一并删除。" : ""}`;
  byId("delete-error").hidden = true;
  byId("delete-dialog").showModal();
}

byId("resume-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!resumeAction) return;
  const { mode, id } = resumeAction;
  const title = byId("resume-title-input").value;
  try {
    let created;
    if (mode === "create") created = library.create(title, byId("create-kind").value === "sample" ? exampleData : blankData());
    if (mode === "copy") created = library.duplicate(id, title, byId("copy-version").value);
    if (mode === "rename") library.rename(id, title);
    byId("resume-dialog").close();
    byId("resume-search").value = "";
    if (created) {
      openResume(created.id);
      feedback(mode === "copy" ? "副本已创建。您正在编辑副本，原简历保持不变。" : "新简历已创建，仅在本次演示中保留。");
    } else {
      render();
      feedback("简历名称已更新，其他简历不受影响。");
    }
  } catch (cause) {
    byId("resume-form-error").textContent = cause.message;
    byId("resume-form-error").hidden = false;
  }
});
byId("resume-dialog").addEventListener("close", () => { resumeAction = null; });
byId("delete-confirm").addEventListener("click", () => {
  if (!deleteId) return;
  try {
    library.remove(deleteId);
    if (activeId === deleteId) activeId = library.list()[0]?.id ?? null;
    byId("delete-dialog").close();
    showLibrary();
    feedback("已移除选中的演示简历，其他简历和副本均保留。");
  } catch (cause) {
    byId("delete-error").textContent = cause.message;
    byId("delete-error").hidden = false;
  }
});
byId("delete-dialog").addEventListener("close", () => { deleteId = null; });
for (const id of ["nav-library", "brand-home", "back-to-library"]) byId(id).addEventListener("click", showLibrary);
for (const id of ["new-resume", "empty-create"]) byId(id).addEventListener("click", () => openResumeDialog("create"));
byId("nav-editor").addEventListener("click", () => openResume(activeId));
byId("resume-switcher").addEventListener("change", () => openResume(byId("resume-switcher").value));
byId("rename-active").addEventListener("click", () => openResumeDialog("rename", activeId));
byId("copy-active").addEventListener("click", () => openResumeDialog("copy", activeId));
byId("resume-search").addEventListener("input", renderLibrary);

basicFields.forEach((id) => byId(id).addEventListener("input", edited));
for (const [id, property] of [["section-title", "title"], ["section-subtitle", "subtitle"], ["body", "body"]]) {
  byId(id).addEventListener("input", () => { sections[selected][property] = byId(id).value; edited(); });
}
byId("entry-visible").addEventListener("change", () => { sections[selected].entryVisible = byId("entry-visible").checked; edited(); });
byId("avatar-show").addEventListener("click", () => { avatarVisible = true; edited(); });
byId("avatar-hide").addEventListener("click", () => { avatarVisible = false; edited(); });
byId("font-size").addEventListener("change", edited);
byId("line-height").addEventListener("change", edited);
byId("zoom").addEventListener("change", () => {
  library.setView(activeId, { zoom: byId("zoom").value });
  fitPaper();
});
const tabs = [...document.querySelectorAll("[data-section]")];
tabs.forEach((button, index) => {
  button.addEventListener("click", () => selectSection(button.dataset.section));
  button.addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next === undefined) return;
    event.preventDefault();
    selectSection(tabs[next].dataset.section);
    tabs[next].focus();
    tabs[next].scrollIntoView({ block: "nearest", inline: "nearest" });
  });
});
document.querySelectorAll("[data-format]").forEach((button) => {
  button.addEventListener("click", () => {
    const area = byId("body");
    const selection = area.value.slice(area.selectionStart, area.selectionEnd) || "文字";
    const prefix = area.selectionStart > 0 && area.value[area.selectionStart - 1] !== "\n" ? "\n" : "";
    const text = { bold: `**${selection}**`, italic: `*${selection}*`, bullet: `${prefix}- ${selection}`, ordered: `${prefix}1. ${selection}`, link: `[${selection}](https://example.com)` }[button.dataset.format];
    if (area.value.length - (area.selectionEnd - area.selectionStart) + text.length > 10000) { feedback("正文已达到长度上限，请先缩短内容。"); return; }
    area.setRangeText(text, area.selectionStart, area.selectionEnd, "end");
    sections[selected].body = area.value;
    area.focus();
    edited();
  });
});
function renderModules() {
  const fragment = document.createDocumentFragment();
  order.forEach((key, index) => {
    const row = textElement("div", "module-row", "");
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = sections[key].visible;
    input.addEventListener("change", () => { sections[key].visible = input.checked; edited(); });
    label.append(input, document.createTextNode(sections[key].label));
    const actions = textElement("div", "module-order", "");
    for (const [offset, title] of [[-1, "上移"], [1, "下移"]]) {
      const button = textElement("button", "icon-button", offset === -1 ? "↑" : "↓");
      button.type = "button";
      button.setAttribute("aria-label", `${title}${sections[key].label}`);
      button.disabled = index + offset < 0 || index + offset >= order.length;
      button.addEventListener("click", () => {
        [order[index], order[index + offset]] = [order[index + offset], order[index]];
        edited();
        renderModules();
        const movedButton = [...byId("module-list").querySelectorAll("button")].find((item) => item.getAttribute("aria-label") === `${title}${sections[key].label}` && !item.disabled);
        if (movedButton) movedButton.focus();
      });
      actions.append(button);
    }
    row.append(label, actions);
    fragment.append(row);
  });
  byId("module-list").replaceChildren(fragment);
}
for (const id of ["modules", "settings", "diagnostics", "guide"]) {
  byId(id).addEventListener("click", () => {
    if (id === "modules") renderModules();
    byId(`${id}-dialog`).showModal();
  });
}
document.querySelectorAll("[data-close]").forEach((button) => {
  button.addEventListener("click", () => byId(button.dataset.close).close("cancel"));
});
const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
byId("simulate").addEventListener("click", async () => {
  const targetId = activeId;
  const scenario = byId("scenario").value;
  const ticket = library.beginSave(targetId);
  byId("feedback").hidden = true;
  render();
  await delay(350);
  const job = library.finishSave(ticket, scenario === "save-error");
  render();
  if (!job) return;
  await delay(500);
  library.finishCompile(job, scenario === "compile-error");
  render();
});
byId("export").addEventListener("click", () => {
  const record = library.get(activeId);
  feedback(`模拟导出“${record.title}” r${record.preview.revision}，应使用这份简历预览的同一份 PDF。没有生成或下载文件。`);
});
byId("old-export").addEventListener("click", () => {
  const record = library.get(activeId);
  pendingOldExport = { id: record.id, title: record.title, revision: record.preview.revision };
  byId("old-description").textContent = `将导出“${record.title}”上次成功版本 r${record.preview.revision}，不包含之后的修改。`;
  byId("old-dialog").returnValue = "cancel";
  byId("old-dialog").showModal();
});
byId("old-dialog").addEventListener("close", () => {
  if (byId("old-dialog").returnValue === "confirm" && pendingOldExport) {
    feedback(`已明确选择“${pendingOldExport.title}”旧版 r${pendingOldExport.revision}（模拟），没有生成或下载文件。`);
  }
  pendingOldExport = null;
});
byId("backup").addEventListener("click", () => { feedback("工程备份应包含已保存内容、配置和头像；不依赖 PDF 编译成功。导入始终创建副本。此处仅演示规则，没有生成备份文件。"); });
new ResizeObserver(fitPaper).observe(byId("preview-scroll"));
new ResizeObserver(fitPaper).observe(byId("resume-paper"));
render();
