import { useCallback, useEffect, useRef, useState } from "react";
import { api, type TrackData } from "../api";
import { notifyProjectChanged, PROJECT_CHANGED } from "../shell/projectEvents";
import { ErrorState, LoadingState } from "../ui";

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  return `${minutes}:${String(whole % 60).padStart(2, "0")}`;
}

function timeRange(start: number, end: number): string {
  return `${clock(start)}–${clock(end)}`;
}

function energyWord(energy: number | undefined): string {
  const value = Number(energy ?? 0);
  if (value > 0.4) return "loud";
  if (value > 0.2) return "medium";
  return "quiet";
}

function sectionColor(index: number): string {
  return `var(--sec-${(index % 5) + 1})`;
}

function defaultName(index: number): string {
  return `Section ${index + 1}`;
}

function lrcText(segments: { start: number; text: string }[]): string {
  return segments
    .map((segment) => {
      const minutes = Math.floor(segment.start / 60);
      const seconds = segment.start - minutes * 60;
      return `[${String(minutes).padStart(2, "0")}:${seconds.toFixed(2).padStart(5, "0")}]${segment.text}`;
    })
    .join("\n");
}

export function TrackStage({ slug }: { slug: string }) {
  const [data, setData] = useState<TrackData | null>(null);
  const [names, setNames] = useState<string[]>([]);
  const [namesSaving, setNamesSaving] = useState(false);
  const [namesSaved, setNamesSaved] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [lyricsSaving, setLyricsSaving] = useState(false);
  const [modeSaving, setModeSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savedTimer = useRef<number | null>(null);

  const loadEpoch = useRef(0);
  const load = useCallback(async () => {
    const epoch = ++loadEpoch.current;
    try {
      const next = await api.track(slug);
      if (epoch !== loadEpoch.current) return;
      setData(next);
      setNames(
        (next.music?.sections || []).map(
          (section, index) => section.name || defaultName(index),
        ),
      );
      setError(null);
    } catch (caught) {
      if (epoch !== loadEpoch.current) return;
      setError(String(caught));
    }
  }, [slug]);

  useEffect(() => {
    setData(null);
    setNames([]);
    setEditing(false);
    setDraft("");
    void load();
    return () => { loadEpoch.current += 1; };
  }, [load]);

  useEffect(() => {
    const changed = () => void load();
    window.addEventListener(PROJECT_CHANGED, changed);
    return () => window.removeEventListener(PROJECT_CHANGED, changed);
  }, [load]);

  useEffect(() => {
    if (!data || data.music) return;
    let tries = 0;
    const timer = window.setInterval(async () => {
      tries += 1;
      try {
        const next = await api.track(slug);
        setData(next);
        setNames(
          (next.music?.sections || []).map(
            (section, index) => section.name || defaultName(index),
          ),
        );
        if (next.music || tries >= 20) window.clearInterval(timer);
      } catch {
        if (tries >= 20) window.clearInterval(timer);
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [data?.music, slug]);

  useEffect(
    () => () => {
      if (savedTimer.current) window.clearTimeout(savedTimer.current);
    },
    [],
  );

  const flashSaved = () => {
    setNamesSaved(true);
    if (savedTimer.current) window.clearTimeout(savedTimer.current);
    savedTimer.current = window.setTimeout(() => setNamesSaved(false), 2000);
  };

  const analyze = async () => {
    setAnalyzing(true);
    setError(null);
    try {
      await api.analyze(slug);
      await load();
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setAnalyzing(false);
    }
  };

  const saveNames = async () => {
    const sections = data?.music?.sections || [];
    if (!sections.length || namesSaving) return;
    setNamesSaving(true);
    setError(null);
    try {
      const saved = await api.saveMusicNotes(
        slug,
        sections.map((section, index) => ({
          start: Number(section.start),
          name: names[index]?.trim() || defaultName(index),
        })),
      );
      setNames(
        sections.map(
          (section, index) =>
            saved.sections.find(
              (item) => Math.abs(Number(item.start) - Number(section.start)) < 0.0005,
            )?.name || defaultName(index),
        ),
      );
      flashSaved();
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setNamesSaving(false);
    }
  };

  const setMode = async (mode: "vocal" | "instrumental") => {
    if (!data || data.music_mode === mode || modeSaving) return;
    setModeSaving(true);
    setError(null);
    try {
      await api.setMusicMode(slug, mode);
      setData({ ...data, music_mode: mode });
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setModeSaving(false);
    }
  };

  const startEditing = () => {
    const segments = data?.lyrics?.segments || [];
    const lines = data?.lyrics?.lines || [];
    setDraft(lines.length ? lines.join("\n") : lrcText(segments));
    setEditing(true);
  };

  const saveLyrics = async () => {
    if (lyricsSaving || !draft.trim()) return;
    setLyricsSaving(true);
    setError(null);
    try {
      const result = await api.saveLyrics(slug, draft);
      if (result.error) {
        setError(result.error);
        return;
      }
      setEditing(false);
      setDraft("");
      await load();
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setLyricsSaving(false);
    }
  };

  const music = data?.music;
  const sections = music?.sections || [];
  const segments = data?.lyrics?.segments || [];
  const lines = data?.lyrics?.lines || [];
  const hasLyrics = segments.length > 0 || lines.length > 0;
  const instrumental = data?.music_mode === "instrumental";
  const musicVideo = !data || data.kind === "music_video";

  return (
    <>
      <div className="stage-head">
        <h1>Track</h1>
        <p>Listen, name the parts of the song and add the lyrics. Everything here is measured on this computer.</p>
      </div>
      {error && (
        <ErrorState
          what={data ? "saving the track" : "reading the track"}
          error={error}
          compact={!!data}
          onRetry={data ? undefined : () => void load()}
        />
      )}
      {!data && !error && <LoadingState>Reading the song and its sections…</LoadingState>}

      <div className="facts-row">
        <div className="fact">
          <b>{data ? clock(data.duration) : "—"}</b>
          <span>length</span>
        </div>
        <div className="fact">
          <b>{music?.estimated_tempo_bpm ? `about ${Math.round(music.estimated_tempo_bpm)}` : "—"}</b>
          <span>BPM, estimated</span>
        </div>
        <div className="fact">
          <b>{sections.length || "—"}</b>
          <span>sections found</span>
        </div>
        <div className="fact">
          <b>
            <div className="ui-seg track-mode" role="group" aria-label="Music">
              <button
                type="button"
                aria-pressed={!instrumental}
                disabled={!data || modeSaving}
                onClick={() => void setMode("vocal")}
              >
                Vocals
              </button>
              <button
                type="button"
                aria-pressed={instrumental}
                disabled={!data || modeSaving}
                onClick={() => void setMode("instrumental")}
              >
                Instrumental
              </button>
            </div>
          </b>
          <span>{modeSaving ? "saving…" : "music"}</span>
        </div>
      </div>

      {data && (
        <div className="stage-columns">
          <section className="stage-block">
            <h2>
              Sections <small>Name them the way you talk about the song</small>
              {namesSaved && <span className="saved-note">Saved</span>}
            </h2>
            {!sections.length && (
              <div className="empty-block">
                <p>No measured sections yet.</p>
                <button type="button" className="ui-btn ui-btn--primary" onClick={analyze} disabled={analyzing}>
                  {analyzing ? "Measuring…" : "Measure the song"}
                </button>
              </div>
            )}
            {!!sections.length && (
              <>
                <div className="sections">
                  {sections.map((section, index) => (
                    <div className="sec-row" key={`${section.start}-${index}`}>
                      <span className="sw" style={{ background: sectionColor(index) }} />
                      <input
                        value={names[index] ?? defaultName(index)}
                        aria-label={`Name for section ${index + 1}`}
                        maxLength={80}
                        onChange={(event) =>
                          setNames((current) => {
                            const next = [...current];
                            next[index] = event.target.value;
                            return next;
                          })
                        }
                        onBlur={() => void saveNames()}
                      />
                      <span className="t">{timeRange(Number(section.start), Number(section.end))}</span>
                      <span className="e">{energyWord(section.energy)}</span>
                    </div>
                  ))}
                </div>
                <p className="hint">
                  Boundaries are estimates; renaming a section never changes the audio. Drag
                  cuts on the timeline in Storyboard.
                </p>
              </>
            )}
          </section>

          <section className="stage-block">
            <h2>
              Lyrics{" "}
              <small>
                {!musicVideo
                  ? "Not part of this film"
                  : segments.length
                    ? `${segments.length} timed lines`
                    : lines.length
                      ? `${lines.length} lines, no times`
                      : "Not added yet"}
              </small>
            </h2>
            {!musicVideo ? (
              <p className="hint">
                {data?.kind === "advert" ? "An advert" : data?.kind === "promo" ? "A promo" : "A film"}{" "}
                is built from its message and ending, not lyrics. The words stay out of the
                story check.
              </p>
            ) : instrumental ? (
              <p className="hint">
                This track is instrumental. The story works from the music itself; there are
                no words to check.
              </p>
            ) : hasLyrics && !editing ? (
              <>
                <div className={`lyric-lines ${segments.length ? "" : "untimed"}`}>
                  {segments.map((segment, index) => (
                    <div key={`${segment.start}-${index}`}>
                      <time>{clock(segment.start)}</time>
                      <span>{segment.text}</span>
                    </div>
                  ))}
                  {!segments.length &&
                    lines.map((line, index) => (
                      <div key={`${line}-${index}`}>
                        <span>{line}</span>
                      </div>
                    ))}
                </div>
                {!segments.length && (
                  <p className="hint">These lines have no timestamps; none were invented.</p>
                )}
                <div className="row-actions">
                  <button type="button" className="ui-btn ui-btn--small" onClick={startEditing}>
                    Edit lyrics
                  </button>
                </div>
              </>
            ) : (
              <>
                <textarea
                  id="track-lyrics"
                  className="lyrics-input"
                  rows={10}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder={"Paste the words, one line at a time.\nLRC timestamps are welcome."}
                  aria-label="Paste lyrics or LRC"
                />
                <div className="row-actions">
                  <button
                    type="button"
                    className="ui-btn ui-btn--primary ui-btn--small"
                    onClick={() => void saveLyrics()}
                    disabled={!draft.trim() || lyricsSaving}
                  >
                    {lyricsSaving ? "Saving…" : editing ? "Save lyrics" : "Add lyrics"}
                  </button>
                  {editing && (
                    <button
                      type="button"
                      className="ui-btn ui-btn--small ui-btn--quiet"
                      onClick={() => {
                        setEditing(false);
                        setDraft("");
                      }}
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
