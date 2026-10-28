import assert from "node:assert/strict";
import test from "node:test";
import { InspectorSaveGuard, leaveInspector, remainingDraft } from "../src/storyboard/inspectorSave.ts";
import { bindRevision, revisionHeaders } from "../src/api/resources.ts";

test("only one write may be pending for the selected shot", () => {
  const guard = new InspectorSaveGuard();
  guard.select("a");
  assert.equal(guard.begin("b"), null);
  const first = guard.begin("a")!;
  assert.ok(first);
  assert.equal(guard.begin("a"), null);
  assert.equal(guard.finish(first, "a"), true);
  assert.ok(guard.begin("a"));
});

test("selection changes discard old completion ownership, even when returning to the same shot", () => {
  const guard = new InspectorSaveGuard();
  guard.select("a");
  const old = guard.begin("a")!;
  guard.select("b");
  const draftB = { purpose: "new shot draft" };
  const pendingB = guard.begin("b")!;
  let draft = draftB;
  if (guard.current(old, "a")) draft = remainingDraft(draft, draftB);
  assert.equal(draft, draftB);
  assert.equal(guard.finish(old, "a"), false);
  assert.equal(guard.begin("b"), null);
  assert.equal(guard.current(pendingB, "b"), true);
  guard.select("a");
  assert.equal(guard.current(old, "a"), false);
});

test("unmount invalidation rejects completions and stale finish cannot clear a newer pending write", () => {
  const guard = new InspectorSaveGuard();
  guard.select("a");
  const old = guard.begin("a")!;
  guard.invalidate();
  assert.equal(guard.current(old, "a"), false);
  assert.equal(guard.finish(old, "a"), false);
  const next = guard.begin("a")!;
  assert.equal(guard.finish(old, "a"), false);
  assert.equal(guard.begin("a"), null);
  assert.equal(guard.current(next, "a"), true);
  assert.equal(guard.finish(next, "a"), true);
});

test("a finished ticket cannot finish a subsequent pending write", () => {
  const guard = new InspectorSaveGuard();
  guard.select("a");
  const old = guard.begin("a")!;
  guard.finish(old, "a");
  const next = guard.begin("a")!;
  assert.equal(guard.finish(old, "a"), false);
  assert.equal(guard.current(old, "a"), false);
  assert.equal(guard.begin("a"), null);
  assert.equal(guard.finish(next, "a"), true);
});

test("acknowledgement removes only unchanged sent fields, preserving typing and unsent fields", () => {
  const sent = { purpose: "save A", text: ["same"], message: "acknowledged" };
  const current = { purpose: "typed B", text: ["same"], message: "acknowledged", image_prompt: "new" };
  assert.deepEqual(remainingDraft(current, sent), { purpose: "typed B", image_prompt: "new" });
  assert.equal(current.message, "acknowledged", "the live draft is not mutated");
  assert.deepEqual(remainingDraft(sent, sent), {});
});

test("surviving draft uses the acknowledged shot revision rather than its own stale base", () => {
  const guard = new InspectorSaveGuard();
  guard.select("a");
  type Shot = { purpose: string };
  let base: Shot = { purpose: "original" };
  bindRevision(base, "film", "storyboard", '"v1"');
  const ticket = guard.begin("a")!;
  const sent = { purpose: "save A" };
  let draft = { purpose: "typed B" };
  const savedShot = { purpose: "save A" };
  bindRevision(savedShot, "film", "storyboard", '"v2"');
  // Same completion guard/base handoff used by ShotInspector.savePatch.
  if (guard.current(ticket, "a")) {
    base = savedShot;
    draft = remainingDraft(draft, sent) as Shot;
  }
  guard.finish(ticket, "a");
  assert.deepEqual(draft, { purpose: "typed B" });
  assert.equal(base, savedShot);
  assert.equal(revisionHeaders(base, "film", "storyboard")["If-Match"], '"v2"');
  assert.ok(guard.begin("a"), "the surviving draft can start its next save");
});

test("navigation is refused during a pending save without discarding newer typing", async () => {
  let left = false;
  const draft = { purpose: "newer typing" };
  const guard = new InspectorSaveGuard();
  guard.select("a");
  guard.begin("a");
  assert.equal(await leaveInspector({
    saving: () => guard.isSaving(), dirty: () => !!draft.purpose,
    save: async () => { throw new Error("must not start a second save"); },
    leave: () => { left = true; },
  }), false);
  assert.equal(left, false);
  assert.equal(draft.purpose, "newer typing");
});

test("navigation stays on the selected shot after a failed save or surviving draft", async () => {
  for (const success of [false, true]) {
    let left = false;
    assert.equal(await leaveInspector({
      saving: () => false, dirty: () => true,
      save: async () => success, leave: () => { left = true; },
    }), false);
    assert.equal(left, false);
  }
});

test("navigation flushes a draft and leaves only after acknowledgement", async () => {
  const order: string[] = [];
  let dirty = true;
  assert.equal(await leaveInspector({
    saving: () => false, dirty: () => dirty,
    save: async () => { order.push("saved"); dirty = false; return true; },
    leave: () => { order.push("left"); },
  }), true);
  assert.deepEqual(order, ["saved", "left"]);
});
