import assert from "node:assert/strict";
import test from "node:test";
import { deliveryWorkflow } from "../src/film/deliveryWorkflow.ts";
import type { DeliveryChecklist, FilmFile, Job } from "../src/api.ts";

const checklist: DeliveryChecklist = {
  signature_required: true, preview_required: false, can_final: false,
  lines: [{ id: "titles", label: "Titles", stage: "film", state: "you", required: true, detail: "", reason: null, expected_hash: "hash" }],
  stills: { kept: 1, total: 1 }, outstanding: ["titles"],
};
const base: FilmFile = { kind: "renders", name: "base.mp4", classification: "base", verified: true, current: true, delivery_ready: false };
const job = (status: string, render_kind = "base") => ({ id: "job", kind: "render", project: "film", status, render_kind, queued_at: 1, cost_usd: 0, progress: { done: 0, total: 0, unit: "", phase: "", stage: "" } }) as Job;

test("base success is not delivery; next review persists without banner", () => {
  const state = deliveryWorkflow([base], checklist, { available: true, current: true, samples: [{ name: "intro", url: "/sample", sha256: "x" }] }, [job("succeeded")]);
  assert.equal(state.title, "Your intro/credits review");
  assert.equal(state.ready, false);
});
test("stale samples do not authorize review; final draws the reviewed titles", () => {
  assert.equal(deliveryWorkflow([base], checklist, { available: true, current: false }, []).title, "Check the titles again");
  assert.equal(deliveryWorkflow([], checklist, null, []).title, "Check the titles");
  const state = deliveryWorkflow([base], { ...checklist, can_final: true, lines: [{ ...checklist.lines[0], state: "done" }] }, null, []);
  assert.match(state.detail, /intro\/credits you approved, exactly as reviewed/);
  assert.equal(state.ready, false);
});
test("only actual current verified final is delivery, never a successful job", () => {
  assert.equal(deliveryWorkflow([], checklist, null, [job("succeeded", "final")]).ready, false);
  const final = { ...base, classification: "final" as const, delivery_ready: true };
  assert.equal(deliveryWorkflow([final], checklist, null, []).ready, true);
  assert.equal(deliveryWorkflow([{ ...final, current: false }], checklist, null, []).ready, false);
});
test("approved titles do not ask for impossible reapproval when another gate remains", () => {
  const state = deliveryWorkflow([base], {
    ...checklist, can_final: false,
    lines: [
      { ...checklist.lines[0], state: "done" },
      { ...checklist.lines[0], id: "preview", label: "Preview", state: "you" },
    ], outstanding: ["preview"],
  }, { available: true, current: true, samples: [{ name: "intro", url: "/sample", sha256: "x" }] }, []);
  assert.equal(state.title, "Finish the delivery gates");
  assert.match(state.detail, /already approved/);
  assert.equal(state.ready, false);
});
test("promo/advert skips signature and stopping/interrupted stay honest", () => {
  const state = deliveryWorkflow([], { ...checklist, signature_required: false, can_final: true }, null, []);
  assert.match(state.detail, /does not require intro/);
  assert.equal(deliveryWorkflow([], checklist, null, [job("stopping")]).title, "Stopping render");
  for (const status of ["failed", "cancelled", "interrupted"]) assert.match(deliveryWorkflow([], checklist, null, [job(status)]).notice!, new RegExp(status));
});
