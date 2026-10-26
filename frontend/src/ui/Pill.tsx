import type { ReactNode } from "react";

export type PillTone = "neutral" | "keep" | "redo" | "old" | "you";

export function Pill({ tone = "neutral", children }: { tone?: PillTone; children: ReactNode }) {
  const classes = ["ui-pill", tone !== "neutral" && `ui-pill--${tone}`].filter(Boolean).join(" ");
  return <span className={classes}>{children}</span>;
}
