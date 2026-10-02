const test = require("node:test");
const assert = require("node:assert/strict");
const { ResumeLibrary } = require("../docs/m0/resume-library.js");

function setup() {
  let id = 0;
  let tick = 0;
  const library = new ResumeLibrary({
    makeId: () => `resume-${++id}`,
    now: () => new Date(Date.UTC(2026, 9, 1, 10, 0, tick++)).toISOString(),
  });
  const data = { basics: { name: "Fictional" }, sections: { project: { body: "Original", visible: false } }, order: ["project"], avatarVisible: true, fontSize: 11 };
  const first = library.create("Original", data);
  return { library, data, first };
}

function compile(library, id) {
  const ticket = library.beginSave(id);
  const job = library.finishSave(ticket);
  library.finishCompile(job);
}

test("creation owns its input and returned snapshots cannot mutate records", () => {
  const { library, data, first } = setup();
  data.basics.name = "changed";
  first.draft.basics.name = "also changed";
  assert.equal(library.get(first.id).draft.basics.name, "Fictional");
});

test("duplicate is a deep independent saved snapshot with fresh identity and no PDF", () => {
  const { library, first } = setup();
  compile(library, first.id);
  const before = library.get(first.id);
  const copy = library.duplicate(first.id, "Copy");
  assert.notEqual(copy.id, first.id);
  assert.equal(copy.revision, 1);
  assert.equal(copy.preview, null);
  assert.deepEqual(copy.draft, before.saved);
  assert.equal(copy.sourceTitle, "Original");
  const draft = copy.draft;
  draft.sections.project.body = "Copy only";
  draft.order.reverse();
  library.updateDraft(copy.id, draft);
  compile(library, copy.id);
  assert.deepEqual(library.get(first.id), before);
});

test("copy defaults to saved content; including unsaved edits is explicit", () => {
  const { library, first } = setup();
  const draft = first.draft;
  draft.basics.name = "Unsaved";
  library.updateDraft(first.id, draft);
  const before = library.get(first.id);
  assert.equal(library.duplicate(first.id, "Saved copy").draft.basics.name, "Fictional");
  assert.equal(library.duplicate(first.id, "Draft copy", "draft").draft.basics.name, "Unsaved");
  assert.deepEqual(library.get(first.id), before);
});

test("title validation rejects blank or oversized names without changing the library", () => {
  const { library, data } = setup();
  for (const title of ["", "  ", "a".repeat(81)]) assert.throws(() => library.create(title, data));
  assert.equal(library.list().length, 1);
  assert.equal(library.create("  Valid  ", data).title, "Valid");
});

test("suggested copy names are distinct and capped at 80 code points", () => {
  const { library, data } = setup();
  const source = library.create("简".repeat(80), data);
  const firstName = library.suggestCopyTitle(source.id);
  library.duplicate(source.id, firstName);
  const secondName = library.suggestCopyTitle(source.id);
  assert.notEqual(firstName, secondName);
  assert.ok([...firstName].length <= 80);
  assert.ok([...secondName].length <= 80);
});

test("renaming changes only the targeted record and invalidates its old preview", () => {
  const { library, first } = setup();
  const copy = library.duplicate(first.id, "Copy");
  compile(library, copy.id);
  const original = library.get(first.id);
  library.rename(copy.id, "Renamed");
  assert.equal(library.get(copy.id).title, "Renamed");
  assert.equal(library.get(copy.id).revision, 2);
  assert.equal(library.get(copy.id).preview.revision, 1);
  assert.deepEqual(library.get(first.id), original);
});

test("deleting either source or copy leaves other documents intact", () => {
  const { library, first } = setup();
  const copy = library.duplicate(first.id, "Copy");
  library.remove(first.id);
  assert.equal(library.get(first.id), null);
  assert.deepEqual(library.get(copy.id), copy);
  library.remove(copy.id);
  assert.deepEqual(library.list(), []);
});

test("each resume retains its own draft, selection and zoom", () => {
  const { library, data, first } = setup();
  const second = library.create("Second", data);
  const changed = first.draft;
  changed.basics.name = "First draft";
  library.updateDraft(first.id, changed);
  library.setView(first.id, { selected: "project", zoom: "100" });
  assert.equal(library.get(first.id).draft.basics.name, "First draft");
  assert.equal(library.get(first.id).selected, "project");
  assert.equal(library.get(second.id).draft.basics.name, "Fictional");
  assert.equal(library.get(second.id).zoom, "fit");
});

test("interleaved saves and compilation update only their owning resume", () => {
  const { library, data, first } = setup();
  const second = library.create("Second", data);
  const a = library.beginSave(first.id);
  const b = library.beginSave(second.id);
  const jobB = library.finishSave(b);
  const jobA = library.finishSave(a);
  library.finishCompile(jobB);
  assert.equal(library.get(first.id).preview, null);
  library.finishCompile(jobA);
  assert.equal(library.get(first.id).preview.resumeId, first.id);
  assert.equal(library.get(second.id).preview.resumeId, second.id);
});

test("edits made during save remain dirty after the captured snapshot completes", () => {
  const { library, first } = setup();
  const ticket = library.beginSave(first.id);
  const changed = first.draft;
  changed.basics.name = "Newer draft";
  library.updateDraft(first.id, changed);
  library.finishCompile(library.finishSave(ticket));
  const result = library.get(first.id);
  assert.equal(result.preview.data.basics.name, "Fictional");
  assert.equal(result.draft.basics.name, "Newer draft");
  assert.notEqual(result.editEpoch, result.savedEpoch);
});

test("save failure retains draft and saved revision; compile failure retains last success", () => {
  const { library, first } = setup();
  compile(library, first.id);
  const draft = first.draft;
  draft.basics.name = "Changed";
  library.updateDraft(first.id, draft);
  assert.equal(library.finishSave(library.beginSave(first.id), true), null);
  assert.equal(library.get(first.id).revision, 1);
  assert.equal(library.get(first.id).saveFailed, true);
  library.finishCompile(library.finishSave(library.beginSave(first.id)), true);
  assert.equal(library.get(first.id).revision, 2);
  assert.equal(library.get(first.id).preview.revision, 1);
  assert.equal(library.get(first.id).draft.basics.name, "Changed");
});

test("busy management and overlapping jobs are rejected", () => {
  const { library, first } = setup();
  library.beginSave(first.id);
  assert.throws(() => library.beginSave(first.id));
  assert.throws(() => library.remove(first.id));
  assert.throws(() => library.rename(first.id, "Busy"));
  assert.throws(() => library.duplicate(first.id, "Busy copy"));
});

test("completed or forged task identities cannot overwrite a later result", () => {
  const { library, first } = setup();
  const ticket = library.beginSave(first.id);
  const job = library.finishSave(ticket);
  assert.equal(library.finishCompile({ ...job, taskId: "stale" }), false);
  assert.equal(library.finishCompile(job), true);
  assert.equal(library.finishCompile(job, true), false);
  assert.equal(library.get(first.id).compileFailed, false);
});

test("listing is most recently updated first without exposing mutable records", () => {
  const { library, data, first } = setup();
  const second = library.create("Second", data);
  assert.equal(library.list()[0].id, second.id);
  library.rename(first.id, "Recently changed");
  assert.equal(library.list()[0].id, first.id);
  library.list()[0].title = "External edit";
  assert.equal(library.get(first.id).title, "Recently changed");
});
