/** One place for the sticky next-step copy and its single primary action. */

export type Stage = "track" | "story" | "storyboard" | "images" | "film";
export type StageState = "done" | "you" | "changed" | "not_ready" | "running";
export type NextTone = "done" | "you" | "changed" | "error";
export type NextTarget =
  | "analysis"
  | "approval"
  | "changes"
  | "brief"
  | "preview"
  | "render"
  | "make-missing"
  | "pictures";

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
};

export type ApprovalFacts = {
  state: "approved" | "stale" | "missing" | "unavailable";
  error?: string | null;
  blocking_stage?: string | null;
  expected_hash?: string | null;
  reason?: string | null;
};

export type ImageFacts = {
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

const DIFFICULTY_WORDS = {
  done: "Done",
  you: "Needs you",
  changed: "Changed",
  not_ready: "Not ready",
} as const;

function approval(map: ApprovalMap, stage: string): ApprovalFacts | undefined {
  return map[stage];
}

function approved(map: ApprovalMap, stage: string): boolean {
  return approval(map, stage)?.state === "approved";
}

function stateOf(project: ProjectFacts, stage: Stage): StageState | undefined {
  return project.stage_states?.[stage];
}

function trackIsReady(project: ProjectFacts): boolean {
  if (stateOf(project, "track") === "done") return true;
  if (project.has_analysis === true) {
    return !needsLyrics(project) || project.has_lyrics === true;
  }
  return false;
}

function needsLyrics(project: ProjectFacts): boolean {
  return (
    project.music_mode === "vocal" &&
    (project.kind === null || project.kind === undefined || project.kind === "music_video")
  );
}

function storyIsDone(project: ProjectFacts, approvals: ApprovalMap): boolean {
  return stateOf(project, "story") === "done" || approved(approvals, "brief");
}

function boardIsDone(project: ProjectFacts, approvals: ApprovalMap): boolean {
  return stateOf(project, "storyboard") === "done" || approved(approvals, "storyboard");
}

function approvedAction(label: string, stage?: string): NextAction[] {
  return [{ label, target: "approval", kind: "primary", ...(stage ? { approve: stage } : {}) }];
}

function continueTo(stage: Stage, label: string): NextAction[] {
  return [{ label, to: stage, kind: "primary" }];
}

function trackStep(project: ProjectFacts): NextStep {
  if (stateOf(project, "track") === "running") {
    return {
      tone: "you",
      title: "Measuring the song…",
      detail: "Local analysis is running. Nothing is uploaded.",
      actions: [],
    };
  }
  if (!trackIsReady(project)) {
    return {
      tone: "you",
      title: "Measure the song first.",
      detail: "Local analysis finds sections, beats and energy. Nothing is uploaded.",
      actions: [{ label: "Run analysis", target: "analysis", kind: "primary" }],
    };
  }
  if (needsLyrics(project) && project.has_lyrics === false) {
    return {
      tone: "you",
      title: "Add the lyrics before approving the story.",
      detail: "The story is checked against the words.",
      actions: [{ label: "Add lyrics", to: "track", kind: "primary" }],
    };
  }
  return {
    tone: "done",
    title: "Track is ready.",
    detail: "The measured song is ready for the story.",
    actions: continueTo("story", "Continue to Story"),
  };
}

function storyStep(project: ProjectFacts, approvals: ApprovalMap): NextStep {
  const brief = approval(approvals, "brief");
  if (brief?.state === "unavailable") {
    if (
      brief.blocking_stage === "analysis" ||
      String(brief.error || "").toLowerCase().includes("analysis")
    ) {
      return {
        tone: "you",
        title: "Measure the song first — the story is built from it.",
        detail: "Local analysis finds the sections, beats and energy the Writer needs.",
        actions: [{ label: "Go to Track", to: "track", kind: "primary" }],
      };
    }
    if (
      brief.blocking_stage === "lyrics" ||
      String(brief.error || "").toLowerCase().includes("lyrics")
    ) {
      return {
        tone: "you",
        title: "Add the lyrics first — the story is checked against them.",
        detail: "Track holds the words the Writer must work from.",
        actions: [{ label: "Go to Track", to: "track", kind: "primary" }],
      };
    }
    return {
      tone: "you",
      title: "The story is not ready yet.",
      detail: brief.error || "Complete the artifact this stage depends on.",
      actions: [{ label: "Go to Story", to: "story", kind: "primary" }],
    };
  }
  if (
    !storyIsDone(project, approvals) &&
    needsLyrics(project) &&
    project.has_lyrics === false
  ) {
    return {
      tone: "you",
      title: "Add the lyrics first — the story is checked against them.",
      detail: "Track holds the words the Writer must work from.",
      actions: [{ label: "Go to Track", to: "track", kind: "primary" }],
    };
  }
  if (storyIsDone(project, approvals)) {
    return {
      tone: "done",
      title: "Story approved.",
      detail: "Changes here will ask you to approve it again.",
      actions: continueTo("storyboard", "Continue to Storyboard"),
    };
  }
  if (stateOf(project, "story") === "not_ready" && !brief) {
    return {
      tone: "you",
      title: "Write the story first.",
      detail: "Pick a direction and shape the treatment.",
      actions: [{ label: "Write the story", to: "story", kind: "primary" }],
    };
  }
  if (
    (!brief || brief.state === "missing") &&
    project.kind !== null &&
    project.kind !== undefined &&
    project.kind !== "music_video" &&
    (project.has_message === false ||
      (project.kind === "advert" && project.has_cta === false))
  ) {
    return {
      tone: "you",
      title:
        project.kind === "advert"
          ? "Say what the advert should make people do."
          : "Say what the promo is about.",
      detail: "The Brief card on Story holds the facts the film must not invent.",
      actions: [{ label: "Edit brief", target: "brief", kind: "primary" }],
    };
  }
  if (project.prompt_version === 2 && (project.profile_version ?? 0) < 1) {
    return {
      tone: "you",
      title: "Build the cast, places and rules.",
      detail:
        "The Writer turns the treatment into the structured profile the stills use. " +
        "The story cannot be approved before it exists.",
      actions: [{ label: "Open Story", to: "story", kind: "primary" }],
    };
  }
  if (brief?.state === "stale" || stateOf(project, "story") === "changed") {
    return {
      tone: "changed",
      title: "The story changed since you approved it.",
      detail:
        brief?.reason || brief?.error || "Read the current version before approving it again.",
      actions: [
        { label: "See what changed", target: "changes" },
        { label: "Approve story", target: "approval", kind: "primary", approve: "brief" },
      ],
    };
  }
  return {
    tone: "you",
    title: "Read the story and approve it.",
    detail: "Approval unlocks the storyboard. A note is optional.",
    actions: approvedAction("Approve story", "brief"),
  };
}

function storyboardStep(project: ProjectFacts, approvals: ApprovalMap): NextStep {
  if (!storyIsDone(project, approvals)) {
    return {
      tone: "you",
      title: "The story needs approval first.",
      detail: "The storyboard is built from the approved story.",
      actions: continueTo("story", "Go to Story"),
    };
  }
  if (stateOf(project, "storyboard") === "not_ready") {
    return {
      tone: "you",
      title: "No storyboard yet. Make one in Storyboard.",
      detail: "Start with a timing skeleton, then shape each shot.",
      actions: continueTo("storyboard", "Make the storyboard"),
    };
  }
  if (boardIsDone(project, approvals)) {
    return {
      tone: "done",
      title: "Storyboard approved.",
      detail: "Its timing and shot content are signed off.",
      actions: continueTo("images", "Continue to Images"),
    };
  }
  if (approval(approvals, "storyboard")?.state === "stale" || stateOf(project, "storyboard") === "changed") {
    return {
      tone: "changed",
      title: "The storyboard changed since you approved it.",
      detail: "Review the current shots before approving again.",
      actions: approvedAction("Approve storyboard", "storyboard"),
    };
  }
  return {
    tone: "you",
    title: "Read the storyboard and approve it.",
    detail: "Shot timing and content unlock the style check.",
    actions: approvedAction("Approve storyboard", "storyboard"),
  };
}

function imagesStep(
  project: ProjectFacts,
  approvals: ApprovalMap,
  images: ImageFacts,
  budget: BudgetFacts,
): NextStep {
  if (!boardIsDone(project, approvals)) {
    return {
      tone: "you",
      title: "Approve the storyboard before making pictures.",
      detail: "Pictures are generated from the approved shots.",
      actions: continueTo("storyboard", "Go to Storyboard"),
    };
  }
  if (images.running) {
    return {
      tone: "you",
      title: "Making stills…",
      detail: images.running_line
        ? `${images.running_line}. They appear below as they arrive; keep reviewing meanwhile.`
        : "They appear below as they arrive; keep reviewing meanwhile.",
      actions: [],
    };
  }
  if (stateOf(project, "images") === "done" || approved(approvals, "stills")) {
    return {
      tone: "done",
      title: "All stills approved.",
      detail: "Every picture is kept.",
      actions: continueTo("film", "Continue to Film"),
    };
  }
  const proof = approval(approvals, "proof");
  const proofChanged = proof?.state === "stale" || stateOf(project, "images") === "changed";
  if (!proof || proof.state !== "approved") {
    const total = images.proof_total ?? 0;
    const missingIds = images.proof_missing_ids || [];
    const staleIds = images.proof_stale_ids || [];
    const needsWork = [...missingIds, ...staleIds];
    const kept = images.proof_kept ?? 0;
    const stale = staleIds.length > 0;
    const title = proofChanged
      ? "The style check changed."
      : stale
        ? "Older style-check stills need a remake."
        : "Finish the style check.";
    if (total > 0 && needsWork.length > 0) {
      const reserve = Number(images.reserve_usd || "0.05");
      return {
        tone: proofChanged ? "changed" : "you",
        title,
        detail: stale
          ? `${staleIds.length} style-check still${
              staleIds.length === 1 ? " is" : "s are"
            } from a previous look; remake ${
              staleIds.length === 1 ? "it" : "them"
            } before approving. The rest wait until they look right.`
          : `Make the ${total} hard shots first; the rest wait until they look right.`,
        actions: [
          {
            label: `${stale ? "Remake" : "Make"} ${needsWork.length} style still${
              needsWork.length === 1 ? "" : "s"
            } · $${(needsWork.length * reserve).toFixed(2)}`,
            target: "make-missing",
            kind: "primary",
            paid: { ids: needsWork, scope: "proof" },
          },
        ],
      };
    }
    if (total > 0 && kept >= total && proof?.expected_hash) {
      return {
        tone: proofChanged ? "changed" : "you",
        title: proofChanged ? "The style check changed." : "All style-check stills kept.",
        detail: "Approve the style check to unlock the rest. A note is optional.",
        actions: approvedAction("Approve style check", "proof"),
      };
    }
    return {
      tone: proofChanged ? "changed" : "you",
      title,
      detail:
        total > 0
          ? `Keep or redo each style-check still (${kept} of ${total} kept), then approve them.`
          : proofChanged
            ? "Review the current style-check shots before making the rest."
            : "Keep or redo the style-check shots, then approve them.",
      actions: [{ label: "Review style check", target: "pictures", kind: "primary" }],
    };
  }
  const left = budget.remaining_usd ? ` Budget left ${budget.remaining_usd}.` : "";
  if (images.missing > 0) {
    const ids = images.missing_ids || [];
    const reserve = Number(images.reserve_usd || "0.05");
    const total = (images.missing * reserve).toFixed(2);
    const label =
      images.missing === 1 && ids.length === 1
        ? `Make ${ids[0]} · $${total}`
        : `Make all ${images.missing} missing · $${total}`;
    return {
      tone: "you",
      title: `Style check approved. Make ${images.missing} missing ${
        images.missing === 1 ? "picture" : "pictures"
      }.`,
      detail: `Only paid scene and generated shots cost money.${left}`,
      actions:
        ids.length === images.missing
          ? [
              {
                label,
                target: "make-missing",
                kind: "primary",
                paid: { ids, scope: "stills" },
              },
            ]
          : [{ label: "Go to Images", target: "pictures", kind: "primary" }],
    };
  }
  if (images.kept < images.total) {
    return {
      tone: "you",
      title: `Review the remaining ${images.total - images.kept} ${
        images.total - images.kept === 1 ? "picture" : "pictures"
      }.`,
      detail: `Keep or redo every paid still.${left}`,
      actions: [{ label: "Review pictures", target: "pictures", kind: "primary" }],
    };
  }
  return {
    tone: "you",
    title: "Approve all stills.",
    detail: "Every picture is kept; sign the full set off.",
    actions: approvedAction("Approve all stills", "stills"),
  };
}

function filmStep(project: ProjectFacts, approvals: ApprovalMap): NextStep {
  if (stateOf(project, "film") === "done") {
    return {
      tone: "done",
      title: "Final ready.",
      detail: "A verified final of the current cut is under Rendered files.",
      actions: [],
    };
  }
  if (!(stateOf(project, "images") === "done" || approved(approvals, "stills"))) {
    return {
      tone: "you",
      title: "Approve every picture before the final.",
      detail: "The final render needs the approved still set.",
      actions: continueTo("images", "Go to Images"),
    };
  }
  const preview = approval(approvals, "preview");
  if (project.preview_required !== false && (!preview || preview.state !== "approved")) {
    return {
      tone: preview?.state === "stale" ? "changed" : "you",
      title:
        preview?.state === "stale"
          ? "The preview changed. Watch it again."
          : "Watch the preview with sound.",
      detail: "The preview is free and marked; it confirms timing and camera.",
      actions: [{ label: "Watch preview", target: "preview", kind: "primary" }],
    };
  }
  const graphics = approval(approvals, "graphics");
  if (project.signature_required !== false && (!graphics || graphics.state !== "approved")) {
    return {
      tone: graphics?.state === "stale" ? "changed" : "you",
      title:
        graphics?.state === "stale"
          ? "The titles changed. Check them again."
          : "Check the titles on real frames.",
      detail: "Check titles renders stills of the real film with its titles. Inspect them and explicitly approve intro/credits before the final.",
      actions: [{ label: "Check titles", target: "render", kind: "primary" }],
    };
  }
  return {
    tone: "done",
    title: "Ready to render final.",
    detail: project.signature_required !== false
      ? "Every gate is approved. Final reuses the reviewed base, adds approved intro/credits, then verifies delivery."
      : "Every gate is approved. Render the final locally, then verify the file before delivery.",
    actions: [{ label: "Render final", target: "render", kind: "primary" }],
  };
}

export function nextStep(
  stage: Stage,
  project: ProjectFacts,
  approvals: ApprovalMap,
  images: ImageFacts,
  budget: BudgetFacts,
): NextStep {
  if (stage === "track") return trackStep(project);
  if (stage === "story") return storyStep(project, approvals);
  if (stage === "storyboard") return storyboardStep(project, approvals);
  if (stage === "images") return imagesStep(project, approvals, images, budget);
  return filmStep(project, approvals);
}

export function stageWord(state: StageState | undefined): string {
  if (!state) return "Not ready";
  if (state === "running") return "Working";
  return DIFFICULTY_WORDS[state];
}
