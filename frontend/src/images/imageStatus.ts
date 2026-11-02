import { type Budget, type ImageShot } from "../api";
import type { NextAction } from "../shell/nextStep";

export type Card = Omit<Budget, "history">;

export type Filter = "all" | "review" | "redo" | "stale" | "missing" | "kept" | "made";

export type PaidRequest = NonNullable<NextAction["paid"]>;

export const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "review", label: "To review" },
  { id: "redo", label: "Redo" },
  { id: "stale", label: "Older prompt" },
  { id: "missing", label: "Not made" },
  { id: "kept", label: "Kept" },
  { id: "made", label: "Made here" },
];

export function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function money(value: string | null | undefined): string {
  const number = Number(value || 0);
  return number.toFixed(2);
}

export function sourceUrl(slug: string, shot: ImageShot): string | null {
  if (shot.plate) return shot.plate;
  if (shot.selected === null) return null;
  return `/api/projects/${slug}/images/${encodeURIComponent(shot.owner)}/${shot.selected}`;
}

export function statusOf(shot: ImageShot): { tone: string; label: string } {
  if (shot.local) return { tone: "made", label: "Made here" };
  if (shot.selected === null) return { tone: "missing", label: "Not made" };
  if (shot.stale) return { tone: "stale", label: "Older prompt" };
  if (shot.review?.verdict === "accept") return { tone: "kept", label: "Kept" };
  if (shot.review?.verdict === "reject") return { tone: "redo", label: "Redo" };
  if (shot.review?.verdict === "uncertain") return { tone: "review", label: "Check" };
  return { tone: "review", label: "To review" };
}

export function matches(shot: ImageShot, filter: Filter): boolean {
  if (filter === "all") return true;
  if (filter === "made") return shot.local;
  if (shot.local) return false;
  if (filter === "missing") return shot.selected === null;
  if (filter === "stale") return shot.stale;
  if (shot.selected === null) return false;
  if (filter === "kept") return !shot.stale && shot.review?.verdict === "accept";
  if (filter === "redo") return shot.review?.verdict === "reject";
  return (
    !shot.stale &&
    shot.review?.verdict !== "accept" &&
    shot.review?.verdict !== "reject"
  );
}
