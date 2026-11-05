import assert from "node:assert/strict";
import { test } from "node:test";
import { bandFor, chosen, describeAnchor, freshId, soundState } from "../src/sound/cueBands.ts";

test("a band is a slice of the ruler and never leaves it", () => {
  assert.deepEqual(bandFor({ start_seconds: 30, end_seconds: 60 }, 120), { left: 25, width: 25 });
  assert.deepEqual(bandFor({ start_seconds: 100, end_seconds: 500 }, 120), {
    left: (100 / 120) * 100,
    width: (20 / 120) * 100,
  });
  assert.equal(bandFor({ start_seconds: null, end_seconds: 5 }, 120), null);
  assert.equal(bandFor({ start_seconds: 5, end_seconds: 5 }, 120)?.width, 0.5);
});

test("the stage's word follows the cues that sound", () => {
  assert.equal(soundState(0, 0), "not_ready");
  assert.equal(soundState(3, 1), "you");
  assert.equal(soundState(3, 3), "done");
});

test("ids are plain words and never collide", () => {
  assert.equal(freshId("music", []), "bed");
  assert.equal(freshId("music", ["bed"]), "bed-2");
  assert.equal(freshId("effect", ["hit", "hit-2"]), "hit-3");
});

test("the chosen version is the one that plays", () => {
  const versions = [
    { version: 1, path: "a", sha256: "x", source: "upload" as const, seconds: 2 },
    { version: 2, path: "b", sha256: "y", source: "generated" as const, seconds: 3 },
  ];
  assert.equal(chosen({ versions, selected: 2 })?.path, "b");
  assert.equal(chosen({ versions, selected: null }), null);
});

test("anchors read as a line, a time or the end", () => {
  assert.equal(describeAnchor({ line: "l003" }, 24), "l003");
  assert.equal(describeAnchor({ frame: 48 }, 24), "2.0 s");
  assert.equal(describeAnchor({ frame: -1 }, 24), "end");
});
