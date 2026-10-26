import { useMemo, useRef, useState } from "react";
import { api, type Music, type Storyboard } from "./api";

const MAX_BARS = 320;

/** A relative level envelope: fine windows in dB, or the 1 Hz energy fallback. */
function waveformBars(music: Music | null): number[] {
  const windows = music?.fine_windows ?? [];
  if (windows.length) {
    const step = Math.max(1, Math.ceil(windows.length / MAX_BARS));
    const bars: number[] = [];
    for (let index = 0; index < windows.length; index += step) {
      const group = windows.slice(index, index + step);
      const average =
        group.reduce((sum, window) => sum + Number(window.level_db ?? -60), 0) / group.length;
      bars.push(Math.max(0.02, Math.min(1, (average + 60) / 60)));
    }
    return bars;
  }
  return (music?.energy_curve ?? []).map((point) =>
    Math.max(0.02, Math.min(1, Number(point.energy ?? 0))),
  );
}

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(whole / 60);
  return `${minutes}:${String(whole % 60).padStart(2, "0")}`;
}

export function Timeline({
  slug,
  board,
  music,
  readOnly = false,
  onChange,
  onError,
}: {
  slug: string;
  board: Storyboard;
  music: Music | null;
  readOnly?: boolean;
  onChange: (board: Storyboard) => void;
  onError: (message: string) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const busy = useRef(false);
  const [drag, setDrag] = useState<{ index: number; frame: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const bars = useMemo(() => waveformBars(music), [music]);
  const total = board.total_frames;
  const seconds = total / board.fps;

  const limits = (index: number) => {
    const left = board.shots[index];
    const right = board.shots[index + 1];
    const rightEnd = right.start_frame + right.duration_frames;
    return {
      low: left.start_frame + Math.max(1, left.dissolve_frames + 1),
      high: rightEnd - Math.max(1, right.dissolve_frames + 1, left.dissolve_frames + 1),
    };
  };

  const frameAt = (clientX: number, index: number) => {
    const box = track.current?.getBoundingClientRect();
    const boundary = board.shots[index].start_frame + board.shots[index].duration_frames;
    if (!box || !box.width) return boundary;
    const raw = Math.round(((clientX - box.left) / box.width) * total);
    const { low, high } = limits(index);
    return Math.max(low, Math.min(high, raw));
  };

  const commit = async (index: number, frame: number) => {
    if (readOnly) return;
    const left = board.shots[index];
    const right = board.shots[index + 1];
    const boundary = left.start_frame + left.duration_frames;
    if (busy.current || frame === boundary) return;
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
    onChange(optimistic);
    setSaving(true);
    try {
      onChange(
        await api.patchShots(slug, [
          { id: left.id, duration_frames: frame - left.start_frame },
          {
            id: right.id,
            start_frame: frame,
            duration_frames: right.start_frame + right.duration_frames - frame,
          },
        ]),
      );
    } catch (error) {
      onChange(board);
      onError(String(error));
    } finally {
      busy.current = false;
      setSaving(false);
    }
  };

  const display = useMemo(() => {
    const values = board.shots.map((shot) => shot.start_frame);
    values.push(total);
    if (drag) values[drag.index + 1] = drag.frame;
    return values;
  }, [board, drag, total]);

  if (!board.shots.length) return null;

  return (
    <div className="timeline" ref={track}>
      <div className="waveform" aria-hidden="true">
        {bars.length ? (
          bars.map((height, index) => (
            <span key={index} style={{ height: `${(height * 100).toFixed(2)}%` }} />
          ))
        ) : (
          <p className="empty">Run analysis in Track to draw the waveform.</p>
        )}
      </div>
      <div className="shot-band">
        {board.shots.map((shot, index) => (
          <div
            key={shot.id}
            className="shot-block"
            style={{
              left: `${(display[index] / total) * 100}%`,
              width: `${((display[index + 1] - display[index]) / total) * 100}%`,
            }}
          >
            <span>{shot.id}</span>
          </div>
        ))}
        {board.shots.slice(1).map((shot, offset) => {
          const index = offset;
          const position = display[index + 1];
          const { low, high } = limits(index);
          return (
            <button
              key={shot.id}
              className="boundary"
              style={{ left: `${(position / total) * 100}%` }}
              role="slider"
              aria-label={`Boundary before ${shot.id}`}
              aria-orientation="horizontal"
              aria-valuemin={low}
              aria-valuemax={high}
              aria-valuenow={position}
              aria-valuetext={`frame ${position} of ${total}`}
              disabled={saving || readOnly}
              onPointerDown={(event) => {
                if (busy.current || readOnly) return;
                event.currentTarget.setPointerCapture(event.pointerId);
                setDrag({ index, frame: position });
              }}
              onPointerMove={(event) => {
                if (!drag || drag.index !== index) return;
                setDrag({ index, frame: frameAt(event.clientX, index) });
              }}
              onPointerUp={(event) => {
                if (!drag || drag.index !== index) return;
                const frame = frameAt(event.clientX, index);
                setDrag(null);
                void commit(index, frame);
              }}
              onPointerCancel={() => setDrag(null)}
              onLostPointerCapture={() => setDrag(null)}
              onKeyDown={(event) => {
                if (busy.current || readOnly) return;
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                event.preventDefault();
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
      </div>
      <div className="timeline-meta">
        <span>{clock(0)}</span>
        <span>
          {board.shots.length} shots · {total} frames · {clock(seconds)}
          {readOnly ? " · edit-owned timing" : ""}
        </span>
        <span>{clock(seconds)}</span>
      </div>
    </div>
  );
}
