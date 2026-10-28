import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import {
  api,
  type AudioWindow,
  type EditPayload,
  type ImageShot,
  type Music,
  type Storyboard,
} from "../api";
import { editBoundaryLimits, moveEditBoundary } from "../film/editTimeline";
import { LoopIcon, NextIcon, PauseIcon, PlayIcon, PrevIcon, VolumeIcon } from "../ui/icons";
import { toast } from "../toast";
import { notifyProjectChanged } from "../shell/projectEvents";
import { usePlayer } from "./player";

const MAX_BARS = 320;
const WAVE_WIDTH = 1000;
const WAVE_HEIGHT = 52;

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  return `${minutes}:${String(whole % 60).padStart(2, "0")}`;
}

function waveformBars(
  music: Music | null,
  duration: number,
): { value: number; section: number; start: number }[] {
  const windows = music?.fine_windows ?? [];
  if (windows.length) {
    const step = Math.max(1, Math.ceil(windows.length / MAX_BARS));
    const bars: { value: number; section: number; start: number }[] = [];
    for (let index = 0; index < windows.length; index += step) {
      const group = windows.slice(index, index + step);
      const average =
        group.reduce((sum, window) => sum + Number(window.level_db ?? -60), 0) / group.length;
      const time = Number(group[0]?.time ?? (index / windows.length) * duration);
      bars.push({
        value: Math.max(0.02, Math.min(1, (average + 60) / 60)),
        section: sectionAt(music, time),
        start: time,
      });
    }
    return bars;
  }
  const points = music?.energy_curve ?? [];
  return points.map((point) => ({
    value: Math.max(0.02, Math.min(1, Number(point.energy ?? 0))),
    section: sectionAt(music, Number(point.time ?? 0)),
    start: Number(point.time ?? 0),
  }));
}

function sectionAt(music: Music | null, time: number): number {
  const sections = music?.sections ?? [];
  const index = sections.findIndex(
    (section) => time >= Number(section.start) && time < Number(section.end),
  );
  return index < 0 ? 0 : index;
}

function sectionColor(index: number): string {
  return `var(--sec-${(index % 5) + 1})`;
}

function sectionName(section: { label?: string; name?: string }, index: number): string {
  return section.name || (section.label && section.label !== "unreviewed" ? section.label : `Section ${index + 1}`);
}

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

function imageUrl(slug: string, image: ImageShot | undefined): string | null {
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
  edit = null,
  onEditChange,
  readOnly = false,
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
  /** The edit owns timing on Film; joins write the whole cut back. */
  edit?: EditPayload | null;
  onEditChange?: (edit: EditPayload) => Promise<boolean>;
  readOnly?: boolean;
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
  const sections = music?.sections ?? [];
  const total = board?.total_frames ?? 0;
  const storyboardCut = stage === "storyboard" && !!board && !readOnly;
  const editCut = stage === "film" && !!board && !!edit && !!onEditChange && !readOnly;
  const cutStage = storyboardCut || editCut;
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
    if (editCut && edit) return editBoundaryLimits(edit, index);
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
    if (editCut && edit && onEditChange) {
      const next = moveEditBoundary(edit, index, frame);
      if (next === edit) return;
      busy.current = true;
      setSaving(true);
      try {
        const saved = await onEditChange(next);
        if (!saved) toast("Could not move the cut.");
      } finally {
        busy.current = false;
        setSaving(false);
      }
      return;
    }
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
      event.target.closest(".spine-cut, .spine-window-handle, .spine-window")
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
  const sectionIndexAt = (seconds: number) =>
    sections.findIndex(
      (section) => seconds >= Number(section.start) && seconds < Number(section.end),
    );
  const nowShot = shotAt(player.time);
  const nowSectionIndex = sectionIndexAt(player.time);
  const nowSection = nowSectionIndex >= 0 ? sections[nowSectionIndex] : null;

  const stops = useMemo(() => {
    if (board?.shots.length) return board.shots.map((shot) => shot.start_frame / (board.fps || 24));
    return (music?.sections ?? []).map((section) => Number(section.start));
  }, [board, music]);

  const jump = (direction: -1 | 1) => {
    const now = player.current();
    if (!stops.length) {
      player.seekBy(direction * 5);
      return;
    }
    if (direction > 0) {
      const next = stops.find((value) => value > now + 0.05);
      if (next !== undefined) player.seek(next);
      return;
    }
    // Back: to the start of this shot, or the previous one when already there.
    const earlier = stops.filter((value) => value < now - 0.75);
    player.seek(earlier.length ? earlier[earlier.length - 1] : 0);
  };

  const cycleLoop = () => {
    const now = player.current();
    const mode = player.loop?.label.startsWith("Shot")
      ? "shot"
      : player.loop?.label.startsWith("Section")
        ? "section"
        : player.loop
          ? "other"
          : "off";
    const shot = shotAt(now);
    const sectionIndex = sectionIndexAt(now);
    if (mode === "off" && shot) {
      player.setLoop({
        start: shot.start_frame / fps,
        end: (shot.start_frame + shot.duration_frames) / fps,
        label: `Shot ${shot.id}`,
      });
      return;
    }
    if ((mode === "off" || mode === "shot") && sectionIndex >= 0) {
      const section = sections[sectionIndex];
      player.setLoop({
        start: Number(section.start),
        end: Number(section.end),
        label: `Section ${sectionName(section, sectionIndex)}`,
      });
      return;
    }
    player.setLoop(null);
  };

  const cycleRate = () => {
    const rates = [1, 0.75, 0.5];
    const index = rates.indexOf(player.rate);
    player.setRate(rates[(index + 1) % rates.length]);
  };

  const keys = useRef({ jump, cycleLoop });
  keys.current = { jump, cycleLoop };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true'], [role='dialog']")) {
        return;
      }
      if (event.key === "," || event.key === ".") {
        event.preventDefault();
        keys.current.jump(event.key === "," ? -1 : 1);
      } else if (event.key === "l" || event.key === "L") {
        event.preventDefault();
        keys.current.cycleLoop();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // A loop that no longer matches the board (a moved cut) is dropped.
  const { loop, setLoop } = player;
  useEffect(() => {
    if (loop && loop.end > shownDuration + 0.5) setLoop(null);
  }, [loop, setLoop, shownDuration]);

  return (
    <footer className="spine" aria-label="Song timeline">
      <div className="spine-transport">
        <div className="spine-buttons">
          <button
            type="button"
            className="spine-btn"
            onClick={() => jump(-1)}
            aria-label={board ? "Previous shot" : "Previous section"}
            title={`${board ? "Previous shot" : "Previous section"} ( , )`}
          >
            <PrevIcon size={16} />
          </button>
          <button
            type="button"
            className="spine-play"
            onClick={player.toggle}
            aria-label={player.playing ? "Pause" : "Play"}
            title={`${player.playing ? "Pause" : "Play"} (Space)`}
          >
            {player.playing ? <PauseIcon /> : <PlayIcon />}
          </button>
          <button
            type="button"
            className="spine-btn"
            onClick={() => jump(1)}
            aria-label={board ? "Next shot" : "Next section"}
            title={`${board ? "Next shot" : "Next section"} ( . )`}
          >
            <NextIcon size={16} />
          </button>
        </div>
        <div className="spine-time">
          <b>{clock(displayTime)}</b> / {clock(shownDuration)}
          {excerptMode && <span className="spine-time-label"> excerpt</span>}
        </div>
        <div className="spine-now" aria-live="off">
          {nowShot ? <b>{nowShot.id}</b> : null}
          {nowSection ? (
            <span>{sectionName(nowSection, nowSectionIndex)}</span>
          ) : !nowShot ? (
            <span>{music ? "—" : "Not measured yet"}</span>
          ) : null}
        </div>
        <div className="spine-tools">
          <button
            type="button"
            className={`spine-chip ${player.loop ? "on" : ""}`}
            onClick={cycleLoop}
            aria-pressed={!!player.loop}
            title="Loop the shot, then the section, then off (L)"
          >
            <LoopIcon size={14} />
            <span>{player.loop ? player.loop.label.split(" ")[0] : "Loop"}</span>
          </button>
          <button
            type="button"
            className="spine-chip"
            onClick={cycleRate}
            title="Playback speed"
            aria-label={`Playback speed ${player.rate}×`}
          >
            {player.rate}×
          </button>
          <button
            type="button"
            className={`spine-chip icon ${player.muted ? "on" : ""}`}
            onClick={player.toggleMute}
            aria-pressed={player.muted}
            aria-label={player.muted ? "Unmute" : "Mute"}
            title={`${player.muted ? "Unmute" : "Mute"} (M)`}
          >
            <VolumeIcon size={14} muted={player.muted || player.volume === 0} />
          </button>
          <input
            className="spine-volume"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={player.muted ? 0 : player.volume}
            onChange={(event) => player.setVolume(Number(event.target.value))}
            aria-label="Volume"
          />
        </div>
      </div>
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
        <svg
          className="spine-wave"
          viewBox={`0 0 ${WAVE_WIDTH} ${WAVE_HEIGHT}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {sections.map((section, index) => {
            const shift = excerptMode && audioWindow ? audioWindow.start : 0;
            const start = shift + Number(section.start);
            const end = shift + Number(section.end);
            if (excerptMode && audioWindow && (end <= audioWindow.start || start >= audioWindow.end)) {
              return null;
            }
            return (
              <rect
                key={`${section.start}-${index}`}
                x={(start / timelineDuration) * WAVE_WIDTH}
                y="0"
                width={((end - start) / timelineDuration) * WAVE_WIDTH}
                height={WAVE_HEIGHT}
                fill={sectionColor(index)}
                opacity=".14"
              />
            );
          })}
          {bars.map((bar, index) => {
            const width = WAVE_WIDTH / Math.max(1, bars.length);
            const height = Math.max(1.5, bar.value * (WAVE_HEIGHT - 6));
            return (
              <rect
                key={`${bar.start}-${index}`}
                x={(index * width).toFixed(2)}
                y={((WAVE_HEIGHT - height) / 2).toFixed(2)}
                width={Math.max(0.6, width - 0.8).toFixed(2)}
                height={height.toFixed(2)}
                fill={sectionColor(bar.section)}
              />
            );
          })}
        </svg>
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
