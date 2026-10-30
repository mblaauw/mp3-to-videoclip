import assert from "node:assert/strict";
import { test } from "node:test";
import type { LyricLine } from "../src/api";
import { applyTap, lineAt, nextToTap, nudge, toSave, undoTap } from "../src/track/lyricTiming.ts";

const line = (index: number, text: string, start: number | null = null): LyricLine => ({
  index,
  text,
  tag: text.startsWith("[") ? text.slice(1, -1) : null,
  start,
  end: null,
  source: start === null ? null : "tapped",
});

const song = () => [line(0, "[Hook]"), line(1, "one"), line(2, "two"), line(3, "[Break]"), line(4, "three")];

test("a tap skips headings and goes to the next untimed line", () => {
  const lines = applyTap(song(), 3);
  assert.equal(lines[0].start, null);
  assert.equal(lines[1].start, 3);
  assert.equal(nextToTap(lines), 2);
});

test("a late-registered tap can't land before the line above it", () => {
  const lines = applyTap(applyTap(song(), 5), 4);
  assert.equal(lines[2].start, 5);
});

test("undo removes the latest time and says where it was", () => {
  const result = undoTap(applyTap(applyTap(song(), 3), 6));
  assert.equal(result?.time, 6);
  assert.equal(result?.lines[2].start, null);
  assert.equal(result?.lines[1].start, 3);
  assert.equal(undoTap(song()), null);
});

test("a nudge stops at the neighbouring lines", () => {
  const lines = [line(0, "one", 2), line(1, "two", 3), line(2, "three", 4)];
  assert.equal(nudge(lines, 1, 0.25)[1].start, 3.25);
  assert.equal(nudge(lines, 1, 5)[1].start, 4);
  assert.equal(nudge(lines, 1, -5)[1].start, 2);
});

test("the sounding line follows the playhead", () => {
  const lines = [line(0, "[Hook]"), line(1, "one", 2), line(2, "two", 5)];
  assert.equal(lineAt(lines, 1), -1);
  assert.equal(lineAt(lines, 2), 1);
  assert.equal(lineAt(lines, 9), 2);
});

test("an LRC file's own times aren't stored as tapped ones", () => {
  const lines: LyricLine[] = [{ ...line(0, "one", 2), source: "lrc" }, line(1, "two", 3), line(2, "three")];
  assert.deepEqual(toSave(lines), [{ index: 1, start: 3, end: null, source: "tapped" }]);
});
