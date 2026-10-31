// Edit-owned primitives shared by the MP4 renderer and the Studio Player.
import assert from "node:assert/strict";
import {mkdtempSync, mkdirSync} from "node:fs";
import {tmpdir} from "node:os";
import path from "node:path";
import test from "node:test";

import {
  accentState,
  activeCrop,
  allocateSpans,
  cameraAtFrame,
  editTransitionStyle,
  flashViolations,
  gradeStyle,
  lookState,
  splitLayout,
  textAnimationStyle,
  validateEditShot,
  validateGrade,
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
  assert.match(whip.outgoingTransform, /translateX\(-/);
  assert.ok(whip.blurShare > 0);
  assert.equal(editTransitionStyle({type: "fade", frames: 6}, 0.5).blurShare, undefined);

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

test("a crop cut jumps to its framing on its frame and holds it", () => {
  const crops = [
    {frame: 30, zoom: 1.35, x: 0.2, y: 0.7},
    {frame: 60, zoom: 1.1},
  ];
  const span = {
    id: "a",
    duration_frames: 120,
    handle: 0,
    edit: {start_frame: 10, motion: {type: "push_in", from: 1, to: 1.08}, crops},
  };
  assert.ok(cameraAtFrame(span, 19).zoom < 1.08);
  assert.deepEqual(cameraAtFrame(span, 20), {zoom: 1.35, x: 0.2, y: 0.7});
  assert.deepEqual(cameraAtFrame(span, 49), {zoom: 1.35, x: 0.2, y: 0.7});
  assert.deepEqual(cameraAtFrame(span, 50), {zoom: 1.1, x: 0.5, y: 0.5});
  assert.equal(activeCrop(undefined, 10), null);
});

test("crop cuts are validated like the Python model", () => {
  const withCrops = (crops) => shot("a", 0, 48, {crops});
  assert.doesNotThrow(() => validateEditShot(withCrops([{frame: 10, zoom: 1.5}]).edit, withCrops([])));
  for (const bad of [
    [{frame: 0, zoom: 1.2}],
    [{frame: 48, zoom: 1.2}],
    [{frame: 10, zoom: 1.7}],
    [{frame: 20, zoom: 1.2}, {frame: 10, zoom: 1.2}],
    [{frame: 10, zoom: 1.2, x: 2}],
  ]) {
    assert.throws(() => validateEditShot(withCrops(bad).edit, withCrops([])));
  }
});

test("capture is optional and bounded", () => {
  const shots = [{id: "a", image: "a.png", start_frame: 0, duration_frames: 24}];
  assert.doesNotThrow(() => validateBaseInput({shots}, 24));
  assert.doesNotThrow(() => validateBaseInput({shots, capture: {format: "jpeg", quality: 95}}, 24));
  assert.throws(() => validateBaseInput({shots, capture: {format: "webp", quality: 95}}, 24), /format/);
  assert.throws(() => validateBaseInput({shots, capture: {format: "jpeg", quality: 0}}, 24), /quality/);
  assert.throws(() => validateBaseInput({shots, capture: "jpeg"}, 24), /capture/);
});

test("the film look is off unless asked for, and the same frame always looks the same", () => {
  assert.equal(lookState(undefined, 10, "s001", 1920, 1080, 24), null);
  assert.equal(lookState({grain: 0, weave: 0, drift: 0}, 10, "s001", 1920, 1080, 24), null);
  const look = {grain: 0.4, weave: 0.4, drift: 0.4};
  assert.deepEqual(lookState(look, 10, "s003", 1920, 1080, 24), lookState(look, 10, "s003", 1920, 1080, 24));
  assert.notDeepEqual(lookState(look, 10, "s003", 1920, 1080, 24), lookState(look, 11, "s003", 1920, 1080, 24));
  assert.notEqual(
    lookState(look, 10, "s003", 1920, 1080, 24).transform,
    lookState(look, 10, "s004", 1920, 1080, 24).transform,
  );
  // Two shots shouldn't share a grain pattern frame for frame.
  const a = lookState(look, 10, "s003", 1920, 1080, 24);
  const b = lookState(look, 10, "s004", 1920, 1080, 24);
  assert.notDeepEqual([a.grainX, a.grainY], [b.grainX, b.grainY]);
});

test("the film look's overscan always covers how far it moves", () => {
  const width = 1920;
  const height = 1080;
  for (let frame = 0; frame < 2000; frame += 7) {
    const {transform} = lookState({weave: 1, drift: 1}, frame, "s002", width, height, 24);
    const [, x, y, , scale] = transform.match(
      /translate\((-?[\d.]+)px, (-?[\d.]+)px\) rotate\((-?[\d.]+)deg\) scale\(([\d.]+)\)/,
    );
    assert.ok(Math.abs(Number(x)) <= ((Number(scale) - 1) * width) / 2 + 0.01);
    assert.ok(Math.abs(Number(y)) <= ((Number(scale) - 1) * height) / 2 + 0.01);
  }
});

test("grade look values are bounded", () => {
  assert.doesNotThrow(() => validateGrade({preset: "neutral", look: {grain: 1, drift: 0}}));
  assert.throws(() => validateGrade({preset: "neutral", look: {grain: 2}}));
  assert.throws(() => validateGrade({preset: "neutral", look: "heavy"}));
});
