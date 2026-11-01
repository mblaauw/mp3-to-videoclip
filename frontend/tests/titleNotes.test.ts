import assert from "node:assert/strict";
import test from "node:test";
import { describeTitlesNote } from "../src/film/titleNotes.ts";

test("a titles failure reads plainly and keeps the engine's words under details", () => {
  const raw = "The titles cannot be laid out yet: text 'A' breaks the horizontal safe margin";
  assert.deepEqual(describeTitlesNote(raw), {
    title: "The titles are not ready yet.",
    reason: "A title is too wide for the frame.",
    details: "text 'A' breaks the horizontal safe margin",
  });
});

test("an unknown reason still opens plainly", () => {
  const note = describeTitlesNote("The titles cannot be laid out yet: something new");
  assert.equal(note.title, "The titles are not ready yet.");
  assert.equal(note.details, "something new");
});

test("other messages pass through", () => {
  assert.deepEqual(describeTitlesNote("The titles have not been set up yet."), {
    title: "The titles have not been set up yet.",
    reason: "",
    details: null,
  });
});
