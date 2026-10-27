import { useEffect, useState, type FormEvent } from "react";
import { api, type KindProfile } from "./api";
import { ErrorState } from "./ui";

const MAX_BYTES = 25_000_000;

const FALLBACK_KINDS: KindProfile[] = [
  {
    id: "music_video",
    label: "Music video",
    purpose: "",
    lengths: [],
    default_length: null,
    allows_full_track: true,
    structures: [],
    text_density: "",
    signature_required: true,
    style_presets: ["photographic-painted-v2", "clean-photographic-v1"],
    default_style: "photographic-painted-v2",
  },
  {
    id: "promo",
    label: "Promo",
    purpose: "",
    lengths: [30, 60, 90],
    default_length: 60,
    allows_full_track: true,
    structures: [],
    text_density: "",
    signature_required: false,
    style_presets: ["clean-photographic-v1"],
    default_style: "clean-photographic-v1",
  },
  {
    id: "advert",
    label: "Advert",
    purpose: "",
    lengths: [6, 15, 30, 60],
    default_length: 30,
    allows_full_track: false,
    structures: [],
    text_density: "",
    signature_required: false,
    style_presets: ["clean-photographic-v1"],
    default_style: "clean-photographic-v1",
  },
];

const LENGTHS: Record<string, number[]> = {
  promo: [30, 60, 90],
  advert: [6, 15, 30, 60],
};

const KIND_HINT: Record<string, string> = {
  music_video: "The song leads. Look, lyrics and story are decided next.",
  promo: "One message, a short excerpt and an ending. Everything else moves to Story.",
  advert: "One message, a call to action and a length. The rest of the brief is on Story.",
};

export function NewProduction({
  onCreated,
  onCancel,
  initialFile = null,
}: {
  onCreated: (slug: string) => void;
  onCancel: () => void;
  initialFile?: File | null;
}) {
  const [file, setFile] = useState<File | null>(initialFile);
  const [title, setTitle] = useState(
    initialFile
      ? initialFile.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim()
      : "",
  );
  const [kind, setKind] = useState("music_video");
  const [mode, setMode] = useState("vocal");
  const [budget, setBudget] = useState("5.00");
  const [message, setMessage] = useState("");
  const [cta, setCta] = useState("");
  const [length, setLength] = useState(30);
  const [kinds, setKinds] = useState<KindProfile[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        const value = settings.default_budget_usd;
        if (typeof value === "number" && value > 0) setBudget(value.toFixed(2));
        setKinds(settings.kinds || []);
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

  const options = kinds.length ? kinds : FALLBACK_KINDS;
  const profile = options.find((item) => item.id === kind);
  const allowed = LENGTHS[kind] || [];
  const lengths = allowed.filter(
    (value) => !profile?.lengths?.length || profile.lengths.includes(value),
  );
  const lengthOptions = lengths.length ? lengths : allowed;
  const isVideo = kind === "music_video";

  const changeKind = (next: string) => {
    setKind(next);
    const nextProfile = options.find((item) => item.id === next);
    const nextLengths = LENGTHS[next] || [];
    const preferred = nextProfile?.default_length || nextLengths[0] || 30;
    setLength(nextLengths.includes(preferred) ? preferred : nextLengths[0] || 30);
    setError(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!file || !title.trim() || busy) return;
    if (!isVideo && !message.trim()) {
      setError("Give the promo or advert one message.");
      return;
    }
    if (kind === "advert" && !cta.trim()) {
      setError("An advert needs a call to action.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await api.createProject(file, {
        title: title.trim(),
        aspect: "16:9",
        music_mode: isVideo ? mode : "vocal",
        budget,
        kind,
        message: isVideo ? undefined : message.trim(),
        cta_text: kind === "advert" ? cta.trim() : undefined,
        length_seconds: isVideo ? undefined : length,
        fade_out: isVideo ? undefined : 1.5,
      });
      onCreated(created.slug);
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="intake new-film" onSubmit={submit}>
      <h2>New film</h2>
      <p className="sub">
        Start from a song. It stays on this computer; nothing is spent until you make pictures.
      </p>
      {error && <ErrorState what="creating the film" error={error} compact />}

      <div className="kind-picker" role="group" aria-label="Kind of film">
        {options.map((item) => (
          <button
            key={item.id}
            type="button"
            className="kind-choice"
            aria-pressed={kind === item.id}
            onClick={() => changeKind(item.id)}
          >
            <b>{item.label}</b>
            <span>{KIND_HINT[item.id]}</span>
          </button>
        ))}
      </div>

      <label
        className={`drop ${dragging ? "dragging" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          choose(event.dataTransfer.files?.[0] || null);
        }}
      >
        <input
          type="file"
          accept=".mp3,audio/mpeg"
          onChange={(event) => choose(event.target.files?.[0] || null)}
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

      <div className="new-film-fields">
        <label>
          Title
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Films need a name"
            maxLength={120}
          />
        </label>
        {isVideo && (
          <label>
            Music
            <select value={mode} onChange={(event) => setMode(event.target.value)}>
              <option value="vocal">Vocals</option>
              <option value="instrumental">Instrumental</option>
            </select>
          </label>
        )}
        {!isVideo && (
          <label>
            One message
            <input
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="The one thing a stranger should repeat"
              maxLength={400}
            />
          </label>
        )}
        {!isVideo && (
          <label>
            Length
            <select value={length} onChange={(event) => setLength(Number(event.target.value))}>
              {lengthOptions.map((value) => (
                <option key={value} value={value}>
                  {value} s
                </option>
              ))}
            </select>
          </label>
        )}
        {kind === "advert" && (
          <label>
            Call to action
            <input
              value={cta}
              onChange={(event) => setCta(event.target.value)}
              placeholder="Pre-save now"
              maxLength={120}
            />
          </label>
        )}
        <label>
          Starting budget (USD)
          <input
            type="number"
            min="0.01"
            step="0.01"
            value={budget}
            onChange={(event) => setBudget(event.target.value)}
          />
        </label>
      </div>

      <p className="hint">
        {isVideo
          ? "Look, lyrics and story are decided in Track and Story."
          : "The look preset defaults from the kind and is changed on Story. The rest of the brief is there too."}
      </p>

      <div className="actions">
        <button type="submit" disabled={!file || !title.trim() || busy}>
          {busy ? "Creating…" : "Create film"}
        </button>
        <button type="button" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
        <span className="meta">Analysis is local and free.</span>
      </div>
    </form>
  );
}
