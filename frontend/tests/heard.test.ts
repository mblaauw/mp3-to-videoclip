import assert from "node:assert/strict";
import { test } from "node:test";
import { coverageShare, heardWords, markHeard, unsent } from "../src/film/heard.ts";

const loud = { muted: false, volume: 0.8, paused: false };

test("a second counts only when it played with the sound on", () => {
  const heard = new Set<number>();
  assert.equal(markHeard(heard, 12.7, loud), true);
  assert.equal(markHeard(heard, 12.9, { ...loud, muted: true }), false);
  assert.equal(markHeard(heard, 13.1, { ...loud, volume: 0.02 }), false);
  assert.equal(markHeard(heard, 14, { ...loud, paused: true }), false);
  assert.equal(markHeard(heard, Number.NaN, loud), false);
  assert.deepEqual([...heard], [12]);
});

test("only what was not reported is sent, in order", () => {
  const heard = new Set([5, 2, 9]);
  const sent = new Set([2]);
  assert.deepEqual(unsent(heard, sent), [5, 9]);
});

test("the words follow the share", () => {
  assert.equal(coverageShare(0, 0), 0);
  assert.equal(coverageShare(99, 100), 0.99);
  assert.equal(heardWords(0, 0), "Not heard yet.");
  assert.equal(heardWords(40, 100), "40 of 100 seconds heard with the sound on.");
  assert.equal(heardWords(99, 100), "Heard start to finish with the sound on.");
});
