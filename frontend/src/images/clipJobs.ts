/** Which clip job is making which shot, remembered in this tab so a reload keeps the picture. */

const KEY = "studio:clip-jobs";

export type ClipJobNote = { shot: string; model: string; typical: number | null; since: number };

export function readClipJobs(): Record<string, ClipJobNote> {
  try {
    const raw = window.sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Record<string, ClipJobNote>) : {};
  } catch {
    return {};
  }
}

export function noteClipJob(jobId: string, note: ClipJobNote): void {
  try {
    const all = readClipJobs();
    all[jobId] = note;
    window.sessionStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    // Without storage the panel still shows the job; only the shot's name is lost on reload.
  }
}

export function forgetClipJobs(keep: string[]): void {
  try {
    const all = readClipJobs();
    const next = Object.fromEntries(Object.entries(all).filter(([id]) => keep.includes(id)));
    window.sessionStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    // Nothing to tidy.
  }
}

/** How far along a clip is, by the clock: capped short of done, since only the provider knows. */
export function progressShare(elapsed: number, typical: number | null): number | null {
  if (typical === null || typical <= 0) return null;
  return Math.min(0.95, Math.max(0, elapsed / typical));
}

export function clock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
