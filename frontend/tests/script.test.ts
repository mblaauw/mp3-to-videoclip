import assert from "node:assert/strict";
import test from "node:test";

import { Resources } from "../src/api/resources.ts";
import { lineAt, parsePasted } from "../src/script/parse.ts";

const beats = [
  { id: "hook", budget: 8 },
  { id: "world", budget: 27 },
  { id: "develop", budget: 40 },
  { id: "reveal", budget: 30 },
  { id: "payoff", budget: 15 },
];

test("a named beat is kept and a plain paste shares the beats by budget", () => {
  const named = parsePasted("hook: A key.\n\nreveal: The door.", beats);
  assert.deepEqual(named.map((line) => line.beat), ["hook", "reveal"]);
  assert.equal(named[0].text, "A key.");
  assert.equal(named[1].id, "l002");
  const plain = parsePasted(Array.from({ length: 24 }, (_, i) => `Line ${i}`).join("\n"), beats);
  assert.equal(plain[0].beat, "hook");
  assert.equal(plain[23].beat, "payoff");
  assert.ok(plain.filter((line) => line.beat === "develop").length > plain.filter((line) => line.beat === "hook").length);
});

test("something that only looks like a beat stays in the words", () => {
  assert.equal(parsePasted("Note: the door.", beats)[0].text, "Note: the door.");
});

test("a pause belongs to the line before it", () => {
  const lines = [
    { id: "a", start: 0, end: 2, pause_after: 1 },
    { id: "b", start: 3, end: 5, pause_after: 0 },
  ];
  assert.equal(lineAt(lines, 2.5)?.id, "a");
  assert.equal(lineAt(lines, 3)?.id, "b");
  assert.equal(lineAt(lines, 6), null);
});

test("a subscriber hears of a change once, and only for its own film and artifact", async () => {
  const store = new Resources();
  const key = "/api/projects/a/script";
  let told = 0;
  const stop = store.subscribe(key, () => {
    told += 1;
  });
  store.invalidate({ slug: "b" });
  store.invalidate({ slug: "a", artifact: "budget" });
  await Promise.resolve();
  assert.equal(told, 0);
  store.invalidate({ slug: "a" });
  store.invalidate({ slug: "a", artifact: "script" });
  await Promise.resolve();
  assert.equal(told, 1);
  stop();
  store.invalidate({ slug: "a" });
  await Promise.resolve();
  assert.equal(told, 1);
});

test("two readers of one key share one fetch", async () => {
  const store = new Resources();
  let fetched = 0;
  const load = async () => {
    fetched += 1;
    return 1;
  };
  await Promise.all([store.read("k", load), store.read("k", load)]);
  assert.equal(fetched, 1);
});
