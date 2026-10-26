import { Button, StatusDot, type StatusTone } from "../ui";
import type { NextAction, NextStep } from "./nextStep";

const TONE: Record<NextStep["tone"], StatusTone> = {
  done: "done",
  you: "you",
  changed: "changed",
  error: "err",
};

export function NextStepBar({
  step,
  ready = true,
  onAction,
}: {
  step: NextStep;
  ready?: boolean;
  onAction: (action: NextAction) => void | Promise<void>;
}) {
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
  return (
    <div className={`next-bar ${step.tone}`} role="status" aria-live="polite">
      <div className="next-say">
        <StatusDot tone={TONE[step.tone]} />
        <strong>{step.title}</strong>
        {step.detail && <span>{step.detail}</span>}
      </div>
      <div className="next-actions">
        {step.actions.map((action, index) => (
          <Button
            key={`${action.label}-${index}`}
            variant={action.kind || (index === 0 ? "primary" : "default")}
            onClick={() => void onAction(action)}
          >
            {action.label}
          </Button>
        ))}
      </div>
    </div>
  );
}
