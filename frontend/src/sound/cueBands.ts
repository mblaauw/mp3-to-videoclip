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

/** A cue at one moment: its end is its start, and its sound plays whole from there. */
export function isMoment(cue: Pick<Cue, "start" | "end">): boolean {
  return JSON.stringify(cue.start) === JSON.stringify(cue.end);
}

/**
 * Where a cue's chosen sound is heard, as the mixer places it: a moment lasts as long as
 * the sound, a stretch played once stops when the sound does, a loop fills the stretch.
 */
export function heardSpan(
  cue: Pick<Cue, "start_seconds" | "end_seconds" | "versions" | "selected" | "loop" | "places">,
  duration: number,
): { start: number; end: number } | null {
  if (cue.start_seconds === null || cue.end_seconds === null || duration <= 0) return null;
  const start = Math.max(0, Math.min(duration, cue.start_seconds));
  let end = Math.max(start, Math.min(duration, cue.end_seconds));
  const sound = chosen(cue)?.seconds ?? 0;
  if (end <= start) end = Math.min(duration, start + sound);
  else if (!cue.places && !cue.loop && sound > 0) end = Math.min(end, start + sound);
  return { start, end };
}

export type PlaysMode = "loop" | "once" | "every" | "at";

/** How a stretch plays its sound: looped to fill, once, every so often, or at places. */
export function playsMode(cue: Pick<Cue, "loop" | "places">): PlaysMode {
  const places = cue.places ?? null;
  if (places && "at" in places) return "at";
  if (places && "every" in places) return "every";
  return cue.loop ? "loop" : "once";
}

/** The fields a choice of plays sets; every cut when there are cuts, else the start. */
export function withPlays(mode: PlaysMode, shots: string[]): Pick<Cue, "loop" | "places"> {
  if (mode === "loop") return { loop: true, places: null };
  if (mode === "once") return { loop: false, places: null };
  if (mode === "every") return { loop: false, places: { every: 2, jitter: 0 } };
  return { loop: false, places: { at: shots.length ? shots.map((shot) => ({ shot })) : [{ frame: 0 }] } };
}

/** Rows for one lane so no two items, labels included, overlap; returns each id's row. */
export function packRows(items: { id: string; start: number; end: number }[]): Record<string, number> {
  const rows: number[] = [];
  const placed: Record<string, number> = {};
  for (const item of [...items].sort((a, b) => a.start - b.start || a.id.localeCompare(b.id))) {
    let row = rows.findIndex((last) => last <= item.start);
    if (row < 0) {
      row = rows.length;
      rows.push(item.end);
    } else rows[row] = item.end;
    placed[item.id] = row;
  }
  return placed;
}

/** Marks along a ruler of the film, a round step apart. */
export function rulerTicks(duration: number): number[] {
  if (duration <= 0) return [0];
  const step = duration <= 40 ? 5 : duration <= 120 ? 10 : duration <= 300 ? 30 : 60;
  const ticks = [];
  for (let at = 0; at <= duration + 1e-6; at += step) ticks.push(at);
  return ticks;
}

/** A moment to a tenth: 0:13.2. */
export function clockTenths(seconds: number): string {
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  const rest = (safe - minutes * 60).toFixed(1).padStart(4, "0");
  return `${minutes}:${rest}`;
}

/** A level as people write it: −8 dB, 0 dB, +3 dB. */
export function dbWords(db: number): string {
  if (db === 0) return "0 dB";
  return `${db > 0 ? "+" : "−"}${Math.abs(db)} dB`;
}

/** How the chosen sound fills the cue: looped, once, whole from a moment, or placed. */
export function fitWords(
  cue: Pick<Cue, "start" | "end" | "loop" | "places" | "versions" | "selected" | "start_seconds" | "end_seconds" | "places_seconds">,
): string | null {
  const sound = chosen(cue);
  if (!sound) return null;
  const length = `${sound.seconds.toFixed(1)} s`;
  if (cue.start_seconds === null || cue.end_seconds === null) return null;
  if (isMoment(cue)) return `Plays its ${length} sound whole from ${clockTenths(cue.start_seconds)}.`;
  const span = Math.max(0, cue.end_seconds - cue.start_seconds);
  const mode = playsMode(cue);
  if (mode === "every" || mode === "at") {
    const count = cue.places_seconds?.length ?? 0;
    return `Plays its ${length} sound ${count} time${count === 1 ? "" : "s"}, whole each time.`;
  }
  if (mode === "loop" && sound.seconds > 0 && sound.seconds < span) {
    return `Loops its ${length} sound ${(span / sound.seconds).toFixed(1)} times to fill ${span.toFixed(1)} s.`;
  }
  if (sound.seconds < span) return `Plays its ${length} sound once; ${(span - sound.seconds).toFixed(1)} s of the stretch stays quiet.`;
  return `Plays ${span.toFixed(1)} s of its ${length} sound.`;
}

/** Where an anchor is now, as far as the page knows, so an edit moves on the map at once. */
export function anchorSeconds(
  anchor: CueAnchor,
  where: { fps: number; duration: number; shots: { id: string; start: number }[]; lines: { id: string; start: number; end: number }[]; beats: { id: string; start: number; end: number }[] },
  atEnd: boolean,
): number | null {
  if ("frame" in anchor) return anchor.frame === -1 ? where.duration : anchor.frame / where.fps;
  if ("shot" in anchor) return where.shots.find((shot) => shot.id === anchor.shot)?.start ?? null;
  const found = "line" in anchor ? where.lines.find((line) => line.id === anchor.line) : where.beats.find((beat) => beat.id === anchor.beat);
  if (!found) return null;
  return atEnd ? found.end : found.start;
}

/** Dollars as the ledger keeps them, to the cent unless smaller than one: $0.10, $0.0025. */
export function dollars(amount: string | number): string {
  const value = Number(amount);
  if (!Number.isFinite(value)) return `$${amount}`;
  return value > 0 && value < 0.01 ? `$${String(amount)}` : `$${value.toFixed(2)}`;
}
