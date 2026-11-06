import { DIFFICULTY_WORDS, trackStep, storyStep, scriptStep, storyboardStep, soundStep } from "./nextStepSteps.ts";
import { imagesStep, filmStep } from "./nextStepFilm.ts";

/** One place for the sticky next-step copy and its single primary action. */

export type Stage = "track" | "script" | "story" | "storyboard" | "images" | "sound" | "film";
export type StageState = "done" | "you" | "changed" | "not_ready" | "running";
export type NextTone = "done" | "you" | "changed" | "error";
export type NextTarget =
  | "analysis"
  | "lyrics"
  | "approval"
  | "changes"
  | "brief"
  | "preview"
  | "render"
  | "make-missing"
  | "pictures"
  | "world"
  | "settings"
  | "director"
  | "placeholders"
  | "board";

export type NextAction = {
  label: string;
  kind?: "primary" | "default" | "quiet";
  to?: Stage;
  target?: NextTarget;
  /** Approve this stage directly with its already-returned expected hash. */
  approve?: string;
  /** A priced image batch: the bar already showed the reserve total. */
  paid?: { ids: string[]; scope: "proof" | "stills" };
};

export type NextStep = {
  tone: NextTone;
  title: string;
  detail?: string;
  actions: NextAction[];
};

export type ProjectFacts = {
  spine?: string | null;
  kind?: string | null;
  music_mode?: string | null;
  prompt_version?: number | null;
  profile_version?: number;
  has_analysis?: boolean;
  has_lyrics?: boolean;
  has_message?: boolean;
  has_cta?: boolean;
  /** Present on library summaries: whether delivery needs the graphics pass. */
  signature_required?: boolean | null;
  /** Present on library summaries: whether the stills gate sits behind preview. */
  preview_required?: boolean;
  stage_states?: Partial<Record<Stage, StageState>>;
  /** The Sound stage's cues, and how many of them have a sound. */
  sound_cues?: number;
  sound_sounding?: number;
  /** Film knows a current titles review is waiting to be inspected. */
  titles_review_ready?: boolean;
  /** The Director can answer here. Unknown until settings load, so never assumed false. */
  has_model_key?: boolean;
  has_storyboard?: boolean;
  /** The engine's own count of shots the approval would refuse. */
  placeholder_shot_ids?: string[];
  /** Who the owner has not yet confirmed permission for. */
  permission_pending?: string[];
};

export type ApprovalFacts = {
  state: "approved" | "stale" | "missing" | "unavailable";
  error?: string | null;
  blocking_stage?: string | null;
  expected_hash?: string | null;
  reason?: string | null;
};

export type ImageFacts = {
  /** Paid stills whose selected version came from an older prompt. */
  stale?: number;
  total: number;
  selected: number;
  kept: number;
  missing: number;
  missing_ids?: string[];
  reserve_usd?: string;
  /** The style-check shots (present once the Studio knows them). */
  proof_total?: number;
  proof_kept?: number;
  proof_missing_ids?: string[];
  /** Selected style-check stills made from an older prompt. */
  proof_stale_ids?: string[];
  /** A paid batch for this film is queued or running. */
  running?: boolean;
  running_line?: string;
};

export type BudgetFacts = {
  remaining_usd?: string | null;
  cap_usd?: string | null;
  committed_usd?: string;
};

export type ApprovalMap = Partial<Record<string, ApprovalFacts>>;

/** Where a step that names the page you are on acts instead. */
const ON_THIS_PAGE: Record<Stage, NextTarget> = {
  track: "analysis",
  script: "approval",
  story: "brief",
  storyboard: "board",
  images: "pictures",
  sound: "director",
  film: "render",
};

/** A next step never sends the owner to the page they are already on. */
function stayHere(stage: Stage, step: NextStep): NextStep {
  return {
    ...step,
    actions: step.actions.map((action) => {
      if (action.to !== stage) return action;
      const { to: _here, ...rest } = action;
      return { ...rest, target: ON_THIS_PAGE[stage] };
    }),
  };
}

function stepFor(
  stage: Stage,
  project: ProjectFacts,
  approvals: ApprovalMap,
  images: ImageFacts,
  budget: BudgetFacts,
): NextStep {
  if (stage === "track") return trackStep(project);
  if (stage === "script") return scriptStep(project, approvals);
  if (stage === "story") return storyStep(project, approvals);
  if (stage === "storyboard") return storyboardStep(project, approvals);
  if (stage === "images") return imagesStep(project, approvals, images, budget);
  if (stage === "sound") return soundStep(project);
  return filmStep(project, approvals, images);
}

export function nextStep(
  stage: Stage,
  project: ProjectFacts,
  approvals: ApprovalMap,
  images: ImageFacts,
  budget: BudgetFacts,
): NextStep {
  return stayHere(stage, stepFor(stage, project, approvals, images, budget));
}

export function stageWord(state: StageState | undefined): string {
  if (!state) return "Not ready";
  if (state === "running") return "Working";
  return DIFFICULTY_WORDS[state];
}
