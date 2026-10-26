import { useEffect, useState } from "react";
import { api, type ArtifactName, type RatingSummary } from "./api";

const LABELS: Record<ArtifactName, string> = {
  brief: "Brief",
  treatments: "Concepts",
  storyboard: "Storyboard",
  edit: "Edit",
};

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
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setSummary(null);
    setMessage(null);
    setError(null);
    api
      .rating(slug, artifact)
      .then((value) => {
        if (cancelled) return;
        setSummary(value);
        setChosen(value.latest?.rating ?? null);
        setNote(value.latest?.note ?? "");
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [slug, artifact]);

  const save = async () => {
    if (!chosen || busy) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const value = await api.rate(slug, artifact, chosen, note);
      setSummary(value.summary);
      setMessage(
        value.summary.prompt.hash
          ? "Rating saved with this prompt revision."
          : "Rating saved without a prompt revision; it is listed as unbound.",
      );
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!summary) {
    return error ? (
      <p className="error">{error}</p>
    ) : (
      <p className="meta">Loading rating…</p>
    );
  }
  if (!summary.available) {
    return <p className="meta">No {LABELS[artifact]} artifact yet.</p>;
  }
  const prompt = summary.prompt.hash?.slice(0, 10);
  return (
    <div className="rating">
      <div className="rating-actions">
        <span className="meta">Rate this {LABELS[artifact].toLowerCase()}:</span>
        <button
          type="button"
          className={chosen === "up" ? "active" : ""}
          aria-pressed={chosen === "up"}
          onClick={() => setChosen("up")}
        >
          Good
        </button>
        <button
          type="button"
          className={chosen === "down" ? "active" : ""}
          aria-pressed={chosen === "down"}
          onClick={() => setChosen("down")}
        >
          Needs work
        </button>
        <span className="meta">
          {prompt ? `prompt ${prompt}` : "no prompt revision recorded"}
          {summary.history.length > 0
            ? ` · ${summary.history.length} rating${summary.history.length === 1 ? "" : "s"}`
            : ""}
        </span>
      </div>
      <textarea
        value={note}
        onChange={(event) => setNote(event.target.value)}
        rows={2}
        maxLength={1000}
        placeholder="Optional note: what worked, or what should change next time?"
        aria-label={`Rating note for ${LABELS[artifact]}`}
      />
      <div className="rating-actions">
        <button type="button" onClick={save} disabled={!chosen || busy}>
          {busy ? "Saving…" : "Save rating"}
        </button>
        {summary.latest && (
          <span className="meta">
            Latest: {summary.latest.rating === "up" ? "good" : "needs work"} ·{" "}
            {new Date(summary.latest.at).toLocaleString()}
          </span>
        )}
        {summary.stale && (
          <span className="error">The artifact changed since this rating.</span>
        )}
      </div>
      {message && <p className="message">{message}</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
