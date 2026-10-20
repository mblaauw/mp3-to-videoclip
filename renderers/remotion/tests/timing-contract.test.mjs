// Pure timing/frame contract tests for the renderer.
//
// These are the invariants the Remotion compositions rely on: shot spans are
// contiguous and never shortened by a dissolve handle, the camera is a pure
// function of the frame and stays inside the legacy zoom range, a graphics part
// resolves its own frame window, and every graphic fades from and back to zero.
// No browser, no ffmpeg, no filesystem.
import assert from "node:assert/strict";
import test from "node:test";

import {
  ZOOM_RANGE,
  allocateSpans,
  cameraAtFrame,
  graphicsAlpha,
  graphicsFadeSeconds,
  partIsVisible,
  validateGraphicsPart,
} from "../src/timing.mjs";

test("allocateSpans keeps the timeline contiguous and never shortens it", () => {
  const {spans, totalFrames} = allocateSpans([
    {id: "a", image: "a.png", start_frame: 0, duration_frames: 6, dissolve_frames: 2, camera: "hold"},
    {id: "b", image: "b.png", start_frame: 6, duration_frames: 4, camera: "hold"},
  ]);
  assert.equal(totalFrames, 10, "a dissolve handle must not extend the film");
  assert.deepEqual(
    spans.map((span) => [span.index, span.id, span.start_frame, span.duration_frames, span.handle, span.handleEnd]),
    [
      [0, "a", 0, 6, 2, 8],
      [1, "b", 6, 4, 0, 10],
    ],
  );
});

test("allocateSpans rejects a non-contiguous timeline, duplicate ids and a trailing dissolve", () => {
  const shot = (overrides) => ({id: "a", image: "a.png", start_frame: 0, duration_frames: 4, ...overrides});
  assert.throws(() => allocateSpans([shot({}), shot({id: "b", start_frame: 5})]), /contiguous/);
  assert.throws(() => allocateSpans([shot({}), shot({id: "a", start_frame: 4})]), /not unique/);
  assert.throws(() => allocateSpans([shot({dissolve_frames: 2})]), /cannot dissolve/);
  assert.throws(() => allocateSpans([shot({image: "../escape.png"})]), /path separator/);
});

test("cameraAtFrame is a pure frame function clamped to the plate window", () => {
  const span = {id: "s", duration_frames: 5, handle: 0, camera: "zoom_in"};
  assert.deepEqual(cameraAtFrame(span, 0), {zoom: 1, x: 0.5, y: 0.5});
  assert.equal(cameraAtFrame(span, 4).zoom, 1 + ZOOM_RANGE);
  assert.deepEqual(cameraAtFrame(span, 99), cameraAtFrame(span, 4), "over-run frames are clamped");
  assert.deepEqual(cameraAtFrame(span, -5), cameraAtFrame(span, 0), "negative frames are clamped");
  assert.deepEqual(cameraAtFrame(span, 2), cameraAtFrame(span, 2), "the same frame replays identically");
  const pan = {id: "p", duration_frames: 3, handle: 0, camera: "pan_left"};
  assert.equal(cameraAtFrame(pan, 1).zoom, 1 + ZOOM_RANGE);
});

test("validateGraphicsPart resolves the part's own frame window", () => {
  const part = {
    kind: "caption",
    id: "c1",
    frames: 12,
    caption: {id: "c1", style: "caption", text: "hello"},
  };
  assert.equal(validateGraphicsPart(part, 12).frames, 12);
  assert.throws(() => validateGraphicsPart(part, 10), /does not match/);
  assert.throws(() => validateGraphicsPart({kind: "sfx"}, 12), /unsupported graphics part kind/);
  assert.throws(
    () => validateGraphicsPart({kind: "caption", caption: {id: "c1", style: "burst", text: "x"}}, 12),
    /only caption is drawn/,
  );
});

test("graphics fades in from zero and back to zero for every kind", () => {
  assert.equal(graphicsFadeSeconds("identity", 20), 0.6);
  assert.equal(graphicsFadeSeconds("caption", 4), 0.25);
  assert.equal(graphicsFadeSeconds("card", 100), 0.5);
  assert.equal(graphicsAlpha("card", 0, 10), 0);
  assert.equal(graphicsAlpha("card", 5, 10), 1);
  assert.equal(graphicsAlpha("card", 10, 10), 0);
  assert.equal(partIsVisible("card", 5, 10), true);
  assert.equal(partIsVisible("card", 10, 10), false);
});
