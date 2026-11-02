/**
 * The engine's placeholder rule (production/assets.py, has_placeholders): a marked
 * placeholder, never a word such as Spanish "todo" inside lyrics. The approval gate
 * stays on the server; this only decides what the screen shows.
 */
const MARKED = /^\s*(?:todo|tbd|placeholder)(?:\s*[:-]|\s*$)/i;

export const EMPTY_PURPOSE = "TODO: approved story purpose";
export const EMPTY_PROMPT = "TODO: compose this shot";

export function isPlaceholder(value: string | null | undefined): boolean {
  return typeof value === "string" && MARKED.test(value);
}

/** What a field shows: a placeholder reads as an empty field with a hint. */
export function shown(value: string | null | undefined): string {
  return isPlaceholder(value) ? "" : value || "";
}

/** The first thing a card can say about a shot, or nothing if it still needs a job. */
export function shotCaption(shot: { message?: string | null; purpose?: string | null }): string {
  return shown(shot.message) || shown(shot.purpose);
}
