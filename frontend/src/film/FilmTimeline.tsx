import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import type { EditPayload, ImageShot, Music, Storyboard } from "../api";
import type { TitleWindow } from "../baseFilm";
import { usePlayerControls } from "../spine/player";
import { Transport } from "../spine/Transport";
import { clock, sectionColor, sectionName, waveformBars } from "../spine/wave";
import { Waveform } from "../spine/Waveform";
import { imageUrl } from "../storyboard/ShotThumb";
import { editBoundaryLimits, moveEditBoundary } from "./editTimeline";
import { joinSelected, type FilmSelection } from "./selection";

/** Past this many pixels a press on a seam is a retime, not a click. */
const DRAG_THRESHOLD = 4;
const KEY_COMMIT_MS = 350;

function windowLabel(window: TitleWindow & { card?: string[] }): string {
  if (window.kind === "intro") return "Opening";
  if (window.kind === "identity") return "Partners";
  if (window.kind === "lockup") return "End";
  if (window.kind === "card" && window.card) {
    const word = window.card[0].split(" ")[0];
    return word[0] + word.slice(1).toLowerCase();
  }
  return "Caption";
}

/**
 * The film as a strip of its own stills, each as wide as the shot lasts, with
 * the song above it and the titles below. A seam is a join: click selects,
 * shift-click adds, dragging retimes.
 */
export function FilmTimeline({
  slug,
  board,
  music,
  images,
  edit,
  windows,
  selection,
  zoom,
  onZoom,
  onSelectJoin,
  onSelectShot,
  onMoveBoundary,
}: {
  slug: string;
  board: Storyboard | null;
  music: Music | null;
  images: ImageShot[];
  edit: EditPayload | null;
  windows: TitleWindow[];
  selection: FilmSelection;
  zoom: number;
  onZoom: (zoom: number) => void;
  onSelectJoin: (id: string, additive: boolean) => void;
  onSelectShot: (id: string) => void;
  onMoveBoundary: (next: EditPayload, label: string) => void;
}) {
  const player = usePlayerControls();
  const lanes = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const playhead = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ index: number; frame: number } | null>(null);
  const press = useRef<{ index: number; x: number; moved: boolean } | null>(null);
  const keyTimer = useRef<number | null>(null);

  const fps = board?.fps || 24;
  const duration = player.duration || (board ? board.total_frames / fps : 0) || 1;
  const total = board?.total_frames || Math.round(duration * fps);
  const bars = useMemo(() => waveformBars(music, duration), [music, duration]);
  const sections = music?.sections ?? [];
  const imageById = useMemo(() => new Map(images.map((image) => [image.id, image])), [images]);
  const ticks = useMemo(() => {
    const step = zoom >= 3 ? 10 : 30;
    const values: number[] = [];
    for (let seconds = 0; seconds < duration; seconds += step) values.push(seconds);
    return values;
  }, [duration, zoom]);

  // The playhead moves every frame, so it is written straight to the element.
  const { clock: time } = player;
  useEffect(() => {
    const follow = () => {
      const now = time.get();
      if (playhead.current) playhead.current.style.left = `${(now / duration) * 100}%`;
      const box = scroller.current;
      if (box && lanes.current && zoom > 1) {
        const x = (now / duration) * lanes.current.clientWidth;
        if (x < box.scrollLeft + 40 || x > box.scrollLeft + box.clientWidth - 80) {
          box.scrollLeft = x - 120;
        }
      }
    };
    follow();
    return time.subscribe(follow);
  }, [time, duration, zoom]);

  useEffect(
    () => () => {
      if (keyTimer.current) window.clearTimeout(keyTimer.current);
    },
    [],
  );

  const frameAt = (clientX: number, index: number) => {
    const box = lanes.current?.getBoundingClientRect();
    if (!box || !box.width || !edit) return 0;
    const raw = Math.round(((clientX - box.left) / box.width) * total);
    const { low, high } = editBoundaryLimits(edit, index);
    return Math.max(low, Math.min(high, raw));
  };

  const commitMove = (index: number, frame: number) => {
    if (!edit) return;
    const next = moveEditBoundary(edit, index, frame);
    if (next !== edit) onMoveBoundary(next, `Moved the cut into ${edit.shots[index + 1].shot_id}`);
  };

  const seamDown = (event: ReactPointerEvent<HTMLButtonElement>, index: number) => {
    event.stopPropagation();
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    press.current = { index, x: event.clientX, moved: false };
  };
  const seamMove = (event: ReactPointerEvent<HTMLButtonElement>, index: number) => {
    const held = press.current;
    if (!held || held.index !== index) return;
    if (!held.moved && Math.abs(event.clientX - held.x) < DRAG_THRESHOLD) return;
    held.moved = true;
    setDrag({ index, frame: frameAt(event.clientX, index) });
  };
  const seamUp = (event: ReactPointerEvent<HTMLButtonElement>, index: number, id: string) => {
    const held = press.current;
    press.current = null;
    if (!held || held.index !== index) return;
    if (held.moved) {
      commitMove(index, frameAt(event.clientX, index));
      setDrag(null);
      return;
    }
    onSelectJoin(id, event.shiftKey || event.metaKey || event.ctrlKey);
    player.seek((board!.shots[index + 1].start_frame - 1) / fps);
  };
  const seamKey = (event: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!edit) return;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    const { low, high } = editBoundaryLimits(edit, index);
    const from = drag?.index === index ? drag.frame : edit.shots[index + 1].start_frame;
    const step = (event.shiftKey ? 10 : 1) * (event.key === "ArrowLeft" ? -1 : 1);
    const frame = Math.max(low, Math.min(high, from + step));
    setDrag({ index, frame });
    if (keyTimer.current) window.clearTimeout(keyTimer.current);
    // Holding an arrow makes one change, not a save per frame.
    keyTimer.current = window.setTimeout(() => {
      commitMove(index, frame);
      setDrag(null);
    }, KEY_COMMIT_MS);
  };

  const scrub = (event: ReactPointerEvent<HTMLDivElement>) => {
    const box = lanes.current?.getBoundingClientRect();
    if (box?.width) player.seek(((event.clientX - box.left) / box.width) * duration);
  };
  const scrubProps = {
    onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => {
      event.currentTarget.setPointerCapture(event.pointerId);
      scrub(event);
    },
    onPointerMove: (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.buttons) scrub(event);
    },
  };

  const shots = useMemo(() => {
    if (!board) return [];
    const starts = board.shots.map((shot) => shot.start_frame);
    if (drag) starts[drag.index + 1] = drag.frame;
    return board.shots.map((shot, index) => ({
      shot,
      start: starts[index],
      end: index + 1 < starts.length ? starts[index + 1] : total,
    }));
  }, [board, drag, total]);

  return (
    <footer className="film-timeline" aria-label="Film timeline">
      <div className="film-line-head">
        <Transport board={board} music={music} shownDuration={duration} />
        <span className="film-line-hint">
          {edit
            ? "Click a seam between two pictures to change the join. Drag it to retime. Shift-click to pick several."
            : "Make a first cut to edit joins here."}
        </span>
        <label className="film-zoom">
          Zoom
          <input
            type="range"
            min={1}
            max={8}
            step={0.25}
            value={zoom}
            onChange={(event) => onZoom(Number(event.target.value))}
          />
        </label>
      </div>
      <div className="film-scroller" ref={scroller}>
        <div className="film-lanes" ref={lanes} style={{ width: `${zoom * 100}%` }}>
          <div className="film-ruler" {...scrubProps}>
            {ticks.map((seconds) => (
              <span key={seconds} style={{ left: `${(seconds / duration) * 100}%` }}>
                {clock(seconds)}
              </span>
            ))}
          </div>
          <div className="film-sections">
            {sections.map((section, index) => {
              const start = Number(section.start);
              const end = Number(section.end);
              return (
                <button
                  type="button"
                  key={`${start}-${index}`}
                  style={{
                    left: `${(start / duration) * 100}%`,
                    width: `${((end - start) / duration) * 100}%`,
                    background: sectionColor(index),
                  }}
                  onClick={() => player.seek(start)}
                >
                  {sectionName(section, index)}
                </button>
              );
            })}
          </div>
          <div className="film-wave" {...scrubProps}>
            <Waveform bars={bars} sections={sections} duration={duration} />
          </div>
          <div className="film-strip">
            {shots.map(({ shot, start, end }) => {
              const url = imageUrl(slug, imageById.get(shot.id));
              const selected = selection?.kind === "shot" && selection.id === shot.id;
              return (
                <button
                  type="button"
                  key={shot.id}
                  className={`film-tile ${selected ? "selected" : ""}`}
                  style={{
                    left: `${(start / total) * 100}%`,
                    width: `${((end - start) / total) * 100}%`,
                    backgroundImage: url ? `url(${url})` : undefined,
                  }}
                  aria-label={`${shot.id}: ${shot.message || shot.purpose}`}
                  title={`${shot.id}, ${((end - start) / fps).toFixed(1)} s`}
                  onClick={() => {
                    onSelectShot(shot.id);
                    player.seek(start / fps);
                  }}
                />
              );
            })}
            {edit &&
              shots.slice(1).map(({ shot, start }, offset) => {
                const styled =
                  edit.shots.find((item) => item.shot_id === shot.id)?.transition_in.type !== "cut";
                return (
                  <button
                    type="button"
                    key={shot.id}
                    className={`film-seam ${styled ? "styled" : ""} ${
                      joinSelected(selection, shot.id) ? "selected" : ""
                    }`}
                    style={{ left: `${(start / total) * 100}%` }}
                    aria-label={`Join into ${shot.id}`}
                    aria-pressed={joinSelected(selection, shot.id)}
                    onPointerDown={(event) => seamDown(event, offset)}
                    onPointerMove={(event) => seamMove(event, offset)}
                    onPointerUp={(event) => seamUp(event, offset, shot.id)}
                    onPointerCancel={() => {
                      press.current = null;
                      setDrag(null);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        event.stopPropagation();
                        onSelectJoin(shot.id, event.shiftKey);
                        player.seek((start - 1) / fps);
                      } else {
                        seamKey(event, offset);
                      }
                    }}
                  />
                );
              })}
          </div>
          {windows.length > 0 && (
            <div className="film-titles-lane">
              {windows.map((window) => (
                <button
                  type="button"
                  key={window.id}
                  style={{
                    left: `${(window.start_frame / total) * 100}%`,
                    width: `${(window.frames / total) * 100}%`,
                  }}
                  title={windowLabel(window)}
                  onClick={() => player.seek((window.start_frame + window.frames / 2) / fps)}
                >
                  {windowLabel(window)}
                </button>
              ))}
            </div>
          )}
          <div className="film-playhead" ref={playhead} aria-hidden="true" />
        </div>
      </div>
    </footer>
  );
}
