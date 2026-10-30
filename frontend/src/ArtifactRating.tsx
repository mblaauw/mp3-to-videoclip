import { useEffect, useState } from "react";
import { api, type ArtifactName, type RatingSummary } from "./api";

const LABELS: Record<ArtifactName, string> = {
  brief: "brief",
  treatments: "concept set",
  storyboard: "storyboard",
  edit: "cut",
};

function ThumbUp() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
      <path
        d="M6.2 7.2 8.4 2h.9c.8 0 1.3.7 1.1 1.5L9.8 6h2.8c1 0 1.6.9 1.3 1.8l-1.2 4.1c-.2.7-.8 1.1-1.5 1.1H6.2V7.2ZM2 7.2h2.6v5.8H2V7.2Z"
        fill="currentColor"
      />
    </svg>
  );
}

function ThumbDown() {
  return (
    <svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true">
      <path
        d="M9.8 8.8 7.6 14h-.9c-.8 0-1.3-.7-1.1-1.5L6.2 10H3.4c-1 0-1.6-.9-1.3-1.8l1.2-4.1c.2-.7.8-1.1 1.5-1.1h5V8.8ZM14 8.8h-2.6V3H14v5.8Z"
        fill="currentColor"
      />
    </svg>
  );
}

/**
 * One-click evaluation, not an approval. Good saves at once; Needs work saves
 * at once and then offers the optional one-line note. All four artifacts keep
 * their own spot, beside the title of the thing being judged.
 */
export function ArtifactRating({
  slug,
  artifact,
}: {
  slug: string;
  artifact: ArtifactName;
}) {
  const [summary, setSummary] = useState<RatingSummary | null>(null);
  const [chosen, setChosen] = useState<"up" | "down" | null>(null);
  const [note, setNote] = useState("");
  const [noteOpen, setNoteOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSummary(null);
    setError(null);
    setSaved(false);
    setNoteOpen(false);
    api
      .rating(slug, artifact)
      .then((value) => {
        if (cancelled) return;
        setSummary(value);
        setChosen(value.latest?.rating ?? null);
        setNote(value.latest?.note ?? "");
      })
      .catch((caught) => {
        if (!cancelled) setError(String(caught));
      });
    return () => {
      cancelled = true;
    };
  }, [slug, artifact]);

  useEffect(() => {
    if (!saved) return;
    const timer = window.setTimeout(() => setSaved(false), 1800);
    return () => window.clearTimeout(timer);
  }, [saved]);

  const submit = async (rating: "up" | "down", text: string) => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.rate(slug, artifact, rating, text);
      setSummary(result.summary);
      setChosen(rating);
      setNote(result.entry.note);
      setSaved(true);
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  };

  const choose = async (rating: "up" | "down") => {
    if (busy) return;
    if (rating === "up") {
      setNoteOpen(false);
      await submit("up", "");
      return;
    }
    setNoteOpen(true);
    if (chosen === "down") return;
    await submit("down", note.trim());
  };

  if (!summary) {
    return error ? <span className="rating-error">{error}</span> : null;
  }
  if (!summary.available) {
    return (
      <span className="rating-pending" title={`No ${LABELS[artifact]} yet`}>
        Rate · no {LABELS[artifact]} yet
      </span>
    );
  }

  const prompt = summary.prompt.hash?.slice(0, 10);
  const revision = prompt
    ? `Prompt revision ${prompt}`
    : "No prompt revision recorded for this artifact";
  const latest = summary.latest
    ? `Last rated ${summary.latest.rating === "up" ? "Good" : "Needs work"} · ${new Date(
        summary.latest.at,
      ).toLocaleString()}`
    : "Not rated yet";

  return (
    <div className="rating-inline" aria-label={`Rate the ${LABELS[artifact]}`}>
      <span className="rating-label" title={`${revision}. ${latest}`}>
        Rate {LABELS[artifact]}
      </span>
      <button
        type="button"
        className={`rating-btn ${chosen === "up" ? "on good" : ""}`}
        aria-pressed={chosen === "up"}
        aria-label={`Good ${LABELS[artifact]}`}
        title={revision}
        disabled={busy}
        onClick={() => void choose("up")}
      >
        <ThumbUp /> Good
      </button>
      <button
        type="button"
        className={`rating-btn ${chosen === "down" ? "on bad" : ""}`}
        aria-pressed={chosen === "down"}
        aria-label={`Needs work on ${LABELS[artifact]}`}
        title={revision}
        disabled={busy}
        onClick={() => void choose("down")}
      >
        <ThumbDown /> Needs work
      </button>
      {summary.stale && (
        <span className="rating-stale" title={revision}>
          changed since this rating
        </span>
      )}
      {saved && <span className="rating-saved">Saved</span>}
      {noteOpen && (
        <span className="rating-note">
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void submit("down", note.trim());
                setNoteOpen(false);
              }
              if (event.key === "Escape") setNoteOpen(false);
            }}
            placeholder="What should change? (optional)"
            maxLength={1000}
            aria-label={`Rating note for the ${LABELS[artifact]}`}
          />
          <button
            type="button"
            className="rating-note-save"
            disabled={busy}
            onClick={() => {
              void submit("down", note.trim());
              setNoteOpen(false);
            }}
          >
            Save note
          </button>
        </span>
      )}
      {error && <span className="rating-error">{error}</span>}
    </div>
  );
}
