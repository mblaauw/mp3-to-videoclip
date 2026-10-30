import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import {
  api,
  type AudioWindow,
  type ImageShot,
  type Music,
  type Storyboard,
} from "../api";
import { toast } from "../toast";
import { notifyProjectChanged } from "../shell/projectEvents";
import { usePlayer } from "./player";
import { Transport } from "./Transport";
import { clock, sectionAt, sectionColor, sectionName, waveformBars } from "./wave";
import { Waveform } from "./Waveform";
import { SECTION_EDGE } from "../track/useTrackData";

const MAX_BARS = 320;

function sourceBars(
  peaks: number[],
  sourceDuration: number,
  music: Music | null,
  window: AudioWindow,
): { value: number; section: number; start: number }[] {
  if (!peaks.length || sourceDuration <= 0) return [];
  const step = Math.max(1, Math.ceil(peaks.length / MAX_BARS));
  const bars = [];
  for (let index = 0; index < peaks.length; index += step) {
    const group = peaks.slice(index, index + step);
    const value = group.reduce((sum, item) => sum + Number(item || 0), 0) / group.length;
    const start = (index / peaks.length) * sourceDuration;
    const inWindow = start >= window.start && start < window.end;
    const local = start - window.start;
    bars.push({
      value: Math.max(0.02, Math.min(1, value)),
      section: inWindow ? sectionAt(music, local) : 0,
      start,
    });
  }
  return bars;
}

export function imageUrl(slug: string, image: ImageShot | undefined): string | null {
  if (!image) return null;
  if (image.plate) return image.plate;
  if (image.selected === null) return null;
  return `/api/projects/${slug}/images/${encodeURIComponent(image.owner)}/${image.selected}`;
}

export function Spine({
  slug,
  stage,
  board,
  music,
  images,
  audioWindow = null,
  sourcePeaks = [],
  sourceDuration = 0,
  windowBusy = false,
  windowLocked = false,
  onAudioWindow,
  onAudioWindowCommit,
  onBoardChange,
  readOnly = false,
  bands = [],
}: {
  slug: string;
  stage: string;
  board: Storyboard | null;
  music: Music | null;
  images: ImageShot[];
  audioWindow?: AudioWindow | null;
  sourcePeaks?: number[];
  sourceDuration?: number;
  windowBusy?: boolean;
  windowLocked?: boolean;
  onAudioWindow?: (window: AudioWindow) => void;
  onAudioWindowCommit?: (window: AudioWindow) => Promise<boolean>;
  onBoardChange?: (board: Storyboard) => void;
  readOnly?: boolean;
  /** The story's placed passages, drawn on the song while on Story. */
  bands?: { start: number; end: number }[];
}) {
  const player = usePlayer();
  const canvasRef = useRef<HTMLDivElement>(null);
  const busy = useRef(false);
  const [drag, setDrag] = useState<{ index: number; frame: number } | null>(null);
  const [windowDrag, setWindowDrag] = useState<"start" | "end" | null>(null);
  const windowDraft = useRef<AudioWindow | null>(null);
  const windowOrigin = useRef<AudioWindow | null>(null);
  const commitTimer = useRef<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [hover, setHover] = useState<{ x: number; time: number } | null>(null);
  const scrubbing = useRef(false);
  const excerptMode =
    stage === "story" &&
    !!audioWindow &&
    sourceDuration > 0 &&
    sourcePeaks.length > 0 &&
    !!onAudioWindow &&
    !!onAudioWindowCommit;
  const windowEditable = excerptMode && !windowLocked;
  const timelineDuration = excerptMode
    ? sourceDuration
    : player.duration || (board ? board.total_frames / (board.fps || 24) : 0) || 1;
  const bars = useMemo(
    () =>
      excerptMode && audioWindow
        ? sourceBars(sourcePeaks, sourceDuration, music, audioWindow)
        : waveformBars(music, timelineDuration),
    [audioWindow, excerptMode, music, sourceDuration, sourcePeaks, timelineDuration],
  );
  const [edgeDrag, setEdgeDrag] = useState<{ index: number; time: number } | null>(null);
  const edgeGrab = useRef<number | null>(null);
  const sections = useMemo(() => {
    const list = music?.sections ?? [];
    if (!edgeDrag) return list;
    return list.map((section, index) =>
      index === edgeDrag.index
        ? { ...section, start: edgeDrag.time }
        : index === edgeDrag.index - 1
          ? { ...section, end: edgeDrag.time }
          : section,
    );
  }, [edgeDrag, music?.sections]);
  const edgesEditable = stage === "track" && !excerptMode;
  const total = board?.total_frames ?? 0;
  const cutStage = stage === "storyboard" && !!board && !readOnly;
  const windowLength = audioWindow ? Math.max(0, audioWindow.end - audioWindow.start) : 0;

  useEffect(
    () => () => {
      if (commitTimer.current) window.clearTimeout(commitTimer.current);
    },
    [],
  );

  const scheduleWindowCommit = (next: AudioWindow) => {
    if (!onAudioWindowCommit) return;
    if (commitTimer.current) window.clearTimeout(commitTimer.current);
    commitTimer.current = window.setTimeout(() => {
      commitTimer.current = null;
      windowDraft.current = null;
      void onAudioWindowCommit(next);
    }, 500);
  };

  const limits = (index: number) => {
    if (!board) return { low: 0, high: total };
    const left = board.shots[index];
    const right = board.shots[index + 1];
    const rightEnd = right.start_frame + right.duration_frames;
    return {
      low: left.start_frame + Math.max(1, left.dissolve_frames + 1),
      high: rightEnd - Math.max(1, right.dissolve_frames + 1, left.dissolve_frames + 1),
    };
  };

  const frameAt = (clientX: number, index: number) => {
    const box = canvasRef.current?.getBoundingClientRect();
    if (!box || !box.width || !board) return 0;
    // Same basis as the drawing: lane width is the timeline in seconds.
    const seconds = ((clientX - box.left) / box.width) * timelineDuration -
      (excerptMode && audioWindow ? audioWindow.start : 0);
    const raw = Math.round(seconds * (board.fps || 24));
    const { low, high } = limits(index);
    return Math.max(low, Math.min(high, raw));
  };

  const commit = async (index: number, frame: number) => {
    if (!board || readOnly || busy.current) return;
    const left = board.shots[index];
    const right = board.shots[index + 1];
    const boundary = left.start_frame + left.duration_frames;
    if (frame === boundary) return;
    const optimistic: Storyboard = {
      ...board,
      shots: board.shots.map((shot, position) => {
        if (position === index) return { ...shot, duration_frames: frame - shot.start_frame };
        if (position === index + 1) {
          return {
            ...shot,
            start_frame: frame,
            duration_frames: shot.start_frame + shot.duration_frames - frame,
          };
        }
        return shot;
      }),
    };
    busy.current = true;
    setSaving(true);
    onBoardChange?.(optimistic);
    try {
      const updated = await api.patchShots(slug, [
        { id: left.id, duration_frames: frame - left.start_frame },
        {
          id: right.id,
          start_frame: frame,
          duration_frames: right.start_frame + right.duration_frames - frame,
        },
      ], board);
      onBoardChange?.(updated);
      notifyProjectChanged();
    } catch (error) {
      onBoardChange?.(board);
      toast(`Could not move the cut: ${String(error)}`);
    } finally {
      busy.current = false;
      setSaving(false);
    }
  };

  const display = useMemo(() => {
    if (!board) return [];
    const values = board.shots.map((shot) => shot.start_frame);
    values.push(total);
    if (drag) values[drag.index + 1] = drag.frame;
    return values;
  }, [board, drag, total]);

  const sourceTimeAt = (clientX: number): number => {
    const box = canvasRef.current?.getBoundingClientRect();
    if (!box || !box.width) return 0;
    return Math.max(
      0,
      Math.min(sourceDuration, ((clientX - box.left) / box.width) * sourceDuration),
    );
  };

  const dragWindow = (edge: "start" | "end", clientX: number) => {
    if (!audioWindow || !onAudioWindow || !windowEditable) return;
    const at = Math.round(sourceTimeAt(clientX) * 100) / 100;
    if (edge === "start") {
      const start = Math.max(0, Math.min(at, audioWindow.end - 1));
      if (start === audioWindow.start) return;
      const next = { ...audioWindow, start };
      windowDraft.current = next;
      onAudioWindow(next);
      return;
    }
    const end = Math.min(sourceDuration, Math.max(at, audioWindow.start + 1));
    if (end === audioWindow.end) return;
    const next = { ...audioWindow, end };
    windowDraft.current = next;
    onAudioWindow(next);
  };

  const finishWindow = async () => {
    if (!onAudioWindowCommit || !windowDrag) return;
    const value = windowDraft.current || audioWindow;
    setWindowDrag(null);
    windowOrigin.current = null;
    windowDraft.current = null;
    if (value) await onAudioWindowCommit(value);
  };

  const cancelWindow = () => {
    if (windowOrigin.current && onAudioWindow) onAudioWindow(windowOrigin.current);
    windowOrigin.current = null;
    windowDraft.current = null;
    setWindowDrag(null);
  };

  const timeAtPointer = (clientX: number): number => {
    const box = canvasRef.current?.getBoundingClientRect();
    if (!box || !box.width) return 0;
    const ratio = Math.max(0, Math.min(1, (clientX - box.left) / box.width));
    if (excerptMode && audioWindow) {
      const source = ratio * sourceDuration;
      return Math.max(0, Math.min(windowLength, source - audioWindow.start));
    }
    return ratio * timelineDuration;
  };

  const startScrub = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    if (
      event.target instanceof Element &&
      event.target.closest(".spine-cut, .spine-edge, .spine-window-handle, .spine-window")
    ) {
      return;
    }
    scrubbing.current = true;
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Older browsers: scrubbing still works while the pointer stays inside.
    }
    player.seek(timeAtPointer(event.clientX));
  };

  const moveScrub = (event: ReactPointerEvent<HTMLDivElement>) => {
    const box = canvasRef.current?.getBoundingClientRect();
    if (box && box.width) {
      const x = Math.max(0, Math.min(box.width, event.clientX - box.left));
      setHover({ x: (x / box.width) * 100, time: timeAtPointer(event.clientX) });
    }
    if (scrubbing.current) player.seek(timeAtPointer(event.clientX));
  };

  const endScrub = () => {
    scrubbing.current = false;
  };

  const shift = excerptMode && audioWindow ? audioWindow.start : 0;
  const toPercent = (seconds: number) => ((shift + seconds) / timelineDuration) * 100;
  const playheadPosition = toPercent(player.time);
  const displayTime = player.time;
  const shownDuration = excerptMode && audioWindow ? windowLength : timelineDuration;

  // What is under the playhead, in the player's own time.
  const fps = board?.fps || 24;
  const shotAt = (seconds: number) =>
    board?.shots.find(
      (shot) =>
        seconds >= shot.start_frame / fps &&
        seconds < (shot.start_frame + shot.duration_frames) / fps,
    ) || null;
  const nowShot = shotAt(player.time);

  return (
    <footer className="spine" aria-label="Song timeline">
      <Transport
        board={board}
        music={music}
        shownDuration={shownDuration}
        excerptMode={excerptMode}
      />
      <div
        className="spine-track"
        role="slider"
        tabIndex={0}
        aria-label={excerptMode ? "Seek in the song excerpt" : "Seek in the song"}
        aria-valuemin={0}
        aria-valuemax={Math.round(shownDuration)}
        aria-valuenow={Math.round(displayTime)}
        aria-valuetext={`${clock(displayTime)} of ${clock(shownDuration)}${
          nowShot ? `, shot ${nowShot.id}` : ""
        }`}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            player.seekBy((event.key === "ArrowLeft" ? -1 : 1) * (event.shiftKey ? 1 : 5));
          } else if (event.key === "Home") {
            event.preventDefault();
            player.seek(0);
          } else if (event.key === "End") {
            event.preventDefault();
            player.seek(shownDuration);
          }
        }}
      >
        <div
          className={`spine-lane ${scrubbing.current ? "scrubbing" : ""}`}
          ref={canvasRef}
          onPointerDown={startScrub}
          onPointerMove={moveScrub}
          onPointerUp={endScrub}
          onPointerCancel={endScrub}
          onPointerLeave={() => setHover(null)}
        >
        <div className="spine-sections">
          {sections.map((section, index) => {
            if (excerptMode && audioWindow) {
              const start = audioWindow.start + Number(section.start);
              const end = audioWindow.start + Number(section.end);
              if (end <= audioWindow.start || start >= audioWindow.end) return null;
              return (
                <span
                  key={`${section.start}-${index}`}
                  style={{
                    left: `${(start / timelineDuration) * 100}%`,
                    width: `${((end - start) / timelineDuration) * 100}%`,
                    borderColor: sectionColor(index),
                  }}
                >
                  {end - start > 6 ? sectionName(section, index) : ""}
                </span>
              );
            }
            const start = Number(section.start);
            const end = Number(section.end);
            return (
              <span
                key={`${start}-${index}`}
                style={{
                  left: `${(start / timelineDuration) * 100}%`,
                  width: `${((end - start) / timelineDuration) * 100}%`,
                  borderColor: sectionColor(index),
                }}
              >
                {end - start > 6 ? sectionName(section, index) : ""}
              </span>
            );
          })}
        </div>
        <Waveform
          bars={bars}
          sections={sections}
          duration={timelineDuration}
          shift={shift}
          clip={excerptMode ? audioWindow : null}
        />
        {!bars.length && (
          <p className="spine-empty">
            {music
              ? "The waveform is empty."
              : excerptMode
                ? "The source waveform is empty."
                : "Run analysis in Track to draw the waveform."}
          </p>
        )}
        {excerptMode && audioWindow && (
          <div
            className="spine-window"
            style={{
              left: `${(audioWindow.start / timelineDuration) * 100}%`,
              width: `${((audioWindow.end - audioWindow.start) / timelineDuration) * 100}%`,
            }}
            aria-hidden="true"
          >
            <span
              className="spine-fade in"
              style={{ width: `${(audioWindow.fade_in / Math.max(1, windowLength)) * 100}%` }}
            />
            <span
              className="spine-fade out"
              style={{ width: `${(audioWindow.fade_out / Math.max(1, windowLength)) * 100}%` }}
            />
            <span className="spine-window-label">
              Excerpt {windowLength.toFixed(1)} s
            </span>
          </div>
        )}
        {excerptMode && audioWindow && onAudioWindow && windowEditable && (
          <>
            <button
              type="button"
              className={`spine-window-handle start ${windowDrag === "start" ? "dragging" : ""}`}
              style={{ left: `${(audioWindow.start / timelineDuration) * 100}%` }}
              role="slider"
              aria-label="Excerpt start"
              aria-orientation="horizontal"
              aria-valuemin={0}
              aria-valuemax={Math.max(0, Math.round(audioWindow.end - 1))}
              aria-valuenow={Math.round(audioWindow.start)}
              aria-valuetext={`${audioWindow.start.toFixed(1)} s of the source`}
              disabled={windowBusy}
              onPointerDown={(event) => {
                event.stopPropagation();
                if (commitTimer.current) window.clearTimeout(commitTimer.current);
                windowOrigin.current = audioWindow;
                windowDraft.current = audioWindow;
                setWindowDrag("start");
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerMove={(event) => {
                if (windowDrag !== "start") return;
                event.stopPropagation();
                dragWindow("start", event.clientX);
              }}
              onPointerUp={(event) => {
                event.stopPropagation();
                void finishWindow();
              }}
              onPointerCancel={cancelWindow}
              onKeyDown={(event) => {
                if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
                event.preventDefault();
                event.stopPropagation();
                const step = event.shiftKey ? 1 : 0.25;
                const start = Math.max(
                  0,
                  Math.min(
                    audioWindow.end - 1,
                    Math.round((audioWindow.start + (event.key === "ArrowLeft" ? -step : step)) * 100) / 100,
                  ),
                );
                const next = { ...audioWindow, start };
                onAudioWindow(next);
                scheduleWindowCommit(next);
              }}
            />
            <button
              type="button"
              className={`spine-window-handle end ${windowDrag === "end" ? "dragging" : ""}`}
              style={{ left: `${(audioWindow.end / timelineDuration) * 100}%` }}
              role="slider"
              aria-label="Excerpt end"
              aria-orientation="horizontal"
              aria-valuemin={Math.round(audioWindow.start + 1)}
              aria-valuemax={Math.round(timelineDuration)}
              aria-valuenow={Math.round(audioWindow.end)}
              aria-valuetext={`${audioWindow.end.toFixed(1)} s of the source`}
              disabled={windowBusy}
              onPointerDown={(event) => {
                event.stopPropagation();
                if (commitTimer.current) window.clearTimeout(commitTimer.current);
                windowOrigin.current = audioWindow;
                windowDraft.current = audioWindow;
                setWindowDrag("end");
                event.currentTarget.setPointerCapture(event.pointerId);
              }}
              onPointerMove={(event) => {
                if (windowDrag !== "end") return;
                event.stopPropagation();
                dragWindow("end", event.clientX);
              }}
              onPointerUp={(event) => {
                event.stopPropagation();
                void finishWindow();
              }}
              onPointerCancel={cancelWindow}
              onKeyDown={(event) => {
                if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
                event.preventDefault();
                event.stopPropagation();
                const step = event.shiftKey ? 1 : 0.25;
                const end = Math.min(
                  timelineDuration,
                  Math.max(
                    audioWindow.start + 1,
                    Math.round((audioWindow.end + (event.key === "ArrowLeft" ? -step : step)) * 100) / 100,
                  ),
                );
                const next = { ...audioWindow, end };
                onAudioWindow(next);
                scheduleWindowCommit(next);
              }}
            />
          </>
        )}
        <div className="spine-strip">
          {board?.shots.map((shot) => {
            const image = images.find((item) => item.id === shot.id || item.owner === shot.id);
            const url = imageUrl(slug, image);
            const status = image?.review?.verdict === "accept"
              ? "keep"
              : image?.review?.verdict === "reject"
                ? "redo"
                : "";
            const fps = board.fps || 24;
            const shift = excerptMode && audioWindow ? audioWindow.start : 0;
            return (
              <button
                type="button"
                key={shot.id}
                className={`spine-cell ${url ? "" : "none"} ${status}`}
                style={{
                  left: `${((shift + shot.start_frame / fps) / timelineDuration) * 100}%`,
                  width: `${(shot.duration_frames / fps / timelineDuration) * 100}%`,
                  backgroundImage: url ? `url(${url})` : undefined,
                }}
                aria-label={`${shot.id}, ${shot.purpose}`}
                onClick={() => {
                  player.seek(shot.start_frame / board.fps);
                  window.dispatchEvent(
                    new CustomEvent("studio:select-shot", { detail: shot.id }),
                  );
                }}
              >
                {status && <span className={`st ${status}`} />}
              </button>
            );
          })}
        </div>
        {display.slice(1, -1).map((position, offset) => {
          if (!cutStage || !board) return null;
          const index = offset;
          const { low, high } = limits(index);
          return (
            <button
              type="button"
              key={`cut-${board.shots[index].id}`}
              className="spine-cut"
              style={{ left: `${toPercent(position / fps)}%` }}
              role="slider"
              aria-label={`Boundary before ${board.shots[index + 1].id}`}
              aria-orientation="horizontal"
              aria-valuemin={low}
              aria-valuemax={high}
              aria-valuenow={position}
              aria-valuetext={`frame ${position} of ${total}`}
              disabled={saving}
              onPointerDown={(event) => {
                if (busy.current) return;
                event.stopPropagation();
                event.currentTarget.setPointerCapture(event.pointerId);
                setDrag({ index, frame: position });
              }}
              onPointerMove={(event) => {
                if (!drag || drag.index !== index) return;
                event.stopPropagation();
                setDrag({ index, frame: frameAt(event.clientX, index) });
              }}
              onPointerUp={(event) => {
                if (!drag || drag.index !== index) return;
                event.stopPropagation();
                const frame = frameAt(event.clientX, index);
                setDrag(null);
                void commit(index, frame);
              }}
              onPointerCancel={() => setDrag(null)}
              onLostPointerCapture={() => setDrag(null)}
              onKeyDown={(event) => {
                if (busy.current) return;
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
                event.stopPropagation();
                const step = event.shiftKey ? 10 : 1;
                const next =
                  event.key === "Home"
                    ? low
                    : event.key === "End"
                      ? high
                      : position + (event.key === "ArrowLeft" ? -step : step);
                void commit(index, Math.max(low, Math.min(high, next)));
              }}
            />
          );
        })}
        {edgesEditable &&
          sections.slice(1).map((section, offset) => {
            const index = offset + 1;
            const at = Number(section.start);
            const previous = Number(sections[index - 1].start);
            const next = index + 1 < sections.length ? Number(sections[index + 1].start) : timelineDuration;
            const finish = (time: number) =>
              window.dispatchEvent(new CustomEvent(SECTION_EDGE, { detail: { index, time } }));
            const edgeTime = (clientX: number) =>
              Math.max(previous + 2, Math.min(next - 2, timeAtPointer(clientX)));
            return (
              <button
                type="button"
                key={`edge-${index}`}
                className={`spine-edge ${edgeDrag?.index === index ? "dragging" : ""}`}
                style={{ left: `${toPercent(at)}%` }}
                role="slider"
                aria-label={`Edge before ${sectionName(section, index)}`}
                aria-orientation="horizontal"
                aria-valuemin={Math.round(previous)}
                aria-valuemax={Math.round(next)}
                aria-valuenow={Math.round(at)}
                aria-valuetext={clock(at)}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  event.currentTarget.setPointerCapture(event.pointerId);
                  edgeGrab.current = index;
                  setEdgeDrag({ index, time: at });
                }}
                onPointerMove={(event) => {
                  if (edgeGrab.current !== index) return;
                  event.stopPropagation();
                  setEdgeDrag({ index, time: edgeTime(event.clientX) });
                }}
                onPointerUp={(event) => {
                  if (edgeGrab.current !== index) return;
                  event.stopPropagation();
                  edgeGrab.current = null;
                  setEdgeDrag(null);
                  const time = edgeTime(event.clientX);
                  // `at` is already the dragged position; compare with where the edge was.
                  if (time !== Number(music?.sections?.[index]?.start)) finish(time);
                }}
                onPointerCancel={() => {
                  edgeGrab.current = null;
                  setEdgeDrag(null);
                }}
                onKeyDown={(event) => {
                  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
                  event.preventDefault();
                  event.stopPropagation();
                  const step = event.shiftKey ? 1 : 0.25;
                  finish(at + (event.key === "ArrowLeft" ? -step : step));
                }}
              />
            );
          })}
        {bands.map((band) => (
          <div
            key={band.start}
            className={`spine-band ${player.time >= band.start && player.time < band.end ? "on" : ""}`}
            style={{
              left: `${toPercent(band.start)}%`,
              width: `${toPercent(band.end) - toPercent(band.start)}%`,
            }}
            aria-hidden="true"
          />
        ))}
        {player.loop && (
          <div
            className="spine-loop"
            style={{
              left: `${Math.max(0, toPercent(player.loop.start))}%`,
              width: `${Math.max(0, toPercent(player.loop.end) - toPercent(player.loop.start))}%`,
            }}
            aria-hidden="true"
          />
        )}
        {hover && (
          <div className="spine-ghost" style={{ left: `${hover.x}%` }} aria-hidden="true">
            <span>
              {clock(hover.time)}
              {shotAt(hover.time) ? ` · ${shotAt(hover.time)?.id}` : ""}
            </span>
          </div>
        )}
        <div
          className="spine-playhead"
          style={{ left: `${Math.min(100, Math.max(0, playheadPosition))}%` }}
        />
        </div>
      </div>
    </footer>
  );
}
