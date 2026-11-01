import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { isPlaceholder, shotCaption, shown } from "../src/storyboard/placeholders.ts";

const cases = JSON.parse(readFileSync(new URL("../../tests/fixtures/placeholder-cases.json", import.meta.url), "utf8")) as [string, boolean][];

test("the screen's placeholder rule is the engine's", () => {
  for (const [value, expected] of cases) assert.equal(isPlaceholder(value), expected, value);
});

test("a placeholder reads as empty", () => {
  assert.equal(shown("TODO: compose this shot"), "");
  assert.equal(shown("A real job"), "A real job");
  assert.equal(shown(null), "");
});

test("a card says the first real thing about a shot", () => {
  assert.equal(shotCaption({ message: "", purpose: "TODO: approved story purpose" }), "");
  assert.equal(shotCaption({ message: "It says this", purpose: "TODO: x" }), "It says this");
  assert.equal(shotCaption({ message: "TODO", purpose: "Its job" }), "Its job");
});
