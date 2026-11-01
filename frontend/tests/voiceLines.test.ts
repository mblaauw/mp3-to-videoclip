import assert from "node:assert/strict";
import test from "node:test";
import type { EditPayload } from "../src/api.ts";
import {
  addVoiceLine,
  removeVoiceLine,
  setVoiceStart,
  updateVoiceLine,
} from "../src/film/voiceLines.ts";

const edit = (): EditPayload => ({
  sections: [],
  shots: [],
  grade: {} as EditPayload["grade"],
  voice: [
    { id: "line-1", text: "One door.", start_frame: 24 },
    { id: "line-2", text: "One pulse.", start_frame: 96 },
  ],
});

test("a new line keeps the list in time order", () => {
  const next = addVoiceLine(edit(), 48, "Another world.");
  assert.deepEqual(
    next.voice?.map((line) => line.id),
    ["line-1", "line-3", "line-2"],
  );
});

test("a new line never reuses an id that still has takes", () => {
  const next = addVoiceLine(edit(), 200, "x", ["line-3"]);
  assert.equal(next.voice?.at(-1)?.id, "line-4");
});

test("moving a line reorders the list", () => {
  const next = updateVoiceLine(edit(), "line-1", { start_frame: 120 });
  assert.deepEqual(
    next.voice?.map((line) => line.id),
    ["line-2", "line-1"],
  );
});

test("a typed time stays inside the film and on a whole frame", () => {
  assert.equal(setVoiceStart(edit(), "line-1", 2.51, 24, 1680).voice?.[0].start_frame, 60);
  assert.equal(setVoiceStart(edit(), "line-1", -3, 24, 1680).voice?.[0].start_frame, 0);
  assert.equal(setVoiceStart(edit(), "line-2", 999, 24, 1680).voice?.at(-1)?.start_frame, 1679);
});

test("removing a line leaves the others alone and the input unchanged", () => {
  const original = edit();
  const next = removeVoiceLine(original, "line-1");
  assert.deepEqual(next.voice?.map((line) => line.id), ["line-2"]);
  assert.equal(original.voice?.length, 2);
});
