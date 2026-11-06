import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { nextEpisode, type Series } from "./library/entries";
import { api, type KindProfile, type Settings, type StylePreset } from "./api";
import { Button, ErrorState } from "./ui";
import {
  adjusted,
  clock,
  destinationsFor,
  keepDestinations,
  parseBudget,
  startFrom,
  stillsFor,
  timeline,
  titleFromFile,
  WHOLE_TRACK,
  type Aspect,
  type Choices,
  type Destination,
  type Format,
} from "./newFilm/model";

const MAX_BYTES = 50_000_000;

const TITLES = [
  { id: "joint-v1", label: "25/40 signature", hint: "Your brand kit's opening and closing, landscape only" },
  { id: "title-v1", label: "Short title and end card", hint: "The title over the first picture, a card at the end" },
  { id: "none", label: "None", hint: "Picture from the first frame to the last" },
];

const KIND_HINT: Record<string, string> = {
  music_video: "The song leads, from its first note to its last.",
  promo: "One message, on the song or an excerpt of it.",
  advert: "One audience, one action, a fixed length.",
  narrative: "A narrator leads. It starts from words; music is optional.",
};

type Loaded = {
  kinds: KindProfile[];
  formats: Format[];
  looks: StylePreset[];
  destinations: Destination[];
  structures: NonNullable<Settings["structures"]>;
  defaultTitles: Record<string, string>;
  defaultLook: string;
  defaultKind: string;
  defaultAspect: string;
  reservePerStill: number;
};

function read(settings: Settings): Loaded {
  const start = settings.new_films;
  return {
    kinds: settings.kinds ?? [],
    formats: settings.formats ?? [],
    looks: settings.style_presets ?? [],
    destinations: settings.publish_presets ?? [],
    structures: settings.structures ?? [],
    defaultTitles: settings.default_titles ?? {},
    defaultLook: start.look,
    defaultKind: start.kind,
    defaultAspect: start.aspect,
    reservePerStill: settings.pictures?.reserve_usd_per_still ?? 0,
  };
}

/** The format a new film opens on: the kind and shape Settings prefer, else the first. */
function openingFormat(loaded: Loaded): Format | undefined {
  const ofKind = loaded.formats.filter((item) => item.kind === loaded.defaultKind);
  return (
    ofKind.find((item) => item.aspect === loaded.defaultAspect) ?? ofKind[0] ?? loaded.formats[0]
  );
}

/** A song's length, read in the browser before anything is uploaded. */
function useSongSeconds(file: File | null): number | null {
  const [seconds, setSeconds] = useState<number | null>(null);
  useEffect(() => {
    setSeconds(null);
    if (!file || typeof URL.createObjectURL !== "function") return;
    const url = URL.createObjectURL(file);
    const audio = new Audio();
    audio.preload = "metadata";
    audio.onloadedmetadata = () => {
      if (Number.isFinite(audio.duration)) setSeconds(audio.duration);
    };
    audio.src = url;
    return () => {
      audio.onloadedmetadata = null;
      URL.revokeObjectURL(url);
    };
  }, [file]);
  return seconds;
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
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [formatId, setFormatId] = useState<string | null>(null);
  const [start, setStart] = useState<Choices | null>(null);
  const [choices, setChoices] = useState<Choices | null>(null);
  const [file, setFile] = useState<File | null>(initialFile);
  const [title, setTitle] = useState(initialFile ? titleFromFile(initialFile.name) : "");
  const [mode, setMode] = useState("vocal");
  const [budget, setBudget] = useState("5.00");
  const [message, setMessage] = useState("");
  const [cta, setCta] = useState("");
  const [ctaUrl, setCtaUrl] = useState("");
  const [fictional, setFictional] = useState(false);
  const [seriesList, setSeriesList] = useState<Series[]>([]);
  const [series, setSeries] = useState("");
  const [episode, setEpisode] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const songSeconds = useSongSeconds(file);

  const pick = useCallback((format: Format, from: Loaded) => {
    const profile = from.kinds.find((item) => item.id === format.kind);
    const first = startFrom(format, {
      titles: from.defaultTitles,
      look: from.defaultLook,
      looks: profile?.style_presets,
    });
    setFormatId(format.id);
    setStart(first);
    setChoices(first);
    setError(null);
  }, []);

  const load = useCallback(() => {
    setLoadError(null);
    api
      .settings()
      .then((settings) => {
        const value = read(settings);
        setLoaded(value);
        if (settings.new_films.budget_usd > 0) setBudget(settings.new_films.budget_usd.toFixed(2));
        const opening = openingFormat(value);
        if (opening) pick(opening, value);
      })
      .catch((caught) => setLoadError(String(caught)));
  }, [pick]);

  useEffect(load, [load]);
  useEffect(() => {
    api.library().then((view) => setSeriesList(view.series), () => setSeriesList([]));
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
    if (!title.trim()) setTitle(titleFromFile(picked.name));
  };

  const profile = loaded?.kinds.find((item) => item.id === choices?.kind);
  const format = loaded?.formats.find((item) => item.id === formatId);
  const isStory = choices?.kind === "narrative";
  const isVideo = choices?.kind === "music_video";
  const money = parseBudget(budget);

  const missing = useMemo(() => {
    const out: string[] = [];
    if (!file && !isStory) out.push("an MP3");
    if (!title.trim()) out.push("a title");
    if (!isVideo && !isStory && !message.trim()) out.push("the one message");
    if (choices?.kind === "advert" && !cta.trim()) out.push("a call to action");
    if (money === null) out.push("a budget");
    return out;
  }, [file, isStory, isVideo, title, message, choices?.kind, cta, money]);

  if (loadError) {
    return (
      <div className="new-film">
        <h2>New film</h2>
        <ErrorState what="reading the formats" error={loadError} onRetry={load} />
      </div>
    );
  }
  if (!loaded || !choices || !profile) {
    return (
      <div className="new-film">
        <h2>New film</h2>
        <p className="hint">Reading the formats…</p>
      </div>
    );
  }

  const set = (patch: Partial<Choices>) => setChoices({ ...choices, ...patch });
  const changeShape = (aspect: Aspect) =>
    set({
      aspect,
      // The signature is a landscape package: a portrait film can't have it.
      titles: aspect === "9:16" && choices.titles === "joint-v1" ? "title-v1" : choices.titles,
      destinations: keepDestinations(choices.destinations, aspect, loaded.destinations),
    });
  const changeKind = (kind: string) => {
    const first = loaded.formats.find((item) => item.kind === kind);
    if (first) pick(first, loaded);
  };

  const lengths = [...(profile.allows_full_track ? [WHOLE_TRACK] : []), ...profile.lengths];
  const titleOptions = TITLES.filter((item) => choices.aspect === "16:9" || item.id !== "joint-v1");
  const places = destinationsFor(choices.aspect, loaded.destinations);
  const looks = profile.style_presets
    .map((id) => loaded.looks.find((item) => item.id === id) ?? { id, name: id, description: "" });
  const look = looks.find((item) => item.id === choices.look);
  const storyTemplates = loaded.structures;
  const changed = adjusted(choices, start);
  const structureLabel = isStory
    ? storyTemplates.find((item) => item.id === choices.structure)?.label ?? ""
    : choices.structure ?? "";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (missing.length || busy || money === null) return;
    setBusy(true);
    setError(null);
    const wholeTrack = choices.length === WHOLE_TRACK;
    try {
      const created = await api.createProject(file, {
        title: title.trim(),
        kind: choices.kind,
        aspect: choices.aspect,
        titles: choices.titles,
        structure: choices.structure ?? undefined,
        fictional: isStory ? fictional : undefined,
        music_mode: mode,
        budget: money.toFixed(2),
        style_preset: choices.look,
        message: isVideo || isStory ? undefined : message.trim(),
        cta_text: isVideo || isStory ? undefined : cta.trim(),
        cta_url: isVideo || isStory ? undefined : ctaUrl.trim(),
        length_seconds: wholeTrack ? undefined : choices.length,
        fade_out: wholeTrack ? undefined : 1.5,
        destinations: choices.destinations,
        series: series || undefined,
        episode: series ? episode : undefined,
      });
      onCreated(created.slug, isStory ? "story" : "track");
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  };

  // The format's answers, each a fact the preview shows and a click can change.
  const facts = (
    <dl className="nf-facts">
      <dt>Length</dt>
      <dd>
        {lengths.length > 1 ? (
          <Segmented label="Length">
            {lengths.map((value) => (
              <Option key={value} checked={choices.length === value} onPick={() => set({ length: value })}>
                {value === WHOLE_TRACK ? "Whole song" : clock(value)}
              </Option>
            ))}
          </Segmented>
        ) : (
          <span>The whole song</span>
        )}
      </dd>
      <dt>Shape</dt>
      <dd>
        <Segmented label="Shape">
          {(["16:9", "9:16"] as const).map((value) => (
            <Option key={value} checked={choices.aspect === value} onPick={() => changeShape(value)}>
              <span className={`nf-glyph small ${value === "9:16" ? "tall" : "wide"}`} aria-hidden="true" />
              {value === "16:9" ? "16:9 landscape" : "9:16 portrait"}
            </Option>
          ))}
        </Segmented>
      </dd>
      <dt>{isStory ? "Structure" : "First concept"}</dt>
      <dd>
        <span>{structureLabel || "The Writer proposes three on Story"}</span>
        <small>
          {isStory
            ? "The beats the script fills, scaled to the length. A format is its structure."
            : structureLabel
              ? "Story's first concept uses it; the other two may differ."
              : "Story offers concepts in different structures to choose from."}
        </small>
      </dd>
      <dt>Titles</dt>
      <dd>
        <select aria-label="Titles" value={choices.titles} onChange={(event) => set({ titles: event.target.value })}>
          {titleOptions.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
        <small>{TITLES.find((item) => item.id === choices.titles)?.hint}</small>
      </dd>
      <dt>Look</dt>
      <dd>
        <span className="nf-look-row">
          <span className={`look-swatch nf-swatch preset-${choices.look}`} aria-hidden="true" />
          <select aria-label="Look" value={choices.look} onChange={(event) => set({ look: event.target.value })}>
            {looks.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </span>
        <small>{look?.description ? `${look.description} ` : ""}Change it on Story, beside the cast and places.</small>
      </dd>
      <dt>Goes to</dt>
      <dd>
        <fieldset className="nf-places">
          <legend className="sr-only">Goes to</legend>
          <div className="chips">
            {places.map((item) => (
              <label className="ui-chip" key={item.id}>
                <input
                  type="checkbox"
                  checked={choices.destinations.includes(item.id)}
                  onChange={(event) => {
                    const next = event.target.checked
                      ? [...choices.destinations, item.id]
                      : choices.destinations.filter((id) => id !== item.id);
                    if (next.length) set({ destinations: next });
                  }}
                />{" "}
                {item.label}
              </label>
            ))}
          </div>
          <small>Publish packs a version for each. You can change them there.</small>
        </fieldset>
      </dd>
      {isStory && (
        <>
          <dt>Narrator</dt>
          <dd>
            <span>Settings' voice</span>
            <small>Chosen and heard on Story, where the words are, before any line is recorded.</small>
          </dd>
        </>
      )}
      <dt>Budget</dt>
      <dd>
        {money === null ? "Not set" : `$${money.toFixed(2)}`}
        {stillsFor(money, loaded.reservePerStill) !== null && (
          <small> about {stillsFor(money, loaded.reservePerStill)} stills</small>
        )}
      </dd>
    </dl>
  );

  return (
    <form className="new-film" onSubmit={submit} aria-label="New film">
      <div className="nf-main">
        <header className="nf-head">
          <h2>New film</h2>
          <p>Choose what you're making; the format answers the rest, shown beside it. Everything can still change on Story; nothing is spent until you make pictures.</p>
        </header>
        {error && <ErrorState what="creating the film" error={error} compact />}

        <section className="nf-section" aria-labelledby="nf-kind">
          <h3 id="nf-kind">What are you making?</h3>
          <div className="nf-kinds">
            {loaded.kinds.map((item) => (
              <button
                key={item.id}
                type="button"
                className="nf-kind"
                aria-pressed={choices.kind === item.id}
                onClick={() => changeKind(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <p className="nf-kind-hint">
            {KIND_HINT[choices.kind] ?? profile.purpose}
          </p>
          <div className="nf-formats" role="group" aria-label="Format">
            {loaded.formats
              .filter((item) => item.kind === choices.kind)
              .map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="nf-format"
                  aria-pressed={formatId === item.id}
                  aria-label={`${item.label}, ${item.length ? clock(item.length) : "whole song"}, ${item.aspect}`}
                  onClick={() => pick(item, loaded)}
                >
                  <span className={`nf-glyph ${item.aspect === "9:16" ? "tall" : "wide"}`} aria-hidden="true" />
                  <b>{item.label}</b>
                  <span className="nf-format-facts">
                    {item.length ? clock(item.length) : "Whole song"} · {item.aspect}
                  </span>
                  <span className="nf-format-blurb">{item.blurb}</span>
                </button>
              ))}
          </div>
        </section>

        <section className="nf-section nf-grid" aria-labelledby="nf-brief">
          <h3 id="nf-brief" className="nf-span">The film</h3>
          <label className="nf-field nf-span">
            <span>Title</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder={isStory ? "Name the film" : "Taken from the MP3's name when you add it"}
              maxLength={120}
            />
          </label>
          <label
            className={`nf-drop nf-span ${isStory ? "compact" : ""} ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
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
              aria-label={isStory ? "Music bed MP3" : "Song MP3"}
              onChange={(event) => choose(event.target.files?.[0] || null)}
            />
            {file ? (
              <>
                <strong>{file.name}</strong>
                <span>
                  {songSeconds !== null ? `${clock(songSeconds)} · ` : ""}
                  {(file.size / 1_000_000).toFixed(1)} MB · choose another to replace it
                </span>
              </>
            ) : (
              <>
                <strong>{isStory ? "Add a music bed, optional" : "Drop the song, or choose a file"}</strong>
                <span>
                  {isStory
                    ? "MP3, up to 50 MB. The Sound stage can also make one or take one later."
                    : "MP3, up to 50 MB. It stays on this computer."}
                </span>
              </>
            )}
          </label>
          {!isStory && (
            <Segmented label="Music" className="nf-field">
              <Option checked={mode === "vocal"} onPick={() => setMode("vocal")}>
                Vocals
              </Option>
              <Option checked={mode === "instrumental"} onPick={() => setMode("instrumental")}>
                Instrumental
              </Option>
            </Segmented>
          )}
          {!isVideo && !isStory && (
            <>
              <label className="nf-field nf-span">
                <span>One message</span>
                <input
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  placeholder="The one thing a stranger should repeat"
                  maxLength={400}
                />
              </label>
              <label className="nf-field">
                <span>{choices.kind === "advert" ? "Call to action" : "Ending line (optional)"}</span>
                <input
                  value={cta}
                  onChange={(event) => setCta(event.target.value)}
                  placeholder={choices.kind === "advert" ? "Pre-save now" : "Out Friday"}
                  maxLength={120}
                />
              </label>
              <label className="nf-field">
                <span>Link (optional)</span>
                <input
                  value={ctaUrl}
                  onChange={(event) => setCtaUrl(event.target.value)}
                  placeholder="example.com"
                  maxLength={300}
                />
              </label>
            </>
          )}
          {isStory && (
            <label className="nf-switch nf-span">
              <input type="checkbox" checked={fictional} onChange={(event) => setFictional(event.target.checked)} />
              <span>
                <b>An invented world</b>
                <small>The Writer may invent people and places, and lists everything it invents.</small>
              </span>
            </label>
          )}
          <label className="nf-field">
            <span>Budget</span>
            <span className="nf-money">
              <span aria-hidden="true">$</span>
              <input
                inputMode="decimal"
                aria-label="Budget in dollars"
                value={budget}
                onChange={(event) => setBudget(event.target.value)}
                aria-invalid={money === null}
              />
            </span>
            <small>
              {money === null
                ? "An amount in dollars, like 5.00."
                : "The most this film may spend. You can add to it later."}
            </small>
          </label>
          {seriesList.length > 0 && (
            <label className="nf-field">
              <span>Series</span>
              <select
                value={series}
                onChange={(event) => {
                  const picked = event.target.value;
                  setSeries(picked);
                  setEpisode(nextEpisode(seriesList.find((item) => item.id === picked)));
                }}
              >
                <option value="">Not in a series</option>
                {seriesList.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title}
                  </option>
                ))}
              </select>
              {series && <small>Its recurring cast, places and look join the film from the start.</small>}
            </label>
          )}
          {series && (
            <label className="nf-field">
              <span>Episode</span>
              <input
                type="number"
                min="1"
                step="1"
                value={episode}
                onChange={(event) => setEpisode(Math.max(1, Math.round(Number(event.target.value) || 1)))}
              />
            </label>
          )}
        </section>
      </div>

      <Glance
        title={title}
        choices={choices}
        formatLabel={changed || !format ? "Your own format" : format.label}
        adjustedFrom={changed && format ? format.label : null}
        kindLabel={profile.label}
        bar={timeline(choices, storyTemplates.map((item) => ({ ...item, beats: item.beats ?? [] })), file ? songSeconds : null)}
        hasSong={!!file}
        missing={missing}
        busy={busy}
        onCancel={onCancel}
      >
        {facts}
      </Glance>
    </form>
  );
}

function Segmented({ label, className, children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <div className={className ?? ""} role="radiogroup" aria-label={label}>
      {className && <span>{label}</span>}
      <div className="nf-segmented">{children}</div>
    </div>
  );
}

function Option({ checked, onPick, children }: { checked: boolean; onPick: () => void; children: ReactNode }) {
  return (
    <button type="button" role="radio" aria-checked={checked} onClick={onPick}>
      {children}
    </button>
  );
}

function Glance({
  title,
  choices,
  formatLabel,
  adjustedFrom,
  kindLabel,
  bar,
  hasSong,
  missing,
  busy,
  onCancel,
  children,
}: {
  title: string;
  choices: Choices;
  formatLabel: string;
  adjustedFrom: string | null;
  kindLabel: string;
  bar: ReturnType<typeof timeline>;
  hasSong: boolean;
  missing: string[];
  busy: boolean;
  onCancel: () => void;
  children: ReactNode;
}) {
  const isStory = choices.kind === "narrative";
  const total = bar.segments.reduce((sum, item) => sum + item.seconds, 0) || 1;
  const length = isStory || choices.length ? clock(choices.length) : bar.total ? clock(bar.total) : "Whole song";
  return (
    <aside className="nf-glance" aria-label="At a glance">
      <div className={`nf-frame ${choices.aspect === "9:16" ? "tall" : "wide"}`}>
        <div className={`look-swatch nf-frame-picture preset-${choices.look}`}>
          {choices.titles !== "none" ? (
            <b>{title.trim() || "Your title"}</b>
          ) : (
            <span>No title card</span>
          )}
        </div>
      </div>
      <p className="nf-glance-name">
        <b>{formatLabel}</b>
        <span>
          {kindLabel} · {length} · {choices.aspect}
          {adjustedFrom ? ` · Adjusted from ${adjustedFrom}` : ""}
        </span>
      </p>

      <div className="nf-bar" aria-label={isStory ? "Beats" : "The song"}>
        {bar.segments.map((item, index) => (
          <span
            key={`${item.label}-${index}`}
            className={`nf-seg ${item.tone}`}
            style={{ flexGrow: item.seconds / total }}
            title={`${item.label}, ${clock(item.seconds)}`}
          />
        ))}
      </div>
      <ol className="nf-bar-key">
        {bar.segments
          .filter((item) => item.tone !== "rest")
          .map((item, index) => (
            <li key={`${item.label}-${index}`}>
              {item.label}
              {isStory ? <small> {clock(item.seconds)}</small> : null}
            </li>
          ))}
      </ol>
      {!isStory && (
        <p className="nf-note">
          {!hasSong
            ? "Add the song to see how much of it the film uses."
            : choices.length === WHOLE_TRACK
              ? "Track measures the song when the film is made."
              : "Drag the excerpt along the song on the spine to move it."}
        </p>
      )}

      {children}

      <div className="nf-actions">
        <Button type="submit" variant="primary" disabled={missing.length > 0 || busy}>
          {busy ? "Creating…" : "Create film"}
        </Button>
        <Button variant="quiet" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
      </div>
      <p className="nf-note" role="status">
        {missing.length
          ? `Still needed: ${missing.join(", ")}.`
          : isStory
            ? "Story opens next. Nothing is spent until you record lines or make pictures."
            : "Track opens next and measures the song on this computer, for free."}
      </p>
    </aside>
  );
}
