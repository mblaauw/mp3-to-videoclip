import type {
  ApprovalFacts,
  ApprovalMap,
  NextAction,
  NextStep,
  ProjectFacts,
  Stage,
  StageState,
} from "./nextStep.ts";
export const DIFFICULTY_WORDS = {
  done: "Done",
  you: "Needs you",
  changed: "Changed",
  not_ready: "Not ready",
} as const;

export function approval(map: ApprovalMap, stage: string): ApprovalFacts | undefined {
  return map[stage];
}

export function approved(map: ApprovalMap, stage: string): boolean {
  return approval(map, stage)?.state === "approved";
}

export function stateOf(project: ProjectFacts, stage: Stage): StageState | undefined {
  return project.stage_states?.[stage];
}

function trackIsMeasured(project: ProjectFacts): boolean {
  return stateOf(project, "track") === "done" || project.has_analysis === true;
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

export function boardIsDone(project: ProjectFacts, approvals: ApprovalMap): boolean {
  return stateOf(project, "storyboard") === "done" || approved(approvals, "storyboard");
}

export function approvedAction(label: string, stage?: string): NextAction[] {
  return [{ label, target: "approval", kind: "primary", ...(stage ? { approve: stage } : {}) }];
}

export function continueTo(stage: Stage, label: string): NextAction[] {
  return [{ label, to: stage, kind: "primary" }];
}

export function trackStep(project: ProjectFacts): NextStep {
  if (stateOf(project, "track") === "running") {
    return {
      tone: "you",
      title: "Measuring the song…",
      detail: "Local analysis is running. Nothing is uploaded.",
      actions: [],
    };
  }
  if (!trackIsMeasured(project)) {
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
      actions: [{ label: "Add lyrics", target: "lyrics", kind: "primary" }],
    };
  }
  return {
    tone: "done",
    title: "Track is ready.",
    detail: "The measured song is ready for the story.",
    actions: continueTo("story", "Continue to Story"),
  };
}

export function storyStep(project: ProjectFacts, approvals: ApprovalMap): NextStep {
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
    const refused = /permission to upload\/depict (\S+)/.exec(String(brief.error || ""));
    if (refused) {
      const names = project.permission_pending?.length
        ? project.permission_pending.join(", ")
        : refused[1];
      return {
        tone: "you",
        title: `Confirm permission for ${names}.`,
        detail: "The World part holds the card. Only you can confirm it.",
        actions: [{ label: "Go to World", target: "world", kind: "primary" }],
      };
    }
    return {
      tone: "you",
      title: "The story is not ready yet.",
      detail: brief.error || "Complete the artifact this stage depends on.",
      actions: [{ label: "Open the brief", target: "brief", kind: "primary" }],
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
  if ((project.prompt_version ?? 0) >= 2 && (project.profile_version ?? 0) < 1) {
    if (project.has_model_key === false) {
      return {
        tone: "you",
        title: "The director needs a model key.",
        detail: "The Writer builds the cast, places and rules the stills use. Add a key to ask it.",
        actions: [{ label: "Open settings", target: "settings", kind: "primary" }],
      };
    }
    return {
      tone: "you",
      title: "Ask the Writer to build the cast and places.",
      detail:
        "The Writer turns the treatment into the structured profile the stills use. " +
        "The story cannot be approved before it exists.",
      actions: [{ label: "Open the Director", target: "director", kind: "primary" }],
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

export function scriptStep(project: ProjectFacts, approvals: ApprovalMap): NextStep {
  if (!storyIsDone(project, approvals)) {
    return {
      tone: "you",
      title: "The story needs approval first.",
      detail: "The narrator's words come from the approved story.",
      actions: continueTo("story", "Go to Story"),
    };
  }
  const script = approval(approvals, "script");
  const voice = approval(approvals, "voice");
  if (!script || script.state === "missing" || script.state === "unavailable") {
    return {
      tone: "you",
      title: "Write the script with the Writer.",
      detail: "Each line sits on a beat, and the beat sheet shows it against that beat's budget.",
      actions: [],
    };
  }
  if (script.state !== "approved") {
    return {
      tone: script.state === "stale" ? "changed" : "you",
      title: script.state === "stale" ? "The script changed. Approve it again." : "Approve the script.",
      detail: "Takes are only bought for an approved script. Nothing is spent here.",
      actions: approvedAction("Approve the script", "script"),
    };
  }
  if (!voice || voice.state === "missing" || voice.state === "unavailable") {
    return {
      tone: "you",
      title: "Build the soundtrack.",
      detail: "Record the lines or bring your own takes, keep the ones you like, and hear the draft.",
      actions: [],
    };
  }
  if (voice.state !== "approved") {
    return {
      tone: voice.state === "stale" ? "changed" : "you",
      title: voice.state === "stale" ? "The voice changed. Approve it again." : "Approve the voice.",
      detail: "The kept takes are the film's clock, so the shots are cut to them next.",
      actions: approvedAction("Approve the voice", "voice"),
    };
  }
  return {
    tone: "done",
    title: "The voice is approved.",
    detail: "The storyboard is built from when each line is said.",
    actions: continueTo("storyboard", "Go to Storyboard"),
  };
}

export function storyboardStep(project: ProjectFacts, approvals: ApprovalMap): NextStep {
  if (!storyIsDone(project, approvals)) {
    return {
      tone: "you",
      title: "The story needs approval first.",
      detail: "The storyboard is built from the approved story.",
      actions: continueTo("story", "Go to Story"),
    };
  }
  if (project.spine === "soundtrack" && !approved(approvals, "script")) {
    return {
      tone: "you",
      title: "The script needs approval first.",
      detail: "A story film's shots are cut to its lines.",
      actions: continueTo("script", "Go to Script"),
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
  const unfinished = project.placeholder_shot_ids?.length ?? 0;
  if (unfinished > 0) {
    return {
      tone: "you",
      title: `${unfinished} ${unfinished === 1 ? "shot still needs" : "shots still need"} a job and a prompt.`,
      detail: "The storyboard cannot be approved until every shot says what it is for.",
      actions: [{ label: "Show them", target: "placeholders", kind: "primary" }],
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

/** Sound is optional: the bar says where it stands and never blocks the film. */
export function soundStep(project: ProjectFacts): NextStep {
  const cues = project.sound_cues ?? 0;
  const silent = cues - (project.sound_sounding ?? 0);
  if (cues === 0) {
    return {
      tone: "done",
      title: "The film's sound is its music or its narration",
      detail: "Add a cue here when a moment needs one; the film can be rendered without.",
      actions: continueTo("film", "Go to Film"),
    };
  }
  if (silent > 0) {
    return {
      tone: "you",
      title: `${silent} of ${cues} cue${cues === 1 ? "" : "s"} ${silent === 1 ? "has" : "have"} no sound yet`,
      detail: "Make it at the shown price, bring your own file, or remove the cue.",
      actions: continueTo("film", "Go to Film anyway"),
    };
  }
  return {
    tone: "done",
    title: `${cues} cue${cues === 1 ? "" : "s"} in the mix`,
    detail: "The Player and every render hear them under the speech.",
    actions: continueTo("film", "Go to Film"),
  };
}
