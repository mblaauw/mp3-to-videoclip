import { useState } from "react";
import { api } from "../api";
import { Button, ErrorState } from "../ui";

/** A 2× copy of the selected still. Two clicks: first the price, then the purchase. */
export function MakeSharper({
  slug,
  shotId,
  disabled,
  onStarted,
}: {
  slug: string;
  shotId: string;
  disabled: boolean;
  onStarted: () => void;
}) {
  const [quote, setQuote] = useState<{ id: string; price: string } | null>(null);
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
  return (
    <span className="make-sharper">
      {quote ? (
        <>
          <Button
            size="small"
            variant="primary"
            disabled={busy || disabled}
            onClick={() =>
              void run(async () => {
                const started = await api.generateUpscale(slug, quote.id);
                if (started.needs_budget) throw new Error("The budget has no room for this.");
                setQuote(null);
                onStarted();
              })
            }
          >
            Buy · ${quote.price}
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
              const { estimate } = await api.estimateUpscale(slug, [shotId]);
              setQuote({ id: estimate.quote_id, price: estimate.reserve_usd });
            })
          }
        >
          {busy ? "Working it out…" : "Make sharper"}
        </Button>
      )}
      {error && <ErrorState what="making a sharper version" error={error} compact />}
    </span>
  );
}
