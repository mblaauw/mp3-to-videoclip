import { useState } from "react";
import { api, type Job } from "../api";
import { Button, StatusDot } from "../ui";
import { useProjectJobs } from "./store";

const TITLE: Record<string, string> = {
  images: "Making stills",
  render: "Rendering",
  analysis: "Measuring the song",
  transcription: "Transcribing the lyrics",
};

/** Engine phases in plain words; unknown phases are shown as they come. */
const PHASE: Record<string, string> = {
  starting: "Starting",
  "submitting-images": "Sending to the image service",
  "receiving-images": "Receiving stills",
  "validating-request": "Checking the request",
  "bundle-cached": "Renderer ready",
  bundling: "Preparing the renderer",
  "selecting-composition": "Preparing the film",
  "rendering-visuals": "Rendering frames",
  rendering: "Rendering frames",
  encoding: "Encoding",
  "muxing-audio": "Adding the music",
  "verifying-output": "Checking the file",
};

function phaseWords(phase: string | undefined): string {
  if (!phase) return "";
  return PHASE[phase] || phase.replace(/[-_]/g, " ");
}

export function jobLine(job: Job): string {
  const progress = job.progress;
  const parts: string[] = [];
  if (job.status === "stopping") return "Stopping — waiting for work already started to finish";
  if (job.status === "interrupted") return "Interrupted — check existing results before retrying";
  if (job.status === "queued") parts.push("Waiting for the film's previous job");
  else if (progress.phase) parts.push(phaseWords(progress.phase));
  if (progress.total > 0) {
    parts.push(`${progress.done} of ${progress.total}${progress.unit ? ` ${progress.unit}` : ""}`);
  }
  return parts.join(" · ");
}

/**
 * Inline progress for a film's background work, shown where its result will
 * appear (the contact sheet for stills, the delivery card for renders).
 */
export function JobBanner({
  slug,
  kinds,
  className = "",
}: {
  slug: string;
  kinds: string[];
  className?: string;
}) {
  const active = useProjectJobs(slug).filter((job) => kinds.includes(job.kind));
  const [cancelling, setCancelling] = useState<string | null>(null);
  if (!active.length) return null;
  return (
    <div className={`job-banner ${className}`} role="status" aria-live="polite">
      {active.map((job) => {
        const { done, total } = job.progress;
        const percent = total > 0 ? Math.min(100, (done / Math.max(1, total)) * 100) : null;
        return (
          <div className="job-banner-row" key={job.id}>
            <StatusDot tone={job.status === "running" ? "run" : "you"} />
            <div className="job-banner-copy">
              <b>{TITLE[job.kind] || job.kind.replace(/_/g, " ")}</b>
              <span>{jobLine(job) || "Working…"}</span>
            </div>
            <Button
              size="small"
              variant="quiet"
              disabled={cancelling === job.id || job.status === "stopping"}
              title={
                job.kind === "images"
                  ? "Sends no more stills. A still that is already out finishes and is recorded."
                   : "Requests a stop. This film stays busy until work already running finishes."
              }
              onClick={async () => {
                setCancelling(job.id);
                try {
                  await api.cancelJob(job.id);
                } finally {
                  setCancelling(null);
                }
              }}
            >
              {job.status === "stopping" || cancelling === job.id ? "Stopping…" : "Cancel"}
            </Button>
            <div
              className={`job-bar ${percent === null ? "indeterminate" : ""}`}
              role="progressbar"
              aria-label={`${TITLE[job.kind] || job.kind} progress`}
              {...(percent === null
                ? {}
                : { "aria-valuemin": 0, "aria-valuemax": total, "aria-valuenow": done })}
            >
              <i style={percent === null ? undefined : { width: `${percent}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}
