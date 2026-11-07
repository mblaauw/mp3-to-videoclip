import { errorAction } from "./errors.ts";

export const OPEN_SETTINGS = "studio-open-settings";
/** The film's budget card, where a paid task that never came back is checked or settled. */
export const OPEN_BUDGET = "studio-open-budget";

/** The toast button for an error code. Settings is reachable anywhere; a stage needs its film. */
export function toastAction(code: string | null | undefined, slug?: string | null) {
  const action = errorAction(code);
  if (!action) return undefined;
  if ("settings" in action) {
    return {
      label: action.label,
      run: () => window.dispatchEvent(new Event(OPEN_SETTINGS)),
    };
  }
  if ("budget" in action) {
    return {
      label: action.label,
      run: () => window.dispatchEvent(new Event(OPEN_BUDGET)),
    };
  }
  if (!slug) return undefined;
  const place = `#/${encodeURIComponent(slug)}/${action.stage}`;
  return {
    label: action.label,
    run: () => {
      window.location.hash = place;
    },
  };
}
