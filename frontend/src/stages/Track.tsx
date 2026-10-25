import { useEffect, useState } from "react";
import { api } from "../api";

type TrackData = {
  music: any;
  lyrics: any;
  music_mode: string | null;
};

function clock(seconds: number): string {
  const whole = Math.floor(seconds);
  const minutes = Math.floor(whole / 60);
  const rest = (seconds - minutes * 60).toFixed(2).padStart(5, "0");
  return `${minutes}:${rest}`;
}

export function TrackStage({ slug }: { slug: string }) {
  const [data, setData] = useState<TrackData | null>(null);
  const [busy, setBusy] = useState(false);
  const [lrc, setLrc] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api
      .track(slug)
      .then(setData)
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, [slug]);

  useEffect(() => {
    if (!slug || data?.music) return;
    let tries = 0;
    const id = setInterval(async () => {
      tries += 1;
      try {
        const next = await api.track(slug);
        setData(next);
        if (next.music || tries >= 20) clearInterval(id);
      } catch {
        if (tries >= 20) clearInterval(id);
      }
    }, 3000);
    return () => clearInterval(id);
  }, [slug, data?.music]);

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

  const saveLyrics = async () => {
    if (!lrc.trim() || saving) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.saveLyrics(slug, lrc);
      if (result.error) {
        setError(result.error);
      } else {
        setLrc("");
        await load();
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  const music = data?.music as any;
  const lyrics = data?.lyrics as any;
  return (
    <>
      <h2>Track</h2>
      <p className="sub">Music measurement and lyrics. Local analysis; no upload.</p>
      {error && <p className="error">{error}</p>}
      <div className="card">
        <h3>Analysis</h3>
        {music ? (
          <div className="pre">
            {music.estimated_tempo_bpm
              ? `~${music.estimated_tempo_bpm} BPM (estimate)`
              : "No tempo measured"}
            {"\n"}
            {(music.sections || [])
              .map((s: any) => `${Number(s.start).toFixed(1)}s ${s.label}`)
              .join("\n")}
          </div>
        ) : (
          <p className="empty">
            No analysis yet. Intake queues one; it appears here when done.
          </p>
        )}
        <button onClick={run} disabled={busy}>
          {busy ? "Analyzing…" : "Run analysis"}
        </button>
      </div>
      <div className="card lyrics">
        <h3>Lyrics</h3>
        {data?.music_mode === "instrumental" ? (
          <p className="empty">Instrumental track — no lyrics stage.</p>
        ) : lyrics?.segments?.length ? (
          <>
            <p className="meta">
              {lyrics.segments.length} timestamped segment
              {lyrics.segments.length === 1 ? "" : "s"}; review before approving the brief.
            </p>
            <div className="pre">
              {lyrics.segments.map((s: any, index: number) => (
                <div key={index}>
                  [{clock(Number(s.start))}] {s.text}
                </div>
              ))}
            </div>
          </>
        ) : (
          <>
            <p className="empty">
              Paste timestamped lyrics (LRC). Positions come from your file — nothing is
              invented.
            </p>
            <textarea
              value={lrc}
              onChange={(e) => setLrc(e.target.value)}
              rows={8}
              placeholder={"[00:12.34] First line\n[00:18.90] Next line"}
            />
            <button onClick={saveLyrics} disabled={saving || !lrc.trim()}>
              {saving ? "Saving…" : "Import LRC"}
            </button>
          </>
        )}
      </div>
    </>
  );
}
