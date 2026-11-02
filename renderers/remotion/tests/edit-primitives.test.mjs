// Edit-owned primitives shared by the MP4 renderer and the Studio Player.
import assert from "node:assert/strict";
import {mkdtempSync, mkdirSync} from "node:fs";
import {tmpdir} from "node:os";
import path from "node:path";
import test from "node:test";

import * as timing from "../src/timing.mjs";
import {
  accentState,
  activeCrop,
  allocateSpans,
  cameraAtFrame,
  editTransitionStyle,
  flashViolations,
  gradeStyle,
  lookState,
  parallaxState,
  clipFrame,
  validateClip,
  validateDepthLayers,
  splitLayout,
  textAnimationStyle,
  validateEditShot,
  validateGrade,
} from "../src/timing.mjs";
import {validateBaseInput, validateChunks, validateRequest} from "../src/request.mjs";

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
    [{frame: 48, zoom: 1.2}],
    [{frame: 10, zoom: 1.7}],
    [{frame: 20, zoom: 1.2}, {frame: 10, zoom: 1.2}],
    [{frame: 10, zoom: 1.2, x: 2}],
  ]) {
    assert.throws(() => validateEditShot(withCrops(bad).edit, withCrops([])));
  }
});

test("chunks are ordered, inside the film and local", () => {
  const chunk = (start, frames, output = `/tmp/c${start}.mp4`) => ({start, frames, output});
  assert.deepEqual(validateChunks([chunk(0, 10), chunk(20, 5)], 25), [chunk(0, 10), chunk(20, 5)]);
  assert.throws(() => validateChunks([], 25), /non-empty/);
  assert.throws(() => validateChunks([chunk(0, 10), chunk(9, 5)], 25), /before the previous/);
  assert.throws(() => validateChunks([chunk(20, 6)], 25), /past the film/);
  assert.throws(() => validateChunks([chunk(0, 0)], 25), /frames/);
  assert.throws(() => validateChunks([chunk(0, 5, "c.mp4")], 25), /absolute/);
  assert.throws(() => validateChunks([chunk(0, 5, "/tmp/c.mov")], 25), /\.mp4/);
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


test("a crop may reframe a shot from its first frame, never before it", () => {
  assert.doesNotThrow(() => timing.validateEditCrops([{frame: 24, zoom: 1.5}], 24, 24, "s001"));
  assert.throws(() => timing.validateEditCrops([{frame: 23, zoom: 1.5}], 24, 24, "s001"));
});

test("brand text styles are accepted and a colour must be a hex value", () => {
  const item = {id: "t", style: "logotype", text: "Name", in_frame: 0, out_frame: 24, color: "#D9B36C"};
  assert.doesNotThrow(() => timing.validateEditText(item));
  assert.throws(() => timing.validateEditText({...item, color: "gold"}));
});


test("fade_in rises and then stays, so words hold through the last frame", () => {
  assert.equal(timing.textAnimationStyle("fade_in", 0).opacity, 0);
  assert.equal(timing.textAnimationStyle("fade_in", 0.5).opacity, 1);
  assert.equal(timing.textAnimationStyle("fade_in", 1).opacity, 1);
});

test("the grain is a large tile, turned and mirrored per frame, the same on any machine", () => {
  const look = {grain: 0.5, weave: 0, drift: 0};
  const seen = new Set();
  for (let frame = 0; frame < 200; frame += 1) {
    const state = lookState(look, frame, "s001", 1920, 1080, 24);
    assert.match(state.grainTransform, /^rotate\((0|90|180|270)deg\) scaleX\(-?1\)$/);
    assert.ok(state.grainSpan >= Math.hypot(1920, 1080));
    seen.add(state.grainTransform);
  }
  assert.equal(seen.size, 8);
  assert.deepEqual(lookState(look, 7, "s001", 1920, 1080, 24), lookState(look, 7, "s001", 1920, 1080, 24));
});

test("parallax is off at zero, and the far layer never moves", () => {
  assert.equal(parallaxState(0, "push_in", 10, 100, "s001", 1920, 1080, 24), null);
  assert.equal(parallaxState(undefined, "hold", 10, 100, "s001", 1920, 1080, 24), null);
  for (const motion of ["hold", "push_in", "pull_back", "pan_left", "pan_right"]) {
    const state = parallaxState(1, motion, 40, 100, "s001", 1920, 1080, 24);
    assert.equal(Math.abs(state.far.x), 0, motion);
    assert.equal(state.far.scale, 1, motion);
  }
});

test("a push-in is a dolly: the near layer grows more than the mid, from nothing", () => {
  const start = parallaxState(1, "push_in", 0, 100, "s001", 1920, 1080, 24);
  assert.equal(start.near.scale, 1);
  const end = parallaxState(1, "push_in", 99, 100, "s001", 1920, 1080, 24);
  assert.ok(end.near.scale > end.mid.scale && end.mid.scale > end.far.scale);
  assert.ok(end.near.scale < 1.03, "small by design");
});

test("a pan slides the layers against each other, and each stays within its amplitude", () => {
  const state = parallaxState(0.5, "pan_right", 0, 100, "s001", 1920, 1080, 24);
  assert.ok(Math.abs(state.near.x) > Math.abs(state.mid.x));
  assert.ok(Math.abs(state.near.x) <= 0.5 * 0.012 * 1080 + 1e-6);
});

test("parallax is the same on any machine and differs between shots", () => {
  const one = parallaxState(1, "hold", 30, 100, "s001", 1920, 1080, 24);
  assert.deepEqual(one, parallaxState(1, "hold", 30, 100, "s001", 1920, 1080, 24));
  assert.notDeepEqual(one, parallaxState(1, "hold", 30, 100, "s002", 1920, 1080, 24));
});

test("a depth amount is validated with the rest of the look", () => {
  assert.doesNotThrow(() => validateGrade({look: {depth: 0.5}}));
  assert.throws(() => validateGrade({look: {depth: 2}}));
  assert.throws(() => validateGrade({typeface: "comic"}));
});

test("a depth entry needs all three layers", () => {
  assert.doesNotThrow(() => validateDepthLayers({far: "a", mid: "b", near: "c"}, "s"));
  assert.doesNotThrow(() => validateDepthLayers(undefined, "s"));
  assert.throws(() => validateDepthLayers({far: "a", mid: "b"}, "s"));
});

test("the new curves start at 0, end at 1 and differ where they should", async () => {
  const {ease, rampedTravel, editCamera, textSafeBox, lookState, kineticWordStyle} = await import("../src/timing.mjs");
  for (const name of ["ease_in", "ease_out", "snap"]) {
    assert.equal(ease(0, name), 0);
    assert.equal(ease(1, name), 1);
  }
  assert.ok(ease(0.5, "ease_in") < 0.5 && ease(0.5, "ease_out") > 0.5);
  assert.ok(ease(0.2, "snap") > ease(0.2, "ease_out"));
  // With a ramp, the move reaches its share on the frame, and still finishes.
  assert.equal(rampedTravel(0.25, "smoothstep", 0.25, 0.7), 0.7);
  assert.equal(rampedTravel(1, "smoothstep", 0.25, 0.7), 1);
  assert.ok(rampedTravel(0.5, "smoothstep", 0.25, 0.7) > 0.7);
  const motion = {type: "push_in", from: 1, to: 1.1, ramp: {frame: 12, share: 0.5}};
  assert.ok(Math.abs(editCamera(motion, 0.25, 0.25).zoom - 1.05) < 1e-9);
  // A portrait frame pushes text in from the top and bottom; a landscape one leaves it.
  assert.deepEqual(textSafeBox({top: 10}, 1920, 1080), {top: 10});
  assert.equal(textSafeBox({bottom: 10}, 1080, 1920).bottom, 1920 * 0.12);
  assert.equal(lookState({grain: 0}, 1, "s", 1920, 1080, 24), null);
  const look = lookState({haze: 0.5, flare: 1}, 1, "s", 1920, 1080, 24);
  assert.ok(look.haze > 0 && look.flare > 0 && look.flareX > 0 && look.flareX < 1);
  assert.equal(kineticWordStyle(10, 10, 100, 24).opacity, 0);
  assert.ok(kineticWordStyle(20, 10, 100, 24).opacity > 0.9);
});

test("an impulse kicks, dies away and stays within the frame", () => {
  const accents = [{frame: 10, type: "impulse", amount: 1.1, duration_frames: 8, direction: "left"}];
  assert.equal(accentState(accents, 9).punch, 1);
  const first = accentState(accents, 10);
  assert.ok(first.punch > 1.09);
  assert.equal(first.shiftX, -0.5);
  assert.equal(accentState(accents, 18).punch, 1);
  assert.equal(accentState(accents, 18).shiftX, 0);
  assert.throws(() => accentState([{...accents[0], amount: 1.15}], 10), /impulse/);
  assert.throws(() => accentState([{...accents[0], duration_frames: 20}], 10), /impulse/);
});

test("a clip shorter than its shot holds its last frame and is never stretched", () => {
  const clip = {file: "a.mp4", frames: 48, fps: 24};
  assert.deepEqual(clipFrame(clip, 0, 24), {frame: 0, held: false, last: 47});
  assert.equal(clipFrame(clip, 46, 24).frame, 46);
  assert.equal(clipFrame(clip, 46, 24).held, false);
  assert.equal(clipFrame(clip, 47, 24).held, true);
  assert.equal(clipFrame(clip, 500, 24).frame, 47);
  // The same two seconds at another film rate.
  assert.equal(clipFrame(clip, 500, 30).frame, 59);
});

test("a clip that is not a flat mp4 with its frames is refused", () => {
  validateClip(undefined, "shot a");
  validateClip({file: "abc.mp4", frames: 48, fps: 24}, "shot a");
  assert.throws(() => validateClip({file: "../abc.mp4", frames: 48, fps: 24}, "shot a"));
  assert.throws(() => validateClip({file: "abc.mov", frames: 48, fps: 24}, "shot a"));
  assert.throws(() => validateClip({file: "abc.mp4", frames: 0, fps: 24}, "shot a"));
  assert.throws(() => validateClip({file: "abc.mp4", frames: 48, fps: 0}, "shot a"));
});
