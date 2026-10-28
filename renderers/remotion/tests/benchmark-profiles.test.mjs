import assert from "node:assert/strict";
import test from "node:test";
import {benchmarkOptions} from "../src/benchmark-profiles.mjs";

test("default encoder settings and alpha remain unchanged", () => {
  assert.deepEqual(benchmarkOptions(null, "base"), {});
  assert.deepEqual(benchmarkOptions(undefined, "graphics"), {});
});

test("hardware experiment is explicit, required, base-only and bitrate labelled", () => {
  assert.deepEqual(benchmarkOptions("videotoolbox-20m", "base"), {
    hardwareAcceleration: "required", videoBitrate: "20M",
  });
  assert.throws(() => benchmarkOptions("videotoolbox-20m", "graphics"), /base-only/);
  for (const profile of ["auto", "", "videotoolbox", true]) {
    assert.throws(() => benchmarkOptions(profile, "base"), /unknown/);
  }
});
