import type { EditPayload, Storyboard } from "../api";
import type { EditTransition } from "../baseFilm";

/** Drag limits for the join between two edit-owned shots. */
export type BoundaryLimits = { low: number; high: number };

export const TRANSITION_TYPES: { value: EditTransition["type"]; label: string }[] = [
  { value: "cut", label: "Cut" },
  { value: "fade", label: "Fade" },
  { value: "wipe_left", label: "Wipe left" },
  { value: "wipe_right", label: "Wipe right" },
  { value: "dip_to_black", label: "Dip to black" },
  { value: "dip_to_white", label: "Dip to white" },
  { value: "whip_pan", label: "Whip pan" },
  { value: "push", label: "Push" },
  { value: "slide", label: "Slide" },
];

function maxFrame(values: number[], fallback: number): number {
  return values.reduce((best, value) => Math.max(best, value), fallback);
}

function minFrame(values: number[], fallback: number): number {
  return values.reduce((best, value) => Math.min(best, value), fallback);
}

/**
 * A boundary can move without invalidating either shot: both durations stay
 * longer than their incoming transitions, and timed accents/text stay inside
 * the shot that owns them.
 */
export function editBoundaryLimits(edit: EditPayload, index: number): BoundaryLimits {
  const left = edit.shots[index];
  const right = edit.shots[index + 1];
  if (!left || !right) return { low: 0, high: 0 };
  const leftStart = left.start_frame;
  const rightEnd = right.start_frame + right.duration_frames;
  const low = maxFrame(
    [
      leftStart + 1,
      leftStart + left.transition_in.frames + 1,
      leftStart + right.transition_in.frames + 1,
      ...left.accents.map((accent) => accent.frame + 1),
      ...left.text.map((item) => item.out_frame),
    ],
    leftStart + 1,
  );
  const high = minFrame(
    [
      rightEnd - 1,
      rightEnd - right.transition_in.frames - 1,
      ...right.accents.map((accent) => accent.frame),
      ...right.text.map((item) => item.in_frame),
    ],
    rightEnd - 1,
  );
  return { low, high };
}

/** Move one join; every other shot keeps its span, so the cut still covers the film. */
export function moveEditBoundary(edit: EditPayload, index: number, frame: number): EditPayload {
  const left = edit.shots[index];
  const right = edit.shots[index + 1];
  if (!left || !right) return edit;
  const { low, high } = editBoundaryLimits(edit, index);
  if (low > high) return edit;
  const at = Math.max(low, Math.min(high, Math.round(frame)));
  if (at === left.start_frame + left.duration_frames) return edit;
  const rightEnd = right.start_frame + right.duration_frames;
  return {
    ...edit,
    shots: edit.shots.map((shot, position) => {
      if (position === index) return { ...shot, duration_frames: at - shot.start_frame };
      if (position === index + 1) {
        return { ...shot, start_frame: at, duration_frames: rightEnd - at };
      }
      return shot;
    }),
  };
}

/** Edit one shot's incoming join without touching timing or content. */
export function setEditTransition(
  edit: EditPayload,
  shotId: string,
  change: Partial<EditTransition>,
): EditPayload {
  return {
    ...edit,
    shots: edit.shots.map((shot) => {
      if (shot.shot_id !== shotId) return shot;
      const type = change.type ?? shot.transition_in.type;
      const frames =
        type === "cut"
          ? 0
          : Math.max(0, Math.min(48, Math.round(change.frames ?? shot.transition_in.frames)));
      return {
        ...shot,
        transition_in: {
          ...shot.transition_in,
          ...change,
          type,
          frames,
          direction: type === "cut" ? null : change.direction ?? shot.transition_in.direction,
          reason: type === "cut" ? "" : change.reason ?? shot.transition_in.reason ?? "",
        },
      };
    }),
  };
}

/** The filmstrip and spine use edit order and spans once a cut owns timing. */
export function applyEditBoard(board: Storyboard, edit: EditPayload): Storyboard {
  const byId = new Map(board.shots.map((shot) => [shot.id, shot]));
  const shots = edit.shots.flatMap((decision) => {
    const shot = byId.get(decision.shot_id);
    if (!shot) return [];
    return [
      {
        ...shot,
        start_frame: decision.start_frame,
        duration_frames: decision.duration_frames,
        dissolve_frames: 0,
        transition: null,
      },
    ];
  });
  return shots.length === board.shots.length ? { ...board, shots } : board;
}
