import assert from "node:assert/strict";
import test from "node:test";
import { roleForStage, STAGE_ROLE, SUGGESTIONS } from "../src/director/chat.ts";

test("the drawer opens on the Writer where the Writer works, and on the Editor at the cut", () => {
  assert.equal(roleForStage("sound"), "writer");
  assert.equal(roleForStage("publish"), "writer");
  assert.equal(roleForStage("script"), "writer");
  assert.equal(roleForStage("film"), "editor");
  assert.equal(roleForStage("track"), "editor");
});

test("every stage with suggestions has a role", () => {
  assert.deepEqual(Object.keys(STAGE_ROLE).sort(), Object.keys(SUGGESTIONS).sort());
});
