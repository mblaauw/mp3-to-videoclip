/**
 * One global notice channel. Failed API writes land here (so no failure is
 * silent), and so do short confirmations and finished background jobs.
 * Tone defaults to "error" so every existing `toast(message)` call keeps its
 * meaning; pass "done" or "info" for good news.
 */

export type ToastTone = "error" | "done" | "info";

export type ToastDetail = {
  message: string;
  tone: ToastTone;
  /** Optional action, e.g. jump to the stills when a batch finishes. */
  action?: { label: string; run: () => void };
};

export function toast(
  message: string,
  tone: ToastTone = "error",
  action?: ToastDetail["action"],
) {
  window.dispatchEvent(
    new CustomEvent<ToastDetail>("studio-toast", { detail: { message, tone, action } }),
  );
}
