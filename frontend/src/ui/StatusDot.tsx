export type StatusTone = "idle" | "done" | "you" | "changed" | "run" | "err";

export function StatusDot({ tone = "idle", label }: { tone?: StatusTone; label?: string }) {
  const classes = ["ui-dot", tone !== "idle" && `ui-dot--${tone}`].filter(Boolean).join(" ");
  if (!label) return <span className={classes} aria-hidden="true" />;
  return <span className={classes} role="img" aria-label={label} />;
}
