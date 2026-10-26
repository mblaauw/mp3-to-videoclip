import type { ReactNode } from "react";

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="ui-field">
      <span>{label}</span>
      {children}
      {hint && <p className="ui-hint">{hint}</p>}
    </label>
  );
}
