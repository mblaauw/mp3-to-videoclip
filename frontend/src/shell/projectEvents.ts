/**
 * One app-wide signal for "the data behind this view changed; read it again".
 *
 * Sources: a save in this tab, a server `project.changed` event (another tab,
 * the director's tools, a finished or progressing job, a CLI write), and a
 * reconnect of the event stream. Bursts are coalesced into one dispatch so a
 * job that finishes three stills in a row, or a save that is echoed back by the
 * server, reloads each view once instead of three times.
 */

import { useEffect, useRef } from "react";

export const PROJECT_CHANGED = "studio:project-changed";

export type ProjectChange = {
  /** The film that changed; absent means "anything may have changed". */
  slug?: string;
  /** Where the notice came from: "local", "request", "job", "director", "disk", "reconnect". */
  source?: string;
  /** Optional hint at what changed ("images", "render", "brief"…). */
  artifact?: string;
};

export type ProjectChangeDetail = {
  slugs: string[];
  /** True when at least one notice did not name a film. */
  any: boolean;
  sources: string[];
  artifacts: string[];
};

const COALESCE_MS = 120;
let pending: ProjectChange[] = [];
let timer: number | null = null;

function flush() {
  timer = null;
  const batch = pending;
  pending = [];
  if (!batch.length) return;
  const detail: ProjectChangeDetail = {
    slugs: [...new Set(batch.map((item) => item.slug).filter(Boolean) as string[])],
    any: batch.some((item) => !item.slug),
    sources: [...new Set(batch.map((item) => item.source || "local"))],
    artifacts: [...new Set(batch.map((item) => item.artifact).filter(Boolean) as string[])],
  };
  window.dispatchEvent(new CustomEvent<ProjectChangeDetail>(PROJECT_CHANGED, { detail }));
}

export function notifyProjectChanged(change: ProjectChange = {}) {
  pending.push({ source: "local", ...change });
  if (timer === null) timer = window.setTimeout(flush, COALESCE_MS);
}

/** Does this notice concern the given film? */
export function concerns(event: Event, slug: string): boolean {
  const detail = (event as CustomEvent<ProjectChangeDetail | undefined>).detail;
  if (!detail) return true;
  return detail.any || detail.slugs.includes(slug);
}

/**
 * Run `reload` whenever the given film (or anything) changes. The callback is
 * kept in a ref, so callers can pass an inline function without re-subscribing.
 */
export function useProjectChanged(
  slug: string | null | undefined,
  reload: (detail: ProjectChangeDetail | undefined) => void,
) {
  const ref = useRef(reload);
  ref.current = reload;
  useEffect(() => {
    const handler = (event: Event) => {
      if (slug && !concerns(event, slug)) return;
      ref.current((event as CustomEvent<ProjectChangeDetail | undefined>).detail);
    };
    window.addEventListener(PROJECT_CHANGED, handler);
    return () => window.removeEventListener(PROJECT_CHANGED, handler);
  }, [slug]);
}
