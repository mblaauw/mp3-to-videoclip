import { useEffect, useState } from "react";
import { api } from "../api";
import { Button, ErrorState } from "../ui";

/** The owner's one authorisation for a first draft, with both parts of the ceiling in view. */
export function FirstDraftDialog({ slug, onClose }: { slug: string; onClose: () => void }) {
  const [plan, setPlan] = useState<Awaited<ReturnType<typeof api.firstDraft>> | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.firstDraft(slug).then(setPlan, (caught) => setError(String(caught)));
  }, [slug]);
  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.startFirstDraft(slug);
      onClose();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="popover first-draft" role="dialog" aria-label="Make a first draft">
      <h3>Make a first draft</h3>
      {plan && (
        <ul>
          <li>
            Up to {plan.stills} stills, at most ${plan.stills_usd}.
          </li>
          <li>
            The Writer and Editor, about ${plan.model_usd}. Most text models have no known price
            yet, so this also stops at {plan.model_tokens.toLocaleString()} tokens.
          </li>
          <li>Nothing past the proof: stills, titles and a final stay yours to approve.</li>
        </ul>
      )}
      <label className="check-line">
        <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
        The cast will be invented; confirm them for me
      </label>
      {error && <ErrorState what="starting the draft" error={error} compact />}
      <div className="row-actions">
        <Button size="small" variant="primary" disabled={!agreed || busy || !plan} onClick={() => void start()}>
          Make a first draft · up to ${plan?.ceiling_usd ?? "1.00"}
        </Button>
        <Button size="small" variant="quiet" onClick={onClose}>
          Not now
        </Button>
      </div>
    </div>
  );
}
