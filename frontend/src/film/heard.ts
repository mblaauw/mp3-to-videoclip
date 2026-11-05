/** Which whole seconds a media element really played with the sound on. Pure, so it is tested. */

export type Sound = { muted: boolean; volume: number; paused: boolean };

/** The volume under which nothing is heard, as far as the owner is concerned. */
export const QUIET = 0.05;

/** Mark the second under the playhead, when it was audible. Returns whether it was marked. */
export function markHeard(heard: Set<number>, time: number, sound: Sound): boolean {
  if (sound.paused || sound.muted || sound.volume <= QUIET || !Number.isFinite(time) || time < 0) {
    return false;
  }
  heard.add(Math.floor(time));
  return true;
}

/** The seconds not yet reported, in order. */
export function unsent(heard: Set<number>, sent: Set<number>): number[] {
  return [...heard].filter((second) => !sent.has(second)).sort((a, b) => a - b);
}

/** A share of a whole film, for the words beside the player. */
export function coverageShare(heard: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(1, heard / total);
}

export function heardWords(heard: number, total: number): string {
  if (total <= 0) return "Not heard yet.";
  const share = coverageShare(heard, total);
  if (share >= 0.98) return "Heard start to finish with the sound on.";
  return `${heard} of ${total} seconds heard with the sound on.`;
}
