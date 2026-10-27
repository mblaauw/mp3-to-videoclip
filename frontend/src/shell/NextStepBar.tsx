import { useEffect, useRef, useState } from "react";
import { Button, StatusDot, type StatusTone } from "../ui";
import type { NextAction, NextStep } from "./nextStep";

const TONE: Record<NextStep["tone"], StatusTone> = {
  done: "done",
  you: "you",
  changed: "changed",
  error: "err",
};

/**
 * The one sticky "what now" bar. It is the only place a stage is approved:
 * an approve action carries an optional note, shows its own progress and
 * cannot be double-clicked, so no stage needs a second approval card.
 */
export function NextStepBar({
  step,
  ready = true,
  onAction,
  back,
}: {
  step: NextStep;
  ready?: boolean;
  onAction: (action: NextAction, note?: string) => void | Promise<unknown>;
  /** The previous stage, so the way back is as obvious as the way forward. */
  back?: { label: string; onClick: () => void } | null;
}) {
  const [busy, setBusy] = useState<number | null>(null);
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("");
  const noteRef = useRef<HTMLInputElement>(null);
  const approving = step.actions.some((action) => action.approve);
  const key = `${step.title}|${step.actions.map((action) => action.label).join("|")}`;

  useEffect(() => {
    // A different step is a different decision: never carry a note across.
    setNoteOpen(false);
    setNote("");
    setBusy(null);
  }, [key]);

  useEffect(() => {
    if (noteOpen) noteRef.current?.focus();
  }, [noteOpen]);

  if (!ready) {
    return (
      <div className="next-bar" role="status" aria-live="polite">
        <div className="next-say">
          <StatusDot tone="run" />
          <strong>Checking approvals…</strong>
        </div>
      </div>
    );
  }

  const run = async (action: NextAction, index: number) => {
    if (busy !== null) return;
    setBusy(index);
    try {
      await onAction(action, action.approve ? note.trim() : undefined);
    } finally {
      setBusy(null);
    }
  };

  const primary = step.actions.findIndex((action) => action.approve);

  return (
    <div className={`next-bar ${step.tone}`} role="status" aria-live="polite">
      {back && (
        <button type="button" className="next-back" onClick={back.onClick}>
          <span aria-hidden="true">←</span> {back.label}
        </button>
      )}
      <div className="next-say">
        <StatusDot tone={TONE[step.tone]} />
        <strong>{step.title}</strong>
        {step.detail && <span>{step.detail}</span>}
      </div>
      <div className="next-actions">
        {approving &&
          (noteOpen ? (
            <input
              ref={noteRef}
              className="next-note"
              value={note}
              maxLength={2000}
              placeholder="What did you check? (optional)"
              aria-label="Approval note"
              onChange={(event) => setNote(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && primary >= 0) {
                  event.preventDefault();
                  void run(step.actions[primary], primary);
                }
                if (event.key === "Escape") {
                  setNoteOpen(false);
                  setNote("");
                }
              }}
            />
          ) : (
            <Button size="small" variant="quiet" onClick={() => setNoteOpen(true)}>
              Add a note
            </Button>
          ))}
        {step.actions.map((action, index) => (
          <Button
            key={`${action.label}-${index}`}
            variant={action.kind || (index === 0 ? "primary" : "default")}
            disabled={busy !== null}
            aria-busy={busy === index}
            onClick={() => void run(action, index)}
          >
            {busy === index ? (action.approve ? "Approving…" : "Working…") : action.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
