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
  const base = [];
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
    const start = requireIndex(shot.start_frame, `shot ${shot.id} start_frame`);
    const duration = requireIndex(shot.duration_frames, `shot ${shot.id} duration_frames`, {
      allowZero: false,
    });
    if (start !== cursor) {
      fail(
        `shot ${shot.id} start_frame ${start} breaks the contiguous timeline; expected ${cursor}`,
      );
    }
    const legacyHandle = requireIndex(
      shot.dissolve_frames ?? 0,
      `shot ${shot.id} dissolve_frames`,
    );
    if (legacyHandle > 0 && index === shots.length - 1) {
      fail(`last shot ${shot.id} cannot dissolve into a missing shot`);
    }
    validateAssetName(shot.image);
    if (shot.split_panes !== undefined && shot.split_panes !== null) {
      validateSplitPanes(shot.split_panes, shot.id);
    }
    if (shot.edit !== undefined && shot.edit !== null) {
      validateEditShot(shot.edit, shot);
    }
    if (shot.grade !== undefined && shot.grade !== null) {
      validateGrade(shot.grade);
    }
    base.push({
      ...shot,
      index,
      start_frame: start,
      duration_frames: duration,
      legacyHandle,
    });
    cursor += duration;
  });
  const spans = base.map((span) => {
    const next = base[span.index + 1];
    // An edit transition is owned by the incoming shot. Legacy shots keep the
    // outgoing dissolve handle exactly as before.
    const handle = next?.edit
      ? validateEditTransition(next.edit.transition_in, next.id).frames
      : span.legacyHandle;
    if (handle > 0 && span.index === base.length - 1) {
      fail(`last shot ${span.id} cannot transition into a missing shot`);
    }
    return {
      ...span,
      dissolve_frames: handle,
      handle,
      handleEnd: span.start_frame + span.duration_frames + handle,
    };
  });
  spans.forEach((span) => {
    if (span.handle === 0) return;
    const next = spans[span.index + 1];
    if (span.handle >= Math.min(span.duration_frames, next.duration_frames)) {
      fail(
        `shot ${span.id} transition ${span.handle} must be shorter than both adjacent shots`,
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
  if (span.edit?.motion) {
    const crop = activeCrop(span.edit.crops, span.edit.start_frame + local);
    if (crop) return {zoom: crop.zoom, x: crop.x ?? 0.5, y: crop.y ?? 0.5};
    return editCamera(span.edit.motion, local / last);
  }
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

/** The latest crop cut at this absolute frame, or null before the first one. */
export function activeCrop(crops, absoluteFrame) {
  if (!Array.isArray(crops)) return null;
  let active = null;
  for (const crop of crops) {
    if (crop.frame <= absoluteFrame) active = crop;
  }
  return active;
}

/** Edit-owned motion, bounded like the legacy camera. */
export function editCamera(motion, progress) {
  if (motion === null || typeof motion !== "object" || Array.isArray(motion)) {
    fail("edit motion must be an object");
  }
  const kind = motion.type ?? "hold";
  if (!EDIT_MOTIONS.includes(kind)) {
    fail(`unsupported edit motion ${JSON.stringify(kind)}; expected ${EDIT_MOTIONS.join(", ")}`);
  }
  const from = Number(motion.from ?? motion.from_scale ?? 1.0);
  const to = Number(motion.to ?? motion.to_scale ?? 1.0);
  if (!Number.isFinite(from) || !Number.isFinite(to) || from < 1 || to < 1) {
    fail("edit motion scale must be finite and >= 1");
  }
  if (from > 1.3 || to > 1.3) fail("edit motion scale must stay <= 1.3");
  const anchor = motion.anchor ?? [0.5, 0.5];
  if (!Array.isArray(anchor) || anchor.length !== 2) fail("edit motion anchor must be [x, y]");
  const x = clamp01(anchor[0]);
  const y = clamp01(anchor[1]);
  const p = ease(progress, easingName(motion.easing));
  if (kind === "hold") return {zoom: 1, x, y};
  if (kind === "push_in" || kind === "pull_back") {
    return {zoom: lerp(from, to, p), x, y};
  }
  if (kind === "pan_left") return {zoom: from, x: 1 - p, y};
  return {zoom: from, x: p, y};
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

export const EDIT_TRANSITIONS = [
  "cut",
  "fade",
  "wipe_left",
  "wipe_right",
  "dip_to_black",
  "dip_to_white",
  "whip_pan",
  "push",
  "slide",
];
export const EDIT_MOTIONS = ["hold", "push_in", "pull_back", "pan_left", "pan_right"];
export const EDIT_ACCENTS = ["punch_in", "flash", "light_leak"];
export const TEXT_ANIMATIONS = ["fade", "type_on", "slide_up", "pop", "kinetic_words"];
export const EDIT_TEXT_STYLES = ["super", "title", "lower_third", "lyric", "card"];
export const GRADE_PRESETS = {
  neutral: {contrast: 1, saturation: 1, brightness: 1, vignette: 0},
  "warm-night": {
    contrast: 1.08,
    saturation: 1.12,
    brightness: 0.97,
    vignette: 0.18,
    tint: "rgba(255, 154, 84, 0.1)",
  },
  "clean-day": {
    contrast: 1.02,
    saturation: 1.04,
    brightness: 1.05,
    vignette: 0.04,
    tint: null,
  },
  monochrome: {
    contrast: 1.12,
    saturation: 0,
    brightness: 1.02,
    vignette: 0.14,
    tint: null,
  },
  vivid: {
    contrast: 1.16,
    saturation: 1.3,
    brightness: 1.02,
    vignette: 0.06,
    tint: null,
  },
  "film-fade": {
    contrast: 0.96,
    saturation: 0.86,
    brightness: 1.04,
    vignette: 0.24,
    tint: "rgba(244, 224, 190, 0.08)",
  },
};

export function validateEditTransition(value, label = "edit transition") {
  if (value === undefined || value === null) return {type: "cut", frames: 0};
  if (typeof value !== "object" || Array.isArray(value)) fail(`${label} must be an object`);
  const type = value.type ?? "cut";
  if (!EDIT_TRANSITIONS.includes(type)) {
    fail(`${label} has unsupported type ${JSON.stringify(type)}`);
  }
  const frames = requireIndex(value.frames ?? 0, `${label}.frames`);
  if (type === "cut" && frames !== 0) fail(`${label} cut cannot have handle frames`);
  if (type !== "cut" && frames === 0) fail(`${label} ${type} needs at least one handle frame`);
  if (value.reason !== undefined && typeof value.reason !== "string") {
    fail(`${label}.reason must be a string`);
  }
  if (
    value.direction !== undefined &&
    value.direction !== null &&
    !["left", "right", "up", "down"].includes(value.direction)
  ) {
    fail(`${label}.direction must be left, right, up or down`);
  }
  return value;
}

export function validateEditMotion(value) {
  if (value === undefined || value === null) return {type: "hold"};
  if (typeof value !== "object" || Array.isArray(value)) fail("edit motion must be an object");
  const type = value.type ?? "hold";
  if (!EDIT_MOTIONS.includes(type)) fail(`unsupported edit motion ${JSON.stringify(type)}`);
  const from = requireNumber(value.from ?? value.from_scale ?? 1.0, "edit motion.from");
  const to = requireNumber(value.to ?? value.to_scale ?? 1.0, "edit motion.to");
  if (from < 1 || from > 1.3 || to < 1 || to > 1.3) {
    fail("edit motion scale must stay between 1.0 and 1.3");
  }
  if (type === "hold" && (from !== 1 || to !== 1)) {
    fail("a hold keeps the image at scale 1.00");
  }
  const anchor = value.anchor ?? [0.5, 0.5];
  if (!Array.isArray(anchor) || anchor.length !== 2) fail("edit motion anchor must be [x, y]");
  for (const number of anchor) {
    requireNumber(number, "edit motion anchor");
    if (number < 0 || number > 1) fail("edit motion anchor is normalized 0..1");
  }
  easingName(value.easing);
  return value;
}

export function validateEditAccent(value, label = "edit accent") {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail(`${label} must be an object`);
  }
  if (!EDIT_ACCENTS.includes(value.type)) {
    fail(`${label} has unsupported type ${JSON.stringify(value.type)}`);
  }
  requireIndex(value.frame, `${label}.frame`);
  const amount = requireNumber(value.amount ?? 1.04, `${label}.amount`);
  if (amount < 1 || amount > 1.2) fail(`${label}.amount must stay between 1.0 and 1.2`);
  requireIndex(value.duration_frames ?? 6, `${label}.duration_frames`, {allowZero: false});
  return value;
}

export function validateEditText(value, label = "edit text") {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail(`${label} must be an object`);
  }
  if (typeof value.id !== "string" || value.id.length === 0) fail(`${label}.id must be set`);
  if (typeof value.text !== "string" || value.text.length === 0) fail(`${label}.text must be set`);
  if (!EDIT_TEXT_STYLES.includes(value.style ?? "super")) {
    fail(`${label}.style is not supported`);
  }
  if (!TEXT_ANIMATIONS.includes(value.animation ?? "fade")) {
    fail(`${label}.animation is not supported`);
  }
  requireIndex(value.in_frame, `${label}.in_frame`);
  requireIndex(value.out_frame, `${label}.out_frame`);
  if (value.out_frame <= value.in_frame) fail(`${label}.out_frame must follow in_frame`);
  return value;
}

export function validateEditCrops(crops, start, duration, id) {
  if (crops === undefined || crops === null) return;
  if (!Array.isArray(crops)) fail(`edit shot ${id} crops must be an array`);
  let previous = start;
  for (const [index, crop] of crops.entries()) {
    const label = `edit shot ${id} crop ${index}`;
    if (crop === null || typeof crop !== "object") fail(`${label} must be an object`);
    requireIndex(crop.frame, `${label}.frame`);
    if (crop.frame <= previous || crop.frame >= start + duration) {
      fail(`${label} must be inside the shot, in order`);
    }
    previous = crop.frame;
    const zoom = requireNumber(crop.zoom, `${label}.zoom`);
    if (zoom < 1 || zoom > 1.6) fail(`${label}.zoom must stay between 1.0 and 1.6`);
    for (const key of ["x", "y"]) {
      const value = requireNumber(crop[key] ?? 0.5, `${label}.${key}`);
      if (value < 0 || value > 1) fail(`${label}.${key} is normalized 0..1`);
    }
  }
}

export function validateEditShot(value, shot) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail(`shot ${shot.id} edit must be an object`);
  }
  if (value.shot_id !== shot.id) {
    fail(`shot ${shot.id} edit names ${JSON.stringify(value.shot_id)}`);
  }
  requireIndex(value.start_frame, `edit shot ${shot.id} start_frame`);
  const duration = requireIndex(value.duration_frames, `edit shot ${shot.id} duration_frames`, {
    allowZero: false,
  });
  if (value.start_frame !== shot.start_frame || duration !== shot.duration_frames) {
    fail(`shot ${shot.id} edit timing does not match its effective span`);
  }
  validateEditMotion(value.motion);
  validateEditTransition(value.transition_in, `edit shot ${shot.id} transition_in`);
  for (const [index, accent] of (value.accents ?? []).entries()) {
    validateEditAccent(accent, `edit shot ${shot.id} accent ${index}`);
    if (accent.frame < value.start_frame || accent.frame >= value.start_frame + duration) {
      fail(`edit shot ${shot.id} accent ${index} is outside the shot`);
    }
  }
  validateEditCrops(value.crops, value.start_frame, duration, shot.id);
  for (const [index, text] of (value.text ?? []).entries()) {
    validateEditText(text, `edit shot ${shot.id} text ${index}`);
    if (
      text.in_frame < value.start_frame ||
      text.out_frame > value.start_frame + duration
    ) {
      fail(`edit shot ${shot.id} text ${text.id} is outside the shot`);
    }
  }
  return value;
}

export function validateGrade(value) {
  if (value === undefined || value === null) return null;
  if (typeof value !== "object" || Array.isArray(value)) fail("grade must be an object");
  const preset = value.preset ?? "neutral";
  if (!Object.hasOwn(GRADE_PRESETS, preset)) {
    fail(`unsupported grade preset ${JSON.stringify(preset)}`);
  }
  const strength = requireNumber(value.strength ?? 1, "grade.strength");
  if (strength < 0 || strength > 1) fail("grade.strength must be between 0 and 1");
  if (value.look !== undefined && value.look !== null) {
    if (typeof value.look !== "object" || Array.isArray(value.look)) {
      fail("grade.look must be an object");
    }
    for (const key of ["grain", "weave", "drift"]) {
      const amount = requireNumber(value.look[key] ?? 0, `grade.look.${key}`);
      if (amount < 0 || amount > 1) fail(`grade.look.${key} must be between 0 and 1`);
    }
  }
  if (value.overrides !== undefined && value.overrides !== null) {
    if (typeof value.overrides !== "object" || Array.isArray(value.overrides)) {
      fail("grade.overrides must be an object");
    }
    for (const [key, raw] of Object.entries(value.overrides)) {
      const range = POST_EFFECT_RANGES[key];
      if (!range) fail(`unsupported grade override ${JSON.stringify(key)}`);
      const number = requireNumber(raw, `grade.overrides.${key}`);
      if (number < range[0] || number > range[1]) {
        fail(`grade.overrides.${key} must be between ${range[0]} and ${range[1]}`);
      }
    }
  }
  return value;
}

/** Resolve a named grade, then apply the advanced slider overrides. */
export function gradeStyle(grade, legacyPostEffects) {
  if (grade === undefined || grade === null) return postEffectsStyle(legacyPostEffects);
  validateGrade(grade);
  const preset = GRADE_PRESETS[grade.preset ?? "neutral"];
  const strength = grade.strength ?? 1;
  const values = {};
  for (const key of Object.keys(POST_EFFECT_RANGES)) {
    const neutral = key === "vignette" ? 0 : 1;
    values[key] = neutral + (Number(preset[key] ?? neutral) - neutral) * strength;
  }
  if (grade.overrides) {
    for (const [key, raw] of Object.entries(grade.overrides)) values[key] = raw;
  }
  const filters = [];
  if (values.saturation === 0) filters.push("grayscale(1)");
  else if (values.saturation !== 1) filters.push(`saturate(${values.saturation})`);
  if (values.contrast !== 1) filters.push(`contrast(${values.contrast})`);
  if (values.brightness !== 1) filters.push(`brightness(${values.brightness})`);
  return {
    filter: filters.length > 0 ? filters.join(" ") : "none",
    vignette: values.vignette,
    tint: preset.tint ?? null,
    values,
  };
}

export function editTransitionStyle(value, progress) {
  const transition = validateEditTransition(value);
  const p = smoothstep(progress);
  const kind = transition.type;
  const defaultStyle = {kind, clipPath: null, opacity: 1, transform: null, filter: null, black: 0, white: 0};
  if (kind === "cut") return defaultStyle;
  if (kind === "fade" || kind === "wipe_left" || kind === "wipe_right") {
    const legacy = transitionStyle(kind, progress);
    return {...defaultStyle, ...legacy};
  }
  if (kind === "dip_to_black" || kind === "dip_to_white") {
    return {
      ...defaultStyle,
      opacity: smoothstep(clamp01((p - 0.45) / 0.55)),
      black: kind === "dip_to_black" ? Math.sin(Math.PI * p) : 0,
      white: kind === "dip_to_white" ? Math.sin(Math.PI * p) : 0,
    };
  }
  const direction = transition.direction ?? "left";
  if (kind === "whip_pan") {
    // Both shots travel together, and the blur runs along the move, peaking mid-whip.
    const sign = direction === "right" ? -1 : 1;
    return {
      ...defaultStyle,
      transform: `translateX(${sign * (1 - p) * 100}%)`,
      outgoingTransform: `translateX(${-sign * p * 100}%)`,
      blurShare: 0.03 * Math.sin(Math.PI * p),
    };
  }
  if (kind === "push") {
    return {
      ...defaultStyle,
      transform: `translateX(${(direction === "right" ? -1 : 1) * (1 - p) * 16}%) scale(${
        1.08 - 0.08 * p
      })`,
      opacity: p,
    };
  }
  const offset = (1 - p) * 100;
  const transform =
    direction === "up"
      ? `translateY(${offset}%)`
      : direction === "down"
        ? `translateY(-${offset}%)`
        : direction === "right"
          ? `translateX(-${offset}%)`
          : `translateX(${offset}%)`;
  return {...defaultStyle, transform};
}

/** A shot's own number, from its id, so moving or inserting shots changes nothing. */
function shotSeed(shotId) {
  let value = 2166136261;
  for (const character of String(shotId)) {
    value = Math.imul(value ^ character.codePointAt(0), 16777619) >>> 0;
  }
  return value;
}

function frameNoise(frame, salt) {
  // A small integer hash, so the same frame always gets the same value on any machine.
  let value = (Math.imul(frame + 1, 2654435761) ^ Math.imul(salt + 1, 40503)) >>> 0;
  value = Math.imul(value ^ (value >>> 15), 2246822519) >>> 0;
  return ((value ^ (value >>> 13)) >>> 0) / 4294967295;
}

const GRAIN_STRENGTH = 0.26;
const WEAVE_SHARE = 0.0011;
const DRIFT_SHARE = 0.007;
const DRIFT_TILT_DEGREES = 0.12;
export const GRAIN_TILE = 256;

/**
 * The film look at one frame of a shot, or null when off. Pure and deterministic, so
 * the Player and the MP4 draw the same thing. It counts from the shot's own start and
 * seeds from its id, so a shot that moves along the film looks exactly the same and
 * its render can be reused. The picture is scaled just enough that no moved edge shows.
 */
export function lookState(look, localFrame, shotId, width, height, fps) {
  if (look === undefined || look === null) return null;
  const grain = Number(look.grain ?? 0);
  const weave = Number(look.weave ?? 0);
  const drift = Number(look.drift ?? 0);
  if (grain <= 0 && weave <= 0 && drift <= 0) return null;
  const seed = shotSeed(shotId);
  const frame = localFrame;
  const seconds = frame / fps;
  const phase = (seed % 1000) / 1000 * 2 * Math.PI;
  const reach = Math.min(width, height);
  const driftPixels = drift * DRIFT_SHARE * reach;
  const weavePixels = weave * WEAVE_SHARE * reach;
  const dx =
    driftPixels * (0.7 * Math.sin((2 * Math.PI * seconds) / 11 + phase) +
      0.3 * Math.sin((2 * Math.PI * seconds) / 4.3 + phase * 2)) +
    weavePixels * (frameNoise(frame, seed + 1) * 2 - 1);
  const dy =
    driftPixels * (0.7 * Math.sin((2 * Math.PI * seconds) / 13 + phase + 1) +
      0.3 * Math.sin((2 * Math.PI * seconds) / 5.1 + phase * 3)) +
    weavePixels * (frameNoise(frame, seed + 2) * 2 - 1);
  const tilt = drift * DRIFT_TILT_DEGREES * Math.sin((2 * Math.PI * seconds) / 17 + phase);
  const margin = driftPixels + weavePixels;
  // Room for the shift on the short side, plus what the tilt swings into the corners.
  const tiltMargin = (Math.abs(drift * DRIFT_TILT_DEGREES) * Math.PI) / 180;
  const scale = 1 + (2 * margin) / reach + 2 * tiltMargin * (Math.max(width, height) / reach);
  return {
    transform: `translate(${dx.toFixed(3)}px, ${dy.toFixed(3)}px) rotate(${tilt.toFixed(4)}deg) scale(${scale.toFixed(5)})`,
    grainOpacity: grain * GRAIN_STRENGTH,
    grainX: Math.floor(frameNoise(frame, seed + 3) * GRAIN_TILE),
    grainY: Math.floor(frameNoise(frame, seed + 4) * GRAIN_TILE),
  };
}

/** Overlay strength and camera bump from the accents active at an absolute frame. */
export function accentState(accents, frame) {
  if (accents === undefined || accents === null) return {punch: 1, flash: 0, leak: 0};
  if (!Array.isArray(accents)) fail("edit accents must be an array");
  let punch = 1;
  let flash = 0;
  let leak = 0;
  for (const [index, accent] of accents.entries()) {
    validateEditAccent(accent, `edit accent ${index}`);
    const k = frame - accent.frame;
    if (k < 0) continue;
    const duration = accent.duration_frames ?? 6;
    if (k >= duration) continue;
    const remaining = 1 - smoothstep(k / duration);
    if (accent.type === "punch_in") punch = Math.max(punch, 1 + (accent.amount - 1) * remaining);
    if (accent.type === "flash") flash = Math.max(flash, remaining);
    if (accent.type === "light_leak") leak = Math.max(leak, remaining);
  }
  return {punch, flash, leak};
}

/** Text animation state for one layer at a 0..1 window progress. */
export function textAnimationStyle(animation, progress, index = 0, count = 1) {
  if (!TEXT_ANIMATIONS.includes(animation)) {
    fail(`unsupported text animation ${JSON.stringify(animation)}`);
  }
  const p = clamp01(progress);
  const enter = smoothstep(clamp01(p * 5));
  const leave = 1 - smoothstep(clamp01((p - 0.85) / 0.15));
  const opacity = enter * leave;
  if (animation === "type_on") {
    return {opacity, reveal: smoothstep(clamp01(p * 2.4)), transform: null};
  }
  if (animation === "slide_up") {
    return {
      opacity,
      reveal: 1,
      transform: `translateY(${(1 - enter) * 26}px)`,
    };
  }
  if (animation === "pop") {
    const overshoot = 1 + 0.12 * (1 - enter);
    return {opacity, reveal: 1, transform: `scale(${overshoot})`};
  }
  if (animation === "kinetic_words") {
    const start = (index / Math.max(count, 1)) * 0.45;
    const local = smoothstep(clamp01((p - start) / 0.45));
    return {
      opacity: local * leave,
      reveal: 1,
      transform: `translateY(${(1 - local) * 18}px) scale(${0.92 + 0.08 * local})`,
    };
  }
  return {opacity, reveal: 1, transform: null};
}

/** Normalized pane rectangles for the split primitive. */
export function splitLayout(count, layout = "row") {
  if (![2, 3].includes(count)) fail("a split needs two or three panes");
  if (!["row", "column", "grid"].includes(layout)) {
    fail(`unsupported split layout ${JSON.stringify(layout)}`);
  }
  if (count === 2 && layout === "column") {
    return [
      {left: 0, top: 0, width: 1, height: 0.5},
      {left: 0, top: 0.5, width: 1, height: 0.5},
    ];
  }
  if (count === 3 && layout === "grid") {
    return [
      {left: 0, top: 0, width: 0.5, height: 0.5},
      {left: 0.5, top: 0, width: 0.5, height: 0.5},
      {left: 0.25, top: 0.5, width: 0.5, height: 0.5},
    ];
  }
  const width = 1 / count;
  return Array.from({length: count}, (_value, index) => ({
    left: index * width,
    top: 0,
    width,
    height: 1,
  }));
}

export function validateSplitPanes(panes, shotId = "shot") {
  if (!Array.isArray(panes) || panes.length < 2 || panes.length > 3) {
    fail(`${shotId} split_panes must have two or three panes`);
  }
  for (const [index, pane] of panes.entries()) {
    if (pane === null || typeof pane !== "object" || Array.isArray(pane)) {
      fail(`${shotId} split pane ${index} must be an object`);
    }
    if (pane.image !== undefined) validateAssetName(pane.image);
    else if (pane.src !== undefined && pane.src !== null) {
      if (typeof pane.src !== "string") fail(`${shotId} split pane ${index} src must be a string`);
    } else {
      fail(`${shotId} split pane ${index} needs an image`);
    }
    if (pane.crop !== undefined) {
      const crop = pane.crop;
      if (crop === null || typeof crop !== "object") fail(`${shotId} split crop must be an object`);
      for (const key of ["zoom", "x", "y"]) {
        if (crop[key] !== undefined) requireNumber(crop[key], `${shotId} split crop ${key}`);
      }
    }
  }
  return panes;
}

/** The photosensitivity rule, independent of any particular edit object. */
export function flashViolations(spans, fps) {
  requireIndex(fps, "fps", {allowZero: false});
  const frames = [];
  for (const span of spans) {
    for (const accent of span.edit?.accents ?? []) {
      validateEditAccent(accent, `shot ${span.id} accent`);
      if (accent.type === "flash") frames.push(accent.frame);
    }
  }
  frames.sort((a, b) => a - b);
  const violations = [];
  let left = 0;
  for (let right = 0; right < frames.length; right += 1) {
    while (frames[right] - frames[left] >= fps) left += 1;
    if (right - left + 1 > 3) {
      violations.push({
        start_frame: frames[left],
        frames: right - left + 1,
        window_frames: fps,
      });
    }
  }
  return violations;
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

/**
 * The planned title window covering `frame` (start inclusive, end exclusive),
 * or null. Windows come from the engine's integer-frame title plan and never
 * overlap, so at most one matches.
 */
export function titleWindowAt(windows, frame) {
  for (const window of windows) {
    if (frame >= window.start_frame && frame < window.start_frame + window.frames) return window;
  }
  return null;
}
