import { type Stage } from "./nextStep";

const DIRECTOR_OPEN = "studio.director.";

/** Film gives the picture its room; other stages keep the Director beside the work. */
export function directorDefault(stage: Stage): boolean {
  try {
    const saved = window.localStorage.getItem(DIRECTOR_OPEN + stage);
    if (saved !== null) return saved === "1";
  } catch {
    // Storage can be blocked; the default still works.
  }
  return stage !== "film" && window.innerWidth > 1180;
}

export function rememberDirector(stage: Stage, open: boolean) {
  try {
    window.localStorage.setItem(DIRECTOR_OPEN + stage, open ? "1" : "0");
  } catch {
    // Storage can be blocked; the choice just lasts this visit.
  }
}
