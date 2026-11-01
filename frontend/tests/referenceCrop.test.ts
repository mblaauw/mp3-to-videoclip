import assert from "node:assert/strict";
import test from "node:test";
import { cropBox } from "../src/images/referenceCrop.ts";

const shown = { width: 688, height: 384 };
const source = { width: 1376, height: 768 };

test("a drag becomes pixels of the source still", () => {
  assert.deepEqual(cropBox({ x: 100, y: 50 }, { x: 200, y: 300 }, shown, source), [200, 100, 400, 600]);
});

test("the drag can run in any direction", () => {
  assert.deepEqual(cropBox({ x: 200, y: 300 }, { x: 100, y: 50 }, shown, source), [200, 100, 400, 600]);
});

test("a drag past the edge stops at the edge", () => {
  assert.deepEqual(cropBox({ x: 600, y: 300 }, { x: 900, y: 900 }, shown, source), [1200, 600, 1376, 768]);
});

test("a click means the whole still", () => {
  assert.equal(cropBox({ x: 100, y: 50 }, { x: 103, y: 52 }, shown, source), null);
});
