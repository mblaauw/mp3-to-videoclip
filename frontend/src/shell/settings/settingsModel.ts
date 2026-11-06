/** The panel's decisions, free of React so they can be tested on their own. */

export type TabId = "roles" | "voices" | "pictures" | "sounds" | "keys" | "new-films" | "computer" | "costs";

export const TABS: { id: TabId; label: string; hint: string }[] = [
  { id: "roles", label: "Roles", hint: "Who answers in the Director" },
  { id: "voices", label: "Voices", hint: "The narrator" },
  { id: "pictures", label: "Pictures", hint: "Stills, clips, upscaling" },
  { id: "sounds", label: "Sounds", hint: "Beds and effects" },
  { id: "keys", label: "Keys", hint: "Each provider's key" },
  { id: "new-films", label: "New films", hint: "Starting defaults" },
  { id: "computer", label: "This computer", hint: "Tools and folders" },
  { id: "costs", label: "Costs", hint: "Spent and reserved" },
];

export type CatalogPrice = { amount: string; unit: string };

export type CatalogModel = {
  id: string;
  provider: string;
  label: string;
  capabilities: string[];
  price: CatalogPrice | null;
  price_note: string;
  price_checked: string;
  recommended: string[];
  source: "static" | "listed";
};

export type CatalogVoice = {
  id: string;
  provider: string;
  model: string;
  label: string;
  language: string;
  preview_url: string;
  recommended: boolean;
};

export type CatalogProvider = {
  id: string;
  label: string;
  kind: string;
  lists_models: boolean;
  fetched_at: string | null;
  unlocks: string[];
  ready: {
    key: boolean;
    reachable: { ok: boolean; message: string; at: string } | null;
    unlocks: string[];
  };
};

export type CatalogFolders = {
  projects: { path: string; films: number };
  library: { path: string; entries: number; series: number };
};

export type Catalog = {
  providers: CatalogProvider[];
  models: CatalogModel[];
  voices: CatalogVoice[];
  computer: Record<string, boolean>;
  lyric_tools: { supported: boolean; reason: string | null; ready: boolean; download_gb: number };
  depth_tools: { supported: boolean; reason: string | null; ready: boolean; download_gb: number };
  folders?: CatalogFolders;
  notes: Record<string, string>;
};

/** Where to put a value in a nested patch, from a dotted path. */
export function patchAt(path: string, value: unknown): Record<string, unknown> {
  return path
    .split(".")
    .reverse()
    .reduce<unknown>((inner, key) => ({ [key]: inner }), value) as Record<string, unknown>;
}

export function readAt(source: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>(
      (value, key) => (value && typeof value === "object" ? (value as Record<string, unknown>)[key] : undefined),
      source,
    );
}

export function matches(query: string, ...words: (string | undefined)[]): boolean {
  const wanted = query.trim().toLowerCase();
  return !wanted || words.some((word) => word?.toLowerCase().includes(wanted));
}

const UNIT: Record<string, string> = {
  "1k_tokens_in": "per 1,000 tokens in",
  "1k_tokens_out": "per 1,000 tokens out",
  image: "per image",
  second: "per second",
  "1k_chars": "per 1,000 characters",
  run: "per run",
  clip: "per clip",
};

/** A price only ever appears as the catalogue states it, with the day it was read. */
export function priceWords(model: CatalogModel | undefined): string {
  if (!model?.price) return "Price unknown";
  const words = `$${model.price.amount} ${UNIT[model.price.unit] ?? model.price.unit}`;
  return model.price_checked ? `${words}, read ${model.price_checked}` : words;
}

export function modelsFor(
  catalog: Catalog,
  capabilities: string[],
  provider?: string,
): CatalogModel[] {
  return catalog.models.filter(
    (model) =>
      (provider === undefined || model.provider === provider) &&
      capabilities.every((capability) => model.capabilities.includes(capability)),
  );
}

const ROLES = ["writer", "editor", "critic", "narrator"] as const;

/** Each role's recommended provider and model. Everything else in a role is kept. */
export function recommendedRoles(catalog: Catalog): Record<string, unknown> {
  const roles: Record<string, unknown> = {};
  for (const role of ROLES) {
    const model = catalog.models.find((item) => item.recommended.includes(role));
    if (model) roles[role] = { provider: model.provider, model: model.id };
  }
  return { roles };
}

export function recommendedVoices(catalog: Catalog): Record<string, unknown> {
  const voice = catalog.voices.find((item) => item.recommended);
  return voice ? { voices: { provider: voice.provider, default_voice: voice.id } } : {};
}

/** The catalogue's recommended bed and effects models; the reserve is left alone. */
export function recommendedSounds(catalog: Catalog): Record<string, unknown> {
  const sounds: Record<string, string> = {};
  const music = catalog.models.find((item) => item.recommended.includes("music"));
  const effects = catalog.models.find((item) => item.recommended.includes("effects"));
  if (music) sounds.music_model = music.id;
  if (effects) sounds.effects_model = effects.id;
  return { sounds };
}

/** Empty choices mean each look's own model, which is what films use today. */
export function recommendedPictures(looks: string[]): Record<string, unknown> {
  const image_model_by_look = Object.fromEntries(looks.map((look) => [look, ""]));
  return { pictures: { image_model_by_look, video_model: "", upscaler: "" } };
}

export type Missing = { id: string; label: string; tab: TabId; field: string };

/** What stands between this computer and a first film, each with where to fix it. */
export function missingForFilm(
  settings: { role_keys?: { writer?: boolean }; roles?: { writer?: { provider?: string } }; has_runware_key?: unknown },
  computer: Record<string, boolean>,
): Missing[] {
  const missing: Missing[] = [];
  if (!settings.role_keys?.writer) {
    missing.push({
      id: "writer-key",
      label: "A Writer key, so the Director can answer",
      tab: "keys",
      field: `key-${settings.roles?.writer?.provider || "direct"}`,
    });
  }
  if (!settings.has_runware_key) {
    missing.push({
      id: "runware-key",
      label: "A Runware key, for pictures",
      tab: "keys",
      field: "key-runware",
    });
  }
  if (computer.renderer === false) {
    missing.push({
      id: "renderer",
      label: "The renderer, to make the film",
      tab: "computer",
      field: "install-renderer",
    });
  }
  if (computer.ffmpeg === false) {
    missing.push({
      id: "ffmpeg",
      label: "FFmpeg, to finish the film. Install it, then reopen Settings",
      tab: "computer",
      field: "tool-ffmpeg",
    });
  }
  return missing;
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`;
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(0)} MB`;
  if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(0)} KB`;
  return `${bytes} B`;
}

export function money(value: string | undefined): string {
  return `$${Number(value ?? 0).toFixed(2)}`;
}

