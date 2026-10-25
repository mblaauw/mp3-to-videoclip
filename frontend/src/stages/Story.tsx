import { useEffect, useState } from "react";
import { api, type Brief } from "../api";
import { ApprovalBar } from "../ApprovalBar";

export function StoryStage({ slug }: { slug: string }) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [direction, setDirection] = useState("");
  const [style, setStyle] = useState("");
  const [treatment, setTreatment] = useState("");
  const [look, setLook] = useState("");
  const [saving, setSaving] = useState(false);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .brief(slug)
      .then((b) => {
        setBrief(b);
        setDirection(b.direction || "");
        setStyle(b.style || "");
        setTreatment(b.treatment || "");
        setLook(b.creative?.look || "");
      })
      .catch((e) => setError(String(e)));
  }, [slug]);

  const save = async () => {
    setSaving(true);
    setError(null);
    try {
      const updated = await api.patchBrief(slug, {
        direction,
        style,
        treatment,
        creative: { ...(brief?.creative || {}), look },
      });
      setBrief(updated);
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
      <button onClick={save} disabled={saving}>
        {saving ? "Saving…" : "Save brief"}
      </button>
    </>
  );
}