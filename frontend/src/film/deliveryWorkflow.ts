import type { DeliveryChecklist, FilmFile, GraphicsReview, Job } from "../api.ts";

export const DELIVERY_STAGES: Record<string, string> = {
  "base-render": "Base film",
  "graphics-review": "Titles review stills",
  "preview-render": "Marked preview",
  "final-render": "Final film",
  "final-composite": "Final composite",
};

/** Derive the next human action from evidence, never from a job's success alone. */
export function deliveryWorkflow(
  files: FilmFile[], checklist: DeliveryChecklist | null,
  graphics: GraphicsReview | null, jobs: Job[],
): { title: string; detail: string; ready: boolean; notice: string | null } {
  const latest = [...jobs].sort((a, b) => (b.queued_at || 0) - (a.queued_at || 0))[0];
  const active = jobs.find((job) => ["queued", "running", "stopping"].includes(job.status));
  const notice = latest && ["failed", "cancelled", "interrupted"].includes(latest.status)
    ? `Last ${latest.render_kind || "render"} job ${latest.status}. Check existing results before retrying.${latest.error ? ` ${latest.error}` : ""}` : null;
  const result = (title: string, detail: string, ready = false) => ({ title, detail, ready, notice });
  if (active) {
    if (active.status === "stopping") return result("Stopping render", "Waiting for work already started to finish. No next stage starts automatically.");
    return result(active.status === "queued" ? "Render queued" : DELIVERY_STAGES[active.progress.stage || ""] || `Rendering ${active.render_kind || "film"}`,
      active.render_kind === "titles" ? "Rendering stills of the real film with its titles. Your explicit intro/credits approval comes next."
        : active.render_kind === "base" ? "The base is not delivery and does not prepare the titles review."
        : "The file must finish and pass verification before it is ready. No approval is automatic.");
  }
  if (files.some((file) => file.classification === "final" && file.current && file.verified && file.delivery_ready)) {
    return result("Ready for delivery", "A current final file has passed verification. Play or download Final delivery in Files.", true);
  }
  if (!checklist) return result("Reading delivery status", "Delivery is not confirmed until the gates and file reports can be read.");
  if (!checklist.signature_required) return result(checklist.can_final ? "Ready to render final" : "Finish the delivery gates",
    "This production does not require intro/credits. Render final after the gates pass; the output is then verified.");
  const titles = checklist.lines.find((line) => line.id === "titles");
  if (titles?.state === "done") return checklist.can_final
    ? result("Ready for final composite", "Render final reuses the reviewed base, adds the approved intro/credits, then verifies the file. It does not rerender the base.")
    : result("Finish the delivery gates", "Intro/credits are already approved. Complete the remaining gates below before rendering the final composite; no second titles approval is needed.");
  if (graphics?.available && graphics.current === true && graphics.samples?.length) return result("Your intro/credits review", "Inspect every actual composited sample, then explicitly approve intro/credits. Rendering final remains a separate action.");
  return result(graphics?.available ? "Check the titles again" : "Check the titles", "Check titles renders stills of the real film with its titles. Then: your intro/credits review → final render → verification → ready for delivery.");
}
