// Pure frame functions shared by the Remotion components, the render CLI and
// node:test. Nothing here reads a clock, a random number, the DOM, the network
// or the filesystem: every value is a function of an explicit frame index.
//
// The timing model mirrors the local FFmpeg renderer (src/mp3_to_videoclip/render.py):
// every shot owns exactly `duration_frames` of the final output and may carry
// `dissolve_frames` extra *handle* frames that are only ever consumed while the
// next shot fades in over it. sum(duration + dissolve) - sum(dissolve) ==
// sum(duration), so a transition can never shorten the allocated film.

/** Restrained legacy camera moves, mirroring render.py `ZOOM_RANGE`. */
export const ZOOM_RANGE = 0.08;
export const CAMERA_MOVES = ["hold", "zoom_in", "zoom_out", "pan_left", "pan_right"];

/** Local graphics fade constants, mirroring graphics.py. */
export const INTRO_REFERENCE_SECONDS = 25.0;
export const MIN_CAPTION_GAP = 0.25;
export const SAFE_MARGIN = 0.07;

/**
 * Brand plate window. models.BrandPackage.duration_seconds defaults to 8
 * (5..10) and render.py fades it in/out over BRAND_PLATE_FADE_SECONDS.
 */
export const BRAND_PLATE_SECONDS = 8;
export const BRAND_PLATE_FADE_SECONDS = 0.5;

/** Accepted image filenames: a flat, safe basename compiled by Python. */
export const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp"];
const SAFE_ASSET_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const SCHEME_RE = /^[A-Za-z][A-Za-z0-9+.-]*:/;

export function fail(message) {
  throw new Error(message);
}

export function clamp(value, low, high) {
  return Math.min(Math.max(value, low), high);
}

export function clamp01(value) {
  return clamp(Number(value), 0, 1);
}

/** Smoothstep 0..1, identical to graphics.py `ramp` / render.py progress shaping. */
export function smoothstep(progress) {
  const p = clamp01(progress);
  return p * p * (3 - 2 * p);
}

export function easingName(value) {
  if (value === undefined || value === null) return "linear";
  if (value !== "linear" && value !== "smoothstep") {
    fail(`unsupported easing ${JSON.stringify(value)}; expected "linear" or "smoothstep"`);
  }
  return value;
}

export function ease(progress, easing = "linear") {
  return easing === "smoothstep" ? smoothstep(progress) : clamp01(progress);
}

function requireIndex(value, label, {allowZero = true} = {}) {
  if (!Number.isInteger(value) || (allowZero ? value < 0 : value <= 0)) {
    fail(`${label} must be ${allowZero ? "a non-negative" : "a positive"} integer, got ${JSON.stringify(value)}`);
  }
  return value;
}

function requireNumber(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail(`${label} must be a finite number, got ${JSON.stringify(value)}`);
  }
  return value;
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

// --------------------------------------------------------------------------- //
// base film: asset names, spans, layers
// --------------------------------------------------------------------------- //
export function validateAssetName(name) {
  if (typeof name !== "string" || name.length === 0) {
    fail("shot image must be a non-empty string");
  }
  if (SCHEME_RE.test(name)) {
    fail(`shot image ${JSON.stringify(name)} looks like a URL/scheme; remote or absolute sources are not allowed`);
  }
  if (name.includes("/") || name.includes("\\")) {
    fail(`shot image ${JSON.stringify(name)} contains a path separator; use a flat relative asset filename`);
  }
  if (name === "." || name === ".." || name.startsWith(".")) {
    fail(`shot image ${JSON.stringify(name)} is not a safe asset filename`);
  }
  if (!SAFE_ASSET_RE.test(name)) {
    fail(`shot image ${JSON.stringify(name)} is not a safe asset filename`);
  }
  const lower = name.toLowerCase();
  if (!IMAGE_EXTENSIONS.some((extension) => lower.endsWith(extension))) {
    fail(
      `shot image ${JSON.stringify(name)} must end with one of ${IMAGE_EXTENSIONS.join(", ")}`,
    );
  }
  return name;
}

/**
 * Validate the declared shot list and allocate its absolute frame spans.
 *
 * Returns `{spans, totalFrames}` where each span is the shot plus its resolved
 * `handle` (== `dissolve_frames`) and `handleEnd` (the exclusive frame where its
 * plate finally stops being needed). Allocation is contiguous: a declared
 * `start_frame` that does not equal the running sum of durations fails instead
 * of being silently reordered or shortened.
 */
export function allocateSpans(shots) {
  if (!Array.isArray(shots) || shots.length === 0) {
    fail("shots must be a non-empty array");
  }
  const ids = new Set();
  const spans = [];
  let cursor = 0;
  shots.forEach((shot, index) => {
    if (shot === null || typeof shot !== "object") {
      fail(`shot ${index} must be an object`);
    }
    if (typeof shot.id !== "string" || shot.id.length === 0) {
      fail(`shot ${index} needs a non-empty string id`);
    }
    if (ids.has(shot.id)) fail(`shot id ${JSON.stringify(shot.id)} is not unique`);
    ids.add(shot.id);
    const duration = requireIndex(shot.duration_frames, `shot ${shot.id} duration_frames`, {
      allowZero: false,
    });
    const start = requireIndex(shot.start_frame, `shot ${shot.id} start_frame`);
    if (start !== cursor) {
      fail(
        `shot ${shot.id} start_frame ${start} breaks the contiguous timeline; expected ${cursor}`,
      );
    }
    const handle = requireIndex(shot.dissolve_frames ?? 0, `shot ${shot.id} dissolve_frames`);
    if (handle > 0 && index === shots.length - 1) {
      fail(`last shot ${shot.id} cannot dissolve into a missing shot`);
    }
    validateAssetName(shot.image);
    spans.push({
      ...shot,
      index,
      start_frame: start,
      duration_frames: duration,
      dissolve_frames: handle,
      handle,
      handleEnd: start + duration + handle,
    });
    cursor += duration;
  });
  spans.forEach((span) => {
    if (span.handle === 0) return;
    const next = spans[span.index + 1];
    if (span.handle >= Math.min(span.duration_frames, next.duration_frames)) {
      fail(
        `shot ${span.id} dissolve_frames ${span.handle} must be shorter than both adjacent shots`,
      );
    }
  });
  return {spans, totalFrames: cursor};
}

/** The shot that owns the *allocated* frame `frame`, or -1. */
export function allocatedIndex(spans, frame) {
  if (frame < 0) return -1;
  for (let i = spans.length - 1; i >= 0; i -= 1) {
    if (frame >= spans[i].start_frame && frame < spans[i].start_frame + spans[i].duration_frames) {
      return i;
    }
  }
  return -1;
}

/**
 * Incoming opacity over `handle` frames, starting at the incoming shot's
 * declared `start_frame`: 0 at the first overlap frame, smoothstep towards 1,
 * and exactly 1 from `start_frame + handle` onwards (the frame where the
 * outgoing plate is removed).
 */
export function dissolveAlpha(frame, startFrame, handle) {
  const k = frame - startFrame;
  if (k <= 0) return 0;
  if (handle <= 0 || k >= handle) return 1;
  return smoothstep(k / handle);
}

/**
 * The at-most-two layers visible at absolute `frame`, bottom first.
 *
 * `[{index, localFrame, alpha, progress}]`. During an overlap the outgoing shot
 * keeps rendering its own handle frames at alpha 1 and the incoming shot fades
 * in over it; nothing is shortened and no third layer is ever produced.
 */
export function visibleLayers(spans, frame) {
  const index = allocatedIndex(spans, frame);
  if (index < 0) return [];
  const span = spans[index];
  const previous = index > 0 ? spans[index - 1] : null;
  const layers = [];
  let alpha = 1;
  let progress = 1;
  if (previous && previous.handle > 0) {
    const k = frame - span.start_frame;
    if (k < previous.handle) {
      progress = k / previous.handle;
      alpha = dissolveAlpha(frame, span.start_frame, previous.handle);
      const localFrame = frame - previous.start_frame;
      if (localFrame < 0 || localFrame >= previous.duration_frames + previous.handle) {
        fail(
          `shot ${previous.id} handle exhausted at frame ${frame} (local ${localFrame}); ` +
            "the timeline would have to overlap a third layer",
        );
      }
      layers.push({index: index - 1, localFrame, alpha: 1, progress: 1});
    }
  }
  const localFrame = frame - span.start_frame;
  if (localFrame < 0 || localFrame >= span.duration_frames + span.handle) {
    fail(`shot ${span.id} has no plate frame for local frame ${localFrame}`);
  }
  layers.push({index, localFrame, alpha, progress});
  return layers;
}

// --------------------------------------------------------------------------- //
// camera and post effects
// --------------------------------------------------------------------------- //
/** Legacy selectors, mirroring render.py `_zoompan` exactly. */
export function legacyCamera(move, progress) {
  if (!CAMERA_MOVES.includes(move)) {
    fail(`unsupported camera ${JSON.stringify(move)}; expected one of ${CAMERA_MOVES.join(", ")}`);
  }
  const p = clamp01(progress);
  const centre = 0.5;
  if (move === "hold") return {zoom: 1, x: centre, y: centre};
  if (move === "zoom_in") return {zoom: 1 + ZOOM_RANGE * p, x: centre, y: centre};
  if (move === "zoom_out") return {zoom: 1 + ZOOM_RANGE - ZOOM_RANGE * p, x: centre, y: centre};
  if (move === "pan_left") return {zoom: 1 + ZOOM_RANGE, x: 1 - p, y: centre};
  return {zoom: 1 + ZOOM_RANGE, x: p, y: centre};
}

/** Explicit frame-based keyframes: interpolated between their own frames, clamped outside. */
export function keyframeCamera(keyframes, frame) {
  if (!Array.isArray(keyframes) || keyframes.length === 0) {
    fail("camera_keyframes must be a non-empty array when present");
  }
  const sorted = keyframes.map((keyframe, index) => {
    if (keyframe === null || typeof keyframe !== "object") {
      fail(`camera_keyframes[${index}] must be an object`);
    }
    requireIndex(keyframe.frame, `camera_keyframes[${index}].frame`);
    requireNumber(keyframe.zoom, `camera_keyframes[${index}].zoom`);
    requireNumber(keyframe.x, `camera_keyframes[${index}].x`);
    requireNumber(keyframe.y, `camera_keyframes[${index}].y`);
    if (keyframe.zoom < 1 || keyframe.zoom > 2 || keyframe.x < 0 || keyframe.x > 1 || keyframe.y < 0 || keyframe.y > 1) {
      fail(`camera_keyframes[${index}] is outside the bounded crop contract`);
    }
    return {...keyframe};
  });
  if (sorted[0].frame !== 0) fail("camera_keyframes must begin at zero");
  for (let i = 1; i < sorted.length; i += 1) {
    if (sorted[i].frame <= sorted[i - 1].frame) {
      fail(`camera_keyframes must be strictly ordered: ${sorted[i].frame}`);
    }
  }
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (frame <= first.frame) return {zoom: first.zoom, x: first.x, y: first.y};
  if (frame >= last.frame) return {zoom: last.zoom, x: last.x, y: last.y};
  for (let i = 0; i < sorted.length - 1; i += 1) {
    const a = sorted[i];
    const b = sorted[i + 1];
    if (frame >= a.frame && frame < b.frame) {
      const t = (frame - a.frame) / (b.frame - a.frame);
      return {zoom: lerp(a.zoom, b.zoom, t), x: lerp(a.x, b.x, t), y: lerp(a.y, b.y, t)};
    }
  }
  return {zoom: last.zoom, x: last.x, y: last.y};
}

/**
 * Camera framing for one local frame of a shot's plate.
 *
 * Progress runs over the shot's whole allocated plate (`duration + handle - 1`)
 * exactly like render.py, is clamped outside that window (so a negative or
 * over-run frame can never produce NaN or a mirrored crop), and is shaped by the
 * camera path's easing. Explicit `camera_keyframes` take precedence and are
 * interpolated on their own frames.
 */
export function cameraAtFrame(span, frame) {
  const last = Math.max(span.duration_frames + span.handle - 1, 1);
  const local = clamp(Math.round(frame), 0, last);
  if (Array.isArray(span.camera_keyframes) && span.camera_keyframes.length > 0) {
    return keyframeCamera(span.camera_keyframes, local);
  }
  if (span.camera_path !== undefined && span.camera_path !== null) {
    const path = span.camera_path;
    if (typeof path !== "object") fail(`shot ${span.id} camera_path must be an object`);
    const start = path.start ?? {};
    const end = path.end ?? {};
    const eased = ease(local / last, easingName(path.easing));
    return {
      zoom: lerp(Number(start.zoom ?? 1), Number(end.zoom ?? 1), eased),
      x: lerp(Number(start.x ?? 0.5), Number(end.x ?? 0.5), eased),
      y: lerp(Number(start.y ?? 0.5), Number(end.y ?? 0.5), eased),
    };
  }
  return legacyCamera(span.camera ?? "zoom_in", local / last);
}

/**
 * CSS box for a camera framing. x/y are normalized inside the *available* crop
 * overflow (0 = left/top edge of what the zoom exposes, 1 = right/bottom), so
 * the layer is `zoom` times the canvas and slid by the overflow the zoom reveals.
 */
export function layerRect({width, height, zoom, x, y}) {
  requireNumber(zoom, "camera zoom");
  if (zoom < 1) fail(`camera zoom must be >= 1, got ${zoom}`);
  const layerWidth = width * zoom;
  const layerHeight = height * zoom;
  return {
    width: layerWidth,
    height: layerHeight,
    left: -(layerWidth - width) * clamp01(x),
    top: -(layerHeight - height) * clamp01(y),
  };
}

export const POST_EFFECT_RANGES = {
  contrast: [1, 1.2],
  saturation: [0.7, 1.3],
  brightness: [0.9, 1.1],
  vignette: [0, 0.3],
};

/**
 * Validate `post_effects` and resolve it to CSS.
 *
 * An unknown key is rejected rather than ignored, so a typo cannot silently
 * produce an ungraded film.
 */
export function postEffectsStyle(postEffects) {
  if (postEffects === undefined || postEffects === null) {
    return {filter: "none", vignette: 0, values: {}};
  }
  if (typeof postEffects !== "object" || Array.isArray(postEffects)) {
    fail("post_effects must be an object");
  }
  const filters = [];
  const values = {};
  for (const [key, raw] of Object.entries(postEffects)) {
    const range = POST_EFFECT_RANGES[key];
    if (!range) {
      fail(
        `unsupported post_effects key ${JSON.stringify(key)}; expected one of ` +
          `${Object.keys(POST_EFFECT_RANGES).join(", ")}`,
      );
    }
    const value = requireNumber(raw, `post_effects.${key}`);
    if (value < range[0] || value > range[1]) {
      fail(`post_effects.${key} must be between ${range[0]} and ${range[1]}, got ${value}`);
    }
    values[key] = value;
    if (key === "contrast") filters.push(`contrast(${value})`);
    else if (key === "saturation") filters.push(`saturate(${value})`);
    else if (key === "brightness") filters.push(`brightness(${value})`);
  }
  return {filter: filters.length > 0 ? filters.join(" ") : "none", vignette: values.vignette ?? 0, values};
}

export const TRANSITIONS = ["fade", "wipe_left", "wipe_right"];

export function transitionName(value) {
  if (value === undefined || value === null) return "fade";
  if (!TRANSITIONS.includes(value)) {
    fail(`unsupported transition ${JSON.stringify(value)}; expected one of ${TRANSITIONS.join(", ")}`);
  }
  return value;
}

/**
 * The incoming shot's reveal at `progress` (0..1).
 *
 * `fade` drives opacity; a wipe drives a `clipPath: inset(...)` that reveals the
 * incoming plate from its own starting edge. Both are frame functions of the
 * same eased progress, so a wipe never depends on a CSS clock.
 */
export function transitionStyle(transition, progress) {
  const kind = transitionName(transition);
  const p = smoothstep(progress);
  if (kind === "fade") {
    return {kind, clipPath: null, opacity: p};
  }
  const hidden = (1 - p) * 100;
  if (kind === "wipe_left") {
    return {kind, clipPath: `inset(0 ${hidden}% 0 0)`, opacity: 1};
  }
  return {kind, clipPath: `inset(0 0 0 ${hidden}%)`, opacity: 1};
}

// --------------------------------------------------------------------------- //
// graphics timing (mirrors graphics.py joint-v1)
// --------------------------------------------------------------------------- //
export const GRAPHICS_KINDS = ["intro", "identity", "card", "lockup", "caption"];
export const CAPTION_STYLES = ["caption"];

/**
 * Joint wordmark separators. The names themselves are never invented or
 * rewritten: only a separator *glyph* is normalised to the accent diamond the
 * identity reference asks for, and a name string without a separator is drawn
 * exactly as supplied.
 */
const NAME_SEPARATOR_RE = /(\s+[×xX·◆|/&]\s+)/;
const NAME_SEPARATOR_ONLY_RE = /^[×xX·◆|/&]$/;

export function splitNames(names) {
  if (typeof names !== "string" || names.trim().length === 0) {
    return {parts: [], separator: false};
  }
  const parts = names
    .split(NAME_SEPARATOR_RE)
    .map((token) => token.trim())
    .filter((token) => token.length > 0 && !NAME_SEPARATOR_ONLY_RE.test(token));
  if (parts.length <= 1) return {parts: [names], separator: false};
  return {parts, separator: true};
}

/** The ``joint-v1`` opening choreography, in reference seconds (graphics.py). */
export const JOINT_INTRO_PHASES = {
  scrim: [0.8, 2.0, 24.2, 25.0],
  mark: [0.6, 1.8, 7.6, 8.8],
  names: [2.6, 3.8, 7.4, 8.6],
  title: [8.4, 9.8, 12.1, 13.0],
  time: [13.1, 14.1, 16.9, 17.7],
  mini_credits_1: [17.3, 18.2, 19.5, 20.2],
  mini_credits_2: [19.8, 20.7, 21.9, 22.5],
  tagline: [22.2, 23.0, 24.3, 24.9],
  notes_1: [22.9, 23.5, 24.4, 25.0],
  notes_2: [23.1, 23.7, 24.6, 25.0],
};
export const INTRO_PHASE_NAMES = Object.keys(JOINT_INTRO_PHASES);

/** graphics.py `ramp`: smoothstep 0..1 over [start, end]. */
export function rampAt(t, start, end) {
  return smoothstep((t - start) / Math.max(end - start, 1e-9));
}

/** One named opening phase's opacity at film seconds `t`. */
export function introPhaseAlpha(t, phase, introSeconds) {
  const table = JOINT_INTRO_PHASES[phase];
  if (!table) {
    fail(`unknown intro phase ${JSON.stringify(phase)}; expected one of ${INTRO_PHASE_NAMES.join(", ")}`);
  }
  const k = Number(introSeconds) / INTRO_REFERENCE_SECONDS;
  const [inStart, inEnd, outStart, outEnd] = table;
  return rampAt(t, inStart * k, inEnd * k) * (1 - rampAt(t, outStart * k, outEnd * k));
}

/** All opening phase opacities for one time, for a single scrim/element pass. */
export function introPhasesAt(t, introSeconds) {
  const result = {};
  for (const name of INTRO_PHASE_NAMES) {
    result[name] = introPhaseAlpha(t, name, introSeconds);
  }
  return result;
}

/** graphics.py element fade: in at 0, out at `seconds`, over `fade`. */
export function graphicsFade(localSeconds, seconds, fade) {
  return rampAt(localSeconds, 0, fade) * (1 - rampAt(localSeconds, seconds - fade, seconds));
}

/** Per-kind fade length, mirroring graphics.py. */
export function graphicsFadeSeconds(kind, seconds) {
  if (kind === "identity") return Math.min(0.6, seconds / 4);
  if (kind === "caption") return Math.min(MIN_CAPTION_GAP, seconds / 4);
  return 0.5;
}

export function graphicsAlpha(kind, localSeconds, seconds) {
  return graphicsFade(localSeconds, seconds, graphicsFadeSeconds(kind, seconds));
}

/** Reject anything the renderer does not actually draw, instead of ignoring it. */
export function validateCaptionPart(caption, partId) {
  if (caption === null || typeof caption !== "object") {
    fail(`caption part ${partId} needs a caption object`);
  }
  if (typeof caption.id !== "string" || caption.id.length === 0) {
    fail(`caption part ${partId} needs a non-empty string id`);
  }
  if (!CAPTION_STYLES.includes(caption.style)) {
    fail(
      `caption ${caption.id} style ${JSON.stringify(caption.style)} is not supported by this renderer; ` +
        `only ${CAPTION_STYLES.join(", ")} is drawn (SFX bursts are not ignored, they are rejected)`,
    );
  }
  if (typeof caption.text !== "string" || caption.text.length === 0) {
    fail(`caption ${caption.id} needs non-empty text`);
  }
  return caption;
}

/** Validate a graphics `part` and return it with its resolved frame window. */
export function validateGraphicsPart(part, requestFrames) {
  if (part === null || typeof part !== "object") fail("graphics input.part must be an object");
  if (!GRAPHICS_KINDS.includes(part.kind)) {
    fail(
      `unsupported graphics part kind ${JSON.stringify(part.kind)}; expected one of ${GRAPHICS_KINDS.join(", ")}`,
    );
  }
  const frames = part.frames ?? requestFrames;
  requireIndex(frames, `graphics part ${part.kind} frames`, {allowZero: false});
  if (requestFrames !== undefined && frames !== requestFrames) {
    fail(
      `graphics part ${part.kind} frames ${frames} does not match the requested ${requestFrames}`,
    );
  }
  if (part.kind === "card") {
    const card = part.card;
    if (!Array.isArray(card) || card.length !== 2 || card.some((value) => typeof value !== "string" || value.length === 0)) {
      fail(`card part ${part.id ?? "?"} needs card: [role, name]`);
    }
  }
  if (part.kind === "caption") {
    validateCaptionPart(part.caption, part.id ?? "?");
  }
  return {...part, frames};
}

/** Graphic kinds that must be fully transparent at the given time. */
export function partIsVisible(kind, localSeconds, seconds) {
  return graphicsAlpha(kind, localSeconds, seconds) > 0;
}
