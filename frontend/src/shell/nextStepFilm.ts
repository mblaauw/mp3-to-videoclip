import type {
  ApprovalMap,
  BudgetFacts,
  ImageFacts,
  NextStep,
  ProjectFacts,
} from "./nextStep.ts";
import { approval, approved, stateOf, boardIsDone, approvedAction, continueTo } from "./nextStepSteps.ts";

export function imagesStep(
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
    if (total === 0 && proof?.expected_hash) {
      return {
        tone: proofChanged ? "changed" : "you",
        title: "No stills to buy for this film.",
        detail: "Every picture is your own or made here. Check them, then approve.",
        actions: approvedAction("Approve the pictures", "proof"),
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

/** Stills are approved with the cut, so a new cut needs that sign-off, not a new review. */
function onlyTheCutChanged(approvals: ApprovalMap, images: ImageFacts): boolean {
  return (
    approval(approvals, "stills")?.state === "stale" &&
    !!approval(approvals, "stills")?.expected_hash &&
    images.kept === images.total &&
    images.selected === images.total &&
    !images.stale
  );
}

export function filmStep(project: ProjectFacts, approvals: ApprovalMap, images: ImageFacts): NextStep {
  if (project.has_storyboard === false) {
    return {
      tone: "you",
      title: "This film has no storyboard yet.",
      detail: "The cut is made from the storyboard's shots.",
      actions: continueTo("storyboard", "Go to Storyboard"),
    };
  }
  if (stateOf(project, "film") === "done") {
    return {
      tone: "done",
      title: "Final ready.",
      detail: "A verified final of the current cut is under Rendered files.",
      actions: continueTo("publish", "Go to Publish"),
    };
  }
  if (onlyTheCutChanged(approvals, images)) {
    return {
      tone: "changed",
      title: "The cut changed.",
      detail: "No picture changed. Approving records this cut for the final.",
      actions: approvedAction("Approve this cut", "stills"),
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
    if (project.titles_review_ready) {
      return {
        tone: "you",
        title: "Review the titles.",
        detail: "Open every sample, then approve intro/credits.",
        actions: [{ label: "Review titles", target: "render", kind: "primary" }],
      };
    }
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
      ? "Every gate is approved. Render final draws the film with the intro/credits you approved, then verifies delivery."
      : "Every gate is approved. Render the final locally, then verify the file before delivery.",
    actions: [{ label: "Render final", target: "render", kind: "primary" }],
  };
}
