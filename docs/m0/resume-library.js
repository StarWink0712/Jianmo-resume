"use strict";

// In-memory M0 model, shared by the standalone prototype and Node tests.
(function (root) {
  const clone = (value) => structuredClone(value);
  const validateTitle = (value) => {
    const title = typeof value === "string" ? value.trim() : "";
    if (!title || [...title].length > 80) throw new Error("名称不能为空，且不能超过 80 个字符。");
    return title;
  };

  class ResumeLibrary {
    #records = new Map();
    #sequence = 0;

    constructor({ makeId = () => `resume-${root.crypto.randomUUID()}`, now = () => new Date().toISOString() } = {}) {
      this.makeId = makeId;
      this.now = now;
    }

    #require(id, idle = false) {
      const record = this.#records.get(id);
      if (!record) throw new Error("这份简历不存在。");
      if (idle && record.phase !== "idle") throw new Error("请等待这份简历保存和预览完成。");
      return record;
    }

    create(title, data, sourceTitle = null) {
      title = validateTitle(title);
      const id = this.makeId();
      if (this.#records.has(id)) throw new Error("简历标识发生冲突，请重试。");
      const time = this.now();
      const record = {
        id, title, sourceTitle, createdAt: time, updatedAt: time,
        draft: clone(data), saved: clone(data), initialData: clone(data),
        editEpoch: 0, savedEpoch: 0, revision: 1, preview: null,
        phase: "idle", saveFailed: false, compileFailed: false, error: "",
        selected: "basics", zoom: "fit", task: null,
      };
      this.#records.set(id, record);
      return clone(record);
    }

    get(id) {
      const record = this.#records.get(id);
      return record ? clone(record) : null;
    }

    list() {
      return [...this.#records.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)).map(clone);
    }

    updateDraft(id, data) {
      const record = this.#require(id);
      record.draft = clone(data);
      record.editEpoch += 1;
      record.saveFailed = false;
      record.error = "";
    }

    setView(id, { selected, zoom }) {
      const record = this.#require(id);
      if (selected !== undefined) record.selected = selected;
      if (zoom !== undefined) record.zoom = zoom;
    }

    suggestCopyTitle(id) {
      const source = this.#require(id);
      const titles = new Set([...this.#records.values()].map((record) => record.title));
      for (let index = 1; ; index += 1) {
        const suffix = index === 1 ? "（副本）" : `（副本 ${index}）`;
        const title = [...source.title].slice(0, 80 - [...suffix].length).join("") + suffix;
        if (!titles.has(title)) return title;
      }
    }

    duplicate(id, title = this.suggestCopyTitle(id), version = "saved") {
      const source = this.#require(id, true);
      if (!["saved", "draft"].includes(version)) throw new Error("请选择要复制的版本。");
      return this.create(title, source[version], source.title);
    }

    rename(id, value) {
      const title = validateTitle(value);
      const record = this.#require(id, true);
      if (record.title !== title) {
        record.title = title;
        record.revision += 1;
        record.updatedAt = this.now();
      }
    }

    remove(id) {
      this.#require(id, true);
      this.#records.delete(id);
    }

    beginSave(id) {
      const record = this.#require(id, true);
      record.task = { resumeId: id, taskId: `task-${++this.#sequence}`, epoch: record.editEpoch, data: clone(record.draft) };
      record.phase = "saving";
      record.saveFailed = false;
      record.compileFailed = false;
      record.error = "";
      return clone(record.task);
    }

    #match(ticket, phase) {
      const record = this.#records.get(ticket?.resumeId);
      return record?.phase === phase && record.task?.taskId === ticket?.taskId ? record : null;
    }

    finishSave(ticket, failed = false) {
      const record = this.#match(ticket, "saving");
      if (!record) return null;
      if (failed) {
        record.phase = "idle";
        record.saveFailed = true;
        record.error = "模拟：写入失败。输入仍保留，请重试。本次未确认保存，不递增修订，也不编译。";
        record.task = null;
        return null;
      }
      if (record.savedEpoch !== record.task.epoch) record.revision += 1;
      record.saved = clone(record.task.data);
      record.savedEpoch = record.task.epoch;
      record.updatedAt = this.now();
      record.phase = "compiling";
      record.task.revision = record.revision;
      return clone(record.task);
    }

    finishCompile(ticket, failed = false) {
      const record = this.#match(ticket, "compiling");
      if (!record) return false;
      record.phase = "idle";
      record.compileFailed = failed;
      if (failed) {
        record.error = "模拟：编译失败。保存不受影响，保留上次成功结果，可重新保存并预览。";
      } else {
        record.preview = { resumeId: record.id, revision: record.task.revision, data: clone(record.task.data) };
      }
      record.task = null;
      return true;
    }
  }

  if (typeof module === "object" && module.exports) module.exports = { ResumeLibrary };
  else root.ResumeLibrary = ResumeLibrary;
})(globalThis);
