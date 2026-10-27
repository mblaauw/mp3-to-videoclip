import assert from "node:assert/strict";
import test from "node:test";
import type { EditPayload, Storyboard } from "../src/api.ts";
import {
  applyEditBoard,
  editBoundaryLimits,
  moveEditBoundary,
  setEditTransition,
} from "../src/film/editTimeline.ts";

function edit(): EditPayload {
  return {
    schema_version: 1,
    sections: [],
    grade: { preset: "neutral", strength: 1 },
    shots: [
      {
        shot_id: "s001",
        start_frame: 0,
        duration_frames: 48,
        motion: { type: "hold", from: 1, to: 1, easing: "linear", anchor: [0.5, 0.5] },
        transition_in: { type: "cut", frames: 0 },
        accents: [{ frame: 30, type: "flash" }],
        text: [{ id: "t1", style: "super", text: "A", in_frame: 4, out_frame: 20, animation: "fade" }],
      },
      {
        shot_id: "s002",
        start_frame: 48,
        duration_frames: 48,
        motion: { type: "hold", from: 1, to: 1, easing: "linear", anchor: [0.5, 0.5] },
        transition_in: { type: "fade", frames: 6, reason: "soften" },
        accents: [{ frame: 60, type: "punch_in" }],
        text: [],
      },
    ],
  };
}

function board(): Storyboard {
  return {
    aspect: "16:9",
    fps: 24,
    total_frames: 96,
    shots: [
      {
        id: "s001",
        start_frame: 0,
        duration_frames: 48,
        kind: "scene",
        purpose: "one",
        message: "",
        camera: "hold",
        dissolve_frames: 0,
        framing: null,
        asset_shot_id: null,
        must_show: [],
        scene_id: null,
      },
      {
        id: "s002",
        start_frame: 48,
        duration_frames: 48,
        kind: "scene",
        purpose: "two",
        message: "",
        camera: "hold",
        dissolve_frames: 0,
        framing: null,
        asset_shot_id: null,
        must_show: [],
        scene_id: null,
      },
    ],
  };
}

test("edit boundaries stay inside timed children and transitions", () => {
  const limits = editBoundaryLimits(edit(), 0);
  assert.equal(limits.low, 31);
  assert.equal(limits.high, 60);
});

test("moving a join resizes both shots and keeps total coverage", () => {
  const moved = moveEditBoundary(edit(), 0, 70);
  assert.equal(moved.shots[0].duration_frames, 60);
  assert.equal(moved.shots[1].start_frame, 60);
  assert.equal(moved.shots[1].duration_frames, 36);
  const total = moved.shots.reduce((sum, shot) => sum + shot.duration_frames, 0);
  assert.equal(total, 96);
});

test("a cut clears frames and reason; a named join keeps a reason", () => {
  const cut = setEditTransition(edit(), "s002", { type: "cut", frames: 12, reason: "old" });
  assert.deepEqual(cut.shots[1].transition_in, {
    type: "cut",
    frames: 0,
    direction: null,
    reason: "",
  });
  const fade = setEditTransition(edit(), "s001", { type: "fade", frames: 4, reason: "open" });
  assert.equal(fade.shots[0].transition_in.frames, 4);
  assert.equal(fade.shots[0].transition_in.reason, "open");
});

test("the effective board follows edit order and spans", () => {
  const moved = moveEditBoundary(edit(), 0, 40);
  const effective = applyEditBoard(board(), moved);
  assert.equal(effective.shots[0].duration_frames, 40);
  assert.equal(effective.shots[1].start_frame, 40);
  assert.equal(effective.shots[1].duration_frames, 56);
  assert.equal(effective.total_frames, 96);
});

test("an impossible boundary leaves the cut untouched", () => {
  const value = edit();
  value.shots[0].accents = [{ frame: 90, type: "flash" }];
  const moved = moveEditBoundary(value, 0, 60);
  assert.equal(moved, value);
});
