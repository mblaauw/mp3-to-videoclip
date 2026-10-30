import { useCallback, useEffect, useRef, useState } from "react";
import type { LyricLine } from "../api";
import { api, type LyricTools } from "../api";
import { useApprovals } from "../ApprovalBar";
import { isActive, useProjectJobs } from "../jobs/store";
import { usePlayerControls, usePlayerTime } from "../spine/player";
import { clock } from "../spine/wave";
import {
  applyTap,
  lineAt,
  nextToTap,
  nudge,
  sungCount,
  timedCount,
  undoTap,
} from "./lyricTiming";
import { useLyricTiming } from "./useLyricTiming";
import type { TrackModel } from "./useTrackData";

const REWIND_AFTER_UNDO = 3;
const LEAD_IN = 2;

function lrcText(segments: { start: number; text: string }[]): string {
  return segments
    .map((segment) => {
      const minutes = Math.floor(segment.start / 60);
      const seconds = segment.start - minutes * 60;
      return `[${String(minutes).padStart(2, "0")}:${seconds.toFixed(2).padStart(5, "0")}]${segment.text}`;
    })
    .join("\n");
}

/** The words: the sounding line lights up and stays in view while the song plays. */
function WordRows({
  lines,
  tapping,
  picked,
  onPick,
  onNudge,
}: {
  lines: LyricLine[];
  tapping: boolean;
  picked: number;
  onPick: (index: number) => void;
  onNudge: (index: number, seconds: number) => void;
}) {
  const { playing } = usePlayerControls();
  const time = usePlayerTime(0.1);
  const current = lineAt(lines, time);
  const next = tapping ? nextToTap(lines) : -1;
  const box = useRef<HTMLDivElement>(null);
  const focus = tapping ? next : playing ? current : -1;

  useEffect(() => {
    if (focus < 0) return;
    const row = box.current?.querySelector(`[data-line="${focus}"]`);
    if (!(row instanceof HTMLElement)) return;
    const view = row.closest(".shell-main")?.getBoundingClientRect();
    const rect = row.getBoundingClientRect();
    if (view && (rect.top < view.top + 40 || rect.bottom > view.bottom - 40)) {
      const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      row.scrollIntoView({ block: "center", behavior: calm ? "auto" : "smooth" });
    }
  }, [focus]);

  return (
    <div className="track-words" ref={box}>
      {lines.map((line, index) =>
        line.tag ? (
          <div className="track-tag" key={index}>
            {line.tag}
          </div>
        ) : (
          <div
            key={index}
            data-line={index}
            className={[
              "track-line",
              line.start !== null ? "timed" : "",
              index === current ? "now" : "",
              index === next ? "next" : "",
            ].join(" ")}
            onClick={() => {
              if (line.start !== null && !tapping) onPick(index);
            }}
          >
            <time>{line.start !== null ? clock(line.start) : ""}</time>
            <span>{line.text}</span>
            {index === picked && line.start !== null && !tapping && (
              <span className="track-nudge">
                <button
                  type="button"
                  aria-label={`Move "${line.text}" a quarter second earlier`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onNudge(index, -0.25);
                  }}
                >
                  −¼ s
                </button>
                <button
                  type="button"
                  aria-label={`Move "${line.text}" a quarter second later`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onNudge(index, 0.25);
                  }}
                >
                  +¼ s
                </button>
              </span>
            )}
          </div>
        ),
      )}
    </div>
  );
}

export function LyricsPart({ slug, model }: { slug: string; model: TrackModel }) {
  const { data, lyricsSaving, saveLyrics } = model;
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [tapping, setTapping] = useState(false);
  const [picked, setPicked] = useState(-1);
  const [clearing, setClearing] = useState(false);
  const player = usePlayerControls();
  const { seek, play, pause, setRate, current, rate } = player;
  const segments = data?.lyrics?.segments || [];
  const words = data?.lyrics?.lines || [];
  const hasLyrics = segments.length > 0 || words.length > 0;
  const instrumental = data?.music_mode === "instrumental";
  const musicVideo = !data || data.kind === "music_video";
  const timing = useLyricTiming(slug, data?.lyrics);
  const { lines, change, flush } = timing;
  const sung = sungCount(lines);
  const timed = timedCount(lines);
  const nextLine = nextToTap(lines);
  const storyApproved = useApprovals().states.brief?.state === "approved";
  const [tools, setTools] = useState<LyricTools | null>(null);
  const [askSetup, setAskSetup] = useState(false);
  const timingJobs = useProjectJobs(slug, "lyric_timing");
  const setupJobs = useProjectJobs(slug, "lyric_tools");
  const draftJobs = useProjectJobs(slug, "lyric_draft");
  const draftBusy = draftJobs.some(isActive);
  const [drafted, setDrafted] = useState(false);
  const [embedded, setEmbedded] = useState<string | null>(null);
  const timingBusy = timingJobs.some(isActive);
  const setupBusy = setupJobs.some(isActive);

  useEffect(() => {
    let live = true;
    api.lyricTools(slug).then(
      (value) => {
        if (live) setTools(value);
      },
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [setupBusy, slug]);

  useEffect(() => {
    if (hasLyrics || !data || !musicVideo) return;
    let live = true;
    api.embeddedLyrics(slug).then(
      (value) => {
        if (live) setEmbedded(value.text);
      },
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [data, hasLyrics, musicVideo, slug]);

  // The draft lands in the box, for reading. Only saving makes it the lyrics.
  useEffect(() => {
    if (hasLyrics || draftBusy || !data) return;
    let live = true;
    api.lyricDraft(slug).then(
      (value) => {
        if (!live || !value.lines.length) return;
        setDrafted(true);
        setDraft((current) => current || value.lines.join("\n"));
      },
      () => undefined,
    );
    return () => {
      live = false;
    };
  }, [data, draftBusy, hasLyrics, slug]);

  const draftFromSong = async () => {
    if (tools?.ready) await api.runLyricDraft(slug);
    else setAskSetup(true);
  };

  const timeAutomatically = async () => {
    await flush();
    if (tools?.ready) {
      await api.runLyricTiming(slug);
    } else {
      setAskSetup(true);
    }
  };

  const setUpTools = async () => {
    setAskSetup(false);
    await api.setupLyricTools(slug);
  };

  useEffect(() => {
    setEditing(false);
    setDraft("");
    setTapping(false);
    setPicked(-1);
  }, [slug]);

  const startEditing = () => {
    setDraft(words.length ? words.join("\n") : lrcText(segments));
    setEditing(true);
  };

  const save = async () => {
    await flush();
    if (await saveLyrics(draft)) {
      setEditing(false);
      setDraft("");
      setDrafted(false);
    }
  };

  const stopTapping = useCallback(() => {
    setTapping(false);
    pause();
    setRate(1);
    void flush();
  }, [flush, pause, setRate]);

  const startTapping = () => {
    setPicked(-1);
    const starts = lines.flatMap((line) => (line.start !== null ? [line.start] : []));
    seek(starts.length ? Math.max(0, Math.max(...starts) - LEAD_IN) : 0);
    setTapping(true);
    play();
  };

  const tap = useCallback(() => change(applyTap(lines, current())), [change, current, lines]);

  const undo = useCallback(() => {
    const result = undoTap(lines);
    if (!result) return;
    change(result.lines);
    seek(Math.max(0, result.time - REWIND_AFTER_UNDO));
  }, [change, lines, seek]);

  // While tapping, Space marks a line instead of pausing, so it's taken before the player sees it.
  useEffect(() => {
    if (!tapping) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select")) return;
      if (event.code === "Space") {
        if (target?.closest("button")) return;
        event.preventDefault();
        event.stopPropagation();
        if (!event.repeat) tap();
      } else if (event.key === "Backspace") {
        event.preventDefault();
        undo();
      } else if (event.key === "Escape") {
        stopTapping();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [stopTapping, tap, tapping, undo]);

  return (
    <section className="track-lyrics" aria-label="Lyrics">
      <div className="track-head">
        <h2>Lyrics</h2>
        <small>
          {!musicVideo
            ? "Not part of this film"
            : !hasLyrics
              ? "Not added yet"
              : timed === sung
                ? `${sung} lines, all on the song`
                : timed
                  ? `${timed} of ${sung} lines on the song`
                  : `${sung} lines, no times yet`}
        </small>
        {musicVideo && !instrumental && hasLyrics && !editing && !tapping && (
          <div className="track-actions">
            {tools?.supported && timed < sung && (
              <button
                type="button"
                className={`ui-btn ui-btn--small ${timed === 0 ? "ui-btn--primary" : ""}`}
                onClick={() => void timeAutomatically()}
                disabled={timingBusy || setupBusy}
              >
                {timingBusy
                  ? "Putting the words on…"
                  : setupBusy
                    ? "Setting up…"
                    : "Put the words on the song"}
              </button>
            )}
            <button
              type="button"
              className="ui-btn ui-btn--small"
              onClick={startTapping}
              disabled={timed === sung || timingBusy}
            >
              {timed ? "Carry on tapping" : "Tap the words on"}
            </button>
            {timed > 0 && (
              <button
                type="button"
                className="ui-btn ui-btn--small"
                onBlur={() => setClearing(false)}
                onClick={() => {
                  if (!clearing) {
                    setClearing(true);
                    return;
                  }
                  setClearing(false);
                  change(
                    lines.map((line) =>
                      line.source === "lrc" ? line : { ...line, start: null, end: null, source: null },
                    ),
                  );
                }}
              >
                {clearing ? `Clear all ${timed} times?` : "Clear the times"}
              </button>
            )}
            <button type="button" className="ui-btn ui-btn--small" onClick={startEditing}>
              Edit lyrics
            </button>
          </div>
        )}
      </div>
      {askSetup && musicVideo && !instrumental && tools && (
            <div className="track-setup" role="group" aria-label="Set up the lyric tools">
              <p>
                Putting the words on the song uses free tools on this computer. Setting them up
                downloads about {tools.download_gb} GB once. The song isn't uploaded.
              </p>
              <div className="row-actions">
                <button
                  type="button"
                  className="ui-btn ui-btn--primary ui-btn--small"
                  onClick={() => void setUpTools()}
                >
                  Download and set up
                </button>
                <button
                  type="button"
                  className="ui-btn ui-btn--small ui-btn--quiet"
                  onClick={() => setAskSetup(false)}
                >
                  Not now
                </button>
              </div>
            </div>
          )}
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
          {!!timed && !tapping && lines.some((line) => line.source === "auto") && (
            <p className="hint">
              Estimated from the song: click a line to hear it, and nudge it if
              it's off. Lines they couldn't place stay untimed for you to tap.
            </p>
          )}
          {tapping && (
            <div className="track-tapbar" role="status">
              <button
                type="button"
                className="ui-btn ui-btn--primary"
                onClick={tap}
                disabled={nextLine < 0}
              >
                Space: this line starts now
              </button>
              <button type="button" className="ui-btn ui-btn--small" onClick={undo} disabled={!timed}>
                Undo
              </button>
              <div className="ui-seg" role="group" aria-label="Speed">
                <button type="button" aria-pressed={rate === 1} onClick={() => setRate(1)}>
                  1×
                </button>
                <button type="button" aria-pressed={rate === 0.75} onClick={() => setRate(0.75)}>
                  0.75×
                </button>
              </div>
              <button type="button" className="ui-btn ui-btn--small" onClick={stopTapping}>
                Done
              </button>
              <span className="track-count">
                {timed} of {sung}
              </span>
              <p>{nextLine >= 0 ? lines[nextLine].text : "That's every line. Click one to hear it and nudge it."}</p>
            </div>
          )}
          <WordRows
            lines={lines}
            tapping={tapping}
            picked={picked}
            onPick={(index) => {
              const start = lines[index].start;
              if (start === null) return;
              setPicked(index);
              seek(start);
              play();
            }}
            onNudge={(index, seconds) => {
              const next = nudge(lines, index, seconds);
              change(next);
              const start = next[index].start;
              if (start !== null) seek(start);
            }}
          />
        </>
      ) : (
        <>
          {drafted && !editing && (
            <p className="hint track-drafted">
              Drafted from what the tools heard, not your lyrics. Mistakes are likely, so read it
              against the song before saving.
            </p>
          )}
          <textarea
            id="track-lyrics"
            className="lyrics-input"
            rows={10}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={"Paste the words, one line at a time.\n[Verse] and [Hook] style names become headings, and LRC timestamps are welcome."}
            aria-label="Paste lyrics or LRC"
          />
          {storyApproved && (
            <p className="hint">
              The story is checked against the words, so saving asks you to approve the story,
              storyboard and what follows again. Their text and every picture stay as they are.
            </p>
          )}
          <div className="row-actions">
            <button
              type="button"
              className="ui-btn ui-btn--primary ui-btn--small"
              onClick={() => void save()}
              disabled={!draft.trim() || lyricsSaving}
            >
              {lyricsSaving
                ? "Saving…"
                : storyApproved
                  ? "Save, and approve the story again"
                  : editing
                    ? "Save lyrics"
                    : "Add lyrics"}
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
            {!editing && !draft.trim() && embedded && (
              <button
                type="button"
                className="ui-btn ui-btn--small ui-btn--primary"
                onClick={() => setDraft(embedded)}
              >
                Use the words in this MP3
              </button>
            )}
            {!editing && !draft.trim() && !embedded && tools?.supported && (
              <button
                type="button"
                className="ui-btn ui-btn--small"
                onClick={() => void draftFromSong()}
                disabled={draftBusy || setupBusy}
              >
                {draftBusy ? "Drafting…" : setupBusy ? "Setting up…" : "Draft them from the song"}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
