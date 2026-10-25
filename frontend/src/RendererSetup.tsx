import { useEffect, useState } from "react";
import { api, type SetupStatus } from "./api";

const LABELS: Record<string, string> = {
  node: "Node.js",
  npm: "npm",
  chrome: "Chrome or Chromium",
  ffmpeg: "FFmpeg",
  ffprobe: "ffprobe",
  frontend: "the built Studio page",
};

/**
 * Shown only when the pinned local renderer is missing. The launcher installs it
 * on a fresh clone; this is the in-app retry and the honest tool report.
 */
export function RendererSetup({ onReady }: { onReady?: (ready: boolean) => void }) {
  const [status, setStatus] = useState<SetupStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    api
      .setup()
      .then((value) => {
        setStatus(value);
        onReady?.(value.renderer);
      })
      .catch((e) => setError(String(e)));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!status || status.renderer) return null;
  const missing = Object.entries(LABELS)
    .filter(([key]) => !status[key as keyof SetupStatus])
    .map(([, label]) => label);

  const install = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.installRenderer();
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card setup">
      <h3>Local renderer</h3>
      <p className="sub">
        The pinned Remotion packages are not installed yet. The Studio can install them
        locally; it never downloads a browser and makes no paid call.
      </p>
      {missing.length > 0 && (
        <ul>
          {missing.map((label) => (
            <li key={label} className="missing">
              {label} is missing.
            </li>
          ))}
        </ul>
      )}
      <button onClick={install} disabled={busy || !status.npm}>
        {busy ? "Installing the renderer…" : "Install local renderer"}
      </button>
      {!status.npm && <p className="meta">Node.js, which includes npm, is required first.</p>}
      {error && <p className="error">{error}</p>}
    </div>
  );
}
