import { useEffect, useState } from "react";
import { api, type Budget } from "../api";
import { ApprovalBar } from "../ApprovalBar";

type FilmFile = { kind: "previews" | "renders"; name: string };

export function FilmStage({ slug }: { slug: string }) {
  const [previews, setPreviews] = useState<string[]>([]);
  const [exports, setExports] = useState<string[]>([]);
  const [selected, setSelected] = useState<FilmFile | null>(null);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    api
      .exports(slug)
      .then((d) => {
        setPreviews(d.previews);
        setExports(d.exports);
        setSelected((current) => {
          const all = [
            ...d.previews.map((name) => ({ kind: "previews" as const, name })),
            ...d.exports.map((name) => ({ kind: "renders" as const, name })),
          ];
          if (current && all.some((f) => f.kind === current.kind && f.name === current.name)) {
            return current;
          }
          return all[0] || null;
        });
      })
      .catch(() => {
        setPreviews([]);
        setExports([]);
      });
    api
      .budget(slug)
      .then(setBudget)
      .catch(() => setBudget(null));
  };

  useEffect(() => {
    load();
    // A render is a background job; keep watching until its file appears.
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [slug]);

  const render = async (kind: "preview" | "final") => {
    setBusy(kind);
    setError(null);
    setMessage(`${kind === "final" ? "Final" : "Preview"} queued; it appears here when the job finishes.`);
    try {
      await api.render(slug, kind);
      load();
    } catch (e) {
      setError(String(e));
      setMessage(null);
    } finally {
      setBusy(null);
    }
  };

  const src = selected
    ? `/api/projects/${slug}/film/${selected.kind}/${encodeURIComponent(selected.name)}`
    : null;
  const files: FilmFile[] = [
    ...previews.map((name) => ({ kind: "previews" as const, name })),
    ...exports.map((name) => ({ kind: "renders" as const, name })),
  ];

  return (
    <>
      <h2>Film</h2>
      <p className="sub">Watch the render, check the budget and download the export.</p>
      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}

      <div className="card player">
        <h3>Screen</h3>
        {src && selected ? (
          <>
            <video key={src} controls playsInline preload="metadata" src={src} />
            <div className="film-meta">
              <span>
                {selected.kind === "renders" ? "final" : "preview"} · {selected.name}
              </span>
              <a href={src} download={selected.name}>
                download
              </a>
            </div>
          </>
        ) : (
          <p className="empty">No renders yet. A preview is local and free.</p>
        )}
        {files.length > 0 && (
          <div className="files">
            {files.map((file) => (
              <button
                key={`${file.kind}/${file.name}`}
                className={
                  selected?.kind === file.kind && selected?.name === file.name ? "active" : ""
                }
                onClick={() => setSelected(file)}
              >
                {file.kind === "renders" ? "final" : "preview"} ·{" "}
                {file.name.replace(/^.*-v(\d+)\.mp4$/, "v$1")}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Budget</h3>
        <div className="pre">
          cap {budget?.cap_usd ?? "—"} · committed {budget?.committed_usd ?? "—"} · remaining{" "}
          {budget?.remaining_usd ?? "—"}
        </div>
      </div>

      <div className="card">
        <h3>Render</h3>
        <button onClick={() => render("preview")} disabled={busy !== null}>
          {busy === "preview" ? "Queueing…" : "Render preview"}
        </button>{" "}
        <button onClick={() => render("final")} disabled={busy !== null}>
          {busy === "final" ? "Queueing…" : "Render final"}
        </button>
      </div>

      <ApprovalBar slug={slug} stages={["preview", "graphics"]} />
    </>
  );
}
