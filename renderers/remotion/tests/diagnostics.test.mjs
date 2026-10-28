import assert from "node:assert/strict";
import test from "node:test";
import {createDiagnostics} from "../src/diagnostics.mjs";

test("observers preserve args identity and only report observed encoder/capture", () => {
  const d = createDiagnostics();
  const args = ["-f", "image2pipe", "-c:v", "png", "-i", "-", "-c:v", "libx264"];
  assert.equal(d.ffmpegOverride({type: "pre-stitcher", args}), args);
  assert.deepEqual(args, ["-f", "image2pipe", "-c:v", "png", "-i", "-", "-c:v", "libx264"]);
  assert.deepEqual(d.data.ffmpeg[0].video_encoders, ["libx264"]);
  assert.equal(d.data.ffmpeg[0].capture_mode, "image2pipe");
  assert.match(d.data.fallback_reason, /unavailable/);
});
test("actual completion milliseconds retained; missing encoded time stays unknown", () => {
  const d = createDiagnostics();
  d.onStart({resolvedConcurrency: 2, parallelEncoding: true});
  d.onProgress({renderedDoneIn: 1234, encodedDoneIn: null});
  d.onProgress({renderedDoneIn: null, encodedDoneIn: NaN});
  assert.equal(d.data.renderedDoneIn, 1234);
  assert.equal(d.data.encodedDoneIn, null);
  assert.equal(d.data.parallelEncoding, true);
  d.onProgress({encodedDoneIn: 456});
  assert.equal(d.data.encodedDoneIn, 456);
  assert.match(d.data.timing_note, /not additive/);
});
