import { useEffect, useState } from "react";
import { api } from "../api";

export function TrackStage({ slug }: { slug: string }) {
  const [data, setData] = useState<{ music: any; lyrics: any } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api
      .track(slug)
      .then(setData)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, [slug]);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.analyze(slug);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const music = data?.music as any;
  return (
    <>
      <h2>Track</h2>
      <p className="sub">Music measurement and lyrics. Local analysis; no upload.</p>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <h3>Analysis</h3>
        {music ? (
          <div className="pre">
            {music.estimated_tempo_bpm ? `~${music.estimated_tempo_bpm} BPM (estimate)` : "No tempo"}
            {"\n"}
            {(music.sections || []).map((s: any) => `${s.start.toFixed(1)}s ${s.label}`).join("\n")}
          </div>
        ) : (
          <p className="empty">No analysis yet.</p>
        )}
        <button onClick={run} disabled={busy}>
          {busy ? "Analyzing…" : "Run analysis"}
        </button>
      </div>
      <div className="card">
        <h3>Lyrics</h3>
        {data?.lyrics ? (
          <div className="pre">{(data.lyrics as any).segments?.length ?? 0} segments</div>
        ) : (
          <p className="empty">Paste lyrics or transcribe (paid).</p>
        )}
      </div>
    </>
  );
}