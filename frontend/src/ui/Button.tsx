import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "default" | "primary" | "quiet";
type Size = "default" | "small";

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
};

export function Button({
  variant = "default",
  size = "default",
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  const classes = [
    "ui-btn",
    variant !== "default" && `ui-btn--${variant}`,
    size === "small" && "ui-btn--small",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button type={type} className={classes} {...rest}>
      {children}
    </button>
  );
}
