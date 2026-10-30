import assert from "node:assert/strict";
import test from "node:test";
import type { EditPayload } from "../src/api.ts";
import { joinMaxFrames, setEditMotion, setJoins, SET_BY_HAND } from "../src/film/editTimeline.ts";
import { joinSelected, selectJoin, stepJoin } from "../src/film/selection.ts";

test("a click picks one join; a modified click adds and removes", () => {
  let current = selectJoin(null, "s002", false);
  assert.deepEqual(current, { kind: "join", ids: ["s002"] });
  current = selectJoin(current, "s005", true);
  assert.deepEqual(current, { kind: "join", ids: ["s002", "s005"] });
  assert.ok(joinSelected(current, "s005"));
  current = selectJoin(current, "s002", true);
  current = selectJoin(current, "s005", true);
  assert.equal(current, null);
  assert.deepEqual(selectJoin({ kind: "shot", id: "s009" }, "s002", true), { kind: "join", ids: ["s002"] });
});

test("stepping finds the next and previous join around the playhead", () => {
  const shots = [
    { id: "a", start_frame: 0 },
    { id: "b", start_frame: 48 },
    { id: "c", start_frame: 96 },
  ];
  assert.equal(stepJoin(shots, 0, 1), "b");
  assert.equal(stepJoin(shots, 47, 1), "c", "already at b's last frame before the seam");
  assert.equal(stepJoin(shots, 96, -1), "b");
  assert.equal(stepJoin(shots, 10, -1), null, "the first shot has no join");
  assert.equal(stepJoin(shots, 95, 1), null);
});

function edit(): EditPayload {
  const shot = (id: string, start: number, frames: number) => ({
    shot_id: id,
    start_frame: start,
    duration_frames: frames,
    motion: { type: "hold", from: 1, to: 1, easing: "smoothstep", anchor: [0.5, 0.5] },
    transition_in: { type: "cut", frames: 0 },
    accents: [],
    text: [],
  });
  return {
    sections: [],
    grade: { preset: "neutral", strength: 1 },
    shots: [shot("a", 0, 96), shot("b", 96, 20), shot("c", 116, 200), shot("d", 316, 200)],
  } as unknown as EditPayload;
}

test("a join can't outlast either shot or the 48-frame limit", () => {
  assert.equal(joinMaxFrames(edit(), ["b"]), 19);
  assert.equal(joinMaxFrames(edit(), ["c"]), 19);
  assert.equal(joinMaxFrames(edit(), ["d"]), 48);
  assert.equal(joinMaxFrames(edit(), ["b", "d"]), 19, "bulk uses the tightest join");
});

test("joins set by hand carry a reason, keep an existing one and clear on a cut", () => {
  const next = setJoins(edit(), ["c", "d"], "fade", 12);
  const c = next.shots[2].transition_in;
  assert.deepEqual([c.type, c.frames, c.reason], ["fade", 12, SET_BY_HAND]);
  const kept = setJoins(
    { ...next, shots: next.shots.map((s) => (s.shot_id === "c" ? { ...s, transition_in: { ...s.transition_in, reason: "lift" } } : s)) },
    ["c"],
    "push",
    6,
  );
  assert.equal(kept.shots[2].transition_in.reason, "lift");
  const cut = setJoins(next, ["c"], "cut", 0).shots[2].transition_in;
  assert.deepEqual([cut.type, cut.frames, cut.reason], ["cut", 0, ""]);
});

test("camera moves match the seeded scales, which the model validates", () => {
  const scale = (type: Parameters<typeof setEditMotion>[2]) => {
    const { from, to, reason } = setEditMotion(edit(), "a", type).shots[0].motion;
    return [from, to, reason];
  };
  assert.deepEqual(scale("hold"), [1, 1, SET_BY_HAND]);
  assert.deepEqual(scale("push_in"), [1, 1.08, SET_BY_HAND]);
  assert.deepEqual(scale("pull_back"), [1.08, 1, SET_BY_HAND]);
  assert.deepEqual(scale("pan_left"), [1.08, 1.08, SET_BY_HAND]);
});
