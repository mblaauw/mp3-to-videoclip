import { useEffect, useRef, useState } from "react";
import { api, type Budget, type Job, type ProjectSummary } from "../api";
import { useJobs } from "../jobs/store";
import { toast } from "../toast";
import { Button, Pill, StatusDot, type PillTone, type StatusTone } from "../ui";
import { ChatIcon, ClockIcon, GearIcon, MarkIcon } from "../ui/icons";
import { stageWord, type Stage, type StageState } from "./nextStep";
import { STAGES } from "./stages";

const JOB_LABEL: Record<string, string> = {
  analysis: "Measuring the song",
  images: "Making pictures",
  render: "Rendering the film",
};

const JOB_PAST: Record<string, string> = {
  analysis: "Measured the song",
  images: "Made the pictures",
  render: "Rendered the film",
};

const JOB_TONE: Record<string, { dot: StatusTone; pill: PillTone; word: string }> = {
  queued: { dot: "you", pill: "neutral", word: "Queued" },
  running: { dot: "run", pill: "you", word: "Running" },
  succeeded: { dot: "done", pill: "keep", word: "Done" },
  failed: { dot: "err", pill: "redo", word: "Failed" },
  cancelled: { dot: "idle", pill: "neutral", word: "Cancelled" },
  needs_budget: { dot: "you", pill: "you", word: "Needs budget" },
};

function meterWidth(value: string | null | undefined, cap: string | null | undefined): string {
  if (!cap || Number(cap) <= 0) return "0%";
  return `${Math.min(100, (Number(value || 0) / Number(cap)) * 100)}%`;
}

function BudgetPopover({
  slug,
  project,
  budget,
  onChanged,
  onClose,
}: {
  slug: string;
  project: ProjectSummary;
  budget: Budget | null;
  onChanged: () => void;
  onClose: () => void;
}) {
  const [amount, setAmount] = useState("2.00");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const remaining = budget?.remaining_usd ?? project.remaining_usd;
  const cap = budget?.cap_usd ?? null;

  const add = async () => {
    if (busy || !Number(amount)) return;
    setBusy(true);
    setError(null);
    try {
      const current = Number(cap || 0);
      const next = (current + Number(amount)).toFixed(2);
      await api.addBudget(slug, next, "Added from the Studio budget card");
      onChanged();
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="popover budget-popover" role="dialog" aria-label="Budget">
      <h3>{project.title} budget</h3>
      <div className="bigmeter" aria-hidden="true">
        <i
          style={{ width: meterWidth(budget?.spent_usd, cap), background: "var(--gold)" }}
        />
        <i
          style={{
            width: meterWidth(budget?.reserved_usd, cap),
            background: "var(--gold-wash)",
          }}
        />
      </div>
      <div className="pop-row">
        <span>Spent on {budget?.paid_stills ?? 0} stills</span>
        <b>{budget?.spent_usd ?? "0.00"}</b>
      </div>
      <div className="pop-row">
        <span>Reserved for running jobs</span>
        <b>{budget?.reserved_usd ?? "0.00"}</b>
      </div>
      <div className="pop-row">
        <span>Left</span>
        <b>
          {remaining ?? "—"} of {cap ?? "—"}
        </b>
      </div>
      <p className="pop-hint">
        The app spends inside this budget without asking. When it runs out, jobs pause and ask
        you.
      </p>
      <div className="pop-add">
        <input
          aria-label="Amount to add"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          inputMode="decimal"
        />
        <Button size="small" onClick={add} disabled={busy || !Number(amount)}>
          {busy ? "Adding…" : "Add to budget"}
        </Button>
      </div>
      {error && <p className="pop-error">{error}</p>}
      {!!budget?.history?.length && (
        <div className="pop-history">
          {budget.history
            .slice(-3)
            .reverse()
            .map((entry, index) => (
              <div className="pop-row" key={`${entry.at}-${index}`}>
                <span>{entry.reason}</span>
                <b>{entry.cap_usd}</b>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

function JobsPopover({
  jobs,
  project,
}: {
  jobs: Job[];
  project: ProjectSummary | null;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const active = jobs.filter((job) =>
    ["queued", "running", "needs_budget"].includes(job.status),
  );
  const shown = [...active, ...jobs.filter((job) => !active.includes(job))].slice(0, 8);
  const cancel = async (job: Job) => {
    setBusy(job.id);
    try {
      await api.cancelJob(job.id);
    } catch (caught) {
      toast(String(caught));
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="popover jobs-popover" role="dialog" aria-label="Jobs">
      <h3>Jobs</h3>
      {!shown.length && <p className="pop-hint">No jobs yet.</p>}
      {shown.map((job) => {
        const tone = JOB_TONE[job.status] || {
          dot: "idle" as const,
          pill: "neutral" as const,
          word: job.status,
        };
        const running = ["queued", "running", "needs_budget"].includes(job.status);
        const label = JOB_LABEL[job.kind] || job.kind.replaceAll("_", " ");
        return (
          <div className="job-row" key={job.id}>
            <StatusDot tone={tone.dot} />
            <span className="job-row-title">
              {job.status === "succeeded" ? JOB_PAST[job.kind] || label : label}
            </span>
            <Pill tone={tone.pill}>{tone.word}</Pill>
            {running && (
              <Button
                size="small"
                variant="quiet"
                onClick={() => cancel(job)}
                disabled={busy === job.id}
              >
                Cancel
              </Button>
            )}
            <span className="job-row-sub">
              {job.project === project?.slug ? project?.title : job.project}
              {job.progress.total > 0
                ? ` · ${job.progress.done} of ${job.progress.total} ${job.progress.unit}`
                : job.status === "running"
                  ? " · working…"
                  : ""}
              {job.cost_usd > 0 ? ` · $${job.cost_usd.toFixed(2)} so far` : ""}
            </span>
            {job.status === "running" && job.progress.total === 0 && (
              <div
                className="job-bar indeterminate"
                role="progressbar"
                aria-label={`${label} progress`}
              >
                <i />
              </div>
            )}
            {job.status === "running" && job.progress.total > 0 && (
              <div
                className="job-bar"
                role="progressbar"
                aria-label={`${label} progress`}
                aria-valuemin={0}
                aria-valuemax={job.progress.total}
                aria-valuenow={job.progress.done}
              >
                <i
                  style={{
                    width: `${Math.min(
                      100,
                      (job.progress.done / Math.max(1, job.progress.total)) * 100,
                    )}%`,
                  }}
                />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function TopBar({
  project,
  stage,
  budget,
  stageStates,
  onNavigate,
  onSettings,
  onBudgetChanged,
  directorOpen,
  onDirector,
}: {
  project: ProjectSummary | null;
  stage: Stage | null;
  budget: Budget | null;
  stageStates?: Partial<Record<Stage, StageState>>;
  onNavigate: (stage: Stage) => void;
  onSettings: () => void;
  onBudgetChanged: () => void;
  directorOpen: boolean;
  onDirector: () => void;
}) {
  const { jobs } = useJobs();
  const [pop, setPop] = useState<"budget" | "jobs" | null>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const running = jobs.filter((job) => job.status === "running").length;
  const activeJobs = jobs.filter((job) =>
    ["queued", "running", "needs_budget"].includes(job.status),
  ).length;
  const latest = jobs[0];
  const finished = latest?.finished_at ? Number(latest.finished_at) : 0;
  const recent = finished > 0 && Date.now() / 1000 - finished < 30;
  const jobStatus = activeJobs
    ? `${activeJobs} ${activeJobs === 1 ? "job" : "jobs"} in the tray.`
    : latest && recent
      ? `${JOB_PAST[latest.kind] || latest.kind.replaceAll("_", " ")}: ${latest.status}.`
      : "No jobs running.";
  const remaining = budget?.remaining_usd ?? project?.remaining_usd;
  const cap = budget?.cap_usd ?? null;
  const analysisRunning = jobs.some(
    (job) =>
      job.project === project?.slug &&
      job.kind === "analysis" &&
      ["queued", "running"].includes(job.status),
  );

  useEffect(() => {
    if (!pop) return;
    const close = (event: MouseEvent) => {
      if (!rightRef.current?.contains(event.target as Node)) setPop(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPop(null);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [pop]);

  useEffect(() => {
    if (!stage) return;
    const current = document.querySelector<HTMLElement>(`.step[aria-current="page"]`);
    current?.scrollIntoView({ block: "nearest", inline: "center", behavior: "auto" });
  }, [stage]);

  const states = stageStates || project?.stage_states || {};
  return (
    <header className="topbar">
      <a className="mark" href="#/" aria-label="Library">
        <MarkIcon />
        <span className="mark-word">Studio</span>
      </a>
      {project && stage && (
        <>
          <nav className="crumb" aria-label="Breadcrumb">
            <span className="crumb-sep">/</span>
            <span className="crumb-film">{project.title}</span>
          </nav>
          <nav className="stepper" aria-label="Stages">
            {STAGES.map((item, index) => {
              const state = (
                item.id === "track" && analysisRunning ? "running" : states[item.id]
              ) as StageState | undefined;
              return (
                <button
                  type="button"
                  key={item.id}
                  className={`step ${state || "not_ready"}`}
                  aria-current={item.id === stage ? "page" : undefined}
                  onClick={() => onNavigate(item.id)}
                >
                  <span className="step-n">{index + 1}</span>
                  <StatusDot
                    tone={
                      state === "done"
                        ? "done"
                        : state === "changed"
                          ? "changed"
                          : state === "not_ready"
                            ? "idle"
                            : state === "running"
                              ? "run"
                              : "you"
                    }
                  />
                  <span className="step-label">{item.label}</span>
                  <span className="step-state">{stageWord(state)}</span>
                </button>
              );
            })}
          </nav>
        </>
      )}
      <div className="top-right" ref={rightRef}>
        {project && (
          <button
            type="button"
            className="budget-chip"
            aria-expanded={pop === "budget"}
            aria-label="Budget"
            onClick={() => setPop(pop === "budget" ? null : "budget")}
          >
            <span>{remaining ? `$${remaining} left` : "Budget"}</span>
            {cap && (
              <span className="meter" aria-hidden="true">
                <i
                  style={{
                    width: meterWidth(budget?.committed_usd, cap),
                  }}
                />
              </span>
            )}
          </button>
        )}
        <button
          type="button"
          className="icon-btn jobs-button"
          aria-expanded={pop === "jobs"}
          aria-label={running ? `Jobs, ${running} running` : "Jobs"}
          onClick={() => setPop(pop === "jobs" ? null : "jobs")}
        >
          <ClockIcon />
          {running > 0 && <span className="jobs-count">{running}</span>}
        </button>
        {project && (
          <button
            type="button"
            className="icon-btn"
            aria-expanded={directorOpen}
            aria-label="Director"
            onClick={onDirector}
          >
            <ChatIcon />
          </button>
        )}
        <button type="button" className="icon-btn" aria-label="Settings" onClick={onSettings}>
          <GearIcon />
        </button>
        <span className="sr-only" role="status" aria-live="polite">
          {jobStatus}
        </span>
        {pop === "budget" && project && (
          <BudgetPopover
            slug={project.slug}
            project={project}
            budget={budget}
            onChanged={onBudgetChanged}
            onClose={() => setPop(null)}
          />
        )}
        {pop === "jobs" && <JobsPopover jobs={jobs} project={project} />}
      </div>
    </header>
  );
}
