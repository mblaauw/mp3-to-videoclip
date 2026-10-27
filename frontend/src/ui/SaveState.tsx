export type SaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";

function stamp(at: number | null): string {
  if (!at) return "";
  return new Date(at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/**
 * One quiet, consistent save indicator for autosaving fields: it says whether
 * the text on screen is the text on disk, and offers a retry when it is not.
 */
export function SaveState({
  status,
  savedAt = null,
  onRetry,
}: {
  status: SaveStatus;
  savedAt?: number | null;
  onRetry?: () => void;
}) {
  if (status === "idle" && !savedAt) return null;
  const word =
    status === "saving"
      ? "Saving…"
      : status === "dirty"
        ? "Unsaved changes"
        : status === "error"
          ? "Not saved"
          : `Saved${savedAt ? ` · ${stamp(savedAt)}` : ""}`;
  return (
    <span className={`save-state ${status}`} role="status" aria-live="polite">
      <i aria-hidden="true" />
      {word}
      {status === "error" && onRetry && (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </span>
  );
}
