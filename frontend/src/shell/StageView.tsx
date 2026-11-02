import { type AudioWindow, type ImageShot, type IntakePayload, type Music, type Storyboard } from "../api";
import { ImagesStage } from "../stages/Images";
import { FilmStage } from "../stages/Film";
import { StoryStage } from "../stages/Story";
import { StoryboardStage } from "../stages/Storyboard";
import { TrackStage } from "../stages/Track";
import { type Stage } from "./nextStep";
import { type PaidRequest } from "./shellState";

import { ScriptStage } from "../stages/Script";

export function StageView({
  filmSide,
  filmLine,
  filmFull,
  onFilmFull,
  onShowFilmPanel,
  deliveryAsk,
  onTitlesReady,
  music,
  slug,
  stage,
  intake,
  audioWindow,
  windowLocked = false,
  onIntakeChange,
  onInspect,
  pendingPaid,
  onPendingConsumed,
  reserve,
  onNavigate,
  images,
  board,
  onStoryBands,
}: {
  board: Storyboard | null;
  onStoryBands: (bands: { start: number; end: number }[]) => void;
  filmSide: HTMLElement | null;
  filmLine: HTMLElement | null;
  filmFull: boolean;
  onFilmFull: (next: boolean) => void;
  onShowFilmPanel: () => void;
  deliveryAsk: number;
  onTitlesReady: (ready: boolean) => void;
  music: Music | null;
  slug: string;
  stage: Stage;
  intake: IntakePayload | null;
  audioWindow: AudioWindow | null;
  windowLocked?: boolean;
  onIntakeChange: (intake: IntakePayload) => void;
  onInspect: (shotId: string) => void;
  pendingPaid: PaidRequest | null;
  onPendingConsumed: () => void;
  reserve: string;
  onNavigate: (stage: Stage) => void;
  images: ImageShot[];
}) {
  if (stage === "track") return <TrackStage slug={slug} />;
  if (stage === "script") return <ScriptStage slug={slug} />;
  if (stage === "story")
    return (
      <StoryStage
        slug={slug}
        intake={intake}
        audioWindow={audioWindow}
        windowLocked={windowLocked}
        onIntakeChange={onIntakeChange}
        music={music}
        board={board}
        images={images}
        onBands={onStoryBands}
      />
    );
  if (stage === "storyboard")
    return <StoryboardStage slug={slug} images={images} onInspect={onInspect} />;
  if (stage === "images")
    return (
      <ImagesStage
        slug={slug}
        reserve={reserve}
        pendingPaid={pendingPaid}
        onPendingConsumed={onPendingConsumed}
        onNavigate={onNavigate}
      />
    );
  return (
    <FilmStage
      slug={slug}
      onNavigate={onNavigate}
      sideSlot={filmSide}
      lineSlot={filmLine}
      music={music}
      full={filmFull}
      onFull={onFilmFull}
      onShowPanel={onShowFilmPanel}
      deliveryAsk={deliveryAsk}
      onTitlesReady={onTitlesReady}
    />
  );
}
