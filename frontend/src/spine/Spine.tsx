import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { api, type ImageShot, type Music, type Storyboard } from "../api";
import { PauseIcon, PlayIcon } from "../ui/icons";
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
  onBoardChange,
  readOnly = false,
}: {
  slug: string;
  stage: string;
  board: Storyboard | null;
  music: Music | null;
  images: ImageShot[];
  onBoardChange?: (board: Storyboard) => void;
  readOnly?: boolean;
}) {
  const player = usePlayer();
  const canvasRef = useRef<HTMLDivElement>(null);
  const busy = useRef(false);
  const [drag, setDrag] = useState<{ index: number; frame: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const duration =
    player.duration || (board ? board.total_frames / (board.fps || 24) : 0) || 1;
  const bars = useMemo(() => waveformBars(music, duration), [music, duration]);
  const sections = music?.sections ?? [];
  const total = board?.total_frames ?? 0;
  const cutStage = stage === "storyboard" && !!board && !readOnly;

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
    const raw = Math.round(((clientX - box.left) / box.width) * total);
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
      ]);
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

  const seekFromPointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.target instanceof Element && event.target.closest(".spine-cut")) return;
    const box = canvasRef.current?.getBoundingClientRect();
    if (!box || !box.width) return;
    player.seek(((event.clientX - box.left) / box.width) * duration);
  };

  return (
    <footer className="spine" aria-label="Song timeline">
      <div className="spine-transport">
        <button
          type="button"
          className="spine-play"
          onClick={player.toggle}
          aria-label={player.playing ? "Pause" : "Play"}
        >
          {player.playing ? <PauseIcon /> : <PlayIcon />}
        </button>
        <div className="spine-time">
          <b>{clock(player.time)}</b> / {clock(duration)}
        </div>
      </div>
      <div
        className="spine-track"
        ref={canvasRef}
        role="slider"
        tabIndex={0}
        aria-label="Seek in the song"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(player.time)}
        onPointerDown={seekFromPointer}
        onKeyDown={(event) => {
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            player.seekBy(event.key === "ArrowLeft" ? -5 : 5);
          }
        }}
      >
        <div className="spine-sections">
          {sections.map((section, index) => {
            const start = Number(section.start);
            const end = Number(section.end);
            return (
              <span
                key={`${start}-${index}`}
                style={{
                  left: `${(start / duration) * 100}%`,
                  width: `${((end - start) / duration) * 100}%`,
                  borderColor: sectionColor(index),
                }}
              >
                {end - start > 6 ? section.label : ""}
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
          {sections.map((section, index) => (
            <rect
              key={`${section.start}-${index}`}
              x={(Number(section.start) / duration) * WAVE_WIDTH}
              y="0"
              width={((Number(section.end) - Number(section.start)) / duration) * WAVE_WIDTH}
              height={WAVE_HEIGHT}
              fill={sectionColor(index)}
              opacity=".14"
            />
          ))}
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
            {music ? "The waveform is empty." : "Run analysis in Track to draw the waveform."}
          </p>
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
            return (
              <button
                type="button"
                key={shot.id}
                className={`spine-cell ${url ? "" : "none"} ${status}`}
                style={{
                  left: `${(shot.start_frame / total) * 100}%`,
                  width: `${(shot.duration_frames / total) * 100}%`,
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
              style={{ left: `${(position / total) * 100}%` }}
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
        <div
          className="spine-playhead"
          style={{ left: `${Math.min(100, (player.time / duration) * 100)}%` }}
        />
      </div>
    </footer>
  );
}
