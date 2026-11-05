import type { StageState } from "../shell/nextStep";

export type CueAnchor = { frame: number } | { line: string };
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
  why?: string;
  versions: CueVersion[];
  selected: number | null;
  start_seconds: number | null;
  end_seconds: number | null;
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

export function describeAnchor(anchor: CueAnchor, fps: number): string {
  if ("line" in anchor) return anchor.line;
  if (anchor.frame === -1) return "end";
  return `${(anchor.frame / fps).toFixed(1)} s`;
}
