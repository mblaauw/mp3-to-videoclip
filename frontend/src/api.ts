import type { PreviewShot } from "./baseFilm";
import { toast } from "./toast";

export type ProjectSummary = {
  slug: string;
  title: string;
  duration: number | null;
  archived: boolean;
  render: string | null;
  still_count: number;
  error?: string | null;
};

export type ProjectDetail = {
  slug: string;
  title: string;
  duration: number;
  fps: number;
  width: number;
  height: number;
  music_mode: string | null;
  archived: false;
  shots: number;
  stills: number;
  approvals: string[];
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
  asset_shot_id: string | null;
  must_show: string[];
  scene_id: string | null;
};

export type Storyboard = {
  aspect: string;
  fps: number;
  total_frames: number;
  shots: Shot[];
};

export type MusicWindow = {
  time: number;
  end?: number;
  level_db?: number;
};

export type Music = {
  duration?: number;
  estimated_tempo_bpm?: number | null;
  beats?: number[];
  energy_curve?: { time: number; energy: number }[];
  fine_windows?: MusicWindow[];
  sections?: { start: number; end: number; label: string }[];
  warnings?: string[];
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

export type ImageReview = {
  shot_id: string;
  version: number;
  sha256: string;
  input_hash: string;
  verdict: "accept" | "reject" | "uncertain";
  note: string;
  reviewer: string;
  inspected: boolean;
  at: string;
};

export type ImageShot = {
  id: string;
  owner: string;
  selected: number | null;
  versions: ImageVersion[];
  review: ImageReview | null;
};

export type SetupStatus = {
  node: boolean;
  npm: boolean;
  chrome: boolean;
  ffmpeg: boolean;
  ffprobe: boolean;
  renderer: boolean;
  frontend: boolean;
};

export type GraphicsSample = {
  name: string;
  url: string;
  sha256: string;
};

export type GraphicsReview = {
  available: boolean;
  current?: boolean;
  reason?: string | null;
  warning?: string;
  base?: string;
  samples?: GraphicsSample[];
};

export type PreviewInput = {
  available: boolean;
  reason?: string;
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  shots: PreviewShot[];
  audio: string;
  preview_banner: boolean;
  preview_placeholders: string[];
  stale_shots: string[];
  brand_plate?: string | null;
  brand_duration_frames?: number;
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

async function errorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const parsed = JSON.parse(text);
    const detail = parsed.detail || parsed.error || text;
    return typeof detail === "string" ? detail : JSON.stringify(detail);
  } catch {
    return text;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!res.ok) {
    const message = await errorMessage(res);
    toast(message);
    throw new Error(`${res.status}: ${message}`);
  }
  return (await res.json()) as T;
}

export const api = {
  projects: () => request<ProjectSummary[]>("/api/projects"),
  createProject: async (
    file: File,
    meta: { title: string; aspect: string; music_mode: string; budget: string },
  ) => {
    const params = new URLSearchParams({
      title: meta.title,
      filename: file.name,
      aspect: meta.aspect,
      music_mode: meta.music_mode,
      budget: meta.budget,
    });
    const res = await fetch(`/api/projects?${params}`, {
      method: "POST",
      headers: { "Content-Type": file.type || "audio/mpeg" },
      body: file,
    });
    if (!res.ok) {
      const message = await errorMessage(res);
      toast(message);
      throw new Error(`${res.status}: ${message}`);
    }
    return (await res.json()) as {
      slug: string;
      title: string;
      duration: number;
      analysis_job: string | null;
    };
  },
  project: (slug: string) => request<ProjectDetail>(`/api/projects/${slug}`),
  brief: (slug: string) => request<Brief>(`/api/projects/${slug}/brief`),
  storyboard: (slug: string) =>
    request<Storyboard | { available: false }>(`/api/projects/${slug}/storyboard`),
  track: (slug: string) =>
    request<{ music: Music | null; lyrics: unknown; music_mode: string | null }>(
      `/api/projects/${slug}/track`,
    ),
  images: (slug: string) => request<{ shots: ImageShot[] }>(`/api/projects/${slug}/images`),
  graphicsReview: (slug: string) =>
    request<GraphicsReview>(`/api/projects/${slug}/graphics-review`),
  preview: (slug: string) => request<PreviewInput>(`/api/projects/${slug}/preview`),
  exports: (slug: string) =>
    request<{ exports: string[]; previews: string[] }>(
      `/api/projects/${slug}/exports`,
    ),
  budget: (slug: string) => request<Budget>(`/api/projects/${slug}/budget`),
  jobs: () => request<Job[]>("/api/jobs"),
  settings: () => request<Record<string, unknown>>("/api/settings"),
  setup: () => request<SetupStatus>("/api/setup"),
  installRenderer: () =>
    request<{ installed: boolean; already_present: boolean; output: string }>(
      "/api/setup/renderer",
      { method: "POST", body: JSON.stringify({}) },
    ),
  chat: (slug: string) => request<{ messages: unknown[] }>(`/api/projects/${slug}/chat`),
  analyze: (slug: string) =>
    request<unknown>(`/api/projects/${slug}/analyze`, { method: "POST", body: "{}" }),
  saveLyrics: (slug: string, lrc: string) =>
    request<{ status?: string; segments?: number; error?: string }>(
      `/api/projects/${slug}/lyrics`,
      { method: "PUT", body: JSON.stringify({ lrc }) },
    ),
  setProofShots: (slug: string, shot_ids: string[]) =>
    request<{ proof_shot_ids: string[] }>(`/api/projects/${slug}/proof-shots`, {
      method: "POST",
      body: JSON.stringify({ shot_ids }),
    }),
  createSkeleton: (slug: string) =>
    request<Storyboard>(`/api/projects/${slug}/storyboard/skeleton`, {
      method: "POST",
      body: JSON.stringify({ timing: "adaptive" }),
    }),
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
  reviewImage: (
    slug: string,
    body: {
      shot_id: string;
      version: number;
      verdict: "accept" | "reject" | "uncertain";
      note: string;
      inspected: boolean;
    },
  ) =>
    request<{ review: ImageReview }>(`/api/projects/${slug}/images/review`, {
      method: "POST",
      body: JSON.stringify(body),
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
  approvals: (slug: string, stages: string[]) =>
    request<{ stages: ApprovalState[] }>(
      `/api/projects/${slug}/approvals?stages=${encodeURIComponent(stages.join(","))}`,
    ),
  approve: (
    slug: string,
    stage: string,
    body: {
      expected_hash: string;
      note: string;
      confirmed: true;
      preview_watched?: boolean;
      inspected?: boolean;
      acknowledge_uncertain?: boolean;
    },
  ) =>
    request<{ approved: string }>(`/api/projects/${slug}/approvals/${stage}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  render: (slug: string, kind: "preview" | "base" | "final") =>
    request<unknown>(`/api/projects/${slug}/render`, {
      method: "POST",
      body: JSON.stringify({ kind }),
    }),
};