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

export type Job = {
  id: string;
  kind: string;
  project: string;
  status: string;
  progress: { done: number; total: number; unit: string };
  cost_usd: number;
  error: string | null;
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
  images: (slug: string) => request<Record<string, unknown>>(`/api/projects/${slug}/images`),
  exports: (slug: string) => request<{ exports: string[] }>(`/api/projects/${slug}/exports`),
  budget: (slug: string) => request<Budget>(`/api/projects/${slug}/budget`),
  jobs: () => request<Job[]>("/api/jobs"),
  settings: () => request<Record<string, unknown>>("/api/settings"),
  chat: (slug: string) => request<{ messages: unknown[] }>(`/api/projects/${slug}/chat`),
  analyze: (slug: string) =>
    request<unknown>(`/api/projects/${slug}/analyze`, { method: "POST", body: "{}" }),
};