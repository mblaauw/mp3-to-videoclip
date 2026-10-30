import type { Concept, ConceptBeat, StoryPassage } from "../api";

const SPAN = /^\s*(\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)\s*s\b[^:]*:\s*(.+)$/s;

function labelOf(text: string): string {
  const first = text.split(/\s[—–]\s|[:.;]/)[0].trim();
  const words = first.split(/\s+/);
  return words.length > 8 ? `${words.slice(0, 7).join(" ")}…` : first;
}

function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Older concepts keep their times inside free text. Null when any step has none. */
export function parseShape(shape: string[]): ConceptBeat[] | null {
  const beats: ConceptBeat[] = [];
  for (const step of shape) {
    const match = SPAN.exec(step);
    if (!match) return null;
    const start = Number(match[1]);
    const end = Number(match[2]);
    if (!(end > start)) return null;
    const text = match[3].trim();
    beats.push({ start, end, label: labelOf(text), text: sentence(text) });
  }
  return beats.length ? beats : null;
}

/** The concept's timed beats, or null when it can only be read as text. */
export function conceptBeats(concept: Concept): ConceptBeat[] | null {
  if (concept.beats?.length) return concept.beats;
  return parseShape(concept.shape ?? []);
}

/** Your story's placed passages, drawn the same way as a concept's beats. */
export function passageBeats(passages: StoryPassage[]): ConceptBeat[] {
  return passages.flatMap((passage) =>
    passage.start !== null && passage.end !== null
      ? [
          {
            start: passage.start,
            end: passage.end,
            label: labelOf(passage.text),
            text: passage.text,
          },
        ]
      : [],
  );
}

/** The passage playing at a time, if that part of the song has one. */
export function passageAt(passages: StoryPassage[], seconds: number): number {
  return passages.findIndex(
    (passage) =>
      passage.start !== null &&
      passage.end !== null &&
      seconds >= passage.start &&
      seconds < passage.end,
  );
}
