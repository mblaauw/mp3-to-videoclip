import assert from "node:assert/strict";
import { test } from "node:test";
import { addEdge, joinNext, moveEdge } from "../src/track/sectionEdit.ts";

const song = () => [
  { start: 0, name: "Intro" },
  { start: 30, name: "Hook" },
  { start: 60, name: "Verse" },
];

test("an edge stays clear of its neighbours", () => {
  assert.equal(moveEdge(song(), 1, 40, 100)[1].start, 40);
  assert.equal(moveEdge(song(), 1, 59.5, 100)[1].start, 58);
  assert.equal(moveEdge(song(), 1, 1, 100)[1].start, 2);
  assert.equal(moveEdge(song(), 2, 99.9, 100)[2].start, 98);
});

test("the start of the song can't move", () => {
  assert.equal(moveEdge(song(), 0, 10, 100)[0].start, 0);
});

test("adding an edge splits the section under it", () => {
  const next = addEdge(song(), 45, 100);
  assert.deepEqual(next?.map((section) => section.start), [0, 30, 45, 60]);
  assert.equal(next?.[2].name, "Hook (2)");
});

test("an edge too close to another is refused", () => {
  assert.equal(addEdge(song(), 31, 100), null);
  assert.equal(addEdge(song(), 99, 100), null);
});

test("joining keeps the first name", () => {
  assert.deepEqual(joinNext(song(), 0).map((section) => section.name), ["Intro", "Verse"]);
  assert.equal(joinNext(song(), 2).length, 3);
});
