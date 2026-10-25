import { useEffect, useState } from "react";
import { api, type Brief } from "../api";

export function StoryStage({ slug }: { slug: string }) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [treatment, setTreatment] = useState("");
  const [look, setLook] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .brief(slug)
      .then((b) => {
        setBrief(b);
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
        treatment,
        creative: { ...(brief?.creative || {}), look },
      });
      setBrief(updated);
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