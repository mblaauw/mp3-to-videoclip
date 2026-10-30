// The title layer draws the one planned window that covers the current frame.
import assert from "node:assert/strict";
import test from "node:test";

import {titleWindowAt} from "../src/timing.mjs";

const windows = [
  {kind: "intro", id: "intro", start_frame: 0, frames: 600},
  {kind: "caption", id: "c", start_frame: 1440, frames: 84},
  {kind: "card", id: "card-01", start_frame: 4795, frames: 144},
  {kind: "lockup", id: "lockup", start_frame: 4939, frames: 816},
];

test("a window starts on its first frame and ends before start + frames", () => {
  assert.equal(titleWindowAt(windows, 0).id, "intro");
  assert.equal(titleWindowAt(windows, 599).id, "intro");
  assert.equal(titleWindowAt(windows, 600), null);
  assert.equal(titleWindowAt(windows, 1439), null);
  assert.equal(titleWindowAt(windows, 1440).id, "c");
  assert.equal(titleWindowAt(windows, 1523).id, "c");
  assert.equal(titleWindowAt(windows, 1524), null);
});

test("adjacent credit windows hand over on the exact frame", () => {
  assert.equal(titleWindowAt(windows, 4938).id, "card-01");
  assert.equal(titleWindowAt(windows, 4939).id, "lockup");
  assert.equal(titleWindowAt(windows, 5754).id, "lockup");
  assert.equal(titleWindowAt(windows, 5755), null);
});

test("no plan draws nothing", () => {
  assert.equal(titleWindowAt([], 10), null);
});
