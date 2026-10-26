// Edit-owned primitives shared by the MP4 renderer and the Studio Player.
import assert from "node:assert/strict";
import {mkdtempSync, mkdirSync} from "node:fs";
import {tmpdir} from "node:os";
import path from "node:path";
import test from "node:test";

import {
  accentState,
  allocateSpans,
  editTransitionStyle,
  flashViolations,
  gradeStyle,
  splitLayout,
  textAnimationStyle,
  validateEditShot,
} from "../src/timing.mjs";
import {validateBaseInput, validateRequest} from "../src/request.mjs";

const shot = (id, start, duration, edit = {}) => ({
  id,
  start_frame: start,
  duration_frames: duration,
  image: `${id}.png`,
  edit: {
    shot_id: id,
    start_frame: start,
    duration_frames: duration,
    motion: {type: "hold"},
    transition_in: {type: "cut", frames: 0},
    ...edit,
  },
});

test("an edit transition owns the handle of the shot before it", () => {
  const {spans, totalFrames} = allocateSpans([
    shot("a", 0, 24),
    shot("b", 24, 24, {
      transition_in: {type: "whip_pan", frames: 6, direction: "left", reason: "chorus"},
    }),
  ]);
  assert.equal(totalFrames, 48);
  assert.equal(spans[0].handle, 6, "the incoming edit transition extends the outgoing plate");
  assert.equal(spans[0].handleEnd, 30);
  assert.equal(spans[1].handle, 0);
});

test("edit validation rejects a transition without handles", () => {
  assert.throws(
    () =>
      validateEditShot(
        {
          shot_id: "a",
          start_frame: 0,
          duration_frames: 24,
          motion: {type: "hold"},
          transition_in: {type: "dip_to_black", frames: 0},
        },
        {id: "a", start_frame: 0, duration_frames: 24},
      ),
    /at least one handle frame/,
  );
});

test("every edit transition is a pure reveal with a bounded visual", () => {
  const cut = editTransitionStyle({type: "cut", frames: 0}, 0.5);
  assert.equal(cut.opacity, 1);
  assert.equal(cut.transform, null);

  const fade = editTransitionStyle({type: "fade", frames: 6}, 0.5);
  assert.equal(fade.kind, "fade");
  assert.ok(fade.opacity > 0 && fade.opacity < 1);

  const wipe = editTransitionStyle({type: "wipe_right", frames: 6}, 0.5);
  assert.match(wipe.clipPath, /inset/);

  const black = editTransitionStyle({type: "dip_to_black", frames: 6}, 0.5);
  assert.ok(black.black > 0.9, "midpoint is black");
  assert.equal(black.white, 0);

  const white = editTransitionStyle({type: "dip_to_white", frames: 6}, 0.5);
  assert.ok(white.white > 0.9);

  const whip = editTransitionStyle(
    {type: "whip_pan", frames: 6, direction: "left"},
    0.25,
  );
  assert.match(whip.transform, /translateX/);
  assert.match(whip.filter, /blur/);

  const push = editTransitionStyle({type: "push", frames: 6}, 0.25);
  assert.match(push.transform, /scale/);

  const slide = editTransitionStyle(
    {type: "slide", frames: 6, direction: "up"},
    0.25,
  );
  assert.match(slide.transform, /translateY/);
});

test("accents punch, flash and leak on the absolute frame only", () => {
  const accents = [
    {frame: 10, type: "punch_in", amount: 1.05, duration_frames: 4},
    {frame: 10, type: "flash", duration_frames: 2},
    {frame: 20, type: "light_leak", duration_frames: 6},
  ];
  const atHit = accentState(accents, 10);
  assert.ok(atHit.punch > 1);
  assert.equal(atHit.flash, 1);
  const after = accentState(accents, 14);
  assert.equal(after.punch, 1);
  assert.equal(after.flash, 0);
  const leak = accentState(accents, 21);
  assert.ok(leak.leak > 0);
  assert.equal(leak.flash, 0);
});

test("grade presets interpolate and slider overrides win", () => {
  const warm = gradeStyle({preset: "warm-night", strength: 1});
  assert.match(warm.filter, /saturate/);
  assert.ok(warm.vignette > 0);
  assert.match(warm.tint, /rgba/);

  const mono = gradeStyle({preset: "monochrome", strength: 1});
  assert.match(mono.filter, /grayscale/);

  const overridden = gradeStyle({
    preset: "neutral",
    strength: 1,
    overrides: {brightness: 1.05},
  });
  assert.match(overridden.filter, /brightness\(1.05\)/);
  assert.equal(overridden.vignette, 0);
});

test("text animation presets cover fade, type-on, slide, pop and kinetic words", () => {
  for (const animation of ["fade", "type_on", "slide_up", "pop", "kinetic_words"]) {
    const value = textAnimationStyle(animation, 0.25, 1, 3);
    assert.ok(value.opacity >= 0 && value.opacity <= 1, animation);
    assert.ok(value.reveal >= 0 && value.reveal <= 1, animation);
  }
  assert.ok(textAnimationStyle("type_on", 0.1).reveal < 0.5);
  assert.match(textAnimationStyle("slide_up", 0.1).transform, /translateY/);
  assert.match(textAnimationStyle("pop", 0.1).transform, /scale/);
});

test("split layouts are normalized, bounded pane rectangles", () => {
  const row = splitLayout(2, "row");
  assert.deepEqual(row, [
    {left: 0, top: 0, width: 0.5, height: 1},
    {left: 0.5, top: 0, width: 0.5, height: 1},
  ]);
  const column = splitLayout(2, "column");
  assert.equal(column[0].height, 0.5);
  assert.equal(column[1].top, 0.5);
  const grid = splitLayout(3, "grid");
  assert.equal(grid.length, 3);
  for (const rect of grid) {
    assert.ok(rect.left >= 0 && rect.top >= 0);
    assert.ok(rect.left + rect.width <= 1);
    assert.ok(rect.top + rect.height <= 1);
  }
  assert.throws(() => splitLayout(4, "row"), /two or three/);
});

test("the flash rule is exactly three in any one second", () => {
  const flashes = (frames) => [
    shot("a", 0, 48, {
      accents: frames.map((frame) => ({frame, type: "flash", duration_frames: 2})),
    }),
  ];
  assert.equal(flashViolations(flashes([0, 6, 12]), 24).length, 0);
  assert.ok(flashViolations(flashes([0, 6, 12, 18]), 24).length > 0);
  assert.equal(flashViolations(flashes([0, 23, 24, 30]), 24).length, 0);
});

test("the renderer request refuses four flashes in one second", () => {
  const root = mkdtempSync(path.join(tmpdir(), "primitives-"));
  const assets = path.join(root, "assets");
  mkdirSync(assets);
  const input = {
    shots: [
      shot("a", 0, 48, {
        accents: [0, 6, 12, 18].map((frame) => ({
          frame,
          type: "flash",
          duration_frames: 2,
        })),
      }),
    ],
  };
  assert.throws(() => validateBaseInput(input, 24), /flash limit/);
  assert.throws(
    () =>
      validateRequest({
        kind: "base",
        output: path.join(root, "film.mp4"),
        assetRoot: assets,
        width: 192,
        height: 108,
        fps: 24,
        frames: 48,
        input,
      }),
    /flash limit/,
  );
});
