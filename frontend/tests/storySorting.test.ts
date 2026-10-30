import assert from "node:assert/strict";
import test from "node:test";
import type { IdeaParts } from "../src/api.ts";
import { moveSentence, sentences } from "../src/story/sorting.ts";

const parts: IdeaParts = {
  story: ['They walk. "It\'s over." She leaves!'],
  style: ["Soft light."],
  rules: [],
  avoid: ["No faces."],
};

test("sentences are split without changing a character", () => {
  assert.deepEqual(
    sentences(parts).map((item) => item.text),
    ["They walk.", '"It\'s over."', "She leaves!", "Soft light.", "No faces."],
  );
});

test("moving takes one sentence from where it was to where you said", () => {
  const second = sentences(parts)[1];
  const moved = moveSentence(parts, second, "rules");
  assert.deepEqual(moved.story, ["They walk.", "She leaves!"]);
  assert.deepEqual(moved.rules, ['"It\'s over."']);
  assert.deepEqual(moved.style, ["Soft light."]);
});

test("the same sentence twice moves only the one you picked", () => {
  const twice: IdeaParts = { story: ["Again. Then. Again."], style: [], rules: [], avoid: [] };
  const last = sentences(twice)[2];
  assert.deepEqual(moveSentence(twice, last, "style"), {
    story: ["Again.", "Then."],
    style: ["Again."],
    rules: [],
    avoid: [],
  });
});
