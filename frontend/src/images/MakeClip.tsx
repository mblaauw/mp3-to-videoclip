import { useState } from "react";
import { api, type ImageShot } from "../api";
import { Button, ErrorState } from "../ui";

/** A short moving version of the selected still. First the price, then the purchase. */
export function MakeClip({
  slug,
  shot,
  disabled,
  onChanged,
}: {
  slug: string;
  shot: ImageShot;
  disabled: boolean;
  onChanged: () => void;
}) {
  const [quote, setQuote] = useState<{ id: string; price: string; seconds: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (step: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await step();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  };
  const use = (version: number | null) =>
    void run(async () => {
      await api.selectClip(slug, shot.id, version);
      onChanged();
    });
  return (
    <div className="make-clip">
      {quote ? (
        <>
          <Button
            size="small"
            variant="primary"
            disabled={busy || disabled}
            onClick={() =>
              void run(async () => {
                const started = await api.generateClips(slug, quote.id);
                if (started.needs_budget) throw new Error("The budget has no room for this.");
                setQuote(null);
                onChanged();
              })
            }
          >
            Make a clip · up to ${quote.price} for {quote.seconds} s
          </Button>
          <Button size="small" variant="quiet" disabled={busy} onClick={() => setQuote(null)}>
            Not now
          </Button>
        </>
      ) : (
        <Button
          size="small"
          disabled={busy || disabled}
          onClick={() =>
            void run(async () => {
              const { estimate } = await api.estimateClips(slug, [shot.id]);
              setQuote({
                id: estimate.quote_id,
                price: estimate.reserve_usd,
                seconds: estimate.seconds,
              });
            })
          }
        >
          {busy ? "Working it out…" : "Make a clip"}
        </Button>
      )}
      {(shot.clips ?? []).map((clip) => {
        const inUse = shot.clip === clip.version;
        return (
          <div className={`clip-card ${inUse ? "on" : ""}`} key={clip.version}>
            <video
              src={`/api/projects/${slug}/clips/${encodeURIComponent(shot.owner)}/${clip.version}`}
              controls
              muted
              preload="metadata"
            />
            <span className="hint">
              {clip.seconds.toFixed(1)} s
              {clip.current ? "" : ", made from another still. Select that still to use it."}
            </span>
            {inUse ? (
              <Button size="small" disabled={busy} onClick={() => use(null)}>
                Use the still
              </Button>
            ) : (
              <Button
                size="small"
                disabled={busy || !clip.current}
                onClick={() => use(clip.version)}
              >
                Use this clip
              </Button>
            )}
          </div>
        );
      })}
      {error && <ErrorState what="making a clip" error={error} compact />}
    </div>
  );
}
