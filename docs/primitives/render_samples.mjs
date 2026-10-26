// Render the 2-second primitive samples in docs/primitives/.
//
// This uses the production renderer CLI, the shared BaseFilm composition and
// the same timing module as the film. Re-run it after changing a primitive:
// existing clips are refused, so delete the affected .mp4 first.
import {createHash} from "node:crypto";
import {existsSync, mkdirSync, readFileSync, statSync, unlinkSync, writeFileSync} from "node:fs";
import {spawnSync} from "node:child_process";
import {tmpdir} from "node:os";
import path from "node:path";
import {fileURLToPath} from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../..");
const ENGINE = path.join(ROOT, "renderers/remotion");
const ASSETS = path.join(HERE, "assets");
const CACHE = path.join(tmpdir(), "mp3-to-videoclip-primitives");
const WIDTH = 480;
const HEIGHT = 270;
const FPS = 24;
const FRAMES = 48;

const motion = (type = "hold", overrides = {}) => ({
  type,
  from: overrides.from ?? 1,
  to: overrides.to ?? 1,
  easing: overrides.easing ?? "smoothstep",
  anchor: overrides.anchor ?? [0.5, 0.5],
  ...(overrides.reason ? {reason: overrides.reason} : {}),
});

const transition = (type, frames = 0, overrides = {}) => ({
  type,
  frames,
  ...(overrides.direction ? {direction: overrides.direction} : {}),
  ...(overrides.reason ? {reason: overrides.reason} : {}),
});

function decision(shotId, start, duration, overrides = {}) {
  return {
    shot_id: shotId,
    start_frame: start,
    duration_frames: duration,
    motion: overrides.motion ?? motion(),
    transition_in: overrides.transition_in ?? transition("cut"),
    ...(overrides.split_layout ? {split_layout: overrides.split_layout} : {}),
    accents: overrides.accents ?? [],
    text: overrides.text ?? [],
  };
}

function shot(id, start, duration, image, edit, grade, extra = {}) {
  return {
    id,
    start_frame: start,
    duration_frames: duration,
    image,
    camera: "hold",
    dissolve_frames: 0,
    edit,
    grade,
    ...extra,
  };
}

const grade = (preset) => ({preset, strength: 1});
const twoShot = (name, incoming, direction) => ({
  name,
  group: "Transitions",
  label: name.replace("transition-", "").replaceAll("-", " "),
  shots: [
    shot("a", 0, 24, "a.png", decision("a", 0, 24), grade("neutral")),
    shot(
      "b",
      24,
      24,
      "b.png",
      decision("b", 24, 24, {
        transition_in: transition(incoming, 12, {
          direction,
          reason: "visual primitive sample",
        }),
      }),
      grade("neutral"),
    ),
  ],
});

const oneShot = (name, group, label, overrides = {}, extra = {}) => ({
  name,
  group,
  label,
  shots: [
    shot(
      "a",
      0,
      48,
      extra.image ?? "a.png",
      decision("a", 0, 48, overrides),
      extra.grade ?? grade("neutral"),
      extra.shot ?? {},
    ),
  ],
});

const text = (animation) =>
  oneShot(`text-${animation.replaceAll("_", "-")}`, "Text", animation, {
    text: [
      {
        id: "sample",
        style: "title",
        text: "ONE TAKE",
        in_frame: 4,
        out_frame: 46,
        animation,
        reason: "visual primitive sample",
      },
    ],
  });

const samples = [
  twoShot("transition-dip-to-black", "dip_to_black"),
  twoShot("transition-dip-to-white", "dip_to_white"),
  twoShot("transition-whip-pan", "whip_pan", "left"),
  twoShot("transition-push", "push"),
  twoShot("transition-slide", "slide", "up"),
  oneShot("accent-punch-in", "Accents", "punch in", {
    accents: [
      {frame: 24, type: "punch_in", amount: 1.08, duration_frames: 6, reason: "sample"},
    ],
  }),
  oneShot("accent-flash", "Accents", "flash frame", {
    accents: [{frame: 24, type: "flash", duration_frames: 3, reason: "sample"}],
  }),
  oneShot("accent-light-leak", "Accents", "light leak", {
    accents: [{frame: 18, type: "light_leak", duration_frames: 14, reason: "sample"}],
  }),
  oneShot(
    "split-row",
    "Split layouts",
    "two panes, row",
    { split_layout: "row" },
    {
      shot: {
        kind: "split",
        split_panes: [
          {shot_id: "a", image: "a.png", crop: {zoom: 1.1, x: 0.35, y: 0.5}},
          {shot_id: "b", image: "b.png", crop: {zoom: 1.2, x: 0.65, y: 0.5}},
        ],
      },
    },
  ),
  oneShot(
    "split-grid",
    "Split layouts",
    "three panes, grid",
    { split_layout: "grid" },
    {
      shot: {
        kind: "split",
        split_panes: [
          {shot_id: "a", image: "a.png", crop: {zoom: 1, x: 0.5, y: 0.5}},
          {shot_id: "b", image: "b.png", crop: {zoom: 1, x: 0.5, y: 0.5}},
          {shot_id: "c", image: "c.png", crop: {zoom: 1, x: 0.5, y: 0.5}},
        ],
      },
    },
  ),
  text("fade"),
  text("type_on"),
  text("slide_up"),
  text("pop"),
  text("kinetic_words"),
  ...["neutral", "warm-night", "clean-day", "monochrome", "vivid", "film-fade"].map((preset) =>
    oneShot(`grade-${preset}`, "Grade presets", preset, {}, {grade: grade(preset)}),
  ),
];

function requestFor(sample) {
  return {
    kind: "base",
    output: path.join(HERE, `${sample.name}.mp4`),
    assetRoot: ASSETS,
    width: WIDTH,
    height: HEIGHT,
    fps: FPS,
    frames: FRAMES,
    chrome:
      process.env.REMOTION_CHROME ??
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    input: {shots: sample.shots},
  };
}

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function renderSample(sample, index) {
  const output = path.join(HERE, `${sample.name}.mp4`);
  if (existsSync(output)) {
    process.stdout.write(`skip ${sample.name} (exists)\n`);
    return;
  }
  const requestPath = path.join(CACHE, `${sample.name}.request.json`);
  writeFileSync(requestPath, `${JSON.stringify(requestFor(sample), null, 2)}\n`);
  const result = spawnSync(
    process.execPath,
    [path.join(ENGINE, "render.mjs"), requestPath, "--cache-dir", path.join(CACHE, "bundles")],
    {cwd: ROOT, encoding: "utf8", timeout: 180000},
  );
  if (result.status !== 0) {
    throw new Error(`${sample.name}: ${result.stderr || result.stdout}`);
  }
  const sidecar = `${output}.render.json`;
  if (existsSync(sidecar)) unlinkSync(sidecar);
  process.stdout.write(`rendered ${sample.name} (${index + 1}/${samples.length})\n`);
}

function gallery() {
  const groups = [...new Set(samples.map((sample) => sample.group))];
  const cards = groups
    .map((group) => {
      const items = samples
        .filter((sample) => sample.group === group)
        .map(
          (sample) => `        <figure>
          <video src="${sample.name}.mp4" controls loop muted playsinline preload="metadata"></video>
          <figcaption><strong>${sample.label}</strong><code>${sample.name}</code></figcaption>
        </figure>`,
        )
        .join("\n");
      return `      <section>\n        <h2>${group}</h2>\n        <div class="grid">\n${items}\n        </div>\n      </section>`;
    })
    .join("\n");
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Film primitives — 2 second samples</title>
    <style>
      :root { color-scheme: dark; --ink: #f4f1e8; --muted: #9aa7ad; --line: #27333a; --accent: #d8ff3e; }
      * { box-sizing: border-box; }
      body { margin: 0; padding: 40px; background: #0b1015; color: var(--ink); font: 16px/1.5 "Avenir Next", "Helvetica Neue", Arial, sans-serif; }
      h1 { font-size: clamp(32px, 5vw, 64px); letter-spacing: -0.03em; margin: 0 0 8px; }
      h2 { font-size: 20px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--accent); margin: 40px 0 16px; }
      p { color: var(--muted); max-width: 70ch; }
      section + section { border-top: 1px solid var(--line); }
      .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 18px; }
      figure { margin: 0; border: 1px solid var(--line); background: #101820; }
      video { display: block; width: 100%; aspect-ratio: 16 / 9; background: #000; }
      figcaption { display: flex; flex-direction: column; gap: 4px; padding: 10px 12px; }
      strong { font-size: 14px; text-transform: capitalize; }
      code { color: var(--muted); font-size: 12px; }
    </style>
  </head>
  <body>
    <h1>Film primitives</h1>
    <p>Two-second samples rendered through the production <code>BaseFilm</code> and <code>timing.mjs</code>, so the MP4 and Studio Player share these exact primitives. ${samples.length} clips at ${FPS} fps. <a href="contact-sheet.png">Contact sheet</a>.</p>
${cards}
  </body>
</html>
`;
}

mkdirSync(CACHE, {recursive: true});

for (const [index, sample] of samples.entries()) {
  renderSample(sample, index);
}

const manifest = {
  width: WIDTH,
  height: HEIGHT,
  fps: FPS,
  frames: FRAMES,
  seconds: FRAMES / FPS,
  source: "renderers/remotion/src/BaseFilm.jsx + timing.mjs",
  samples: samples.map((sample) => ({
    file: `${sample.name}.mp4`,
    group: sample.group,
    label: sample.label,
    sha256: sha256(path.join(HERE, `${sample.name}.mp4`)),
    bytes: statSync(path.join(HERE, `${sample.name}.mp4`)).size,
  })),
};
writeFileSync(path.join(HERE, "samples.json"), `${JSON.stringify(manifest, null, 2)}\n`);
writeFileSync(path.join(HERE, "index.html"), gallery());
process.stdout.write(`wrote ${samples.length} samples, samples.json and index.html\n`);
