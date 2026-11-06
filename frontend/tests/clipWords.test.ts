import assert from "node:assert/strict";
import { test } from "node:test";
import { modelWords, nearestLength, priceWords } from "../src/images/clipWords.ts";

test("a model reads with its lowest catalogue price", () => {
  assert.equal(modelWords({ id: "k", label: "Kling", price: { amount: "0.042", unit: "second" }, price_note: "", price_checked: "", chosen: true }), "Kling · from $0.042 per second");
  assert.equal(modelWords({ id: "v", label: "Vidu", price: { amount: "0.09625", unit: "clip" }, price_note: "", price_checked: "", chosen: false }), "Vidu · from $0.09625 per clip");
  assert.equal(modelWords({ id: "x", label: "X", price: null, price_note: "", price_checked: "", chosen: false }), "X · price unknown");
});

test("the purchase says the published price, or the reserve, with the choices made", () => {
  const base = { quote_id: "q", tasks: 1, seconds: 8, reserve_usd: "0.8000", model: "veo", warning: null };
  assert.equal(
    priceWords({ ...base, choices: { resolution: "1080p", audio: false, prompt: null }, price_basis: "published rate", rate: { amount: "0.1", unit: "second", label: "720p / 1080p", display: "", usd: "0.8000" } }),
    "Make it · $0.80 for 8 s at 1080p, the published rate",
  );
  assert.equal(
    priceWords({ ...base, seconds: 5, reserve_usd: "0.50", choices: { resolution: null, audio: true, prompt: null }, price_basis: "settings reserve", rate: null }),
    "Make it · up to $0.50 for 5 s, with its own sound, Settings' reserve",
  );
});

test("the nearest length is the first at or above the wish, else the longest", () => {
  assert.equal(nearestLength([4, 6, 8], 5), 6);
  assert.equal(nearestLength([5, 10], 12), 10);
  assert.equal(nearestLength([], 5), null);
});
