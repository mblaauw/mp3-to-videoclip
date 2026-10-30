import type { EditPayload, Storyboard } from "../api";
import type { EditMotion, EditTransition } from "../baseFilm";

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

/** Written for a join or move you picked yourself; a note can replace it (D1). */
export const SET_BY_HAND = "Set by hand";

/** The longest transition every listed join can take: shorter than both its shots. */
export function joinMaxFrames(edit: EditPayload, shotIds: string[]): number {
  let max = 48;
  edit.shots.forEach((shot, index) => {
    if (!shotIds.includes(shot.shot_id) || index === 0) return;
    max = Math.min(max, shot.duration_frames - 1, edit.shots[index - 1].duration_frames - 1);
  });
  return Math.max(0, max);
}

/** Give each listed join a type, keeping any reason it already has. */
export function setJoins(
  edit: EditPayload,
  shotIds: string[],
  type: EditTransition["type"],
  frames: number,
): EditPayload {
  return shotIds.reduce((next, shotId) => {
    const current = next.shots.find((shot) => shot.shot_id === shotId)?.transition_in.reason;
    return setEditTransition(next, shotId, { type, frames, reason: current || SET_BY_HAND });
  }, edit);
}

/** The same restrained moves the first cut seeds from storyboard cameras. */
const MOTION_SCALES: Record<EditMotion["type"], [number, number]> = {
  hold: [1, 1],
  push_in: [1, 1.08],
  pull_back: [1.08, 1],
  pan_left: [1.08, 1.08],
  pan_right: [1.08, 1.08],
};

export function setEditMotion(
  edit: EditPayload,
  shotId: string,
  type: EditMotion["type"],
): EditPayload {
  const [from, to] = MOTION_SCALES[type];
  return {
    ...edit,
    shots: edit.shots.map((shot) =>
      shot.shot_id === shotId
        ? { ...shot, motion: { ...shot.motion, type, from, to, reason: SET_BY_HAND } }
        : shot,
    ),
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
