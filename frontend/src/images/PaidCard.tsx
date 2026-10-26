import { useEffect, useState } from "react";
import { Button } from "../ui";
import type { PaidQuote } from "./paid";

export function PaidCard({
  quote,
  busy,
  onTopUp,
  onConfirm,
  onCancel,
}: {
  quote: PaidQuote;
  busy: boolean;
  onTopUp: (amount: string, uploadsConfirmed: boolean) => void;
  onConfirm: (uploadsConfirmed: boolean) => void;
  onCancel: () => void;
}) {
  const [uploads, setUploads] = useState(false);
  const needsBudget = quote.decision.needs_budget === true;
  const needsUploads = quote.estimate.uploads_required;
  const room = quote.decision.remaining ?? quote.budget?.remaining_usd ?? "0.00";
  const add = quote.decision.suggested_usd || "0.50";
  const roomText = Number(room) > 0 ? Number(room).toFixed(2) : "0.00";
  const addText = Number(add).toFixed(2);

  useEffect(() => {
    setUploads(false);
  }, [quote.estimate.quote_id]);

  return (
    <section className="paid-card" aria-live="polite">
      <header>
        <b>
          {quote.estimate.tasks} still{quote.estimate.tasks === 1 ? "" : "s"} · $
          {quote.estimate.reserve_usd}
        </b>
        <button type="button" className="paid-close" onClick={onCancel} aria-label="Close">
          ×
        </button>
      </header>
      {needsBudget ? (
        <p>
          This needs ${quote.estimate.reserve_usd}; ${roomText} is left in the budget. Add
          ${addText} to the budget and the batch starts.
        </p>
      ) : (
        <p>The quote is ready. Nothing is sent until you confirm.</p>
      )}
      {needsUploads && (
        <label className="check-line">
          <input
            type="checkbox"
            checked={uploads}
            onChange={(event) => setUploads(event.target.checked)}
          />
          Upload the selected reference images to the provider for this batch
        </label>
      )}
      <div className="row-actions">
        {needsBudget ? (
          <Button
            size="small"
            variant="primary"
            disabled={busy || (needsUploads && !uploads)}
            onClick={() => onTopUp(add, uploads)}
          >
            {busy ? "Adding…" : `Add $${addText} to budget`}
          </Button>
        ) : (
          <Button
            size="small"
            variant="primary"
            disabled={busy || (needsUploads && !uploads)}
            onClick={() => onConfirm(uploads)}
          >
            {busy
              ? "Queueing…"
              : `Make ${quote.estimate.tasks} still${
                  quote.estimate.tasks === 1 ? "" : "s"
                } · $${quote.estimate.reserve_usd}`}
          </Button>
        )}
        <Button size="small" variant="quiet" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </section>
  );
}
