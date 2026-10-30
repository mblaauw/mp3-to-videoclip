#!/usr/bin/env node
// Local Remotion render CLI for the mp3-to-videoclip still film.
//
//   node render.mjs <request.json> [--cache-dir <dir>]
//
// The request is the contract owned by src/request.mjs (`validateRequest`); this
// file is the side-effecting half only:
//
//   * bundles once into a content-addressed `.cache/<sha>` directory keyed on
//     src/, package-lock.json and the request's asset root, and reuses it;
//   * renders with the local Chrome executable (never downloads a browser) and
//     refuses any remote asset download;
//   * renders to a private temp file and publishes it with an exclusive hard
//     link, so an existing output is never overwritten, then writes a JSON
//     sidecar next to it;
//   * prints exactly one concise JSON line on stdout.
//
// base     -> h264 / yuv420p / silent
// graphics -> prores 4444 / png / yuva444p10le / muted, preserving alpha
// stills   -> PNG frames of the Base composition into a new directory
import {createHash} from "node:crypto";
import {
  existsSync,
  linkSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";

import {bundle} from "@remotion/bundler";
import {renderMedia, renderStill, selectComposition} from "@remotion/renderer";

import {fail, requestSha256, resolveChrome, validateRequest} from "./src/request.mjs";
import {createProgressWriter} from "./src/progress.mjs";
import {createDiagnostics} from "./src/diagnostics.mjs";
import {benchmarkOptions as resolveBenchmarkOptions} from "./src/benchmark-profiles.mjs";
import {ensureBundleCache} from "./src/bundle-cache.mjs";

const RENDERER_ROOT = path.dirname(fileURLToPath(import.meta.url));
const ENTRY_POINT = path.join(RENDERER_ROOT, "src", "index.jsx");
const SRC_DIR = path.join(RENDERER_ROOT, "src");
const PACKAGE_LOCK = path.join(RENDERER_ROOT, "package-lock.json");
const REMOTION_PACKAGE = path.join(
  RENDERER_ROOT,
  "node_modules",
  "remotion",
  "package.json",
);
const DEFAULT_CACHE_ROOT = path.join(RENDERER_ROOT, ".cache");

/** Composition and encoder settings per requested kind. */
const KIND_SETTINGS = {
  base: {
    compositionId: "Base",
    codec: "h264",
    imageFormat: "png",
    pixelFormat: "yuv420p",
    proResProfile: undefined,
  },
  graphics: {
    compositionId: "Graphics",
    codec: "prores",
    imageFormat: "png",
    pixelFormat: "yuva444p10le",
    proResProfile: "4444",
  },
  stills: {
    compositionId: "Base",
    codec: null,
    imageFormat: "png",
    pixelFormat: null,
    proResProfile: undefined,
  },
};

const USAGE = "usage: node render.mjs <request.json|-> [--cache-dir <dir>] [--progress <file>] [--benchmark-profile videotoolbox-20m]";

function remotionVersion() {
  try {
    return JSON.parse(readFileSync(REMOTION_PACKAGE, "utf8")).version;
  } catch {
    return "unknown";
  }
}

function parseArgs(argv) {
  let requestPath = null;
  let cacheRoot = DEFAULT_CACHE_ROOT;
  let progressFile = null;
  let benchmarkProfile = null;
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--help" || arg === "-h") return {help: true};
    if (arg === "--benchmark-profile") {
      benchmarkProfile = argv[++index];
      if (benchmarkProfile !== "videotoolbox-20m") fail("unknown benchmark profile");
      continue;
    }
    if (arg === "--cache-dir") {
      index += 1;
      if (!argv[index]) fail(`--cache-dir needs a directory (${USAGE})`);
      cacheRoot = path.resolve(argv[index]);
      continue;
    }
    if (arg.startsWith("--cache-dir=")) {
      cacheRoot = path.resolve(arg.slice("--cache-dir=".length));
      continue;
    }
    if (arg === "--progress") {
      index += 1;
      if (!argv[index]) fail(`--progress needs a file path (${USAGE})`);
      progressFile = path.resolve(argv[index]);
      continue;
    }
    if (arg.startsWith("--progress=")) {
      progressFile = path.resolve(arg.slice("--progress=".length));
      continue;
    }
    if (arg.startsWith("-") && arg !== "-") fail(`unknown option ${arg} (${USAGE})`);
    if (requestPath !== null) fail(`unexpected extra argument ${arg} (${USAGE})`);
    requestPath = arg;
  }
  if (requestPath === null) fail(`a request file is required (${USAGE})`);
  return {help: false, requestPath, cacheRoot, progressFile, benchmarkProfile};
}

function loadRequest(requestPath) {
  let text;
  try {
    text = requestPath === "-" ? readFileSync(0, "utf8") : readFileSync(requestPath, "utf8");
  } catch (error) {
    fail(`cannot read request ${requestPath}: ${error.message}`);
  }
  try {
    return JSON.parse(text);
  } catch (error) {
    fail(`request ${requestPath} is not valid JSON: ${error.message}`);
  }
}

function sha256File(file) {
  return createHash("sha256").update(readFileSync(file)).digest("hex");
}

function listFiles(root, prefix = "") {
  const files = [];
  for (const entry of readdirSync(root, {withFileTypes: true}).sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(root, entry.name);
    const relative = prefix === "" ? entry.name : `${prefix}/${entry.name}`;
    if (entry.isDirectory()) files.push(...listFiles(full, relative));
    else if (entry.isFile()) files.push([relative, full]);
  }
  return files;
}

/**
 * Content key for the bundle: every source file, the lockfile and every asset
 * in the request's asset root. A changed pixel set therefore rebundles instead
 * of silently serving stale static assets.
 */
export function bundleKey(assetRoot) {
  const hash = createHash("sha256");
  hash.update("mp3-to-videoclip-remotion-bundle-v2\n");
  for (const [relative, full] of listFiles(SRC_DIR)) {
    hash.update(`src:${relative}:${sha256File(full)}\n`);
  }
  hash.update(`lock:${sha256File(PACKAGE_LOCK)}\n`);
  for (const [relative, full] of listFiles(assetRoot)) {
    hash.update(`asset:${relative}:${sha256File(full)}\n`);
  }
  return hash.digest("hex");
}

/** Bundle into `cacheDir` unless a complete bundle is already there. */
async function ensureBundle(cacheDir, assetRoot, progress) {
  const result = await ensureBundleCache({
    cacheDir,
    key: path.basename(cacheDir),
    build: (staging) => bundle({
      entryPoint: ENTRY_POINT,
      outDir: staging,
      publicDir: assetRoot,
      rootDir: RENDERER_ROOT,
      enableCaching: true,
      onProgress: (percent) => {
        progress.update({
          phase: "bundling-assets",
          done: Math.round(Math.min(Math.max(Number(percent) || 0, 0), 1) * 100),
          total: 100,
          unit: "percent",
        });
      },
    }),
  });
  if (result.bundleCached) progress.update({phase: "bundle-cached"});
  return result;
}

/** Publish `temp` at `target` with an exclusive hard link: never overwrite. */
function publishExclusive(temp, target, label) {
  try {
    linkSync(temp, target);
  } catch (error) {
    if (error.code === "EEXIST") fail(`${label} ${target} already exists; refusing to overwrite`);
    fail(`cannot publish ${label} ${target}: ${error.message}`);
  } finally {
    rmSync(temp, {force: true});
  }
}

function writeExclusive(target, contents) {
  const temp = path.join(path.dirname(target), `.${path.basename(target)}.tmp-${process.pid}`);
  writeFileSync(temp, contents);
  publishExclusive(temp, target, "sidecar");
}

function refuseBrowserDownload() {
  fail(
    "this renderer never downloads a browser; install Chrome/Chromium locally or pass " +
      "`chrome` in the request (or set REMOTION_CHROME)",
  );
}

/** The renderer only reads local loopback/data assets; a real fetch is refused. */
function refuseRemoteAsset(src) {
  if (typeof src === "string" && src.startsWith("data:")) return;
  fail(`remote asset fetch is disabled for this renderer; refusing ${JSON.stringify(src)}`);
}

async function run() {
  const {help, requestPath, cacheRoot, progressFile, benchmarkProfile} = parseArgs(process.argv.slice(2));
  if (help) {
    process.stdout.write(`${USAGE}\n`);
    return;
  }
  const progress = createProgressWriter(progressFile);
  progress.update({phase: "validating-request"});
  try {
    await render(progress, requestPath, cacheRoot, benchmarkProfile);
  } finally {
    progress.close();
  }
}

async function render(progress, requestPath, cacheRoot, benchmarkProfile) {
  const totalStarted = performance.now();
  const diagnostics = createDiagnostics();
  const request = loadRequest(requestPath);
  const normalized = validateRequest(request);
  // Explicit experimental policy, never a fallback or a production default.
  // No CRF: 20 Mbit/s target is not quality-equivalent to the default libx264.
  const benchmarkOptions = resolveBenchmarkOptions(benchmarkProfile, normalized.kind);
  const sha = requestSha256(request);
  if (existsSync(normalized.output)) {
    fail(`output ${normalized.output} already exists; refusing to overwrite`);
  }
  const settings = KIND_SETTINGS[normalized.kind];
  const chrome = normalized.chrome ?? resolveChrome(undefined);

  const cacheKey = bundleKey(normalized.assetRoot);
  const cacheDir = path.join(cacheRoot, cacheKey);
  const bundleStarted = performance.now();
  const {serveUrl, bundleCached} = await ensureBundle(cacheDir, normalized.assetRoot, progress);
  const bundleMs = performance.now() - bundleStarted;

  const inputProps = {
    kind: normalized.kind,
    width: normalized.width,
    height: normalized.height,
    fps: normalized.fps,
    frames: normalized.frames,
    input:
      normalized.kind === "graphics"
        ? {...normalized.input, part: normalized.part}
        : normalized.input,
  };
  const shared = {
    serveUrl,
    inputProps,
    browserExecutable: chrome,
    chromiumOptions: {headless: true},
    onBrowserDownload: refuseBrowserDownload,
    logLevel: "error",
  };

  progress.update({phase: "selecting-composition"});
  const started = process.hrtime.bigint();
  const composition = await selectComposition({...shared, id: settings.compositionId});
  const setupMs = Number(process.hrtime.bigint() - started) / 1e6;
  let renderMediaMs;
  if (normalized.kind === "stills") {
    const stills = await renderStills(progress, shared, composition, normalized);
    const report = {
      frames: normalized.frames,
      width: normalized.width,
      height: normalized.height,
      fps: normalized.fps,
      kind: normalized.kind,
      request_sha256: sha,
      render_seconds: Number((Number(process.hrtime.bigint() - started) / 1e9).toFixed(3)),
      remotion_version: remotionVersion(),
      bundle_cached: bundleCached,
      stills,
      diagnostics: {bundle_ms: bundleMs, composition_setup_ms: setupMs,
        total_ms: performance.now() - totalStarted},
    };
    const sidecarPath = `${normalized.output}.render.json`;
    writeExclusive(sidecarPath, `${JSON.stringify(report, null, 2)}\n`);
    process.stdout.write(`${JSON.stringify({...report, output: normalized.output, sidecar: sidecarPath})}\n`);
    return;
  }
  const extension = path.extname(normalized.output);
  const tempOutput = path.join(
    path.dirname(normalized.output),
    `.${path.basename(normalized.output, extension)}.render-${process.pid}${extension}`,
  );
  try {
    progress.update({
      phase: "rendering-frames",
      done: 0,
      total: normalized.frames,
      unit: "frames",
    });
    const mediaStarted = performance.now();
    await renderMedia({
      ...shared,
      ...benchmarkOptions,
      composition,
      codec: settings.codec,
      outputLocation: tempOutput,
      imageFormat: settings.imageFormat,
      pixelFormat: settings.pixelFormat,
      colorSpace: normalized.kind === "base" ? "bt709" : "default",
      proResProfile: settings.proResProfile,
      muted: true,
      enforceAudioTrack: false,
      overwrite: false,
      concurrency: normalized.concurrency,
      onDownload: refuseRemoteAsset,
      onStart: diagnostics.onStart,
      ffmpegOverride: diagnostics.ffmpegOverride,
      onProgress: (info) => {
        diagnostics.onProgress(info);
        const done = Number(info?.renderedFrames ?? info?.encodedFrames ?? 0);
        progress.update({
          phase: "rendering-frames",
          done: Number.isFinite(done) ? done : 0,
          total: normalized.frames,
          unit: "frames",
        });
      },
    });
    renderMediaMs = performance.now() - mediaStarted;
    const size = statSync(tempOutput, {throwIfNoEntry: false})?.size ?? 0;
    if (size <= 0) fail(`renderer produced no frames at ${tempOutput}`);
    progress.update({phase: "publishing-output"});
    publishExclusive(tempOutput, normalized.output, "output");
  } finally {
    rmSync(tempOutput, {force: true});
  }
  const renderSeconds = Number(process.hrtime.bigint() - started) / 1e9;

  const sidecarPath = `${normalized.output}.render.json`;
  const report = {
    frames: normalized.frames,
    width: normalized.width,
    height: normalized.height,
    fps: normalized.fps,
    kind: normalized.kind,
    request_sha256: sha,
    render_seconds: Number(renderSeconds.toFixed(3)),
    remotion_version: remotionVersion(),
    bundle_cached: bundleCached,
    diagnostics: {
      ...diagnostics.data,
      ...(benchmarkProfile ? {benchmark_profile: benchmarkProfile,
        benchmark_policy: benchmarkOptions,
        benchmark_fallback: "forbidden: hardware acceleration required"} : {}),
      bundle_ms: bundleMs,
      composition_setup_ms: setupMs,
      render_media_ms: renderMediaMs,
      total_ms: performance.now() - totalStarted,
      requested: {codec: settings.codec, imageFormat: settings.imageFormat,
        pixelFormat: settings.pixelFormat, concurrency: normalized.concurrency},
    },
  };
  writeExclusive(sidecarPath, `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`${JSON.stringify({...report, output: normalized.output, sidecar: sidecarPath})}\n`);
}

/** Render each requested frame to PNG in a private directory, then publish it whole. */
async function renderStills(progress, shared, composition, normalized) {
  const temp = path.join(
    path.dirname(normalized.output),
    `.${path.basename(normalized.output)}.render-${process.pid}`,
  );
  mkdirSync(temp);
  try {
    const stills = [];
    for (const [index, frame] of normalized.stills.entries()) {
      progress.update({phase: "rendering-stills", done: index, total: normalized.stills.length,
        unit: "stills"});
      const name = `f${String(frame).padStart(5, "0")}.png`;
      await renderStill({
        ...shared,
        composition,
        frame,
        output: path.join(temp, name),
        imageFormat: "png",
        overwrite: false,
        onDownload: refuseRemoteAsset,
      });
      stills.push({frame, file: name, sha256: sha256File(path.join(temp, name))});
    }
    progress.update({phase: "publishing-output"});
    if (existsSync(normalized.output)) fail(`output ${normalized.output} already exists; refusing to overwrite`);
    renameSync(temp, normalized.output);
    return stills;
  } finally {
    rmSync(temp, {recursive: true, force: true});
  }
}

run().catch((error) => {
  process.stderr.write(`${error?.message ?? error}\n`);
  process.exitCode = 1;
});
