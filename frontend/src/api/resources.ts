/** Shared reads only: components keep their own last success and error state. */
export type ResourceChange = { slug?: string; artifact?: string; source?: string };

const dependencies: Record<string, string[]> = {
  brief: ["brief", "intake", "images", "preview", "approvals", "film", "edit", "history", "treatments", "graphics", "graphics-review"],
  storyboard: ["storyboard", "images", "preview", "approvals", "film", "edit", "history"],
  edit: ["edit", "preview", "approvals", "film", "history"],
  images: ["images", "edit", "preview", "approvals", "film", "budget"],
  budget: ["budget"],
  track: ["track", "music-notes", "preview", "approvals", "film", "intake", "edit"],
  lyrics: ["track", "approvals", "film"],
  treatments: ["treatments", "brief", "intake", "approvals", "history"],
  approvals: ["approvals", "film"],
  graphics: ["graphics", "graphics-review", "preview", "approvals", "film", "exports"],
  render: ["exports", "preview", "graphics-review", "approvals", "film"],
};

type Entry = { promise: Promise<unknown> };
export class Resources {
  private entries = new Map<string, Entry>();

  read<T>(key: string, load: () => Promise<T>): Promise<T> {
    const existing = this.entries.get(key);
    if (existing) return existing.promise as Promise<T>;
    const entry = {} as Entry;
    const current = () => this.entries.get(key) === entry;
    entry.promise = Promise.resolve().then(load).then(
      (value) => current() ? value : this.read(key, load),
      (error: unknown) => {
        // An obsolete failure must not replace the newer success either.
        if (!current()) return this.read(key, load);
        this.entries.delete(key);
        throw error;
      },
    );
    this.entries.set(key, entry);
    return entry.promise as Promise<T>;
  }

  invalidate(change: ResourceChange = {}) {
    if (!change.slug || change.source === "reconnect") {
      this.entries.clear();
      return;
    }
    const affected = change.artifact ? dependencies[change.artifact] : undefined;
    for (const key of this.entries.keys()) {
      if (key === "/api/projects") this.entries.delete(key);
      const match = key.match(/^\/api\/projects\/([^/?]+)(?:\/([^/?]+))?/);
      if (match?.[1] !== change.slug) continue;
      // Missing/unknown hints are whole-project invalidations. Detail always changes.
      if (!affected || !match[2] || affected.includes(match[2])) this.entries.delete(key);
    }
  }
}

export const resources = new Resources();

export function draftError(error: unknown): string {
  return error && typeof error === "object" && "status" in error && error.status === 409
    ? "The saved base changed. Your draft is kept. Reload and review the latest version before trying again."
    : String(error);
}

type Revision = { slug: string; artifact: string; etag: string };
const revisions = new WeakMap<object, Revision>();
export function bindRevision(value: unknown, slug: string, artifact: string, etag: string | null) {
  if (!etag || !value || typeof value !== "object") return;
  revisions.set(value, { slug, artifact, etag });
}
export function revisionHeaders(base: unknown, slug: string, artifact: string): Record<string, string> {
  const revision = base && typeof base === "object" ? revisions.get(base) : undefined;
  return revision?.slug === slug && revision.artifact === artifact
    ? { "If-Match": revision.etag } : {};
}
