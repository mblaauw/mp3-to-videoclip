import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { Music } from "../api";
import { CutList } from "../film/CutList";
import { DeliveryCard } from "../film/DeliveryCard";
import { applyEditBoard } from "../film/editTimeline";
import { FilmTimeline } from "../film/FilmTimeline";
import { LiveViewer } from "../film/LiveViewer";
import { RenderedFiles } from "../film/RenderedFiles";
import { SamplesDialog } from "../film/SamplesDialog";
import { selectJoin, stepJoin, type FilmSelection } from "../film/selection";
import { useFilmData } from "../film/useFilmData";
import { RendererSetup } from "../RendererSetup";
import type { Stage } from "../shell/nextStep";
import { usePlayerControls } from "../spine/player";
import { CreditsCard } from "../story/CreditsCard";
import { Button, ErrorState, LoadingState } from "../ui";

type FilmTab = "cut" | "list" | "files";

const TABS: { id: FilmTab; label: string }[] = [
  { id: "cut", label: "Edit" },
  { id: "list", label: "Cut list" },
  { id: "files", label: "Rendered files" },
];

/**
 * Film renders into the shell's grid: the viewer in the main area, its panel
 * through a portal into the side slot. The Director takes that slot when open
 * and the panel returns, with its state, when it closes.
 */
export function FilmStage({
  slug,
  onNavigate,
  sideSlot,
  lineSlot,
  music,
  full,
  onFull,
}: {
  slug: string;
  onNavigate: (stage: Stage) => void;
  sideSlot: HTMLElement | null;
  lineSlot: HTMLElement | null;
  music: Music | null;
  full: boolean;
  onFull: (next: boolean) => void;
}) {
  const film = useFilmData(slug);
  const { error, notice, load, loaded, rendererReady, setRendererReady } = film;
  const [tab, setTab] = useState<FilmTab>("cut");
  const [selection, setSelection] = useState<FilmSelection>(null);
  const [zoom, setZoom] = useState(1);
  const player = usePlayerControls();
  const edit = film.cut?.present ? film.cut.edit : null;
  const timelineBoard = film.board && edit ? applyEditBoard(film.board, edit) : film.board;
  const fps = timelineBoard?.fps || 24;

  const keys = useRef({ step: (_direction: 1 | -1) => {}, clear: () => {}, nudge: (_frames: number) => {}, zoomBy: (_by: number) => {} });
  keys.current = {
    step: (direction) => {
      if (!timelineBoard) return;
      const id = stepJoin(timelineBoard.shots, Math.round(player.current() * fps), direction);
      const shot = timelineBoard.shots.find((item) => item.id === id);
      if (!id || !shot) return;
      setSelection({ kind: "join", ids: [id] });
      player.seek((shot.start_frame - 1) / fps);
    },
    clear: () => setSelection(null),
    nudge: (frames) => player.seek(player.current() + frames / fps),
    zoomBy: (by) => setZoom((value) => Math.max(1, Math.min(8, value + by))),
  };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true'], [role='dialog'], [role='slider']")) {
        return;
      }
      const act = {
        "[": () => keys.current.step(-1),
        "]": () => keys.current.step(1),
        "+": () => keys.current.zoomBy(0.5),
        "=": () => keys.current.zoomBy(0.5),
        "-": () => keys.current.zoomBy(-0.5),
        Escape: () => keys.current.clear(),
        ArrowLeft: () => keys.current.nudge(event.shiftKey ? -fps : -1),
        ArrowRight: () => keys.current.nudge(event.shiftKey ? fps : 1),
      }[event.key];
      if (!act) return;
      event.preventDefault();
      act();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fps]);

  const moveBoundary = useCallback(
    (next: import("../api").EditPayload) => {
      void film.saveCut(next);
    },
    [film],
  );

  return (
    <div className="film-work">
      <div className="film-bar">
        <div className="board-tabs" role="group" aria-label="Film view">
          {TABS.map((item) => (
            <Button
              key={item.id}
              size="small"
              variant={tab === item.id ? "primary" : "quiet"}
              aria-pressed={tab === item.id}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </Button>
          ))}
        </div>
        {notice && <p className="film-notice">{notice}</p>}
      </div>
      {error && (
        <ErrorState what="working on the film" error={error} compact onRetry={() => void load()} />
      )}
      <RendererSetup onReady={setRendererReady} />
      {!loaded ? (
        <LoadingState>Reading the film, its gates and the cut…</LoadingState>
      ) : tab === "cut" ? (
        <LiveViewer film={film} full={full} onFull={onFull} />
      ) : tab === "list" ? (
        <div className="film-scroll">
          <CutList film={film} onNavigate={onNavigate} onFiles={() => setTab("files")} />
        </div>
      ) : (
        <div className="film-scroll">
          <RenderedFiles film={film} />
        </div>
      )}
      {sideSlot &&
        loaded &&
        createPortal(
          <>
            {rendererReady !== false && <DeliveryCard film={film} onNavigate={onNavigate} />}
            <CreditsCard slug={slug} />
          </>,
          sideSlot,
        )}
      {lineSlot &&
        createPortal(
          <FilmTimeline
            slug={slug}
            board={timelineBoard}
            music={music}
            images={film.images}
            edit={edit}
            windows={film.live?.titles?.windows ?? []}
            selection={selection}
            zoom={zoom}
            onZoom={setZoom}
            onSelectJoin={(id, additive) =>
              setSelection((current) => selectJoin(current, id, additive))
            }
            onSelectShot={(id) => setSelection({ kind: "shot", id })}
            onMoveBoundary={moveBoundary}
          />,
          lineSlot,
        )}
      <SamplesDialog film={film} />
    </div>
  );
}
