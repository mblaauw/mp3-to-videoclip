import { useEffect, useRef, useState } from "react";
import { usePlayerControls, usePlayerTime } from "../spine/player";
import { clock } from "../spine/wave";
import type { TrackModel } from "./useTrackData";

function lrcText(segments: { start: number; text: string }[]): string {
  return segments
    .map((segment) => {
      const minutes = Math.floor(segment.start / 60);
      const seconds = segment.start - minutes * 60;
      return `[${String(minutes).padStart(2, "0")}:${seconds.toFixed(2).padStart(5, "0")}]${segment.text}`;
    })
    .join("\n");
}

/** Timed lines: the current one lights up and stays in view while the song plays. */
export function TimedLines({ lines }: { lines: { start: number; text: string }[] }) {
  const { seek, play, playing } = usePlayerControls();
  const time = usePlayerTime(0.1);
  const box = useRef<HTMLDivElement>(null);
  let current = -1;
  lines.forEach((line, index) => {
    if (line.start <= time) current = index;
  });

  useEffect(() => {
    if (!playing || current < 0) return;
    const row = box.current?.children[current];
    if (!(row instanceof HTMLElement)) return;
    const view = row.closest(".shell-main")?.getBoundingClientRect();
    const rect = row.getBoundingClientRect();
    if (view && (rect.top < view.top + 40 || rect.bottom > view.bottom - 40)) {
      const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      row.scrollIntoView({ block: "center", behavior: calm ? "auto" : "smooth" });
    }
  }, [current, playing]);

  return (
    <div className="track-words" ref={box}>
      {lines.map((line, index) => (
        <div
          className={`track-line timed ${index === current ? "now" : ""}`}
          key={`${line.start}-${index}`}
          onClick={() => {
            seek(line.start);
            play();
          }}
        >
          <time>{clock(line.start)}</time>
          <span>{line.text}</span>
        </div>
      ))}
    </div>
  );
}

export function LyricsPart({ slug, model }: { slug: string; model: TrackModel }) {
  const { data, lyricsSaving, saveLyrics } = model;
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    setEditing(false);
    setDraft("");
  }, [slug]);

  const segments = data?.lyrics?.segments || [];
  const lines = data?.lyrics?.lines || [];
  const hasLyrics = segments.length > 0 || lines.length > 0;
  const instrumental = data?.music_mode === "instrumental";
  const musicVideo = !data || data.kind === "music_video";

  const startEditing = () => {
    setDraft(lines.length ? lines.join("\n") : lrcText(segments));
    setEditing(true);
  };

  const save = async () => {
    if (await saveLyrics(draft)) {
      setEditing(false);
      setDraft("");
    }
  };

  return (
    <section className="track-lyrics" aria-label="Lyrics">
      <div className="track-head">
        <h2>Lyrics</h2>
        <small>
          {!musicVideo
            ? "Not part of this film"
            : segments.length
              ? `${segments.length} timed lines`
              : lines.length
                ? `${lines.length} lines, no times`
                : "Not added yet"}
        </small>
      </div>
      {!musicVideo ? (
        <p className="hint">
          {data?.kind === "advert" ? "An advert" : data?.kind === "promo" ? "A promo" : "A film"} is
          built from its message and ending, not lyrics. The words stay out of the story check.
        </p>
      ) : instrumental ? (
        <p className="hint">
          This track is instrumental. The story works from the music itself; there are no words to
          check.
        </p>
      ) : hasLyrics && !editing ? (
        <>
          {segments.length ? (
            <TimedLines lines={segments} />
          ) : (
            <div className="track-words untimed">
              {lines.map((line, index) => (
                <div className="track-line" key={`${line}-${index}`}>
                  <time />
                  <span>{line}</span>
                </div>
              ))}
            </div>
          )}
          {!segments.length && <p className="hint">These lines have no timestamps; none were invented.</p>}
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
              onClick={() => void save()}
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
  );
}
