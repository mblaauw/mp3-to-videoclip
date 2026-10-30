import { useState } from "react";
import { createPortal } from "react-dom";
import { CutList } from "../film/CutList";
import { DeliveryCard } from "../film/DeliveryCard";
import { LiveViewer } from "../film/LiveViewer";
import { RenderedFiles } from "../film/RenderedFiles";
import { SamplesDialog } from "../film/SamplesDialog";
import { useFilmData } from "../film/useFilmData";
import { RendererSetup } from "../RendererSetup";
import type { Stage } from "../shell/nextStep";
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
  full,
  onFull,
}: {
  slug: string;
  onNavigate: (stage: Stage) => void;
  sideSlot: HTMLElement | null;
  full: boolean;
  onFull: (next: boolean) => void;
}) {
  const film = useFilmData(slug);
  const { error, notice, load, loaded, rendererReady, setRendererReady } = film;
  const [tab, setTab] = useState<FilmTab>("cut");

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
      <SamplesDialog film={film} />
    </div>
  );
}
