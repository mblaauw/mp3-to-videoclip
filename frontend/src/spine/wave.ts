import type { Music } from "../api";

const MAX_BARS = 320;

export function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  return `${minutes}:${String(whole % 60).padStart(2, "0")}`;
}

export function waveformBars(
  music: Music | null,
  duration: number,
): { value: number; section: number; start: number }[] {
  const windows = music?.fine_windows ?? [];
  if (windows.length) {
    const step = Math.max(1, Math.ceil(windows.length / MAX_BARS));
    const bars: { value: number; section: number; start: number }[] = [];
    for (let index = 0; index < windows.length; index += step) {
      const group = windows.slice(index, index + step);
      const average =
        group.reduce((sum, window) => sum + Number(window.level_db ?? -60), 0) / group.length;
      const time = Number(group[0]?.time ?? (index / windows.length) * duration);
      bars.push({
        value: Math.max(0.02, Math.min(1, (average + 60) / 60)),
        section: sectionAt(music, time),
        start: time,
      });
    }
    return bars;
  }
  const points = music?.energy_curve ?? [];
  return points.map((point) => ({
    value: Math.max(0.02, Math.min(1, Number(point.energy ?? 0))),
    section: sectionAt(music, Number(point.time ?? 0)),
    start: Number(point.time ?? 0),
  }));
}

export function sectionAt(music: Music | null, time: number): number {
  const sections = music?.sections ?? [];
  const index = sections.findIndex(
    (section) => time >= Number(section.start) && time < Number(section.end),
  );
  return index < 0 ? 0 : index;
}

export function sectionColor(index: number): string {
  return `var(--sec-${(index % 5) + 1})`;
}

export function sectionName(section: { label?: string; name?: string }, index: number): string {
  return section.name || (section.label && section.label !== "unreviewed" ? section.label : `Section ${index + 1}`);
}
