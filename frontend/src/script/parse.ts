/** One pasted line: its beat if it says one, or the beat its place in the film suggests. */
export type PastedLine = { id: string; text: string; beat: string };

/**
 * Turn pasted text into script lines. "hook: words" names a beat. Lines with no name share the
 * beats in proportion to their budgets, so a plain paste lands in a sensible place to correct.
 */
export function parsePasted(
  text: string,
  beats: readonly { id: string; budget: number }[],
): PastedLine[] {
  const rows = text
    .split(/\n+/)
    .map((row) => row.trim())
    .filter(Boolean);
  const total = beats.reduce((sum, beat) => sum + beat.budget, 0) || 1;
  const known = new Set(beats.map((beat) => beat.id));
  return rows.map((row, index) => {
    const named = row.match(/^([a-z0-9-]+):\s*(.+)$/i);
    const id = `l${String(index + 1).padStart(3, "0")}`;
    if (named && known.has(named[1].toLowerCase())) {
      return { id, text: named[2], beat: named[1].toLowerCase() };
    }
    const place = ((index + 0.5) / rows.length) * total;
    let reached = 0;
    const beat =
      beats.find((item) => {
        reached += item.budget;
        return place <= reached;
      }) ?? beats[beats.length - 1];
    return { id, text: row, beat: beat?.id ?? "" };
  });
}

/** The line being said at this moment; a pause belongs to the line before it. */
export function lineAt<T extends { start: number; end: number; pause_after: number }>(
  lines: readonly T[],
  time: number,
): T | null {
  return lines.find((line) => time >= line.start && time < line.end + line.pause_after) ?? null;
}
