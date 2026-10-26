/** A small app-wide signal for mutations that change the library or shell data. */

export const PROJECT_CHANGED = "studio:project-changed";

export function notifyProjectChanged() {
  window.dispatchEvent(new Event(PROJECT_CHANGED));
}
