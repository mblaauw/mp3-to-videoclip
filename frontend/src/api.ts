import type { components } from "./api/schema";
import { readApiError } from "./api/errors.ts";
import type { PreviewShot } from "./baseFilm";
import { toast } from "./toast.ts";
import { bindRevision, resources, revisionHeaders } from "./api/resources.ts";

export { ApiError } from "./api/errors.ts";

type Schemas = components["schemas"];

/** Generated from `npm run api:types`; the route returns this model. */
export type ProjectSummary = Schemas["ProjectSummary"];

export type AudioWindow = {
  start: number;
  end: number;
  fade_in: number;
  fade_out: number;
};

export type StylePreset = {
  id: string;
  name: string;
  description: string;
  protected?: boolean;
  look?: string;
  image_rules?: string[];
  model?: string | null;
};

export type KindProfile = {
  id: string;
  label: string;
  purpose: string;
  lengths: number[];
  default_length: number | null;
  allows_full_track: boolean;
  structures: string[];
  text_density: string;
  signature_required: boolean;
  style_presets: string[];
  default_style: string;
};

export type ProjectDetail = {
  slug: string;
  title: string;
  kind: string | null;
  duration: number;
  source_duration: number;
  audio_window: AudioWindow | null;
  style_preset: string | null;
  signature_required: boolean | null;
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
  spent_usd: string;
  reserved_usd: string;
  paid_stills: number;
  remaining_usd: string | null;
  history: { at: string; cap_usd: string; reason: string }[];
};

export type ShotKind =
  | "scene"
  | "product"
  | "upload"
  | "card"
  | "bridge"
  | "split"
  | "reprise"
  | "logo"
  | "end_card";

export type Shot = {
  id: string;
  start_frame: number;
  duration_frames: number;
  kind?: ShotKind;
  purpose: string;
  message?: string;
  image_prompt?: string;
  text?: string[];
  camera: string;
  dissolve_frames: number;
  framing: string | null;
  transition?: "fade" | "wipe_left" | "wipe_right" | null;
  asset_shot_id: string | null;
  asset?: string | null;
  product_ref?: string | null;
  motion_prompt?: string;
  music_context?: string;
  lyric_context?: string;
  bridge?: {
    mode: "designed" | "generated";
    match?: {
      type: "shape" | "colour" | "position";
      anchor: [number, number];
      note?: string;
    } | null;
  } | null;
  panes?: { shot_id: string; crop?: { zoom: number; x: number; y: number } }[];
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

export type LyricSegment = {
  start: number;
  end: number;
  text: string;
  flags?: string[];
};

export type Lyrics = {
  language?: string | null;
  provider: string;
  model: string;
  segments: LyricSegment[];
  lines?: string[];
  warning?: string;
};

export type Music = {
  duration?: number;
  estimated_tempo_bpm?: number | null;
  beats?: number[];
  energy_curve?: { time: number; energy: number }[];
  fine_windows?: MusicWindow[];
  sections?: {
    start: number;
    end: number;
    label?: string;
    name?: string;
    energy?: number;
  }[];
  warnings?: string[];
};

export type LyricLine = {
  index: number;
  text: string;
  /** A `[Spoken Hook]` line: a heading of the song, never sung or timed. */
  tag: string | null;
  start: number | null;
  end: number | null;
  source: "tapped" | "auto" | "lrc" | null;
};

export type LyricTools = {
  supported: boolean;
  reason: string | null;
  ready: boolean;
  download_gb: number;
};

export type LyricTiming = { lines: LyricLine[] };

export type LyricTimingSave = {
  index: number;
  start: number;
  end: number | null;
  source: "tapped" | "auto";
};

export type TrackData = {
  music: Music | null;
  lyrics: Lyrics | null;
  music_mode: string | null;
  kind: string;
  duration: number;
  source_duration: number;
  section_names: { start: number; name: string }[];
  /** True while the owner's corrected sections replace the detected ones. */
  section_map?: boolean;
};

export type ConceptBeat = {
  start: number;
  end: number;
  label: string;
  text: string;
};

export type Concept = {
  id: string;
  title: string;
  structure: string;
  logline: string;
  why: string;
  world: string;
  /** Older concepts: free text with the times inside. */
  shape?: string[];
  beats?: ConceptBeat[];
  signature_moment: string;
  risk: string;
};

export type TreatmentsPayload = {
  treatments: Concept[];
  concepts?: Concept[];
  chosen_id?: string | null;
};

export type IdeaPart = "story" | "style" | "rules" | "avoid";
export type IdeaParts = Record<IdeaPart, string[]>;

/** Your newest paste, word for word, and how it is sorted now. */
export type Idea = {
  id: string;
  at: string;
  text: string;
  sorted: IdeaParts | null;
  sorted_by: "writer" | "owner" | null;
  /** False once the brief has been edited since, so sorting would overwrite that. */
  current: boolean;
};

/** A run of the treatment, placed on the song or (null times) not yet. */
export type StoryPassage = {
  text: string;
  start: number | null;
  end: number | null;
  from: number;
  to: number;
};

export type Intent = {
  kind?: string;
  objective?: string;
  audience?: string;
  message?: string;
  reasons?: string[];
  tone?: string[];
  mandatories?: string[];
  avoid?: string[];
  cta?: { text?: string; url?: string } | null;
  length_seconds?: number | null;
  audio_window?: AudioWindow | null;
  notes?: string;
  about?: string;
  performance?: boolean | null;
  reference_links?: string[];
  assets?: string;
};

export type Brief = {
  intent?: Intent | null;
  direction?: string;
  style?: string;
  treatment?: string;
  visual_rules?: string[];
  avoid?: string[];
  characters?: {
    id: string;
    identity?: string;
    description?: string;
    permission_confirmed?: boolean;
    references?: string[];
    default_state?: string;
    states?: Record<
      string,
      {
        description?: string;
        attributes?: Record<string, string>;
        references?: string[];
      }
    >;
  }[];
  creative?: {
    mode?: string;
    look?: string;
    image_rules?: string[];
    proof_shot_ids?: string[];
    world?: string;
    references?: unknown[];
    scenes?: { id: string; description?: string; reference_ids?: string[] }[];
    arc?: { phase?: string; intention?: string }[];
    profile_version?: number;
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
  kind: ShotKind;
  paid: boolean;
  local: boolean;
  plate: string | null;
  message: string;
  text: string[];
  selected: number | null;
  versions: ImageVersion[];
  review: ImageReview | null;
  stale: boolean;
};

export type IntakePayload = {
  title: string;
  kind: string;
  intent: Intent | null;
  brief: Brief;
  prompt_version?: number | null;
  style_preset: string | null;
  style_presets: StylePreset[];
  kinds: KindProfile[];
  source_duration: number;
  duration: number;
  audio_window: AudioWindow | null;
  peaks: number[];
  analysis_needed: boolean;
};

export type Settings = {
  gateway?: "opencode" | "direct";
  opencode_bin?: string;
  opencode_workspace?: string;
  writer_model?: string;
  editor_model?: string;
  llm_model?: string;
  llm_base_url?: string;
  has_llm_api_key?: boolean;
  has_runware_api_key?: boolean;
  brand_name?: string;
  brand_partner?: string;
  default_budget_usd?: number;
  image_reserve_usd?: number;
  default_credit_roles?: string[];
  remotion_dir?: string;
  ffmpeg_path?: string;
  style_presets?: StylePreset[];
  kinds?: KindProfile[];
  shot_kinds?: {
    id: ShotKind;
    label: string;
    icon: string;
    paid: boolean;
    hint: string;
    purpose: string;
  }[];
  [key: string]: unknown;
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
  /** Composition reviews: the film frame, its time and the title window shown. */
  frame?: number | null;
  seconds?: number | null;
  window?: string | null;
  phase?: string | null;
};

export type GraphicsReview = {
  available: boolean;
  current?: boolean;
  reason?: string | null;
  warning?: string;
  method?: "composite" | "composition-v1";
  base?: string;
  samples?: GraphicsSample[];
};

export type ArtifactName = "brief" | "treatments" | "storyboard" | "edit";

export type RatingEntry = {
  artifact: ArtifactName;
  label: string;
  rating: "up" | "down";
  note: string;
  artifact_hash: string;
  prompt_hash: string | null;
  prompt_files: { path: string; version: number }[];
  prompt_role: string | null;
  prompt_task: string | null;
  prompt_words: number | null;
  at: string;
};

export type RatingSummary = {
  artifact: ArtifactName;
  label: string;
  available: boolean;
  artifact_hash: string | null;
  prompt: {
    hash: string | null;
    files: { path: string; version: number }[];
    role: string | null;
    task: string | null;
    words: number | null;
  };
  latest: RatingEntry | null;
  stale: boolean;
  history: RatingEntry[];
};

export type RatingResponse = {
  entry: RatingEntry;
  summary: RatingSummary;
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
  grade?: import("./baseFilm").Grade | null;
  /** Planned titles, or null with a note when this film has none to show yet. */
  titles?: import("./baseFilm").TitlesInput | null;
  titles_note?: string | null;
};

export type EditFinding = {
  code: string;
  message: string;
  shot_id?: string;
  section?: string;
  text_id?: string;
};

export type EditSectionReport = {
  id: string;
  start_frame: number;
  end_frame: number;
  feel: string;
  energy: string | null;
  target_density_per_10s: number;
  density_per_10s: number;
  cuts: number;
  shots: number;
  holds: number;
  accents: number;
  flashes: number;
  techniques: string[];
};

export type EditTechniqueReport = {
  name: string;
  count: number;
  reasons: string[];
  reasoned: boolean;
};

export type EditReport = {
  present: boolean;
  ok: boolean;
  hard: EditFinding[];
  warnings: EditFinding[];
  hash?: string | null;
  coverage?: {
    ok: boolean;
    start_frame?: number;
    end_frame?: number;
    total_frames?: number;
  };
  sections: EditSectionReport[];
  techniques: EditTechniqueReport[];
  counts: {
    shots?: number;
    cuts?: number;
    holds?: number;
    hold_ratio?: number;
    text_layers?: number;
    accents?: number;
    flashes?: number;
    motions?: Record<string, number>;
    transitions?: Record<string, number>;
    accents_by_type?: Record<string, number>;
  };
  ad?: { applicable: boolean; checks: { id: string; ok: boolean; message: string }[] };
};

export type EditPayload = {
  schema_version?: 1;
  sections: unknown[];
  shots: import("./baseFilm").EditShot[];
  grade: import("./baseFilm").Grade;
  notes?: string;
};

export type EditSummary = {
  available: boolean;
  present: boolean;
  edit?: EditPayload;
  report: EditReport;
};

/** The readable cut Film renders. Labels and section names come from the engine. */
export type CutReason = {
  kind: string;
  label: string;
  reason: string;
};

export type CutSection = {
  id: string;
  name: string;
  feel: string;
  start_frame: number;
  end_frame: number;
  techniques: string[];
};

export type CutShot = {
  shot_id: string;
  kind: ShotKind;
  section_id: string | null;
  section_name: string | null;
  start_frame: number;
  duration_frames: number;
  seconds: number;
  transition: { type: string; frames: number; label: string; reason: string };
  motion: { type: string; label: string; reason: string };
  accents: { frame: number; type: string; label: string; reason: string }[];
  text: { id: string; text: string; style: string; in_frame: number; out_frame: number }[];
  reasons: CutReason[];
  reason: string;
};

export type CutSummary = {
  available: boolean;
  present: boolean;
  edit: EditPayload | null;
  sections: CutSection[];
  shots: CutShot[];
  techniques: { name: string; count: number; reasons: string[]; reasoned: boolean }[];
  counts: EditReport["counts"];
  hard: EditFinding[];
  warnings: EditFinding[];
  notes: string;
  grade: string | null;
};

export type HistorySnapshot = {
  hash: string;
  at: number;
  bytes: number;
};

export type HistoryList = {
  artifact: string;
  snapshots: HistorySnapshot[];
};

export type HistoryRestore = {
  artifact: string;
  restored: string;
  previous: string;
};

export type DeliveryLine = {
  id: string;
  label: string;
  stage: "track" | "story" | "storyboard" | "images" | "film";
  state: "done" | "you" | "blocked" | "optional";
  required: boolean;
  detail: string;
  reason: string | null;
  expected_hash: string | null;
};

export type DeliveryChecklist = {
  signature_required: boolean;
  preview_required: boolean;
  can_final: boolean;
  lines: DeliveryLine[];
  stills: { kept: number; total: number };
  outstanding: string[];
};

export type SettingsTest = {
  ok: boolean;
  kind: "runware" | "opencode";
  message: string;
  version?: string;
};

/** Generated from the typed `/api/jobs` response models. */
export type Job = Schemas["JobOut"] & { historical?: boolean; blocking?: boolean };
export type JobDetail = Schemas["JobDetailOut"];

export type ApprovalState = Schemas["ApprovalStateOut"];
export type ApprovalsResponse = Schemas["ApprovalsOut"];
export type ApprovalResponse = Schemas["ApprovalOut"];

export type ApprovalChange = {
  field: string;
  before: string;
  after: string;
};

export type ApprovalChanges = {
  available: boolean;
  reason: string | null;
  changes: ApprovalChange[];
};

export type CreditCard = [string, string];

export type GraphicsSpec = {
  available: boolean;
  guided?: boolean;
  spec?: {
    credit_roles_confirmed?: boolean;
    credits?: { cards?: CreditCard[]; lockup?: string };
    warning?: string;
    [key: string]: unknown;
  };
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
  const method = init?.method?.toUpperCase() || "GET";
  const project = path.match(/^\/api\/projects\/([^/?]+)(?:\/([^/?]+))?/);
  const mutation = method !== "GET" && method !== "HEAD";
  const invalidate = () => resources.invalidate({ slug: project?.[1] });
  const load = async (): Promise<T> => {
    if (mutation) invalidate();
    const res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    }).finally(() => { if (mutation) invalidate(); });
    if (!res.ok) {
      const error = await readApiError(res);
      toast(error.message);
      throw error;
    }
    // Also invalidate reads started while the write was in progress.
    if (mutation) invalidate();
    const value = (await res.json()) as T;
    if (project) {
      const artifact = project[2] || "project";
      const etag = res.headers.get("ETag");
      bindRevision(value, project[1], artifact, etag);
      if (value && typeof value === "object") {
        const nested = value as Record<string, unknown>;
        if (artifact === "edit") bindRevision(nested.edit, project[1], "edit", etag);
        if (artifact === "intake") bindRevision(nested.brief, project[1], "brief", etag);
        if (artifact === "storyboard" && Array.isArray(nested.shots)) {
          nested.shots.forEach((shot) => bindRevision(shot, project[1], "storyboard", etag));
        }
      }
    }
    return value;
  };
  return !mutation && (project || ["/api/projects", "/api/settings", "/api/setup"].includes(path))
    ? resources.read(path, load) : load();
}

export const api = {
  projects: () => request<ProjectSummary[]>("/api/projects"),
  createProject: async (
    file: File,
    meta: {
      title: string;
      aspect: string;
      music_mode: string;
      budget: string;
      kind: string;
      style_preset?: string;
      objective?: string;
      message?: string;
      cta_text?: string;
      cta_url?: string;
      length_seconds?: number;
      window_start?: number;
      fade_in?: number;
      fade_out?: number;
    },
  ) => {
    const params = new URLSearchParams({
      title: meta.title,
      filename: file.name,
      aspect: meta.aspect,
      music_mode: meta.music_mode,
      budget: meta.budget,
      kind: meta.kind,
    });
    if (meta.style_preset) params.set("style_preset", meta.style_preset);
    if (meta.kind !== "music_video") {
      params.set("objective", meta.objective || "");
      params.set("message", meta.message || "");
      params.set("cta_text", meta.cta_text || "");
      params.set("cta_url", meta.cta_url || "");
      params.set("window_start", String(meta.window_start ?? 0));
      params.set("fade_in", String(meta.fade_in ?? 0));
      params.set("fade_out", String(meta.fade_out ?? 1.5));
      if (meta.length_seconds) params.set("length_seconds", String(meta.length_seconds));
    }
    const res = await fetch(`/api/projects?${params}`, {
      method: "POST",
      headers: { "Content-Type": file.type || "audio/mpeg" },
      body: file,
    });
    if (!res.ok) {
      const error = await readApiError(res);
      toast(error.message);
      throw error;
    }
    resources.invalidate();
    return (await res.json()) as {
      slug: string;
      title: string;
      kind: string;
      duration: number;
      source_duration: number | null;
      audio_window: AudioWindow | null;
      signature_required: boolean | null;
      analysis_job: string | null;
    };
  },
  project: (slug: string) => request<ProjectDetail>(`/api/projects/${slug}`),
  brief: (slug: string) => request<Brief>(`/api/projects/${slug}/brief`),
  intake: (slug: string) => request<IntakePayload>(`/api/projects/${slug}/intake`),
  updateIntake: (
    slug: string,
    body: { intent?: Intent; style_preset?: string; audio_window?: AudioWindow | null },
  ) =>
    request<IntakePayload>(`/api/projects/${slug}/intake`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  storyboard: (slug: string) =>
    request<Storyboard | { available: false }>(`/api/projects/${slug}/storyboard`),
  track: (slug: string) => request<TrackData>(`/api/projects/${slug}/track`),
  musicNotes: (slug: string) =>
    request<{ sections: { start: number; name: string }[] }>(
      `/api/projects/${slug}/music-notes`,
    ),
  saveMusicNotes: (slug: string, sections: { start: number; name: string }[]) =>
    request<{ sections: { start: number; name: string }[] }>(
      `/api/projects/${slug}/music-notes`,
      { method: "PUT", body: JSON.stringify({ sections }) },
    ),
  setMusicMode: (slug: string, music_mode: "vocal" | "instrumental") =>
    request<{ music_mode: string }>(`/api/projects/${slug}/music-mode`, {
      method: "PUT",
      body: JSON.stringify({ music_mode }),
    }),
  idea: (slug: string) => request<{ idea: Idea | null }>(`/api/projects/${slug}/idea`),
  keepIdea: (slug: string, text: string) =>
    request<{ idea: Idea }>(`/api/projects/${slug}/idea`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  sortIdea: (slug: string, parts: IdeaParts) =>
    request<{ idea: Idea }>(`/api/projects/${slug}/idea/sorted`, {
      method: "PUT",
      body: JSON.stringify(parts),
    }),
  storyPassages: (slug: string) =>
    request<{ passages: StoryPassage[] }>(`/api/projects/${slug}/story-passages`),
  treatments: (slug: string) =>
    request<TreatmentsPayload>(`/api/projects/${slug}/treatments`),
  putTreatments: (slug: string, payload: { concepts: Concept[]; chosen_id?: string | null }) =>
    request<{ concepts: Concept[]; chosen_id?: string | null }>(
      `/api/projects/${slug}/treatments`,
      { method: "PUT", body: JSON.stringify(payload) },
    ),
  images: (slug: string) => request<{ shots: ImageShot[] }>(`/api/projects/${slug}/images`),
  graphicsReview: (slug: string) =>
    request<GraphicsReview>(`/api/projects/${slug}/graphics-review`),
  graphics: (slug: string) => request<GraphicsSpec>(`/api/projects/${slug}/graphics`),
  saveCredits: (slug: string, cards: CreditCard[], useAsTemplate = false) =>
    request<{ cards: CreditCard[]; confirmed: boolean }>(
      `/api/projects/${slug}/graphics/credits`,
      {
        method: "PUT",
        body: JSON.stringify({ cards, use_as_template: useAsTemplate }),
      },
    ),
  preview: (slug: string) => request<PreviewInput>(`/api/projects/${slug}/preview`),
  edit: (slug: string) => request<EditSummary>(`/api/projects/${slug}/edit`),
  editSummary: async (slug: string): Promise<CutSummary> => {
    const [cut, base] = await Promise.all([
      request<CutSummary>(`/api/projects/${slug}/edit/summary`),
      request<EditSummary>(`/api/projects/${slug}/edit`),
    ]);
    // Transfer provenance only for the exact revision-bearing edit payload.
    if (cut.edit) {
      const etag = revisionHeaders(base.edit, slug, "edit")["If-Match"];
      if (!base.edit || !etag || JSON.stringify(cut.edit) !== JSON.stringify(base.edit)) {
        resources.invalidate({ slug, artifact: "edit" });
        throw new Error("The cut changed while loading. Reload and review before editing.");
      }
      bindRevision(cut.edit, slug, "edit", etag);
    }
    return cut;
  },
  checklist: (slug: string) =>
    request<DeliveryChecklist>(`/api/projects/${slug}/film/checklist`),
  history: (slug: string, artifact: string) =>
    request<HistoryList>(`/api/projects/${slug}/history/${artifact}`),
  restoreHistory: (slug: string, artifact: string) =>
    request<HistoryRestore>(`/api/projects/${slug}/history/${artifact}/restore`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  rating: (slug: string, artifact: ArtifactName) =>
    request<RatingSummary>(`/api/projects/${slug}/ratings?artifact=${artifact}`),
  rate: (slug: string, artifact: ArtifactName, rating: "up" | "down", note: string) =>
    request<RatingResponse>(`/api/projects/${slug}/ratings`, {
      method: "POST",
      body: JSON.stringify({ artifact, rating, note }),
    }),
  seedEdit: (slug: string) =>
    request<EditSummary>(`/api/projects/${slug}/edit/seed`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  saveEdit: (slug: string, edit: unknown, base?: unknown) =>
    request<EditSummary>(`/api/projects/${slug}/edit`, {
      method: "PUT",
      headers: revisionHeaders(base, slug, "edit"),
      body: JSON.stringify({ edit }),
    }),
  exports: (slug: string) =>
    request<FilmExports>(
      `/api/projects/${slug}/exports`,
    ),
  budget: (slug: string) => request<Budget>(`/api/projects/${slug}/budget`),
  addBudget: (slug: string, amount: string, reason: string) =>
    request<{ entry: { at: string; cap_usd: string; reason: string }; cap_usd: string }>(
      `/api/projects/${slug}/budget`,
      { method: "POST", body: JSON.stringify({ amount, reason }) },
    ),
  jobs: () => request<Job[]>("/api/jobs"),
  job: (jobId: string) => request<JobDetail>(`/api/jobs/${jobId}`),
  cancelJob: (jobId: string) =>
    request<{ cancelled: boolean }>(`/api/jobs/${jobId}/cancel`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  settings: () => request<Settings>("/api/settings"),
  saveSettings: (body: Record<string, unknown>) =>
    request<Settings>("/api/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  testSettings: (kind: "runware" | "opencode") =>
    request<SettingsTest>("/api/settings/test", {
      method: "POST",
      body: JSON.stringify({ kind }),
    }),
  setup: () => request<SetupStatus>("/api/setup"),
  installRenderer: () =>
    request<{ installed: boolean; already_present: boolean; output: string }>(
      "/api/setup/renderer",
      { method: "POST", body: JSON.stringify({}) },
    ),
  chat: (slug: string, role?: "writer" | "editor") =>
    request<{ messages: unknown[] }>(
      `/api/projects/${slug}/chat${role ? `?role=${role}` : ""}`,
    ),
  analyze: (slug: string) =>
    request<unknown>(`/api/projects/${slug}/analyze`, { method: "POST", body: "{}" }),
  saveSectionMap: (slug: string, sections: { start: number; name: string }[]) =>
    request<{ sections: { start: number; name: string }[] }>(`/api/projects/${slug}/section-map`, {
      method: "PUT",
      body: JSON.stringify({ sections }),
    }),
  proposeSections: (slug: string) =>
    request<{ sections: { start: number; name: string }[] }>(
      `/api/projects/${slug}/section-map/propose`,
      { method: "POST" },
    ),
  resetSectionMap: (slug: string) =>
    request<{ status: string }>(`/api/projects/${slug}/section-map/reset`, { method: "POST" }),
  lyricTools: (slug: string) => request<LyricTools>(`/api/projects/${slug}/lyric-tools`),
  setupLyricTools: (slug: string) =>
    request<{ job_id: string }>(`/api/projects/${slug}/lyric-tools/setup`, { method: "POST" }),
  runLyricTiming: (slug: string) =>
    request<{ job_id: string }>(`/api/projects/${slug}/lyric-timing/run`, { method: "POST" }),
  embeddedLyrics: (slug: string) =>
    request<{ text: string | null }>(`/api/projects/${slug}/embedded-lyrics`),
  lyricDraft: (slug: string) => request<{ lines: string[] }>(`/api/projects/${slug}/lyric-draft`),
  runLyricDraft: (slug: string) =>
    request<{ job_id: string }>(`/api/projects/${slug}/lyric-draft/run`, { method: "POST" }),
  lyricTiming: (slug: string) => request<LyricTiming>(`/api/projects/${slug}/lyric-timing`),
  saveLyricTiming: (slug: string, lines: LyricTimingSave[]) =>
    request<LyricTiming>(`/api/projects/${slug}/lyric-timing`, {
      method: "PUT",
      body: JSON.stringify({ lines }),
    }),
  saveLyrics: (slug: string, text: string) =>
    request<{ status?: string; segments?: number; lines?: number; error?: string }>(
      `/api/projects/${slug}/lyrics`,
      { method: "PUT", body: JSON.stringify({ text }) },
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
  patchBrief: (slug: string, patch: Partial<Brief>, base?: Brief) =>
    request<Brief>(`/api/projects/${slug}/brief`, {
      method: "PATCH",
      headers: revisionHeaders(base, slug, "brief"),
      body: JSON.stringify(patch),
    }),
  patchShots: (slug: string, changes: Partial<Shot>[], base?: Storyboard | Shot) =>
    request<Storyboard>(`/api/projects/${slug}/storyboard/shots`, {
      method: "PATCH",
      headers: revisionHeaders(base, slug, "storyboard"),
      body: JSON.stringify({ changes }),
    }),
  reviewImage: (
    slug: string,
    body: {
      shot_id: string;
      version: number;
      verdict: "accept" | "reject" | "uncertain";
      note?: string;
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
    request<ApprovalsResponse>(
      `/api/projects/${slug}/approvals?stages=${encodeURIComponent(stages.join(","))}`,
    ),
  approvalChanges: (slug: string, stage: string) =>
    request<ApprovalChanges>(`/api/projects/${slug}/approvals/${stage}/changes`),
  approve: (
    slug: string,
    stage: string,
    body: {
      expected_hash: string;
      note?: string;
      confirmed: true;
      preview_watched?: boolean;
      inspected?: boolean;
      acknowledge_uncertain?: boolean;
    },
  ) =>
    request<ApprovalResponse>(`/api/projects/${slug}/approvals/${stage}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  render: (slug: string, kind: "preview" | "titles" | "base" | "final") =>
    request<unknown>(`/api/projects/${slug}/render`, {
      method: "POST",
      body: JSON.stringify({ kind }),
    }),
};
export type FilmFile = {
  kind: "previews" | "renders";
  name: string;
  classification: "base" | "preview" | "final" | "unknown";
  verified: boolean;
  current: boolean;
  delivery_ready: boolean;
  reason?: string | null;
};
export type FilmExports = {
  exports: string[];
  previews: string[];
  files?: FilmFile[];
  signature_required?: boolean;
};
