/** What the Film panel is showing. Joins are named by the shot they lead into. */
export type FilmSelection =
  | { kind: "join"; ids: string[] }
  | { kind: "shot"; id: string }
  | { kind: "note"; index: number }
  | { kind: "delivery" }
  | null;

/** A plain click picks one join; a modified click adds or removes it. */
export function selectJoin(current: FilmSelection, id: string, additive: boolean): FilmSelection {
  if (!additive) return { kind: "join", ids: [id] };
  const ids = current?.kind === "join" ? current.ids : [];
  const next = ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id];
  return next.length ? { kind: "join", ids: next } : null;
}

export function joinSelected(current: FilmSelection, id: string): boolean {
  return current?.kind === "join" && current.ids.includes(id);
}

/** Shot id of the next join after (or before) a frame, for `[` and `]`. */
export function stepJoin(
  shots: { id: string; start_frame: number }[],
  frame: number,
  direction: 1 | -1,
): string | null {
  const joins = shots.slice(1);
  const found =
    direction > 0
      ? joins.find((shot) => shot.start_frame > frame + 1)
      : [...joins].reverse().find((shot) => shot.start_frame < frame - 1);
  return found?.id ?? null;
}
