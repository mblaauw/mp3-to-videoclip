import assert from "node:assert/strict";
import { test } from "node:test";
import { clock, progressShare } from "../src/images/clipJobs.ts";

test("the ring fills by the clock and stops short of done, since only the provider knows", () => {
  assert.equal(progressShare(0, 70), 0);
  assert.equal(progressShare(35, 70), 0.5);
  assert.equal(progressShare(140, 70), 0.95);
  assert.equal(progressShare(10, null), null);
  assert.equal(progressShare(10, 0), null);
});

test("seconds read as a clock", () => {
  assert.equal(clock(70), "1:10");
  assert.equal(clock(4.4), "0:04");
});
