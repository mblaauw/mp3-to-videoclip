import { useState, type ReactNode } from "react";
import { Button } from "./Button";

function detailText(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

export function State({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return (
    <div className={`ui-state ${tone}`} role="status" aria-live="polite">
      {children}
    </div>
  );
}

export function LoadingState({ children }: { children: ReactNode }) {
  return (
    <State>
      <span className="ui-state-dot" aria-hidden="true" />
      <p>{children}</p>
    </State>
  );
}

/**
 * Friendly failure with the raw exception behind *Copy details*. Copy is the
 * only way the text appears; no path or stack is shown by default.
 */
export function ErrorState({
  what,
  error,
  onRetry,
  retryLabel = "Try again",
  compact = false,
}: {
  what: string;
  error: unknown;
  onRetry?: () => void;
  retryLabel?: string;
  compact?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const detail = detailText(error);

  const copy = async () => {
    setOpen(true);
    try {
      await navigator.clipboard.writeText(detail);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className={`ui-state error ${compact ? "compact" : ""}`} role="alert">
      <p>
        <b>Something went wrong while {what}.</b> Details are in the log.
      </p>
      <div className="ui-state-actions">
        {onRetry && (
          <Button size="small" onClick={onRetry}>
            {retryLabel}
          </Button>
        )}
        <Button
          size="small"
          variant="quiet"
          aria-expanded={open}
          onClick={() => void copy()}
        >
          {copied ? "Copied" : "Copy details"}
        </Button>
      </div>
      {open && <pre className="ui-state-detail">{detail}</pre>}
    </div>
  );
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="ui-state empty">
      <b>{title}</b>
      {children && <p>{children}</p>}
      {action && <div className="ui-state-actions">{action}</div>}
    </div>
  );
}
