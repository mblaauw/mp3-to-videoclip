import { useEffect, type RefObject } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function focusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) =>
      !element.hasAttribute("hidden") &&
      element.getAttribute("aria-hidden") !== "true" &&
      element.offsetParent !== null,
  );
}

/**
 * Keep Tab inside a dialog or lightbox and restore the trigger when it closes.
 * The caller owns Escape so it can decide whether closing is safe.
 */
export function useFocusTrap(active: boolean, ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!active) return;
    const container = ref.current;
    if (!container) return;
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const first = focusable(container)[0];
    if (first) first.focus();
    else {
      container.tabIndex = -1;
      container.focus();
    }

    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const items = focusable(container);
      if (!items.length) {
        event.preventDefault();
        return;
      }
      const head = items[0];
      const tail = items[items.length - 1];
      const active = document.activeElement;
      if (!container.contains(active)) {
        event.preventDefault();
        (event.shiftKey ? tail : head).focus();
      } else if (event.shiftKey && active === head) {
        event.preventDefault();
        tail.focus();
      } else if (!event.shiftKey && active === tail) {
        event.preventDefault();
        head.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (previous && previous.isConnected) previous.focus();
    };
  }, [active, ref]);
}

/** Smooth scrolling is motion; respect the system preference. */
export function scrollBehavior(): ScrollBehavior {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
}
