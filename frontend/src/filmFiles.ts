import type { FilmExports, FilmFile } from "./api.ts";

export function filmFiles(value: FilmExports): FilmFile[] {
  return value.files ?? [
    ...value.exports.map((name) => ({ kind: "renders" as const, name })),
    ...value.previews.map((name) => ({ kind: "previews" as const, name })),
  ].map((file) => ({ ...file, classification: "unknown", verified: false, current: false, delivery_ready: false }));
}

export function selectFilm(files: FilmFile[], current: FilmFile | null): FilmFile | null {
  return files.find((file) => file.kind === current?.kind && file.name === current.name)
    ?? files.find((file) => file.classification === "final" && file.verified && file.current && file.delivery_ready)
    ?? files[0] ?? null;
}

export function filmLabel(file: FilmFile, signatureRequired?: boolean): string {
  switch (file.classification) {
    case "base": return signatureRequired === true ? "Base film — no intro/credits" : "Base film";
    case "preview": return "Marked preview";
    case "final": return file.delivery_ready && file.current && file.verified ? "Final delivery" : "Final render — not current";
    default: return "Unknown report";
  }
}
