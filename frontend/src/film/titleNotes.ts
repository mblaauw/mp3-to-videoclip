/** The engine's titles message in plain words; the raw text stays under Details. */
const PREFIX = "The titles cannot be laid out yet: ";

const REASONS: [RegExp, string][] = [
  [/safe margin/, "A title is too wide for the frame."],
  [/no local font/, "A font the titles need is not on this computer."],
  [/require(s)? (the )?Remotion/, "These titles need the local renderer."],
];

export type TitleNote = { title: string; reason: string; details: string | null };

export function describeTitlesNote(raw: string): TitleNote {
  if (!raw.startsWith(PREFIX)) return { title: raw, reason: "", details: null };
  const details = raw.slice(PREFIX.length);
  const known = REASONS.find(([pattern]) => pattern.test(details));
  return { title: "The titles are not ready yet.", reason: known?.[1] ?? "", details };
}
