import assert from "node:assert/strict";
import test from "node:test";
import { filmUsageLine, usageLine } from "../src/shell/modelCost.ts";

test("a turn reads as its tokens and its estimate", () => {
  const line = usageLine({ prompt_tokens: 1932, completion_tokens: 410, cost_usd: "0.0040", cost_basis: "catalogue estimate" });
  assert.equal(line, "1,932 in · 410 out · about $0.004");
});

test("an unknown cost never reads as free", () => {
  assert.equal(
    usageLine({ prompt_tokens: 10, completion_tokens: 2, cost_usd: null, cost_basis: "unpriced" }),
    "10 in · 2 out · no price known",
  );
  assert.equal(
    usageLine({ prompt_tokens: 0, completion_tokens: 0, cost_usd: null, cost_basis: "tokens not reported" }),
    "Tokens not reported",
  );
  assert.equal(usageLine(undefined), null);
});

test("a film's total is a floor when some turns have no price", () => {
  const base = { prompt_tokens: 1, completion_tokens: 1, cost_usd: "0.25" };
  assert.equal(filmUsageLine({ ...base, turns: 3, unpriced_turns: 0 }), "3 turns, about $0.25");
  assert.equal(filmUsageLine({ ...base, turns: 3, unpriced_turns: 1 }), "3 turns, at least about $0.25");
  assert.equal(filmUsageLine({ ...base, turns: 3, unpriced_turns: 3 }), "3 turns, no price known");
  assert.equal(filmUsageLine({ ...base, turns: 0, unpriced_turns: 0 }), null);
});
