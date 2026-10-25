import { useEffect, useRef, useState } from "react";

type Toast = { id: number; message: string };

export function ToastTray() {
  const [items, setItems] = useState<Toast[]>([]);
  const next = useRef(1);

  useEffect(() => {
    const onToast = (event: Event) => {
      const message = String((event as CustomEvent<string>).detail || "Something went wrong");
      const id = next.current++;
      setItems((current) => [...current.slice(-2), { id, message }]);
      window.setTimeout(
        () => setItems((current) => current.filter((item) => item.id !== id)),
        7000,
      );
    };
    window.addEventListener("studio-toast", onToast);
    return () => window.removeEventListener("studio-toast", onToast);
  }, []);

  if (!items.length) return null;
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((item) => (
        <div className="toast" key={item.id}>
          <span>{item.message}</span>
          <button
            aria-label="Dismiss notification"
            onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}
