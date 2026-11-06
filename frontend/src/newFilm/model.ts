/** The New film form's answers, the formats that fill them and the picture of the film they make. */

export type Aspect = "16:9" | "9:16";

export type Format = {
  id: string;
  kind: string;
  label: string;
  blurb: string;
  /** Seconds; 0 is the whole song. */
  length: number;
  aspect: Aspect;
  titles: string;
  destinations: string[];
  look: string;
  /** A story film's template id, another kind's structure label, or null for the Writer's own. */
  structure: string | null;
};

export type Destination = { id: string; label: string; aspect: string };
export type StructureBeats = { id: string; label: string; length: number; beats: { label: string; seconds: number }[] };

/** What a format decides; the rest of the form is the film's own. */
export type Choices = Omit<Format, "id" | "label" | "blurb">;

export const WHOLE_TRACK = 0;

export function fromFormat(format: Format): Choices {
  return {
    kind: format.kind,
    length: format.length,
    aspect: format.aspect,
    titles: format.titles,
    destinations: [...format.destinations],
    look: format.look,
    structure: format.structure,
  };
}

/**
 * Where a format starts on this computer: the brand signature only once the kit has a name,
 * and the look Settings prefers when this kind offers it.
 */
export function startFrom(
  format: Format,
  defaults: { titles?: Record<string, string>; look?: string; looks?: string[] },
): Choices {
  const start = fromFormat(format);
  if (start.titles === "joint-v1" && defaults.titles?.[format.kind] !== "joint-v1") {
    start.titles = "title-v1";
  }
  if (defaults.look && defaults.looks?.includes(defaults.look)) start.look = defaults.look;
  return start;
}

/** Whether the owner has moved the form away from where its format started. */
export function adjusted(choices: Choices, start: Choices | null): boolean {
  if (!start) return true;
  return (
    start.kind !== choices.kind ||
    start.length !== choices.length ||
    start.aspect !== choices.aspect ||
    start.titles !== choices.titles ||
    start.look !== choices.look ||
    start.structure !== choices.structure ||
    [...start.destinations].sort().join() !== [...choices.destinations].sort().join()
  );
}

/** Where a film of this shape can go: its own shape, or a square crop of it. */
export function destinationsFor(aspect: Aspect, all: Destination[]): Destination[] {
  return all.filter((item) => item.aspect === aspect || item.aspect === "1:1");
}

/** Keep the destinations that still fit; a shape with none left starts on its first. */
export function keepDestinations(chosen: string[], aspect: Aspect, all: Destination[]): string[] {
  const fit = destinationsFor(aspect, all).map((item) => item.id);
  const kept = chosen.filter((id) => fit.includes(id));
  const own = fit.filter((id) => all.find((item) => item.id === id)?.aspect === aspect);
  return kept.length ? kept : own.slice(0, 1);
}

/** A typed amount in dollars, whichever decimal mark the keyboard gave. */
export function parseBudget(text: string): number | null {
  const cleaned = text.trim().replace(/^\$/, "").replace(",", ".");
  if (!/^\d+(\.\d{0,2})?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return value > 0 ? value : null;
}

/** How many stills the cap covers at the reserve each one sets aside. */
export function stillsFor(budget: number | null, reservePerStill: number): number | null {
  if (budget === null || !(reservePerStill > 0)) return null;
  return Math.floor(budget / reservePerStill + 1e-9);
}

export function clock(seconds: number): string {
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole} s`;
  const minutes = Math.floor(whole / 60);
  const rest = whole % 60;
  return rest ? `${minutes}:${String(rest).padStart(2, "0")}` : `${minutes} min`;
}

export type Segment = { label: string; seconds: number; tone: "beat" | "excerpt" | "rest" };

/**
 * The film along its length: a story film's beats scaled to the length it was given, or the
 * song with the part the film uses. The song's own length is only known once it is read.
 */
export function timeline(
  choices: Choices,
  structures: StructureBeats[],
  songSeconds: number | null,
): { total: number | null; segments: Segment[] } {
  if (choices.kind === "narrative") {
    const template = structures.find((item) => item.id === choices.structure);
    if (!template || !template.length) return { total: choices.length || null, segments: [] };
    const scale = choices.length / template.length;
    return {
      total: choices.length,
      segments: template.beats.map((beat) => ({
        label: beat.label,
        seconds: Math.round(beat.seconds * scale * 10) / 10,
        tone: "beat" as const,
      })),
    };
  }
  if (choices.length === WHOLE_TRACK) {
    return {
      total: songSeconds,
      segments: [{ label: "The whole song", seconds: songSeconds ?? 1, tone: "excerpt" }],
    };
  }
  const used = songSeconds === null ? choices.length : Math.min(choices.length, songSeconds);
  const rest = songSeconds === null ? 0 : Math.max(0, songSeconds - used);
  return {
    total: songSeconds,
    segments: [
      { label: `First ${clock(used)}`, seconds: used, tone: "excerpt" },
      ...(rest > 0 ? [{ label: "Rest of the song", seconds: rest, tone: "rest" as const }] : []),
    ],
  };
}

/** The title an MP3's name suggests: no extension, no underscores. */
export function titleFromFile(name: string): string {
  return name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
}
