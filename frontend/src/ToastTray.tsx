import { useEffect, useRef, useState } from "react";
import type { ToastDetail } from "./toast";

type Toast = ToastDetail & { id: number; count: number };

const LIFETIME: Record<ToastDetail["tone"], number> = {
  error: 8000,
  info: 5000,
  done: 4500,
};

export function ToastTray() {
  const [items, setItems] = useState<Toast[]>([]);
  const next = useRef(1);
  const timers = useRef(new Map<number, number>());

  useEffect(() => {
    const schedule = (id: number, tone: ToastDetail["tone"]) => {
      const previous = timers.current.get(id);
      if (previous) window.clearTimeout(previous);
      timers.current.set(
        id,
        window.setTimeout(() => {
          timers.current.delete(id);
          setItems((current) => current.filter((item) => item.id !== id));
        }, LIFETIME[tone]),
      );
    };
    const onToast = (event: Event) => {
      const raw = (event as CustomEvent<ToastDetail | string>).detail;
      const detail: ToastDetail =
        typeof raw === "string" || !raw
          ? { message: String(raw || "Something went wrong"), tone: "error" }
          : { ...raw, message: raw.message || "Something went wrong", tone: raw.tone || "error" };
      setItems((current) => {
        // The same message again (a retried background read, a double click)
        // bumps the existing notice instead of stacking a copy.
        const same = current.find(
          (item) => item.message === detail.message && item.tone === detail.tone,
        );
        if (same) {
          schedule(same.id, same.tone);
          return current.map((item) =>
            item.id === same.id ? { ...item, count: item.count + 1 } : item,
          );
        }
        const id = next.current++;
        schedule(id, detail.tone);
        return [...current.slice(-2), { ...detail, id, count: 1 }];
      });
    };
    window.addEventListener("studio-toast", onToast);
    const live = timers.current;
    return () => {
      window.removeEventListener("studio-toast", onToast);
      for (const timer of live.values()) window.clearTimeout(timer);
      live.clear();
    };
  }, []);

  const dismiss = (id: number) =>
    setItems((current) => current.filter((entry) => entry.id !== id));

  if (!items.length) return null;
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((item) => (
        <div className={`toast ${item.tone}`} key={item.id}>
          <span className="toast-mark" aria-hidden="true" />
          <span className="toast-text">
            {item.message}
            {item.count > 1 && <em> ×{item.count}</em>}
          </span>
          {item.action && (
            <button
              type="button"
              className="toast-action"
              onClick={() => {
                item.action?.run();
                dismiss(item.id);
              }}
            >
              {item.action.label}
            </button>
          )}
          <button
            type="button"
            className="toast-close"
            aria-label="Dismiss notification"
            onClick={() => dismiss(item.id)}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
