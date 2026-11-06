import type { StageState } from "../shell/nextStep";

export type CueAnchor = { frame: number } | { line: string } | { shot: string } | { beat: string };
export type AnchorKind = "frame" | "shot" | "line" | "beat";
export type CuePlaces = { every: number; jitter?: number } | { at: CueAnchor[] } | null;
export type CueKind = "music" | "ambience" | "effect";

export type CueVersion = {
  version: number;
  path: string;
  sha256: string;
  source: "upload" | "generated";
  seconds: number;
  cost_usd?: string;
  model?: string;
};

export type Cue = {
  id: string;
  kind: CueKind;
  prompt: string;
  start: CueAnchor;
  end: CueAnchor;
  gain_db: number;
  duck_db: number;
  loop: boolean;
  /** One sound in many places; null or absent for a plain cue. */
  places?: CuePlaces;
  /** The model this cue is made with; null for Settings' choice. */
  model?: string | null;
  why?: string;
  versions: CueVersion[];
  selected: number | null;
  start_seconds: number | null;
  end_seconds: number | null;
  /** Where the sound lands, resolved by the engine; null for a plain cue. */
  places_seconds?: number[] | null;
};

export const KIND_LABEL: Record<CueKind, string> = {
  music: "Music",
  ambience: "Ambience",
  effect: "Effect",
};

/** A cue's band on a ruler of the film, as percentages; null when it cannot be placed. */
export function bandFor(
  cue: Pick<Cue, "start_seconds" | "end_seconds">,
  duration: number,
): { left: number; width: number } | null {
  if (cue.start_seconds === null || cue.end_seconds === null || duration <= 0) return null;
  const start = Math.max(0, Math.min(duration, cue.start_seconds));
  const end = Math.max(start, Math.min(duration, cue.end_seconds));
  const left = (start / duration) * 100;
  return { left, width: Math.max(0.5, ((end - start) / duration) * 100) };
}

/** The stepper's word for the Sound stage: idle with no cue, done when every cue sounds. */
export function soundState(cues: number, sounding: number): StageState {
  if (cues === 0) return "not_ready";
  return sounding >= cues ? "done" : "you";
}

/** The chosen version of a cue, if one plays. */
export function chosen(cue: Pick<Cue, "versions" | "selected">): CueVersion | null {
  return cue.versions.find((version) => version.version === cue.selected) ?? null;
}

/** A new cue's id that no other cue has. */
export function freshId(kind: CueKind, taken: string[]): string {
  const base = kind === "music" ? "bed" : kind === "ambience" ? "room" : "hit";
  if (!taken.includes(base)) return base;
  let number = 2;
  while (taken.includes(`${base}-${number}`)) number += 1;
  return `${base}-${number}`;
}

export function anchorKind(anchor: CueAnchor): AnchorKind {
  if ("shot" in anchor) return "shot";
  if ("line" in anchor) return "line";
  if ("beat" in anchor) return "beat";
  return "frame";
}

export function describeAnchor(anchor: CueAnchor, fps: number): string {
  if ("line" in anchor) return anchor.line;
  if ("shot" in anchor) return `cut of ${anchor.shot}`;
  if ("beat" in anchor) return `beat ${anchor.beat}`;
  if (anchor.frame === -1) return "end";
  return `${(anchor.frame / fps).toFixed(1)} s`;
}

/** How a cue's places read: once, every so often, or at so many anchors. */
export function placesWords(places: CuePlaces | undefined, landed: number | null | undefined): string {
  if (!places) return "once";
  if ("at" in places) {
    const count = landed ?? places.at.length;
    return `at ${count} place${count === 1 ? "" : "s"}`;
  }
  const jitter = places.jitter ? ` ± ${places.jitter} s` : "";
  const times = landed != null ? `, ${landed} time${landed === 1 ? "" : "s"}` : "";
  return `every ${places.every} s${jitter}${times}`;
}

/** An anchor of a kind, keeping what can be kept from the one before. */
export function anchorOf(kind: AnchorKind, value: string, fps: number, atEnd: boolean): CueAnchor {
  if (kind === "shot") return { shot: value };
  if (kind === "line") return { line: value };
  if (kind === "beat") return { beat: value };
  if (value === "" || value === "end") return { frame: atEnd ? -1 : 0 };
  const seconds = Number(value);
  return { frame: Number.isFinite(seconds) && seconds >= 0 ? Math.round(seconds * fps) : atEnd ? -1 : 0 };
}
