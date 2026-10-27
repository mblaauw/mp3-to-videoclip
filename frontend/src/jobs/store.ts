/**
 * The one shared server-event connection.
 *
 * It keeps the job tray current (queued → running with progress → finished) and
 * turns every server change notice into the app-wide "reload" signal, so a view
 * never needs a manual browser refresh:
 *
 * - `project.changed` — a save from any tab, a director tool, a job that
 *   finished (or finished one more still), or a CLI write the server noticed;
 * - `library.changed` — a film was added or removed;
 * - a reconnect after a drop — anything may have changed while we were away.
 */

import { useEffect, useSyncExternalStore } from "react";
import type { Job, JobDetail } from "../api";
import { notifyProjectChanged } from "../shell/projectEvents";
import { goFilm, parseHash } from "../shell/route";
import { toast } from "../toast";

export type JobsConnection = "connecting" | "live" | "retrying";
export type JobsSnapshot = {
  jobs: Job[];
  connection: JobsConnection;
};

const JOB_EVENTS = [
  "job.queued",
  "job.started",
  "job.progress",
  "job.succeeded",
  "job.failed",
  "job.cancelled",
] as const;

type JobEventName = (typeof JOB_EVENTS)[number];

type ServerEvent = {
  job_id?: string;
  kind?: string;
  project?: string;
  error?: string;
  progress?: Partial<Job["progress"]>;
  source?: string;
  artifact?: string;
  tool?: string;
};

const ACTIVE = ["queued", "running", "needs_budget"];

let snapshot: JobsSnapshot = { jobs: [], connection: "connecting" };
let source: EventSource | null = null;
let retryTimer: number | null = null;
let retry = 0;
let started = false;
let everConnected = false;
const listeners = new Set<() => void>();

function emit(next: Partial<JobsSnapshot>) {
  snapshot = { ...snapshot, ...next };
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return snapshot;
}

function sortJobs(jobs: Job[]): Job[] {
  return [...jobs].sort((a, b) => {
    const activeA = ACTIVE.includes(a.status) ? 1 : 0;
    const activeB = ACTIVE.includes(b.status) ? 1 : 0;
    if (activeA !== activeB) return activeB - activeA;
    const timeA = Number(a.started_at || a.queued_at || 0);
    const timeB = Number(b.started_at || b.queued_at || 0);
    return timeB - timeA;
  });
}

function upsert(job: Job) {
  const index = snapshot.jobs.findIndex((entry) => entry.id === job.id);
  const jobs =
    index === -1
      ? [job, ...snapshot.jobs]
      : snapshot.jobs.map((entry) => (entry.id === job.id ? { ...entry, ...job } : entry));
  emit({ jobs: sortJobs(jobs) });
}

function patch(jobId: string, changes: Partial<Job>) {
  if (!snapshot.jobs.some((entry) => entry.id === jobId)) {
    void refreshJob(jobId);
    return;
  }
  const jobs = snapshot.jobs.map((entry) =>
    entry.id === jobId ? { ...entry, ...changes } : entry,
  );
  emit({ jobs: sortJobs(jobs) });
}

/** Background reads stay quiet; the jobs tray is not an error surface. */
async function getJson<T>(path: string): Promise<T | null> {
  try {
    const response = await fetch(path);
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function refresh() {
  const jobs = await getJson<Job[]>("/api/jobs");
  if (jobs) emit({ jobs: sortJobs(jobs) });
}

async function refreshJob(jobId: string) {
  const job = await getJson<JobDetail>(`/api/jobs/${jobId}`);
  if (job) upsert(job);
}

function parseEvent(event: Event): ServerEvent {
  try {
    return JSON.parse((event as MessageEvent<string>).data) as ServerEvent;
  } catch {
    return {};
  }
}

/** The film this tab is looking at, if any. */
function openSlug(): string | null {
  const route = parseHash(window.location.hash);
  return route.kind === "library" ? null : route.slug;
}

const FINISHED: Record<string, string> = {
  images: "New stills are ready.",
  render: "The render finished.",
  analysis: "The song is measured.",
  transcription: "The lyrics are transcribed.",
};

const FAILED: Record<string, string> = {
  images: "Making the stills stopped",
  render: "The render failed",
  analysis: "Measuring the song failed",
  transcription: "Transcription failed",
};

function announce(name: JobEventName, payload: ServerEvent) {
  const kind = payload.kind || "job";
  const slug = payload.project || "";
  const here = slug && slug === openSlug();
  if (name === "job.succeeded") {
    const message = FINISHED[kind];
    if (!message) return;
    const target = kind === "images" ? "images" : kind === "render" ? "film" : null;
    const route = parseHash(window.location.hash);
    const onPage = route.kind === "film" && route.slug === slug && route.stage === target;
    toast(
      here || !slug ? message : `${slug}: ${message}`,
      "done",
      target && slug && !onPage
        ? { label: target === "images" ? "Review" : "Open Film", run: () => goFilm(slug, target) }
        : undefined,
    );
    return;
  }
  if (name === "job.failed") {
    const what = FAILED[kind] || "A job failed";
    toast(`${here || !slug ? "" : `${slug}: `}${what}: ${payload.error || "unknown error"}`);
  }
}

function handleJob(name: JobEventName, event: Event) {
  const payload = parseEvent(event);
  const jobId = payload.job_id;
  if (!jobId) return;
  const now = Date.now() / 1000;
  if (name === "job.queued") {
    upsert({
      id: jobId,
      kind: payload.kind || "job",
      project: payload.project || "",
      status: "queued",
      progress: { done: 0, total: 0, unit: "", phase: "" },
      cost_usd: 0,
      error: null,
      queued_at: now,
      started_at: null,
      finished_at: null,
    } as Job);
    return;
  }
  if (name === "job.started") {
    patch(jobId, { status: "running", started_at: now });
    return;
  }
  if (name === "job.progress") {
    const current = snapshot.jobs.find((entry) => entry.id === jobId);
    patch(jobId, {
      status: "running",
      progress: { ...(current?.progress || { done: 0, total: 0, unit: "" }), ...payload.progress } as Job["progress"],
    });
    return;
  }
  if (name === "job.succeeded") {
    patch(jobId, { status: "succeeded", finished_at: now });
  } else if (name === "job.failed") {
    patch(jobId, { status: "failed", error: payload.error || "job failed", finished_at: now });
  } else {
    patch(jobId, { status: "cancelled", finished_at: now });
  }
  announce(name, payload);
  void refreshJob(jobId);
}

function handleChange(event: Event) {
  const payload = parseEvent(event);
  const slug = payload.project;
  const open = openSlug();
  // Another film changing does not concern this tab's film view; the library
  // (no film open) shows every film, so it hears every change.
  if (slug && open && slug !== open) return;
  notifyProjectChanged({
    slug: slug || undefined,
    source: payload.source || "server",
    artifact: payload.artifact,
  });
}

function scheduleReconnect() {
  if (retryTimer !== null) return;
  const delay = Math.min(30_000, 1_000 * 2 ** retry);
  retry += 1;
  emit({ connection: "retrying" });
  retryTimer = window.setTimeout(() => {
    retryTimer = null;
    connect();
  }, delay);
}

function connect() {
  if (typeof EventSource === "undefined") return;
  if (source) {
    source.close();
    source = null;
  }
  const stream = new EventSource("/api/events");
  source = stream;
  stream.onopen = () => {
    const resumed = everConnected;
    everConnected = true;
    retry = 0;
    emit({ connection: "live" });
    void refresh();
    // While we were away saves, jobs and director turns may have happened.
    if (resumed) notifyProjectChanged({ source: "reconnect" });
  };
  stream.onerror = () => {
    if (source !== stream) return;
    stream.close();
    source = null;
    scheduleReconnect();
  };
  for (const name of JOB_EVENTS) {
    stream.addEventListener(name, (event) => handleJob(name, event));
  }
  stream.addEventListener("project.changed", handleChange);
  stream.addEventListener("library.changed", () =>
    notifyProjectChanged({ source: "library" }),
  );
}

function wake() {
  if (document.visibilityState !== "visible") return;
  if (snapshot.connection === "live") return;
  if (retryTimer !== null) {
    window.clearTimeout(retryTimer);
    retryTimer = null;
  }
  retry = 0;
  connect();
}

/** Start the one shared SSE connection and initial job snapshot. */
export function startJobs() {
  if (started) return;
  started = true;
  void refresh();
  connect();
  document.addEventListener("visibilitychange", wake);
  window.addEventListener("online", wake);
}

export function useJobs(): JobsSnapshot {
  const state = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  useEffect(() => {
    startJobs();
  }, []);
  return state;
}

export function isActive(job: Job): boolean {
  return ACTIVE.includes(job.status);
}

/** Active jobs for one film, newest first. */
export function useProjectJobs(slug: string, kind?: string): Job[] {
  const { jobs } = useJobs();
  return jobs.filter(
    (job) => job.project === slug && isActive(job) && (!kind || job.kind === kind),
  );
}
