import assert from "node:assert/strict";
import test from "node:test";
import type { EditPayload } from "../src/api.ts";
import { CutEditor } from "../src/film/cutEditor.ts";

const cut = (name: string) => ({ notes: name, sections: [], shots: [], grade: {} }) as unknown as EditPayload;

function gate() {
  const calls: { next: EditPayload; base: EditPayload; resolve: (v: EditPayload) => void; reject: (e: unknown) => void }[] = [];
  const save = (next: EditPayload, base: EditPayload) =>
    new Promise<EditPayload>((resolve, reject) => calls.push({ next, base, resolve, reject }));
  const flush = () => new Promise((resolve) => setImmediate(resolve));
  return { calls, save, flush };
}

test("changes show at once and save in order against the server's last answer", async () => {
  const { calls, save, flush } = gate();
  const editor = new CutEditor(save, () => {});
  const first = cut("first");
  editor.sync(first);
  const a = cut("a");
  const b = cut("b");
  const one = editor.apply(a);
  const two = editor.apply(b);
  assert.equal(editor.current, b);
  assert.equal(editor.saving, true);
  await flush();
  assert.equal(calls.length, 1, "the second save waits for the first");
  assert.equal(calls[0].base, first);
  const answerA = cut("a-saved");
  calls[0].resolve(answerA);
  assert.equal(await one, "saved");
  await flush();
  assert.equal(calls[1].next, b);
  assert.equal(calls[1].base, answerA, "the next save uses the returned revision");
  const answerB = cut("b-saved");
  calls[1].resolve(answerB);
  assert.equal(await two, "saved");
  assert.equal(editor.current, answerB);
  assert.equal(editor.saving, false);
});

test("a failed save returns to the confirmed cut and drops changes built on it", async () => {
  const { calls, save, flush } = gate();
  const editor = new CutEditor(save, () => {});
  const first = cut("first");
  editor.sync(first);
  const one = editor.apply(cut("a"));
  const two = editor.apply(cut("b"));
  await flush();
  calls[0].reject(new Error("boom"));
  assert.equal(await one, "failed");
  assert.equal(await two, "dropped");
  assert.equal(calls.length, 1);
  assert.equal(editor.current, first);
});

test("a 409 is reported as a conflict", async () => {
  const { calls, save, flush } = gate();
  const editor = new CutEditor(save, () => {});
  editor.sync(cut("first"));
  const one = editor.apply(cut("a"));
  await flush();
  calls[0].reject(Object.assign(new Error("stale"), { status: 409 }));
  assert.equal(await one, "conflict");
});

test("a reload never overwrites a change on its way", async () => {
  const { calls, save, flush } = gate();
  const editor = new CutEditor(save, () => {});
  editor.sync(cut("first"));
  const local = cut("local");
  const one = editor.apply(local);
  editor.sync(cut("older reload"));
  assert.equal(editor.current, local);
  await flush();
  const answer = cut("saved");
  calls[0].resolve(answer);
  await one;
  const fresh = cut("fresh reload");
  editor.sync(fresh);
  assert.equal(editor.current, fresh);
});

test("undo walks back several steps, saving each earlier cut", async () => {
  const saved: EditPayload[] = [];
  const editor = new CutEditor(async (next) => {
    saved.push(next);
    return next;
  }, () => {});
  const first = cut("first");
  editor.sync(first);
  const a = cut("a");
  const b = cut("b");
  await editor.apply(a, "to a");
  await editor.apply(b, "to b");
  const one = editor.undo();
  assert.equal(one?.label, "to b");
  assert.equal(await one?.result, "saved");
  assert.equal(editor.current, a);
  const two = editor.undo();
  assert.equal(two?.label, "to a");
  await two?.result;
  assert.equal(editor.current, first);
  assert.equal(editor.undo(), null);
  assert.deepEqual(saved, [a, b, a, first]);
});

test("a conflict clears undo; a plain failure keeps the steps before it", async () => {
  let fail: unknown = null;
  const editor = new CutEditor(async (next) => {
    if (fail) throw fail;
    return next;
  }, () => {});
  editor.sync(cut("first"));
  await editor.apply(cut("a"), "to a");
  fail = new Error("boom");
  assert.equal(await editor.apply(cut("b"), "to b"), "failed");
  assert.deepEqual(editor.history.map((step) => step.label), ["to a"]);
  fail = Object.assign(new Error("stale"), { status: 409 });
  assert.equal(await editor.apply(cut("c"), "to c"), "conflict");
  assert.deepEqual(editor.history, []);
});
