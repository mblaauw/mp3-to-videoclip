export type ProjectSummary = {
  slug: string;
  title: string;
  duration: number | null;
  archived: boolean;
  render: string | null;
  still_count: number;
};

export type Budget = {
  cap_usd: string | null;
  committed_usd: string;
  remaining_usd: string | null;
  history: { at: string; cap_usd: string; reason: string }[];
};

export type Shot = {
  id: string;
  start_frame: number;
  duration_frames: number;
  purpose: string;
  image_prompt: string;
  camera: string;
  dissolve_frames: number;
  framing: string | null;
  must_show: string[];
  scene_id: string | null;
};

export type Storyboard = {
  aspect: string;
  fps: number;
  total_frames: number;
  shots: Shot[];
};

export type Brief = {
  direction?: string;
  style?: string;
  treatment?: string;
  visual_rules?: string[];
  avoid?: string[];
  characters?: { id: string; identity?: string; description?: string }[];
  creative?: {
    mode?: string;
    look?: string;
    image_rules?: string[];
    proof_shot_ids?: string[];
  } | null;
};

export type ImageVersion = {
  version: number;
  path: string;
  sha256: string;
  input_hash: string;
};

export type ImageShot = {
  id: string;
  owner: string;
  selected: number | null;
  versions: ImageVersion[];
};

export type Job = {
  id: string;
  kind: string;
  project: string;
  status: string;
  progress: { done: number; total: number; unit: string };
  cost_usd: number;
  error: string | null;
};

export type ApprovalState = {
  stage: string;
  state: "approved" | "stale" | "missing" | "unavailable";
  expected_hash?: string;
  at?: string | null;
  note?: string | null;
  error?: string;
};

export type BudgetDecision = {
  ok: boolean;
  needs_budget: boolean;
  remaining: string | null;
  cap_usd: string | null;
  requested_usd?: string;
  suggested_usd?: string;
};

export type ImageEstimate = {
  quote_id: string;
  scope: string;
  tasks: number;
  reserve_usd: string;
  cap_usd: string | null;
  uploads_required: boolean;
  shot_ids: string[];
};

export type ImageEstimateResponse = {
  estimate?: ImageEstimate;
  decision?: BudgetDecision;
  budget?: Omit<Budget, "history">;
  error?: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  projects: () => request<ProjectSummary[]>("/api/projects"),
  project: (slug: string) => request<unknown>(`/api/projects/${slug}`),
  brief: (slug: string) => request<Brief>(`/api/projects/${slug}/brief`),
  storyboard: (slug: string) => request<Storyboard>(`/api/projects/${slug}/storyboard`),
  track: (slug: string) => request<{ music: unknown; lyrics: unknown }>(`/api/projects/${slug}/track`),
  images: (slug: string) => request<{ shots: ImageShot[] }>(`/api/projects/${slug}/images`),
  exports: (slug: string) => request<{ exports: string[] }>(`/api/projects/${slug}/exports`),
  budget: (slug: string) => request<Budget>(`/api/projects/${slug}/budget`),
  jobs: () => request<Job[]>("/api/jobs"),
  settings: () => request<Record<string, unknown>>("/api/settings"),
  chat: (slug: string) => request<{ messages: unknown[] }>(`/api/projects/${slug}/chat`),
  analyze: (slug: string) =>
    request<unknown>(`/api/projects/${slug}/analyze`, { method: "POST", body: "{}" }),
  patchBrief: (slug: string, patch: Partial<Brief>) =>
    request<Brief>(`/api/projects/${slug}/brief`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  patchShots: (slug: string, changes: Partial<Shot>[]) =>
    request<Storyboard>(`/api/projects/${slug}/storyboard/shots`, {
      method: "PATCH",
      body: JSON.stringify({ changes }),
    }),
  selectImage: (slug: string, shot_id: string, version: number) =>
    request<unknown>(`/api/projects/${slug}/images/select`, {
      method: "POST",
      body: JSON.stringify({ shot_id, version }),
    }),
  imageEstimate: (
    slug: string,
    body: { shot_ids: string[]; reserve_usd: string; scope: string; regenerate: boolean },
  ) =>
    request<ImageEstimateResponse>(`/api/projects/${slug}/images/estimate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  generateImages: (
    slug: string,
    body: { quote_id: string; note: string; uploads_confirmed: boolean },
  ) =>
    request<{
      job_id?: string;
      error?: string;
      needs_budget?: boolean;
      decision?: BudgetDecision;
      budget?: Omit<Budget, "history">;
      tasks?: number;
      reserve_usd?: string;
    }>(`/api/projects/${slug}/images/generate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  approvals: (slug: string) =>
    request<{ stages: ApprovalState[] }>(`/api/projects/${slug}/approvals`),
  approve: (
    slug: string,
    stage: string,
    body: { expected_hash: string; note: string; confirmed: true },
  ) =>
    request<{ approved: string }>(`/api/projects/${slug}/approvals/${stage}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  render: (slug: string, kind: "preview" | "final") =>
    request<unknown>(`/api/projects/${slug}/render`, {
      method: "POST",
      body: JSON.stringify({ kind }),
    }),
};