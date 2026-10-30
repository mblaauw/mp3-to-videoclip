import type { LyricLine, LyricTimingSave } from "../api";

/** The next sung line with no time, or -1 when every line has one. */
export function nextToTap(lines: LyricLine[]): number {
  return lines.findIndex((line) => !line.tag && line.start === null);
}

export function sungCount(lines: LyricLine[]): number {
  return lines.filter((line) => !line.tag).length;
}

export function timedCount(lines: LyricLine[]): number {
  return lines.filter((line) => !line.tag && line.start !== null).length;
}

/** The line sounding at this moment: the last one started, in lyric order. */
export function lineAt(lines: LyricLine[], time: number): number {
  let found = -1;
  lines.forEach((line, index) => {
    if (line.start !== null && line.start <= time) found = index;
  });
  return found;
}

function latest(lines: LyricLine[], before: number): number {
  let time = 0;
  lines.slice(0, before).forEach((line) => {
    if (line.start !== null) time = Math.max(time, line.start);
  });
  return time;
}

/** A tap can't land before the line above it. */
export function applyTap(lines: LyricLine[], time: number): LyricLine[] {
  const index = nextToTap(lines);
  if (index < 0) return lines;
  const start = Math.max(time, latest(lines, index));
  return lines.map((line, position) =>
    position === index ? { ...line, start, end: null, source: "tapped" } : line,
  );
}

/** Removes the most recent time and says where to listen from again. */
export function undoTap(lines: LyricLine[]): { lines: LyricLine[]; time: number } | null {
  let last = -1;
  lines.forEach((line, index) => {
    if (line.start !== null && line.source !== "lrc") last = index;
  });
  if (last < 0) return null;
  const time = lines[last].start ?? 0;
  return {
    lines: lines.map((line, index) =>
      index === last ? { ...line, start: null, end: null, source: null } : line,
    ),
    time,
  };
}

/** Moves one line, stopping at its neighbours so the lines stay in order. */
export function nudge(lines: LyricLine[], index: number, seconds: number): LyricLine[] {
  const line = lines[index];
  if (!line || line.start === null) return lines;
  const before = latest(lines, index);
  const after = lines.slice(index + 1).find((item) => item.start !== null)?.start ?? Infinity;
  const start = Math.max(before, Math.min(after, line.start + seconds));
  return lines.map((item, position) =>
    position === index ? { ...item, start, end: null, source: "tapped" } : item,
  );
}

/** What the server stores: tapped and automatic lines, not an LRC file's own times. */
export function toSave(lines: LyricLine[]): LyricTimingSave[] {
  return lines.flatMap((line) =>
    line.start !== null && !line.tag && (line.source === "tapped" || line.source === "auto")
      ? [{ index: line.index, start: line.start, end: line.end, source: line.source }]
      : [],
  );
}
