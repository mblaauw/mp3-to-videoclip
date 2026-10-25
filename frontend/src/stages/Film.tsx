import { useEffect, useState } from "react";
import { api, type Budget } from "../api";
import { ApprovalBar } from "../ApprovalBar";

export function FilmStage({ slug }: { slug: string }) {
  const [exports, setExports] = useState<string[]>([]);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    api.exports(slug).then((d) => setExports(d.exports)).catch(() => setExports([]));
    api.budget(slug).then(setBudget).catch(() => setBudget(null));
  };

  useEffect(() => {
    load();
  }, [slug]);

  const render = async (kind: "preview" | "final") => {
    setBusy(kind);
    setError(null);
    try {
      await api.render(slug, kind);
      setTimeout(load, 1500);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <h2>Film</h2>
      <p className="sub">Render the timeline, check the budget and download exports.</p>
      {error && <p className="error">{error}</p>}
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
      <div className="card">
        <h3>Exports</h3>
        {exports.length ? (
          exports.map((e) => (
            <div key={e} className="pre">
              {e}
            </div>
          ))
        ) : (
          <p className="empty">No renders yet.</p>
        )}
      </div>
    </>
  );
}