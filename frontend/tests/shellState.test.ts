import assert from "node:assert/strict";
import { test } from "node:test";
import type { ProjectSummary } from "../src/api.ts";
import { derivedStates, type ApprovalMap, type ImageFacts } from "../src/shell/shellState.ts";

const project = {
  stage_states: { track: "done", story: "done", storyboard: "done", images: "changed", film: "not_ready" },
  sound_cues: 0,
  sound_sounding: 0,
  released: false,
} as unknown as ProjectSummary;

const approvals = (overrides: ApprovalMap = {}): ApprovalMap => ({
  brief: { state: "approved" },
  storyboard: { state: "approved" },
  proof: { state: "approved" },
  stills: { state: "stale", expected_hash: "s" },
  ...overrides,
});

const images = {
  proof_total: 3,
  proof_kept: 3,
  proof_missing_ids: [],
  proof_stale_ids: [],
  total: 25,
  selected: 25,
  kept: 25,
  stale: 0,
  missing: 0,
  missing_ids: [],
  reserve_usd: "0.05",
} as ImageFacts;

test("a stale set with every picture kept is only the cut moving, which Film signs off", () => {
  const states = derivedStates(project, approvals(), images);
  assert.equal(states.images, "done");
  assert.equal(states.film, "you");
});

test("a stale style check is not the cut moving: Images asks for it again first", () => {
  const states = derivedStates(project, approvals({ proof: { state: "stale", expected_hash: "p" } }), images);
  assert.equal(states.images, "changed");
  assert.equal(states.film, "not_ready");
});
