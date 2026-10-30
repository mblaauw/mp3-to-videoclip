import type { GraphicsSample } from "../api";
import type { TitleWindow } from "../baseFilm";

function clock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

const PHASES: Record<string, string> = {
  mark: "mark",
  names: "names",
  title: "title",
  scrim: "backdrop",
  time: "running time",
  tagline: "tagline",
};

/** "Style direction at 3:37" for a sample of the film; the file name for an older review. */
export function sampleTitle(
  sample: GraphicsSample,
  windows: (TitleWindow & { card?: string[] | null })[],
): string {
  if (sample.frame == null || sample.seconds == null) return sample.name;
  const window = windows.find((item) => item.id === sample.window);
  let name = "Film";
  if (window?.kind === "intro") {
    const phase = sample.phase?.replace(/_\d+$/, "") ?? "";
    name = `Opening${phase ? `: ${PHASES[phase] ?? phase.replace(/_/g, " ")}` : ""}`;
  } else if (window?.kind === "identity") name = "Partnership card";
  else if (window?.kind === "lockup") name = "Closing signature";
  else if (window?.kind === "card" && window.card) {
    name = window.card[0][0] + window.card[0].slice(1).toLowerCase();
  } else if (window?.kind === "caption") name = "Caption";
  return `${name} at ${clock(sample.seconds)}`;
}
