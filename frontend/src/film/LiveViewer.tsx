import {
  Suspense,
  lazy,
  useEffect,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { usePlayerControls, usePlayerTime } from "../spine/player";
import { sampleTitle } from "./titleSamples";
import type { FilmData } from "./useFilmData";

const LivePlayer = lazy(() => import("../LivePlayer"));

/**
 * The largest thing on the screen: the renderer's own composition, following
 * the Studio's clock. `full` hides everything else and leaves a thin scrub line.
 */
export function LiveViewer({
  film,
  full,
  onFull,
  tabs,
  status,
}: {
  film: FilmData;
  full: boolean;
  onFull: (next: boolean) => void;
  /** The view switcher and the last change, sharing this row to keep the picture tall. */
  tabs: ReactNode;
  status: ReactNode;
}) {
  const player = usePlayerControls();
  // A tenth of a second is enough for the "now playing" label; the synced
  // preview reads the exact clock itself.
  const playerTime = usePlayerTime(0.1);
  const [showTitles, setShowTitles] = useState(true);
  const { board, cut, live, liveError, boardById, imageById, samples, samplesOpen, sampleIndex } = film;
  const sample = samplesOpen ? samples[sampleIndex] : undefined;
  const fps = board?.fps || 24;
  const currentCutShot = cut?.shots.find(
    (shot) =>
      playerTime >= shot.start_frame / fps &&
      playerTime < (shot.start_frame + shot.duration_frames) / fps,
  );
  const currentBoardShot = currentCutShot
    ? boardById.get(currentCutShot.shot_id)
    : board?.shots.find(
        (shot) =>
          playerTime >= shot.start_frame / fps &&
          playerTime < (shot.start_frame + shot.duration_frames) / fps,
      );
  const currentPicture = currentBoardShot ? imageById.get(currentBoardShot.id) : undefined;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true'], [role='dialog']")) {
        return;
      }
      if (event.key === "f" || event.key === "F") {
        event.preventDefault();
        onFull(!full);
      } else if (event.key === "Escape" && full) {
        onFull(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full, onFull]);

  const scrub = (event: ReactPointerEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    if (box.width) player.seek(((event.clientX - box.left) / box.width) * player.duration);
  };

  return (
    <section className="film-viewer live-preview" aria-label="Live preview">
      <div className="film-frame">
        {live ? (
          <div
            className="film-picture"
            style={{ "--film-ratio": `${live.width} / ${live.height}`, "--film-w": live.width / live.height } as CSSProperties}
          >
            <Suspense fallback={<p className="empty">Loading the player…</p>}>
              <LivePlayer
                input={{ ...live.input, titles: showTitles ? live.titles : null }}
                audio={null}
                durationInFrames={live.durationInFrames}
                fps={live.fps}
                width={live.width}
                height={live.height}
                clock={player.clock}
                playing={player.playing}
              />
            </Suspense>
            {sample && (
              <figure className="film-sample">
                <img src={sample.url} alt={sampleTitle(sample, live.titles?.windows ?? [])} />
                <figcaption>
                  <b>{sampleTitle(sample, live.titles?.windows ?? [])}</b>
                  <span>
                    {sampleIndex + 1} of {samples.length}
                  </span>
                  <button type="button" disabled={sampleIndex === 0} onClick={() => film.openSample(sampleIndex - 1)}>
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={sampleIndex === samples.length - 1}
                    onClick={() => film.openSample(sampleIndex + 1)}
                  >
                    Next
                  </button>
                  <button type="button" onClick={() => film.setSamplesOpen(false)}>
                    Back to the film
                  </button>
                </figcaption>
              </figure>
            )}
          </div>
        ) : (
          <p className="empty">{liveError ?? "No storyboard yet."}</p>
        )}
      </div>
      {full ? (
        <div
          className="film-fullbar"
          role="slider"
          tabIndex={0}
          aria-label="Seek in the film"
          aria-valuemin={0}
          aria-valuemax={Math.round(player.duration)}
          aria-valuenow={Math.round(playerTime)}
          onPointerDown={scrub}
          onPointerMove={(event) => {
            if (event.buttons) scrub(event);
          }}
        >
          <i style={{ width: `${(playerTime / (player.duration || 1)) * 100}%` }} />
        </div>
      ) : (
        <div className="film-viewer-bar">
          {tabs}
          {live && currentBoardShot && (
              <p className="film-now">
                <b>{currentBoardShot.id}</b> {currentBoardShot.message || currentBoardShot.purpose}
                {currentPicture?.stale && <em> Older prompt</em>}
              </p>
            )}
            {status}
            {live && live.stale > 0 && (
              <span className="hint">
                {live.stale} selected still{live.stale === 1 ? " is" : "s are"} older than the
                storyboard
              </span>
            )}
            {live?.titles ? (
              <label className="live-titles">
                <input
                  type="checkbox"
                  checked={showTitles}
                  onChange={(event) => setShowTitles(event.target.checked)}
                />
                Show titles
              </label>
            ) : (
              live?.titlesNote && <span className="hint">{live.titlesNote}</span>
            )}
            <button type="button" className="film-full-btn" onClick={() => onFull(true)} title="Full view (F)">
              Full view
            </button>
          </div>
      )}
    </section>
  );
}
