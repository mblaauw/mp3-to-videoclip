import { useEffect, useSyncExternalStore } from "react";
import type { Job, JobDetail } from "../api";

export type JobsConnection = "connecting" | "live" | "retrying";
export type JobsSnapshot = {
  jobs: Job[];
  connection: JobsConnection;
};

const EVENT_NAMES = [
  "job.queued",
  "job.started",
  "job.succeeded",
  "job.failed",
  "job.cancelled",
] as const;

type JobEvent = {
  job_id?: string;
  kind?: string;
  project?: string;
  error?: string;
};

let snapshot: JobsSnapshot = { jobs: [], connection: "connecting" };
let source: EventSource | null = null;
let retryTimer: number | null = null;
let retry = 0;
let started = false;
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

function upsert(job: Job) {
  const index = snapshot.jobs.findIndex((entry) => entry.id === job.id);
  const jobs =
    index === -1
      ? [job, ...snapshot.jobs]
      : snapshot.jobs.map((entry) => (entry.id === job.id ? { ...entry, ...job } : entry));
  emit({ jobs });
}

function patch(jobId: string, changes: Partial<Job>) {
  const jobs = snapshot.jobs.map((entry) =>
    entry.id === jobId ? { ...entry, ...changes } : entry,
  );
  emit({ jobs });
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
  if (jobs) emit({ jobs });
}

async function refreshJob(jobId: string) {
  const job = await getJson<JobDetail>(`/api/jobs/${jobId}`);
  if (job) upsert(job);
}

function parseEvent(event: Event): JobEvent {
  try {
    return JSON.parse((event as MessageEvent<string>).data) as JobEvent;
  } catch {
    return {};
  }
}

function handle(name: (typeof EVENT_NAMES)[number], event: Event) {
  const payload = parseEvent(event);
  const jobId = payload.job_id;
  if (!jobId) return;
  if (name === "job.queued") {
    upsert({
      id: jobId,
      kind: payload.kind || "job",
      project: payload.project || "",
      status: "queued",
      progress: { done: 0, total: 0, unit: "" },
      cost_usd: 0,
      error: null,
      started_at: null,
      finished_at: null,
    });
    return;
  }
  if (name === "job.started") {
    patch(jobId, { status: "running", started_at: Date.now() / 1000 });
    void refreshJob(jobId);
    return;
  }
  if (name === "job.succeeded") {
    patch(jobId, { status: "succeeded", finished_at: Date.now() / 1000 });
    void refreshJob(jobId);
    return;
  }
  if (name === "job.failed") {
    patch(jobId, {
      status: "failed",
      error: payload.error || "job failed",
      finished_at: Date.now() / 1000,
    });
    void refreshJob(jobId);
    return;
  }
  patch(jobId, { status: "cancelled", finished_at: Date.now() / 1000 });
  void refreshJob(jobId);
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
    retry = 0;
    emit({ connection: "live" });
    void refresh();
  };
  stream.onerror = () => {
    if (source !== stream) return;
    stream.close();
    source = null;
    scheduleReconnect();
  };
  for (const name of EVENT_NAMES) {
    stream.addEventListener(name, (event) => handle(name, event));
  }
}

/** Start the one shared SSE connection and initial job snapshot. */
export function startJobs() {
  if (started) return;
  started = true;
  void refresh();
  connect();
}

export function useJobs(): JobsSnapshot {
  const state = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
  useEffect(() => {
    startJobs();
  }, []);
  return state;
}
