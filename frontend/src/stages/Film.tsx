import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, type EditPayload, type Music } from "../api";
import { CutEditor, type ApplyResult } from "../film/cutEditor";
import { describeNotes } from "../film/cutNotes";
import { CutList } from "../film/CutList";
import { applyEditBoard } from "../film/editTimeline";
import { FilmPanel } from "../film/FilmPanel";
import { FilmTimeline } from "../film/FilmTimeline";
import { LiveViewer } from "../film/LiveViewer";
import { RenderedFiles } from "../film/RenderedFiles";
import { selectJoin, stepJoin, type FilmSelection } from "../film/selection";
import { useFilmData } from "../film/useFilmData";
import { RendererSetup } from "../RendererSetup";
import type { Stage } from "../shell/nextStep";
import { usePlayerControls } from "../spine/player";
import { notifyProjectChanged } from "../shell/projectEvents";
import { toast } from "../toast";
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
  onShowPanel,
  deliveryAsk,
  onTitlesReady,
}: {
  slug: string;
  onNavigate: (stage: Stage) => void;
  sideSlot: HTMLElement | null;
  lineSlot: HTMLElement | null;
  music: Music | null;
  full: boolean;
  onFull: (next: boolean) => void;
  /** The Director holds the panel's slot while open; this hands it back. */
  onShowPanel: () => void;
  /** Bumped when the next-step bar asks for the delivery panel. */
  deliveryAsk: number;
  onTitlesReady: (ready: boolean) => void;
}) {
  const film = useFilmData(slug);
  const { error, notice, load, loaded, setRendererReady } = film;
  const [tab, setTab] = useState<FilmTab>("cut");
  const [selection, setSelection] = useState<FilmSelection>(null);
  const [zoom, setZoom] = useState(1);
  const player = usePlayerControls();
  const [, redraw] = useState(0);
  const editor = useRef<CutEditor | null>(null);
  if (!editor.current) {
    editor.current = new CutEditor(
      async (next, base) => {
        const saved = await api.saveEdit(slug, next, base);
        return saved.edit ?? next;
      },
      () => redraw((value) => value + 1),
    );
  }
  const serverEdit = film.cut?.present ? film.cut.edit : null;
  useEffect(() => editor.current?.sync(serverEdit), [serverEdit]);
  const edit = editor.current.current ?? serverEdit;
  const timelineBoard = film.board && edit ? applyEditBoard(film.board, edit) : film.board;
  const fps = timelineBoard?.fps || 24;
  const findings = film.cut?.present ? film.cut.warnings : null;
  const notes = useMemo(
    () =>
      findings
        ? describeNotes(findings, {
            sections: film.cut?.sections ?? [],
            shots: edit?.shots ?? [],
          })
        : [],
    [findings, film.cut?.sections, edit?.shots],
  );

  const keys = useRef({ step: (_direction: 1 | -1) => {}, clear: () => {}, nudge: (_frames: number) => {}, zoomBy: (_by: number) => {} });
  keys.current = {
    step: (direction) => {
      if (!timelineBoard) return;
      const id = stepJoin(timelineBoard.shots, Math.round(player.current() * fps), direction);
      const shot = timelineBoard.shots.find((item) => item.id === id);
      if (!id || !shot) return;
      select({ kind: "join", ids: [id] });
      player.seek((shot.start_frame - 1) / fps);
    },
    clear: () => {
      if (film.samplesOpen) film.setSamplesOpen(false);
      else setSelection(null);
    },
    nudge: (frames) => {
      if (film.samplesOpen) film.openSample(film.sampleIndex + Math.sign(frames));
      else player.seek(player.current() + frames / fps);
    },
    zoomBy: (by) => setZoom((value) => Math.max(1, Math.min(8, value + by))),
  };
  const undoKey = useRef<() => Promise<void>>(async () => {});
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if ((event.metaKey || event.ctrlKey) && !event.shiftKey && event.key.toLowerCase() === "z") {
        if (target?.closest("input[type='text'], textarea, [contenteditable='true'], [role='dialog']")) {
          return;
        }
        event.preventDefault();
        void undoKey.current();
        return;
      }
      if (event.metaKey || event.ctrlKey || event.altKey) return;
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

  /** After a save: say what happened and bring the Player up to date. */
  const settle = useCallback(
    async (result: ApplyResult, label: string): Promise<boolean> => {
      if (result === "saved") {
        film.setNotice(label);
        notifyProjectChanged();
        await film.reloadLive();
        return true;
      }
      if (result === "conflict") {
        toast("This cut changed somewhere else, so your last change was not saved. The latest cut is loaded and undo starts again.");
        await film.load();
      } else if (result === "failed") {
        toast(`Could not save the cut: ${label}.`);
      }
      return false;
    },
    [film],
  );

  /** Apply a change now and save it in order. */
  const change = useCallback(
    async (next: EditPayload, label: string): Promise<boolean> => {
      return settle(await editor.current!.apply(next, label), label);
    },
    [settle],
  );

  const undo = useCallback(async () => {
    const step = editor.current!.undo();
    if (!step) {
      toast("Nothing to undo.", "info");
      return;
    }
    await settle(await step.result, `Undid: ${step.label}`);
  }, [settle]);
  undoKey.current = undo;

  const watchStop = useRef<(() => void) | null>(null);
  const { clock: playerClock, playing } = player;
  useEffect(() => {
    if (!playing && watchStop.current) {
      watchStop.current();
      watchStop.current = null;
    }
  }, [playing]);
  /** Play two seconds either side of a join, with sound, then stop. */
  const watchJoin = (id: string) => {
    const shot = edit?.shots.find((item) => item.shot_id === id);
    if (!shot) return;
    const end = (shot.start_frame + shot.transition_in.frames) / fps + 2;
    watchStop.current?.();
    player.seek(Math.max(0, shot.start_frame / fps - 2));
    player.play();
    const stop = playerClock.subscribe(() => {
      if (playerClock.get() < end) return;
      stop();
      watchStop.current = null;
      player.pause();
    });
    watchStop.current = stop;
  };

  const select = (next: FilmSelection) => {
    setSelection(next);
    if (next && !sideSlot) onShowPanel();
  };

  const titlesReady = film.samples.length > 0 && film.graphics?.current !== false;
  useEffect(() => {
    onTitlesReady(titlesReady);
    return () => onTitlesReady(false);
  }, [titlesReady, onTitlesReady]);

  useEffect(() => {
    if (!deliveryAsk) return;
    setTab("cut");
    setSelection({ kind: "delivery" });
    onShowPanel();
    // Only a new ask opens it; the handler changes on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deliveryAsk]);

  const tabs = (
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
  );
  const status = (
    <>
      {notice && <p className="film-notice">{notice}</p>}
      {!!editor.current.history.length && (
        <Button size="small" variant="quiet" onClick={() => void undo()} title="Undo (⌘Z)">
          Undo
        </Button>
      )}
    </>
  );

  return (
    <div className="film-work">
      {error && (
        <ErrorState what="working on the film" error={error} compact onRetry={() => void load()} />
      )}
      <RendererSetup onReady={setRendererReady} />
      {!loaded ? (
        <LoadingState>Reading the film, its gates and the cut…</LoadingState>
      ) : tab === "cut" ? (
        <LiveViewer film={film} full={full} onFull={onFull} tabs={tabs} status={status} />
      ) : tab === "list" ? (
        <>
          <div className="film-viewer-bar film-tabbar">
            {tabs}
            {status}
          </div>
          <div className="film-scroll">
            <CutList film={film} notes={notes} onNavigate={onNavigate} />
          </div>
        </>
      ) : (
        <>
          <div className="film-viewer-bar film-tabbar">
            {tabs}
            {status}
          </div>
          <div className="film-scroll">
            <RenderedFiles film={film} />
          </div>
        </>
      )}
      {sideSlot &&
        loaded &&
        createPortal(
          <FilmPanel
            film={film}
            edit={edit}
            notes={notes}
            selection={selection}
            onSelect={select}
            onChange={change}
            onWatchJoin={watchJoin}
            onSeekNote={(note) => player.seek(note.frame / fps)}
            onNavigate={onNavigate}
          />,
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
            notes={notes}
            selection={selection}
            zoom={zoom}
            onZoom={setZoom}
            onSelectJoin={(id, additive) => select(selectJoin(selection, id, additive))}
            onSelectShot={(id) => select({ kind: "shot", id })}
            onSelectNote={(index) => select({ kind: "note", index })}
            onMoveBoundary={(next, label) => void change(next, label)}
          />,
          lineSlot,
        )}
    </div>
  );
}
