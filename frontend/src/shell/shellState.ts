import { soundState } from "../sound/cueBands.ts";
import type { ApprovalState, ImageShot, ProjectSummary } from "../api.ts";
import type { ApprovalFacts, ApprovalMap, ImageFacts, NextAction, Stage, StageState } from "./nextStep.ts";


export const APPROVED: Record<string, string> = {
  brief: "Story approved",
  storyboard: "Storyboard approved",
  proof: "Style check approved",
  stills: "All stills approved",
  preview: "Preview approved",
  graphics: "Titles approved",
};

export const DRAFT_NAME: Record<string, string> = {
  brief: "The story",
  storyboard: "The storyboard",
  proof: "The proof stills",
};

export const APPROVAL_STAGES = [
  "analysis",
  "lyrics",
  "brief",
  "script",
  "voice",
  "storyboard",
  "proof",
  "preview",
  "stills",
  "graphics",
];

export function approvalMap(states: ApprovalState[]): ApprovalMap {
  const result: ApprovalMap = {};
  for (const state of states) {
    result[state.stage] = {
      state: state.state,
      error: state.error,
      blocking_stage: state.blocking_stage,
      expected_hash: state.expected_hash,
      reason: state.reason,
    };
  }
  return result;
}

export function imageFacts(shots: ImageShot[], reserve: string, proofIds: string[]): ImageFacts {
  const paid = shots.filter((shot) => shot.paid);
  const missing = paid.filter((shot) => shot.selected === null);
  const proof = shots.filter((shot) => proofIds.includes(shot.id) && !shot.local);
  return {
    proof_total: proof.length,
    proof_kept: proof.filter(
      (shot) => shot.selected !== null && !shot.stale && shot.review?.verdict === "accept",
    ).length,
    proof_missing_ids: proof.filter((shot) => shot.selected === null).map((shot) => shot.id),
    proof_stale_ids: proof
      .filter((shot) => shot.selected !== null && shot.stale)
      .map((shot) => shot.id),
    total: paid.length,
    selected: paid.filter((shot) => shot.selected !== null).length,
    kept: paid.filter((shot) => shot.review?.verdict === "accept").length,
    stale: paid.filter((shot) => shot.selected !== null && shot.stale).length,
    missing: missing.length,
    missing_ids: missing.map((shot) => shot.id),
    reserve_usd: reserve,
  };
}

function approvalWord(value: ApprovalFacts | undefined): StageState {
  if (!value) return "you";
  if (value.state === "approved") return "done";
  if (value.state === "stale") return "changed";
  if (value.state === "unavailable") return "not_ready";
  return "you";
}

/**
 * The top bar and the next-step bar must agree. Approval endpoints are
 * authoritative; the library summary stays a cheap mtime heuristic only.
 */
export function derivedStates(
  project: ProjectSummary,
  approvals: ApprovalMap,
  images: ImageFacts,
): Partial<Record<Stage, StageState>> {
  const base = { ...(project.stage_states || {}) } as Partial<Record<Stage, StageState>>;
  base.story = approvalWord(approvals.brief);
  base.storyboard =
    base.story === "done" ? approvalWord(approvals.storyboard) : "not_ready";
  if (base.storyboard !== "done") {
    base.images = "not_ready";
  } else if (approvals.stills?.state === "approved") {
    base.images = "done";
  } else if (
    approvals.stills?.state === "stale" &&
    approvals.proof?.state !== "stale" &&
    images.total > 0 &&
    images.kept === images.total &&
    !images.stale
  ) {
    // Every picture is still kept; only the cut moved, and Film asks for that sign-off.
    // A stale style check is not that case: the cut signs off on top of it, so Images
    // must offer the style check again first, or Film and Images send you to each other.
    base.images = "done";
  } else if (approvals.stills?.state === "stale" || approvals.proof?.state === "stale") {
    base.images = "changed";
  } else {
    base.images = "you";
  }
  base.sound = soundState(project.sound_cues ?? 0, project.sound_sounding ?? 0);
  base.film =
    base.film === "done" ? "done" : base.images === "done" ? "you" : "not_ready";
  base.publish = base.film !== "done" ? "not_ready" : project.released ? "done" : "you";
  return base;
}

export type PaidRequest = NonNullable<NextAction["paid"]>;
