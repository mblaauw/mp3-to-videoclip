import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";

const MAX_BYTES = 25_000_000;

export function NewProduction({
  onCreated,
  onCancel,
}: {
  onCreated: (slug: string) => void;
  onCancel: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [aspect, setAspect] = useState("16:9");
  const [mode, setMode] = useState("vocal");
  const [budget, setBudget] = useState("5.00");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        const value = settings.default_budget_usd;
        if (typeof value === "number" && value > 0) setBudget(value.toFixed(2));
      })
      .catch(() => {});
  }, []);

  const choose = (picked: File | null) => {
    if (!picked) return;
    if (!picked.name.toLowerCase().endsWith(".mp3")) {
      setError("Choose an MP3 file.");
      return;
    }
    if (picked.size > MAX_BYTES) {
      setError("That MP3 is larger than the 25 MB intake limit.");
      return;
    }
    setError(null);
    setFile(picked);
    if (!title.trim()) {
      setTitle(picked.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim());
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || !title.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createProject(file, {
        title: title.trim(),
        aspect,
        music_mode: mode,
        budget,
      });
      onCreated(created.slug);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="intake" onSubmit={submit}>
      <h2>New production</h2>
      <p className="sub">
        One MP3 becomes a schema-3 film: measured locally, budgeted, then the story is yours.
      </p>
      {error && <p className="error">{error}</p>}

      <div className="card">
        <h3>Source</h3>
        <label
          className={`drop ${dragging ? "dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            choose(e.dataTransfer.files[0] || null);
          }}
        >
          <input
            type="file"
            accept=".mp3,audio/mpeg"
            onChange={(e) => choose(e.target.files?.[0] || null)}
          />
          {file ? (
            <>
              <strong>{file.name}</strong>
              <span className="meta">{(file.size / 1_000_000).toFixed(1)} MB</span>
            </>
          ) : (
            <>
              <strong>Drop an MP3 here or choose a file</strong>
              <span className="meta">MP3 only · up to 25 MB · stays on this machine</span>
            </>
          )}
        </label>
      </div>

      <div className="card">
        <h3>Film</h3>
        <div className="grid">
          <label>
            Title
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Films need a name"
              maxLength={120}
            />
          </label>
          <label>
            Starting budget (USD)
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
            />
          </label>
          <label>
            Frame
            <select value={aspect} onChange={(e) => setAspect(e.target.value)}>
              <option value="16:9">16:9 landscape</option>
              <option value="9:16">9:16 vertical</option>
            </select>
          </label>
          <label>
            Track
            <select value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="vocal">Vocals</option>
              <option value="instrumental">Instrumental</option>
            </select>
          </label>
        </div>
      </div>

      <div className="actions">
        <button type="submit" disabled={!file || !title.trim() || busy}>
          {busy ? "Measuring and creating…" : "Create and analyse"}
        </button>
        <button type="button" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <span className="meta">
          No image generation runs here. Analysis is local and free.
        </span>
      </div>
    </form>
  );
}
