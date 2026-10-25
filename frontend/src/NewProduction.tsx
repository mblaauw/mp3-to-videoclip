import { useEffect, useState, type FormEvent } from "react";
import { api, type KindProfile, type StylePreset } from "./api";

const MAX_BYTES = 25_000_000;

const FALLBACK_KINDS = [
  {
    id: "music_video",
    label: "Music video",
    default_style: "photographic-painted-v2",
    default_length: null,
    allows_full_track: true,
    lengths: [] as number[],
    style_presets: [
      "photographic-painted-v2",
      "clean-photographic-v1",
      "product-studio-v1",
      "brand-graphic-v1",
    ],
  },
  {
    id: "promo",
    label: "Promo",
    default_style: "clean-photographic-v1",
    default_length: 60,
    allows_full_track: true,
    lengths: [30, 60, 90, 120],
    style_presets: ["clean-photographic-v1", "product-studio-v1", "brand-graphic-v1"],
  },
  {
    id: "advert",
    label: "Advert",
    default_style: "clean-photographic-v1",
    default_length: 30,
    allows_full_track: false,
    lengths: [6, 15, 20, 30, 60],
    style_presets: ["clean-photographic-v1", "product-studio-v1", "brand-graphic-v1"],
  },
];

const FALLBACK_PRESETS: StylePreset[] = [
  { id: "photographic-painted-v2", name: "Photographic painted", description: "" },
  { id: "clean-photographic-v1", name: "Clean photographic", description: "" },
  { id: "product-studio-v1", name: "Product studio", description: "" },
  { id: "brand-graphic-v1", name: "Brand graphic", description: "" },
];

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
  const [kind, setKind] = useState("music_video");
  const [stylePreset, setStylePreset] = useState("photographic-painted-v2");
  const [presets, setPresets] = useState<StylePreset[]>([]);
  const [kinds, setKinds] = useState<KindProfile[]>([]);
  const [objective, setObjective] = useState("");
  const [message, setMessage] = useState("");
  const [ctaText, setCtaText] = useState("");
  const [ctaUrl, setCtaUrl] = useState("");
  const [lengthSeconds, setLengthSeconds] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        const value = settings.default_budget_usd;
        if (typeof value === "number" && value > 0) setBudget(value.toFixed(2));
        setPresets(settings.style_presets || []);
        setKinds(settings.kinds || []);
        const initial = (settings.kinds || []).find((item) => item.id === "music_video");
        if (initial) {
          setStylePreset((current) => current || initial.default_style);
          if (initial.default_length) setLengthSeconds(initial.default_length);
        }
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

  const kindOptions = kinds.length ? kinds : FALLBACK_KINDS;
  const presetOptions = presets.length ? presets : FALLBACK_PRESETS;
  const profile = kindOptions.find((item) => item.id === kind) || null;
  const availablePresets = presetOptions.filter(
    (item) => !profile || profile.style_presets.includes(item.id),
  );

  const changeKind = (next: string) => {
    setKind(next);
    const selected = kindOptions.find((item) => item.id === next);
    if (selected) {
      setStylePreset(selected.default_style);
      if (selected.default_length) setLengthSeconds(selected.default_length);
    }
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || !title.trim() || busy) return;
    if (kind !== "music_video" && (!objective.trim() || !message.trim())) {
      setError("Give the promo or advert an objective and a key message.");
      return;
    }
    if (kind === "advert" && !ctaText.trim()) {
      setError("An advert needs a call to action.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await api.createProject(file, {
        title: title.trim(),
        aspect,
        music_mode: mode,
        budget,
        kind,
        style_preset: stylePreset,
        objective,
        message,
        cta_text: ctaText,
        cta_url: ctaUrl,
        length_seconds:
          kind === "music_video" || lengthSeconds === 0 ? undefined : lengthSeconds,
        fade_out: kind === "music_video" ? 0 : 1.5,
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
            Production kind
            <select value={kind} onChange={(e) => changeKind(e.target.value)}>
              {kindOptions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Style preset
            <select value={stylePreset} onChange={(e) => setStylePreset(e.target.value)}>
              {availablePresets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
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

      {kind !== "music_video" && (
        <div className="card">
          <h3>{kind === "advert" ? "Advert brief" : "Promo brief"}</h3>
          <p className="meta">
            These facts become the brief intent. The Writer may not invent claims, prices,
            dates or offers; it can only work with what you supply.
          </p>
          <div className="grid">
            <label>
              Objective
              <textarea
                rows={2}
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="What should this make someone do?"
              />
            </label>
            <label>
              Key message
              <textarea
                rows={2}
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="The one thing a stranger should repeat"
              />
            </label>
            <label>
              Call to action
              <input
                value={ctaText}
                onChange={(e) => setCtaText(e.target.value)}
                placeholder="Pre-save now"
              />
            </label>
            <label>
              CTA URL
              <input
                value={ctaUrl}
                onChange={(e) => setCtaUrl(e.target.value)}
                placeholder="https://example.com"
              />
            </label>
            <label>
              Target length
              {profile && profile.allows_full_track && kind === "promo" ? (
                <select
                  value={lengthSeconds}
                  onChange={(e) => setLengthSeconds(Number(e.target.value))}
                >
                  {profile.lengths.map((value) => (
                    <option key={value} value={value}>
                      {value} s excerpt
                    </option>
                  ))}
                  <option value={0}>Whole track</option>
                </select>
              ) : (
                <select
                  value={lengthSeconds}
                  onChange={(e) => setLengthSeconds(Number(e.target.value))}
                >
                  {(profile?.lengths || [30]).map((value) => (
                    <option key={value} value={value}>
                      {value} s
                    </option>
                  ))}
                </select>
              )}
            </label>
          </div>
        </div>
      )}

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
