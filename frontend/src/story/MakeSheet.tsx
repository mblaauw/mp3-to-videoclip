import { useState } from "react";
import { api, type Brief, type SheetRow } from "../api";
import { Button, ErrorState } from "../ui";

/** A sheet or plate for one entry. Two clicks: first the price, then the purchase. */
export function MakeSheet({
  slug,
  entryId,
  label,
  row,
  blocked,
  onBriefChange,
}: {
  slug: string;
  entryId: string;
  label: string;
  row: SheetRow | undefined;
  blocked: string | null;
  onBriefChange: (brief: Brief) => void;
}) {
  const [quote, setQuote] = useState<{ id: string; price: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
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
  const version = row?.version ?? null;
  return (
    <div className="make-sheet">
      {version !== null && (
        <a
          href={`/api/projects/${slug}/images/${encodeURIComponent(`sheet:${entryId}`)}/${version}`}
          target="_blank"
          rel="noreferrer"
        >
          <img
            src={`/api/projects/${slug}/images/${encodeURIComponent(`sheet:${entryId}`)}/${version}`}
            alt={`Sheet for ${entryId}`}
          />
        </a>
      )}
      <div className="row-actions">
        {quote ? (
          <>
            <Button
              size="small"
              variant="primary"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const started = await api.generateSheet(slug, quote.id);
                  if (started.needs_budget) throw new Error("The budget has no room for this.");
                  setQuote(null);
                  setNote("Being made. It appears here when it is ready.");
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
            variant="quiet"
            disabled={busy || blocked !== null}
            title={blocked ?? undefined}
            onClick={() =>
              void run(async () => {
                setNote(null);
                const { estimate } = await api.estimateSheet(slug, entryId);
                setQuote({ id: estimate.quote_id, price: estimate.reserve_usd });
              })
            }
          >
            {busy ? "Working it out…" : version === null ? label : `${label} again`}
          </Button>
        )}
        {version !== null && !quote && (
          <Button
            size="small"
            variant="quiet"
            disabled={busy}
            title="The story then needs approving again, because its references change."
            onClick={() =>
              void run(async () => {
                onBriefChange(await api.useSheet(slug, entryId, version));
                setNote("Now a reference. The story needs approving again.");
              })
            }
          >
            Use as reference
          </Button>
        )}
      </div>
      {note && <p className="hint">{note}</p>}
      {version !== null && row && !row.current && (
        <p className="hint">This was made before the description last changed.</p>
      )}
      {error && <ErrorState what="making the sheet" error={error} compact />}
    </div>
  );
}
