export type LibraryKind = "character" | "place" | "narrator" | "look";

export type LibraryEntry = {
  key: string;
  kind: LibraryKind;
  id: string;
  version: number;
  label: string;
  from: { slug: string; title: string; at: string };
  summary: string;
  thumbnail: string | null;
  files: number;
};

export type Series = {
  id: string;
  title: string;
  bible: string;
  recurring: string[];
  episodes: { slug: string; number: number; title: string; at: string }[];
  created_at?: string;
};

export const KIND_WORD: Record<LibraryKind, string> = {
  character: "Characters",
  place: "Places",
  narrator: "Narrators",
  look: "Looks",
};

export const KIND_ORDER: LibraryKind[] = ["character", "place", "narrator", "look"];

/** Entries by kind, in the order the screen shows them; empty kinds are left out. */
export function groupByKind(entries: LibraryEntry[]): { kind: LibraryKind; entries: LibraryEntry[] }[] {
  return KIND_ORDER.map((kind) => ({
    kind,
    entries: entries.filter((entry) => entry.kind === kind).sort((a, b) => a.label.localeCompare(b.label)),
  })).filter((group) => group.entries.length > 0);
}

/** A series id from its title: lowercase words joined by dashes, never empty. */
export function seriesIdFrom(title: string): string {
  const value = title
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
  return value || "series";
}

/** The episode number a new film in this series would take. */
export function nextEpisode(series: Series | null | undefined): number {
  const numbers = (series?.episodes ?? []).map((episode) => episode.number);
  return numbers.length ? Math.max(...numbers) + 1 : 1;
}

/** One line about where an entry came from. */
export function provenance(entry: Pick<LibraryEntry, "from" | "version">): string {
  const when = entry.from.at ? new Date(entry.from.at).toLocaleDateString() : "";
  return `From ${entry.from.title}${when ? `, ${when}` : ""}${entry.version > 1 ? ` · v${entry.version}` : ""}`;
}
