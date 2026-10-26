import type { ButtonHTMLAttributes, ReactNode } from "react";

export type ChipProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  pressed?: boolean;
  count?: number;
  children: ReactNode;
};

export function Chip({ pressed, count, className, children, type = "button", ...rest }: ChipProps) {
  return (
    <button
      type={type}
      className={["ui-chip", className].filter(Boolean).join(" ")}
      aria-pressed={pressed}
      {...rest}
    >
      {children}
      {count !== undefined && <span className="n">{count}</span>}
    </button>
  );
}
