// Opt-in placement only. Existing joint-v1 choreography/copy is not rewritten.
import {graphicsAlpha, introPhasesAt, smoothstep} from "./timing.mjs";

export function validateCompactLayout(layout, part) {
  if (layout === undefined) return null;
  if (!layout || Array.isArray(layout) || typeof layout !== "object" || layout.kind !== "compact-v1") {
    throw new Error("graphics layout must be an explicit compact-v1 object or omitted");
  }
  const keys = ["kind", "identity_switch_frame", "handoff_frames"];
  if (Object.keys(layout).some((key) => !keys.includes(key))) throw new Error("unknown compact layout control");
  const hasSwitch = Object.hasOwn(layout, "identity_switch_frame");
  const hasFade = Object.hasOwn(layout, "handoff_frames");
  if (hasSwitch !== hasFade) throw new Error("compact identity handoff needs both frame controls");
  if (hasSwitch) {
    if (!Number.isInteger(layout.identity_switch_frame) || layout.identity_switch_frame < 1 ||
        !Number.isInteger(layout.handoff_frames) || layout.handoff_frames < 1 ||
        layout.handoff_frames > layout.identity_switch_frame) throw new Error("invalid compact handoff frames");
    if (part?.kind === "identity" && layout.identity_switch_frame + layout.handoff_frames >= part.frames) {
      throw new Error("compact handoff must fit inside the identity part");
    }
  }
  return layout;
}

// Normalized fields; no arbitrary per-frame layout or alternate editorial clock.
export const COMPACT_FIELDS = {
  opening: [.04, .04, .40, .30],
  identityBefore: [.69, .04, .96, .29],
  identityAfter: [.05, .29, .42, .51],
  card: [.04, .03, .40, .25],
  lockup: [.12, .035, .88, .30],
  caption: [.05, .08, .40, .25],
};

export function compactPanels(layout, part, frame, fps) {
  validateCompactLayout(layout, part);
  const seconds = part.frames / fps;
  const alpha = graphicsAlpha(part.kind, frame / fps, seconds);
  if (part.kind === "intro") return [{field: COMPACT_FIELDS.opening, alpha: 1}];
  if (part.kind === "identity") {
    if (layout.identity_switch_frame === undefined) return [{field: COMPACT_FIELDS.identityBefore, alpha}];
    const at = layout.identity_switch_frame, span = layout.handoff_frames;
    // Fade at fixed positions: do not slide copy across the tree or living faces.
    return [
      {field: COMPACT_FIELDS.identityBefore, alpha: alpha * (1 - smoothstep((frame - at + span) / span))},
      {field: COMPACT_FIELDS.identityAfter, alpha: alpha * smoothstep((frame - at) / span)},
    ];
  }
  if (part.kind === "card" || part.kind === "lockup" || part.kind === "caption") {
    return [{field: COMPACT_FIELDS[part.kind], alpha}];
  }
  throw new Error(`compact placement does not replace ${part.kind}`);
}

// The normal opening phase table remains the single source for timing.
export function compactIntroPhases(frame, fps, seconds) {
  return introPhasesAt(frame / fps, seconds);
}
