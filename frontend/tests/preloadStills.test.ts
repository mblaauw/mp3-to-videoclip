import assert from "node:assert/strict";
import test from "node:test";
import { stillSources } from "../src/film/preloadStills.ts";

const shots = [
  { start_frame: 0, src: "a" },
  { start_frame: 100, src: "b" },
  { start_frame: 200, src: "c", split_panes: [{ src: "d" }, { src: "a" }] },
  { start_frame: 300, src: null },
];

test("the stills nearest the playhead load first, each once", () => {
  assert.deepEqual(stillSources(shots, 190), ["c", "d", "a", "b"]);
  assert.deepEqual(stillSources(shots, 0), ["a", "b", "c", "d"]);
});

test("a shot with no still is skipped", () => {
  assert.deepEqual(stillSources([{ start_frame: 0, src: null }], 0), []);
});
