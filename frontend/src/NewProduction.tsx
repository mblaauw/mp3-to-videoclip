import { useEffect, useState, type FormEvent } from "react";
import { api, type KindProfile } from "./api";
import { ErrorState } from "./ui";

const MAX_BYTES = 50_000_000;

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
    id: "narrative",
    label: "Story film",
    purpose: "",
    lengths: [60, 90, 120, 180, 300],
    default_length: 120,
    allows_full_track: false,
    structures: [],
    text_density: "",
    signature_required: false,
    style_presets: ["painted-documentary-v1"],
    default_style: "painted-documentary-v1",
  },
  {
    id: "promo",
    label: "Promo",
    purpose: "",
    lengths: [30, 60, 90, 120],
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
    lengths: [6, 15, 20, 30, 60],
    default_length: 30,
    allows_full_track: false,
    structures: [],
    text_density: "",
    signature_required: false,
    style_presets: ["clean-photographic-v1"],
    default_style: "clean-photographic-v1",
  },
];

const TITLES = [
  { id: "joint-v1", label: "25/40 signature" },
  { id: "title-v1", label: "Short title and end card" },
  { id: "none", label: "None" },
];

/** The whole track, as a length choice for kinds that allow it. */
const WHOLE_TRACK = 0;

const KIND_HINT: Record<string, string> = {
  narrative: "A narrator leads. It starts from words; music, if any, sits under the voice.",
  music_video: "The song leads. Look, lyrics and story are decided next.",
  promo: "One message and an ending, on the whole track or an excerpt. Everything else moves to Story.",
  advert: "One message, a call to action and a length. The rest of the brief is on Story.",
};

/** The length a film starts with: the saved one if this kind offers it. */
function startingLength(profile: KindProfile, saved: number): number {
  if (profile.lengths.includes(saved)) return saved;
  if (profile.allows_full_track) return WHOLE_TRACK;
  return profile.default_length || profile.lengths[0] || 30;
}

export function NewProduction({
  onCreated,
  onCancel,
  initialFile = null,
}: {
  onCreated: (slug: string, first?: "track" | "story") => void;
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
  const [aspect, setAspect] = useState<"16:9" | "9:16">("16:9");
  const [structure, setStructure] = useState("five-beat-2m");
  const [structures, setStructures] = useState<{ id: string; label: string }[]>([]);
  const [fictional, setFictional] = useState(false);
  const [titles, setTitles] = useState<string | null>(null);
  const [defaultTitles, setDefaultTitles] = useState<Record<string, string>>({});
  const [mode, setMode] = useState("vocal");
  const [budget, setBudget] = useState("5.00");
  const [message, setMessage] = useState("");
  const [cta, setCta] = useState("");
  const [length, setLength] = useState(WHOLE_TRACK);
  const [look, setLook] = useState<string | undefined>(undefined);
  const [kinds, setKinds] = useState<KindProfile[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        const start = settings.new_films;
        if (start.budget_usd > 0) setBudget(start.budget_usd.toFixed(2));
        const known = settings.kinds || [];
        setDefaultTitles(settings.default_titles || {});
        setStructures(settings.structures || []);
        if (start.aspect === "9:16") setAspect("9:16");
        setKinds(known);
        setLook(start.look || undefined);
        const profile = known.find((item) => item.id === start.kind);
        if (profile) {
          setKind(profile.id);
          setLength(startingLength(profile, start.length_s));
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
      setError("That MP3 is larger than the 50 MB limit.");
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
  // The signature is a landscape package: a portrait film can't have it.
  const titleOptions = TITLES.filter((item) => aspect === "16:9" || item.id !== "joint-v1");
  const wantedTitles = titles ?? defaultTitles[kind] ?? "title-v1";
  const chosenTitles = titleOptions.some((item) => item.id === wantedTitles)
    ? wantedTitles
    : "title-v1";
  const lengthOptions = [
    ...(profile?.allows_full_track ? [WHOLE_TRACK] : []),
    ...(profile?.lengths ?? []),
  ];
  const isVideo = kind === "music_video";
  const isStory = kind === "narrative";
  const wholeTrack = isVideo || length === WHOLE_TRACK;

  const changeKind = (next: string) => {
    setKind(next);
    const nextProfile = options.find((item) => item.id === next);
    // A kind that can use the whole track starts there; an excerpt is a choice.
    setLength(nextProfile ? startingLength(nextProfile, WHOLE_TRACK) : 30);
    setError(null);
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if ((!file && !isStory) || !title.trim() || busy) return;
    if (!isVideo && !isStory && !message.trim()) {
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
        aspect,
        titles: chosenTitles,
        structure: isStory ? structure : undefined,
        fictional: isStory ? fictional : undefined,
        music_mode: mode,
        budget,
        kind,
        // A saved look only applies to a kind that offers it.
        style_preset: look && profile?.style_presets.includes(look) ? look : undefined,
        message: isVideo || isStory ? undefined : message.trim(),
        cta_text: kind === "advert" ? cta.trim() : undefined,
        length_seconds: wholeTrack ? undefined : length,
        fade_out: wholeTrack ? undefined : 1.5,
      });
      onCreated(created.slug, isStory ? "story" : "track");
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
            <strong>
              {isStory ? "Drop a music bed here, if you want one" : "Drop an MP3 here or choose a file"}
            </strong>
            <span className="meta">
              {isStory ? "Optional · " : ""}MP3 only · up to 50 MB · stays on this machine
            </span>
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
        {!isStory && <label>
          Music
          <select value={mode} onChange={(event) => setMode(event.target.value)}>
            <option value="vocal">Vocals</option>
            <option value="instrumental">Instrumental</option>
          </select>
        </label>}
        {!isVideo && !isStory && (
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
                  {value === WHOLE_TRACK ? "Whole track" : `${value} s`}
                </option>
              ))}
            </select>
          </label>
        )}
        {isStory && (
          <>
            <label>
              Structure
              <select value={structure} onChange={(event) => setStructure(event.target.value)}>
                {structures.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="check-line">
              <input
                type="checkbox"
                checked={fictional}
                onChange={(event) => setFictional(event.target.checked)}
              />
              Fictional world: the Writer may invent, and lists everything it invents
            </label>
          </>
        )}
        <label>
          Shape
          <select
            value={aspect}
            onChange={(event) => setAspect(event.target.value as "16:9" | "9:16")}
          >
            <option value="16:9">16:9, landscape</option>
            <option value="9:16">9:16, portrait</option>
          </select>
        </label>
        <label>
          Titles
          <select value={chosenTitles} onChange={(event) => setTitles(event.target.value)}>
            {titleOptions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
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
        <button type="submit" disabled={(!file && !isStory) || !title.trim() || busy}>
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
