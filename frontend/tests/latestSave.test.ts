import assert from "node:assert/strict";
import test from "node:test";
import { latestSave } from "../src/story/latestSave.ts";

function controlled() {
  const sent: string[] = [];
  const release: (() => void)[] = [];
  const send = (value: string) => {
    sent.push(value);
    return new Promise<void>((resolve) => release.push(resolve));
  };
  return { sent, release, send };
}

test("a value asked for during a save is sent after it, not dropped", async () => {
  const { sent, release, send } = controlled();
  const save = latestSave(send);
  const first = save("objective");
  void save("objective, audience");
  assert.deepEqual(sent, ["objective"]);
  release[0]();
  await new Promise((resolve) => setTimeout(resolve));
  assert.deepEqual(sent, ["objective", "objective, audience"]);
  release[1]();
  await first;
});

test("only the newest waiting value is sent", async () => {
  const { sent, release, send } = controlled();
  const save = latestSave(send);
  const first = save("a");
  void save("b");
  void save("c");
  release[0]();
  await new Promise((resolve) => setTimeout(resolve));
  assert.deepEqual(sent, ["a", "c"]);
  release[1]();
  await first;
});

test("a failed save lets the next one run", async () => {
  const sent: string[] = [];
  const save = latestSave(async (value: string) => {
    sent.push(value);
    if (value === "bad") throw new Error("no");
  });
  await assert.rejects(save("bad"));
  await save("good");
  assert.deepEqual(sent, ["bad", "good"]);
});
