import assert from "node:assert/strict";
import test from "node:test";
import { api } from "../src/api.ts";
import { resources, revisionHeaders } from "../src/api/resources.ts";
import { notifyProjectChanged, PROJECT_CHANGED } from "../src/shell/projectEvents.ts";

const events = new EventTarget();
let flush: (() => void) | undefined;
Object.assign(globalThis, { window: {
  dispatchEvent: (event: Event) => events.dispatchEvent(event),
  setTimeout: (callback: () => void) => { flush = callback; return 1; },
} });
const json = (value: unknown, etag = '"v1"') => new Response(JSON.stringify(value), {
  headers: { "Content-Type": "application/json", ETag: etag },
});
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test("shell, stage and inspector share in-flight AND completed GETs", async () => {
  resources.invalidate();
  const calls: string[] = [];
  globalThis.fetch = async (path) => { calls.push(String(path)); return json({ shots: [] }); };
  const shell = api.storyboard("a");
  const stage = api.storyboard("a");
  const [first, second] = await Promise.all([shell, stage]);
  const inspector = await api.storyboard("a");
  assert.equal(first, second);
  assert.equal(first, inspector);
  assert.equal(calls.length, 1);
  const required = [api.images, api.track, api.intake, api.budget, api.edit, api.brief];
  for (const read of required) {
    await Promise.all([read("a"), read("a"), read("a")]);
    await read("a");
  }
  assert.equal(calls.length, required.length + 1);
});

test("coalesced selective notices retain project/artifact associations; reconnect resets all", async () => {
  resources.invalidate();
  const counts = new Map<string, number>();
  globalThis.fetch = async (path) => {
    const key = String(path); counts.set(key, (counts.get(key) || 0) + 1);
    return json({ shots: [] });
  };
  const readAll = () => Promise.all([api.images("a"), api.track("a"), api.images("b"), api.track("b")]);
  await readAll();
  let dispatched = 0;
  const listener = () => { dispatched += 1; };
  events.addEventListener(PROJECT_CHANGED, listener);
  notifyProjectChanged({ slug: "a", artifact: "images" });
  notifyProjectChanged({ slug: "b", artifact: "track" });
  flush!();
  await readAll();
  assert.equal(dispatched, 1);
  assert.equal(counts.get("/api/projects/a/images"), 2);
  assert.equal(counts.get("/api/projects/a/track"), 1);
  assert.equal(counts.get("/api/projects/b/images"), 1);
  assert.equal(counts.get("/api/projects/b/track"), 2);
  notifyProjectChanged({ source: "reconnect" }); flush!();
  await readAll();
  assert.equal(counts.get("/api/projects/a/track"), 2);
  assert.equal(counts.get("/api/projects/b/images"), 2);
  events.removeEventListener(PROJECT_CHANGED, listener);
});

test("unknown artifacts conservatively invalidate that entire film, never another", async () => {
  resources.invalidate();
  let calls = 0;
  globalThis.fetch = async () => json({ title: String(++calls) });
  const a = await api.brief("a"); const b = await api.brief("b");
  resources.invalidate({ slug: "a", artifact: "future-artifact" });
  assert.notEqual(await api.brief("a"), a);
  assert.equal(await api.brief("b"), b);
  assert.equal(calls, 3);
});

test("late old success cannot overwrite cache OR return stale data to its consumer", async () => {
  resources.invalidate();
  const old = deferred<Response>(); let calls = 0;
  globalThis.fetch = async () => ++calls === 1 ? old.promise : json({ title: "new" });
  const pending = api.brief("a");
  await Promise.resolve();
  resources.invalidate({ slug: "a", artifact: "brief" });
  const fresh = await api.brief("a");
  old.resolve(json({ title: "old" }));
  assert.equal(await pending, fresh);
  assert.equal(await api.brief("a"), fresh);
  assert.equal(calls, 2);
});

test("errors are not cached; prior success remains usable by the component", async () => {
  resources.invalidate();
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return calls === 2 ? new Response('{"detail":"offline"}', { status: 503 }) : json({ title: "saved" });
  };
  const state = await api.brief("a");
  resources.invalidate({ slug: "a" });
  await assert.rejects(api.brief("a"), /offline/);
  assert.equal(state.title, "saved");
  await api.brief("a");
  assert.equal(calls, 3);
});

test("late obsolete failure resolves to current data rather than surfacing stale error", async () => {
  resources.invalidate();
  const old = deferred<Response>(); let calls = 0;
  globalThis.fetch = async () => ++calls === 1 ? old.promise : json({ title: "new" });
  const pending = api.brief("a"); await Promise.resolve();
  resources.invalidate({ slug: "a" });
  const fresh = await api.brief("a"); old.reject(new Error("old failure"));
  assert.equal(await pending, fresh);
});

test("direct mutation invalidates before and after the write; base token stays attached to old draft", async () => {
  resources.invalidate();
  const writes: RequestInit[] = []; let version = 1; let reads = 0;
  const write = deferred<Response>();
  globalThis.fetch = async (_path, init) => {
    if (init?.method === "PATCH") { writes.push(init); return write.promise; }
    reads += 1; return json({ title: `v${version}` }, `"v${version}"`);
  };
  const base = await api.brief("a");
  resources.invalidate({ slug: "a" }); version = 2;
  const background = await api.brief("a");
  const saving = api.patchBrief("a", { title: "draft" }, base);
  const during = await api.brief("a");
  assert.notEqual(during, background);
  assert.equal(new Headers(writes[0].headers).get("If-Match"), '"v1"');
  write.resolve(json({ title: "draft" }, '"v3"')); const saved = await saving;
  assert.equal(revisionHeaders(saved, "a", "brief")["If-Match"], '"v3"');
  assert.equal(revisionHeaders(base, "a", "brief")["If-Match"], '"v1"');
  await api.brief("a"); assert.equal(reads, 4);
  assert.deepEqual(revisionHeaders(base, "b", "brief"), {});
  assert.deepEqual(revisionHeaders(base, "a", "storyboard"), {});
});

test("failed mutations invalidate reads started during the write", async () => {
  resources.invalidate();
  const write = deferred<Response>(); let reads = 0;
  globalThis.fetch = async (_path, init) => init?.method === "PATCH" ? write.promise : json({ title: String(++reads) });
  const base = await api.brief("a");
  const saving = api.patchBrief("a", { title: "draft" }, base);
  const during = await api.brief("a");
  const rejected = assert.rejects(saving, /conflict/);
  write.resolve(new Response('{"detail":"conflict"}', { status: 409 }));
  await rejected;
  assert.notEqual(await api.brief("a"), during);
  assert.equal(reads, 3);
});

test("nested intake brief, board shot, and edit carry their own base revisions", async () => {
  resources.invalidate();
  globalThis.fetch = async (path) => String(path).endsWith("intake")
    ? json({ brief: { title: "a" } }, '"brief-base"')
    : String(path).endsWith("storyboard") ? json({ shots: [{ id: "s1" }] }, '"board-base"')
    : json({ present: true, edit: { shots: [] } }, '"edit-base"');
  const intake = await api.intake("a");
  const board = await api.storyboard("a");
  const edit = await api.edit("a");
  assert.equal(revisionHeaders(intake.brief, "a", "brief")["If-Match"], '"brief-base"');
  assert.equal(revisionHeaders("shots" in board ? board.shots[0] : null, "a", "storyboard")["If-Match"], '"board-base"');
  assert.equal(revisionHeaders(edit.edit, "a", "edit")["If-Match"], '"edit-base"');
});

test("cut summaries receive only an exactly matching edit revision", async () => {
  resources.invalidate();
  globalThis.fetch = async () => json({ present: true, edit: { shots: [] } }, '"cut-base"');
  const cut = await api.editSummary("a");
  assert.equal(revisionHeaders(cut.edit, "a", "edit")["If-Match"], '"cut-base"');
  resources.invalidate();
  globalThis.fetch = async (path) => json({ present: true, edit: { shots: String(path).endsWith("summary") ? [] : ["changed"] } });
  await assert.rejects(api.editSummary("a"), /Reload and review/);
});

test("track changes refresh edit and cut summary without invalidating another project", async () => {
  resources.invalidate();
  const counts = new Map<string, number>();
  globalThis.fetch = async (path) => {
    const key = String(path);
    counts.set(key, (counts.get(key) || 0) + 1);
    return json({ present: true, edit: { shots: [] } });
  };
  const edit = await api.edit("a");
  const summary = await api.editSummary("a");
  const other = await api.editSummary("b");
  notifyProjectChanged({ slug: "a", artifact: "track" });
  flush!();
  assert.notEqual(await api.edit("a"), edit);
  assert.notEqual(await api.editSummary("a"), summary);
  assert.equal(await api.editSummary("b"), other);
  assert.equal(counts.get("/api/projects/a/edit"), 2);
  assert.equal(counts.get("/api/projects/a/edit/summary"), 2);
  assert.equal(counts.get("/api/projects/b/edit"), 1);
  assert.equal(counts.get("/api/projects/b/edit/summary"), 1);
});
