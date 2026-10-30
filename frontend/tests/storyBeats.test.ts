import assert from "node:assert/strict";
import test from "node:test";
import type { Concept, StoryPassage } from "../src/api.ts";
import { conceptBeats, parseShape, passageAt, passageBeats } from "../src/story/beats.ts";

const concept = (fields: Partial<Concept>) => ({ id: "c1", ...fields }) as Concept;

test("older concepts read their times out of the free text", () => {
  const beats = parseShape([
    "0–49.6 s (0.25, 0.24): the dream in four frames — walled axis, his offered hand",
    "49.6-74.4 s: the leak at speed",
  ]);
  assert.deepEqual(beats?.[0], {
    start: 0,
    end: 49.6,
    label: "the dream in four frames",
    text: "The dream in four frames — walled axis, his offered hand",
  });
  assert.equal(beats?.[1].start, 49.6);
});

test("a shape without times stays text, never a guessed time", () => {
  assert.equal(parseShape(["0–10 s: opens", "then it closes"]), null);
  assert.equal(parseShape(["10–5 s: backwards"]), null);
  assert.equal(parseShape([]), null);
  assert.equal(conceptBeats(concept({ shape: ["a", "b", "c", "d"] })), null);
});

test("structured beats win over any older shape", () => {
  const beats = [{ start: 1, end: 2, label: "Here", text: "It happens." }];
  assert.deepEqual(conceptBeats(concept({ beats, shape: ["0–9 s: old"] })), beats);
});

const passage = (start: number | null, end: number | null, text: string): StoryPassage => ({
  start,
  end,
  text,
  from: 0,
  to: text.length,
});

test("only placed passages reach the song", () => {
  const passages = [passage(0, 5, "One walks."), passage(null, null, "Unplaced."), passage(8, 9, "Two.")];
  assert.deepEqual(passageBeats(passages).map((beat) => beat.start), [0, 8]);
  assert.equal(passageAt(passages, 2), 0);
  assert.equal(passageAt(passages, 6), -1);
  assert.equal(passageAt(passages, 8.5), 2);
});
