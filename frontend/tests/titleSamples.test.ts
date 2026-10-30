import assert from "node:assert/strict";
import test from "node:test";
import { sampleTitle } from "../src/film/titleSamples.ts";

const windows = [
  { kind: "intro" as const, id: "intro", start_frame: 0, frames: 600 },
  { kind: "card" as const, id: "card-03", start_frame: 5220, frames: 144, card: ["STYLE DIRECTION", "VJDJ69"] },
  { kind: "lockup" as const, id: "lockup", start_frame: 5652, frames: 97 },
];
const sample = (frame: number, seconds: number, window: string, phase: string | null = null) => ({
  name: `f${frame}.png`, url: "/x", sha256: "h", frame, seconds, window, phase,
});

test("samples are named for what they show, not their file", () => {
  assert.equal(sampleTitle(sample(262, 10.92, "intro", "title"), windows), "Opening: title at 0:10");
  assert.equal(sampleTitle(sample(452, 18.8, "intro", "mini_credits_1"), windows), "Opening: mini credits at 0:18");
  assert.equal(sampleTitle(sample(5292, 220.5, "card-03"), windows), "Style direction at 3:40");
  assert.equal(sampleTitle(sample(5700, 237.5, "lockup"), windows), "Closing signature at 3:57");
});

test("an older review keeps its file names", () => {
  assert.equal(
    sampleTitle({ name: "001-f00314-intro-intro.png", url: "/x", sha256: "h" }, windows),
    "001-f00314-intro-intro.png",
  );
});
