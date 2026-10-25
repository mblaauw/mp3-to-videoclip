import { useEffect, useState } from "react";
import { api, type Brief } from "../api";
import { ApprovalBar } from "../ApprovalBar";
import { IntakeCard } from "../IntakeCard";

export function StoryStage({ slug }: { slug: string }) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [direction, setDirection] = useState("");
  const [style, setStyle] = useState("");
  const [treatment, setTreatment] = useState("");
  const [look, setLook] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setBrief(null);
    setDirection("");
    setStyle("");
    setTreatment("");
    setLook("");
    setError(null);
    api
      .brief(slug)
      .then((b) => {
        setBrief(b);
        setDirection(b.direction || "");
        setStyle(b.style || "");
        setTreatment(b.treatment || "");
        setLook(b.creative?.look || "");
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  const intakeSaved = (updated: Brief) => {
    setBrief(updated);
    setDirection(updated.direction || "");
    setStyle(updated.style || "");
    setTreatment(updated.treatment || "");
    setLook(updated.creative?.look || "");
    setRevision((value) => value + 1);
  };

  const save = async () => {
    // Never PATCH the blank initial form while the current brief is still loading.
    if (!brief || saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.patchBrief(slug, {
        direction,
        style,
        treatment,
        creative: { ...(brief.creative || {}), look },
      });
      setBrief(updated);
      setDirection(updated.direction || "");
      setStyle(updated.style || "");
      setTreatment(updated.treatment || "");
      setLook(updated.creative?.look || "");
      setRevision((value) => value + 1);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <h2>Story</h2>
      <p className="sub">Treatment, look and characters. Every write is a versioned artifact.</p>
      {error && <p className="error">{error}</p>}
      {loading && <p className="meta">Loading the current brief…</p>}
      {!loading && !brief && (
        <button onClick={load} type="button">
          Retry loading the brief
        </button>
      )}
      <IntakeCard slug={slug} onSaved={intakeSaved} />
      <ApprovalBar slug={slug} stages={["brief"]} refresh={revision} />
      <div className="card">
        <h3>Direction and style</h3>
        <div className="split">
          <label>
            Direction
            <textarea
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
              rows={3}
              placeholder="What kind of film is this?"
            />
          </label>
          <label>
            Style
            <textarea
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              rows={3}
              placeholder="One honest sentence about the medium"
            />
          </label>
        </div>
      </div>
      <div className="card">
        <h3>Treatment</h3>
        <textarea value={treatment} onChange={(e) => setTreatment(e.target.value)} rows={10} />
      </div>
      <div className="card">
        <h3>Look</h3>
        <textarea value={look} onChange={(e) => setLook(e.target.value)} rows={10} />
      </div>
      <div className="card">
        <h3>Characters</h3>
        {(brief?.characters || []).map((c) => (
          <div key={c.id} className="pre">
            {c.id}: {c.identity || c.description}
          </div>
        ))}
        {!brief?.characters?.length && <p className="empty">No characters.</p>}
      </div>
      <button onClick={save} disabled={!brief || loading || saving}>
        {saving ? "Saving…" : "Save brief"}
      </button>
    </>
  );
}