import { useState } from "react";
import { Button } from "../ui";

/** One correction per shot is the limit; going past it is a stated decision. */
export function NewRoundCard({
  shots,
  busy,
  onStart,
  onCancel,
}: {
  shots: string[];
  busy: boolean;
  onStart: (note: string) => void;
  onCancel: () => void;
}) {
  const [note, setNote] = useState("");
  return (
    <section className="paid-card" aria-live="polite">
      <header>
        <b>{shots.join(", ")} used their correction</b>
        <button type="button" className="paid-close" onClick={onCancel} aria-label="Close">
          ×
        </button>
      </header>
      <p>
        Each shot gets one remake, so a bad prompt can't quietly use up the budget. Starting a new
        round allows one still and one remake more. Nothing is spent yet.
      </p>
      <label className="ui-field">
        <span>Why is another round worth it?</span>
        <textarea rows={2} value={note} onChange={(event) => setNote(event.target.value)} />
      </label>
      <div className="row-actions">
        <Button
          size="small"
          variant="primary"
          disabled={busy || !note.trim()}
          onClick={() => onStart(note.trim())}
        >
          {busy ? "Starting…" : "Start a new round"}
        </Button>
        <Button size="small" variant="quiet" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
    </section>
  );
}
