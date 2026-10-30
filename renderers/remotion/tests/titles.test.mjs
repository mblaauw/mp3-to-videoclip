// The title layer draws the one planned window that covers the current frame.
import assert from "node:assert/strict";
import test from "node:test";

import {validateStillFrames, validateTitles} from "../src/request.mjs";
import {titleWindowAt} from "../src/timing.mjs";

const windows = [
  {kind: "intro", id: "intro", start_frame: 0, frames: 600},
  {kind: "caption", id: "c", start_frame: 1440, frames: 84},
  {kind: "card", id: "card-01", start_frame: 4795, frames: 144},
  {kind: "lockup", id: "lockup", start_frame: 4939, frames: 816},
];

test("a window starts on its first frame and ends before start + frames", () => {
  assert.equal(titleWindowAt(windows, 0).id, "intro");
  assert.equal(titleWindowAt(windows, 599).id, "intro");
  assert.equal(titleWindowAt(windows, 600), null);
  assert.equal(titleWindowAt(windows, 1439), null);
  assert.equal(titleWindowAt(windows, 1440).id, "c");
  assert.equal(titleWindowAt(windows, 1523).id, "c");
  assert.equal(titleWindowAt(windows, 1524), null);
});

test("adjacent credit windows hand over on the exact frame", () => {
  assert.equal(titleWindowAt(windows, 4938).id, "card-01");
  assert.equal(titleWindowAt(windows, 4939).id, "lockup");
  assert.equal(titleWindowAt(windows, 5754).id, "lockup");
  assert.equal(titleWindowAt(windows, 5755), null);
});

test("no plan draws nothing", () => {
  assert.equal(titleWindowAt([], 10), null);
});

const LOGO = `data:image/svg+xml;base64,${Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"/>').toString("base64")}`;
const titles = (overrides = {}) => ({
  spec: {intro: {names: "A  ×  B", title: "Film"}, credits: {cards: [["MUSIC", "A"]]}},
  logo: LOGO,
  font: null,
  windows: [
    {kind: "intro", id: "intro", start_frame: 0, frames: 600},
    {kind: "card", id: "card-01", start_frame: 4795, frames: 144, card: ["MUSIC", "A"]},
    {kind: "lockup", id: "lockup", start_frame: 4939, frames: 816},
  ],
  ...overrides,
});

test("valid titles keep their integer windows", () => {
  const windows = validateTitles(titles(), 5755);
  assert.deepEqual(windows.map((w) => [w.id, w.start_frame, w.frames]), [
    ["intro", 0, 600],
    ["card-01", 4795, 144],
    ["lockup", 4939, 816],
  ]);
});

test("titles that overlap, overrun, repeat or float are refused", () => {
  const base = titles().windows;
  const bad = [
    [[base[0], {...base[1], start_frame: 500}], /starts before the previous window ends/],
    [[base[0], base[1], {...base[2], frames: 900}], /past the film/],
    [[base[0], {...base[1], id: "intro"}], /unique non-empty ids/],
    [[{...base[0], start_frame: 0.5}], /start_frame must be an integer/],
    [[{...base[0], kind: "banner"}], /unsupported graphics part kind/],
    [[], /non-empty array/],
  ];
  for (const [windows, message] of bad) {
    assert.throws(() => validateTitles(titles({windows}), 5755), message);
  }
});

test("titles draw only local bytes", () => {
  assert.throws(() => validateTitles(titles({logo: "https://example.com/x.svg"}), 5755), /embedded local SVG/);
  assert.throws(() => validateTitles(titles({font: "https://example.com/f.woff2"}), 5755), /local embedded bytes/);
});

test("review stills are unique ascending frames inside the film", () => {
  assert.deepEqual(validateStillFrames([0, 300, 5754], 5755), [0, 300, 5754]);
  assert.throws(() => validateStillFrames([], 5755), /1\.\.64 frames/);
  assert.throws(() => validateStillFrames([300, 300], 5755), /unique and in ascending order/);
  assert.throws(() => validateStillFrames([5755], 5755), /past the film/);
  assert.throws(() => validateStillFrames([1.5], 5755), /integer/);
});
