// Request validation and local-path safety for the render CLI.
//
// Pure except for read-only `node:fs`/`node:path` checks: this module never
// writes, never fetches and never launches a browser. The CLI owns the
// side-effecting half.
import {createHash} from "node:crypto";
import {existsSync, statSync} from "node:fs";
import path from "node:path";

import {
  allocateSpans,
  flashViolations,
  postEffectsStyle,
  transitionName,
  validateEditShot,
  validateGrade,
  validateGraphicsPart,
  validateSplitPanes,
} from "./timing.mjs";
import {validateCompactLayout} from "./compact.mjs";

export const KIND_EXTENSIONS = {base: ".mp4", graphics: ".mov"};
export const MAX_CONCURRENCY = 3;
export const DEFAULT_CONCURRENCY = 2;
const SCHEME_RE = /^[A-Za-z][A-Za-z0-9+.-]*:\/\//;

export function fail(message) {
  throw new Error(message);
}

export function canonicalJson(value) {
  return JSON.stringify(value, (_key, item) => {
    if (item === null || typeof item !== "object" || Array.isArray(item)) return item;
    return Object.fromEntries(Object.keys(item).sort().map((key) => [key, item[key]]));
  });
}

export function sha256(value) {
  return createHash("sha256").update(value).digest("hex");
}

export function requestSha256(request) {
  return sha256(canonicalJson(request));
}

/** Reject remote/relative/scheme outputs; the renderer only writes locally. */
export function localAbsolutePath(value, label) {
  if (typeof value !== "string" || value.length === 0) {
    fail(`${label} must be a non-empty absolute local path`);
  }
  if (SCHEME_RE.test(value) || value.startsWith("//")) {
    fail(`${label} ${JSON.stringify(value)} must be a local path, not a URL`);
  }
  if (!path.isAbsolute(value)) {
    fail(`${label} ${JSON.stringify(value)} must be absolute`);
  }
  return path.normalize(value);
}

export function requireInteger(value, label, {min = 1} = {}) {
  if (!Number.isInteger(value) || value < min) {
    fail(`${label} must be an integer >= ${min}, got ${JSON.stringify(value)}`);
  }
  return value;
}

export function resolveConcurrency(value) {
  if (value === undefined || value === null) return DEFAULT_CONCURRENCY;
  requireInteger(value, "concurrency", {min: 1});
  if (value > MAX_CONCURRENCY) {
    fail(`concurrency ${value} exceeds the maximum of ${MAX_CONCURRENCY}`);
  }
  return value;
}

export function resolveChrome(requestChrome, env = process.env) {
  const explicit = requestChrome ?? env.REMOTION_CHROME ?? env.CHROME_PATH;
  if (explicit) {
    const resolved = localAbsolutePath(explicit, "chrome");
    if (!existsSync(resolved)) fail(`chrome executable ${resolved} does not exist`);
    return resolved;
  }
  const candidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
  ];
  const found = candidates.filter((candidate) => existsSync(candidate));
  if (found.length === 0) {
    fail(
      "no local Chrome/Chromium executable found; pass chrome in the request or set " +
        "REMOTION_CHROME. This renderer never downloads a browser on its own.",
    );
  }
  return found[0];
}

export function outputExtension(kind) {
  return KIND_EXTENSIONS[kind] ?? fail(`unsupported kind ${JSON.stringify(kind)}`);
}

export function requireExistingDirectory(value, label) {
  const resolved = localAbsolutePath(value, label);
  if (!existsSync(resolved) || !statSync(resolved).isDirectory()) {
    fail(`${label} ${resolved} is not an existing local directory`);
  }
  return resolved;
}

/** Validate the whole request shape and return a normalized copy. */
export function validateRequest(request) {
  if (request === null || typeof request !== "object" || Array.isArray(request)) {
    fail("request must be a JSON object");
  }
  const kind = request.kind;
  if (kind !== "base" && kind !== "graphics") {
    fail(`request.kind must be "base" or "graphics", got ${JSON.stringify(kind)}`);
  }
  const output = localAbsolutePath(request.output, "output");
  const extension = outputExtension(kind);
  if (path.extname(output) !== extension) {
    fail(`${kind} output must end with ${extension}, got ${output}`);
  }
  const width = requireInteger(request.width, "width");
  const height = requireInteger(request.height, "height");
  const fps = requireInteger(request.fps, "fps");
  const frames = requireInteger(request.frames, "frames");
  const assetRoot = requireExistingDirectory(request.assetRoot, "assetRoot");
  const chrome = request.chrome === undefined || request.chrome === null
    ? null
    : resolveChrome(request.chrome);
  const concurrency = resolveConcurrency(request.concurrency);
  const input = request.input;
  if (input === null || typeof input !== "object" || Array.isArray(input)) {
    fail("request.input must be an object");
  }
  const normalized = {kind, output, width, height, fps, frames, assetRoot, chrome, concurrency, input};
  if (kind === "base") {
    normalized.base = validateBaseInput(input, fps);
    if (normalized.base.totalFrames !== frames) fail("shot allocations must equal requested frames");
  } else {
    normalized.part = validateGraphicsPart(input.part, frames);
    validateTitleAssets(input);
    validateCompactLayout(input.spec.layout, normalized.part);
  }
  return normalized;
}

/** The spec, logo and font a title element is drawn from: local bytes only. */
export function validateTitleAssets(input) {
  if (input.spec === null || typeof input.spec !== "object") {
    fail("graphics input.spec must be the resolved graphics spec object");
  }
  if (typeof input.logo !== "string" || !input.logo.startsWith("data:image/svg+xml;base64,")) {
    fail("graphics logo must be an embedded local SVG, never a remote URL or black-background raster");
  }
  const svg = Buffer.from(input.logo.split(",")[1], "base64").toString("utf8");
  if (/<script|<foreignObject|\bhref\s*=|https?:\/\//i.test(svg.replace('xmlns="http://www.w3.org/2000/svg"', ''))) {
    fail("SVG logo must not load external resources or scripts");
  }
  if (input.font != null && (typeof input.font !== "string" || !input.font.startsWith("data:font/"))) {
    fail("graphics font must be local embedded bytes or the local system stack");
  }
}

/**
 * Planned titles over a base film: integer-frame windows in order, never
 * overlapping and never past the film, each a drawable title element.
 */
export function validateTitles(titles, totalFrames) {
  if (titles === null || typeof titles !== "object" || Array.isArray(titles)) {
    fail("base input.titles must be an object");
  }
  if (!Array.isArray(titles.windows) || titles.windows.length === 0) {
    fail("base input.titles.windows must be a non-empty array");
  }
  validateTitleAssets(titles);
  const ids = new Set();
  let end = 0;
  const windows = titles.windows.map((window) => {
    const part = validateGraphicsPart(window);
    const start = requireInteger(window.start_frame, `title ${window.id ?? "?"} start_frame`, {min: 0});
    if (typeof window.id !== "string" || window.id.length === 0 || ids.has(window.id)) {
      fail(`title windows need unique non-empty ids, got ${JSON.stringify(window.id)}`);
    }
    ids.add(window.id);
    if (start < end) fail(`title ${window.id} starts before the previous window ends`);
    end = start + part.frames;
    if (end > totalFrames) fail(`title ${window.id} ends at frame ${end}, past the film's ${totalFrames}`);
    validateCompactLayout(titles.spec.layout, part);
    return {...part, start_frame: start};
  });
  return windows;
}

export function validateBaseInput(input, fps) {
  if (!Array.isArray(input.shots) || input.shots.length === 0) {
    fail("base input.shots must be a non-empty array");
  }
  const {spans, totalFrames} = allocateSpans(input.shots);
  if (input.preview_placeholders !== undefined) {
    if (!Array.isArray(input.preview_placeholders)) {
      fail("base input.preview_placeholders must be an array of shot ids");
    }
    const known = new Set(spans.map((span) => span.id));
    for (const id of input.preview_placeholders) {
      if (!known.has(id)) {
        fail(`preview_placeholders references unknown shot id ${JSON.stringify(id)}`);
      }
    }
  }
  if (input.preview_banner !== undefined && typeof input.preview_banner !== "boolean") {
    fail("base input.preview_banner must be a boolean");
  }
  if (input.brand_plate !== undefined && input.brand_plate !== null) {
    if (typeof input.brand_plate !== "string" || !input.brand_plate.startsWith("data:image/")) {
      fail("base input.brand_plate must be a data:image/... URL");
    }
  }
  // Validate camera/effect payloads up front so a bad request fails before bundling.
  for (const span of spans) {
    postEffectsStyle(span.post_effects);
    const transition = span.transition;
    if (transition !== undefined && transition !== null) {
      transitionName(transition);
    }
    if (span.edit !== undefined && span.edit !== null) {
      validateEditShot(span.edit, span);
    }
    if (span.grade !== undefined && span.grade !== null) {
      validateGrade(span.grade);
    }
    if (span.split_panes !== undefined && span.split_panes !== null) {
      validateSplitPanes(span.split_panes, span.id);
    }
  }
  const flashes = flashViolations(spans, fps);
  if (flashes.length > 0) {
    const first = flashes[0];
    fail(
      `flash limit exceeded: ${first.frames} flashes inside ${first.window_frames} frames ` +
        `starting at ${first.start_frame}; at most 3 per second are allowed`,
    );
  }
  const titles =
    input.titles === undefined || input.titles === null
      ? null
      : validateTitles(input.titles, totalFrames);
  return {spans, totalFrames, preview_placeholders: input.preview_placeholders ?? [], titles};
}
