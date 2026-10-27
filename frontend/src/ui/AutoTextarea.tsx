import {
  forwardRef,
  useCallback,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  type TextareaHTMLAttributes,
} from "react";

export type AutoTextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  /** Rows to show when empty. */
  minRows?: number;
  /** Grow up to this many rows, then scroll. */
  maxRows?: number;
};

/**
 * A textarea that grows with its text, so long prompts and notes are read in
 * full instead of through a two-line slot. Height is measured after every
 * value change and on width changes (the sidebar can resize).
 */
export const AutoTextarea = forwardRef<HTMLTextAreaElement, AutoTextareaProps>(
  function AutoTextarea({ minRows = 2, maxRows = 18, className, style, value, ...rest }, ref) {
    const inner = useRef<HTMLTextAreaElement>(null);
    useImperativeHandle(ref, () => inner.current as HTMLTextAreaElement);

    const fit = useCallback(() => {
      const element = inner.current;
      if (!element) return;
      const styles = window.getComputedStyle(element);
      const line = parseFloat(styles.lineHeight) || 22;
      const chrome =
        parseFloat(styles.paddingTop) +
        parseFloat(styles.paddingBottom) +
        parseFloat(styles.borderTopWidth) +
        parseFloat(styles.borderBottomWidth);
      element.style.height = "auto";
      const wanted = element.scrollHeight + parseFloat(styles.borderTopWidth) + parseFloat(styles.borderBottomWidth);
      const low = minRows * line + chrome;
      const high = maxRows * line + chrome;
      element.style.height = `${Math.max(low, Math.min(high, wanted))}px`;
      element.style.overflowY = wanted > high ? "auto" : "hidden";
    }, [maxRows, minRows]);

    useLayoutEffect(() => {
      fit();
    }, [fit, value]);

    useLayoutEffect(() => {
      const element = inner.current;
      if (!element || typeof ResizeObserver === "undefined") return;
      let width = element.clientWidth;
      const observer = new ResizeObserver(() => {
        if (element.clientWidth !== width) {
          width = element.clientWidth;
          fit();
        }
      });
      observer.observe(element);
      return () => observer.disconnect();
    }, [fit]);

    return (
      <textarea
        ref={inner}
        rows={minRows}
        value={value}
        className={["ui-autotext", className].filter(Boolean).join(" ")}
        style={{ resize: "none", ...style }}
        {...rest}
      />
    );
  },
);
