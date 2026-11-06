import { useState } from "react";
import { api } from "../api";
import { Button, ErrorState } from "../ui";

/** Takes of some lines: first the price, then the purchase through the journal. */
export function Buy({
  slug,
  label,
  lineIds,
  regenerate,
}: {
  slug: string;
  label: string;
  lineIds?: string[];
  regenerate?: boolean;
}) {
  const [quote, setQuote] = useState<{ id: string; price: string; lines: number } | null>(null);
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
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const started = await api.generateLines(slug, quote.id);
                if (started.needs_budget) throw new Error("The budget has no room for this.");
                setQuote(null);
              })
            }
          >
            Buy {quote.lines} line{quote.lines === 1 ? "" : "s"} · ${quote.price}
          </Button>
          <Button size="small" variant="quiet" disabled={busy} onClick={() => setQuote(null)}>
            Not now
          </Button>
        </>
      ) : (
        <Button
          size="small"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const made = await api.estimateLines(slug, { line_ids: lineIds, regenerate });
              setQuote({ id: made.quote_id, price: made.reserve_usd, lines: made.tasks });
            })
          }
        >
          {busy ? "Working it out…" : label}
        </Button>
      )}
      {error && <ErrorState what="pricing the takes" error={error} compact />}
    </span>
  );
}
