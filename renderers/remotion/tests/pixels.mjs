#!/usr/bin/env node
// Pixel goldens: four real frames of the composition, compared by structure so a small
// difference between Chrome builds passes and a moved transition, grain or title does not.
//
//   npm run pixels                 # compare
//   UPDATE_PIXELS=1 npm run pixels # regenerate; say why in the commit
//
// Needs a local Chrome (REMOTION_CHROME), which is why plain `npm test` leaves this out.
import {spawnSync} from "node:child_process";
import {existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import path from "node:path";
import process from "node:process";
import {fileURLToPath} from "node:url";

import {decodePng, ssim} from "./pixels-compare.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const REPO = path.resolve(ROOT, "../..");
const GOLDEN = path.join(HERE, "pixels");
const ASSETS = path.join(REPO, "docs/primitives/assets");
const THRESHOLD = 0.98;
// Chrome builds draw the whip's blur differently: Linux scores 0.952 against a Mac golden. A frame off
// scores 0.857 at best and another transition 0.762, so this still fails on a whip that really moved.
// A flipped direction scores 0.974 and passes here; edit-primitives.test.mjs pins direction.
const THRESHOLDS = {whip: 0.93};

const motion = {type: "hold", from: 1, to: 1, easing: "smoothstep", anchor: [0.5, 0.5]};
const neutral = {preset: "neutral", strength: 1};

function shot(id, start, image, overrides = {}, grade = neutral) {
  return {
    id,
    start_frame: start,
    duration_frames: 24,
    image,
    camera: "hold",
    dissolve_frames: 0,
    edit: {
      shot_id: id,
      start_frame: start,
      duration_frames: 24,
      motion,
      transition_in: {type: "cut", frames: 0},
      accents: [],
      text: [],
      ...overrides,
    },
    grade,
  };
}

const inter = readFileSync(path.join(ROOT, "fonts/Inter.woff2")).toString("base64");

const SHOTS = [
  shot("a", 0, "a.png"),
  shot("b", 24, "b.png", {transition_in: {type: "fade", frames: 12, reason: "pixel golden"}}),
  shot("c", 48, "c.png", {
    transition_in: {type: "whip_pan", frames: 12, direction: "left", reason: "pixel golden"},
  }),
  shot("d", 72, "a.png", {}, {...neutral, look: {grain: 0.6, weave: 0.4, drift: 0.5}}),
  shot(
    "e",
    96,
    "b.png",
    {
      text: [{id: "t", style: "title", text: "One Title", in_frame: 96, out_frame: 120, animation: "fade"}],
    },
    {...neutral, typeface: "inter"},
  ),
];

/** A frame's name in the golden folder, and which moment of the composition it pins. */
const FRAMES = {30: "dissolve", 54: "whip", 84: "look", 108: "title"};

function render(work) {
  const output = path.join(work, "stills");
  const request = {
    kind: "stills",
    output,
    assetRoot: ASSETS,
    width: 480,
    height: 270,
    fps: 24,
    frames: 120,
    ...(process.env.REMOTION_CHROME ? {chrome: process.env.REMOTION_CHROME} : {}),
    input: {
      shots: SHOTS,
      still_frames: Object.keys(FRAMES).map(Number),
      typefaces: {inter: {family: "Inter", src: `data:font/woff2;base64,${inter}`}},
    },
  };
  const requestPath = path.join(work, "request.json");
  writeFileSync(requestPath, JSON.stringify(request));
  const result = spawnSync(
    process.execPath,
    [path.join(ROOT, "render.mjs"), requestPath, "--cache-dir", path.join(work, "cache")],
    {cwd: ROOT, encoding: "utf8", timeout: 300_000},
  );
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
  const report = JSON.parse(readFileSync(`${output}.render.json`, "utf8"));
  return Object.fromEntries(report.stills.map((still) => [still.frame, path.join(output, still.file)]));
}

const work = mkdtempSync(path.join(tmpdir(), "mp3-to-videoclip-pixels-"));
let failed = false;
try {
  const stills = render(work);
  for (const [frame, name] of Object.entries(FRAMES)) {
    const target = path.join(GOLDEN, `${name}.png`);
    if (process.env.UPDATE_PIXELS) {
      writeFileSync(target, readFileSync(stills[frame]));
      process.stdout.write(`wrote ${name}.png\n`);
      continue;
    }
    if (!existsSync(target)) throw new Error(`no golden for ${name}; run with UPDATE_PIXELS=1`);
    const score = ssim(decodePng(readFileSync(target)), decodePng(readFileSync(stills[frame])));
    const passed = score >= (THRESHOLDS[name] ?? THRESHOLD);
    failed ||= !passed;
    process.stdout.write(`${passed ? "ok" : "DIFFERENT"} ${name} ${score.toFixed(4)}\n`);
  }
} finally {
  rmSync(work, {recursive: true, force: true});
}
process.exit(failed ? 1 : 0);
