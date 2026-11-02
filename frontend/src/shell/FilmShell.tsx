import { api, type ProjectSummary } from "../api";
import { ApprovalsProvider } from "../ApprovalBar";
import { PlayerProvider } from "../spine/player";
import { Spine } from "../spine/Spine";
import { Director } from "./Director";
import { NextStepBar } from "./NextStepBar";
import { ShotInspector } from "../storyboard/ShotInspector";
import { type Stage } from "./nextStep";
import { notifyProjectChanged } from "./projectEvents";
import { Button } from "../ui";
import { FirstDraftDialog } from "./FirstDraftDialog";
import { TopBar } from "./TopBar";
import { DRAFT_NAME } from "./shellState";
import { StageView } from "./StageView";
import { type FilmShellContentProps, useFilmShellData } from "./useFilmShellData";

export function FilmShell({
  project,
  stage,
  onNavigate,
  onProjectsChanged,
  onSettings,
}: {
  project: ProjectSummary;
  stage: Stage;
  onNavigate: (stage: Stage) => void;
  onProjectsChanged: () => void;
  onSettings: () => void;
}) {
  return (
    <FilmShellContent
      project={project}
      stage={stage}
      onNavigate={onNavigate}
      onProjectsChanged={onProjectsChanged}
      onSettings={onSettings}
    />
  );
}

function FilmShellContent(props: FilmShellContentProps) {
  const { project, stage, onNavigate, onProjectsChanged, onSettings } = props;
  const { act, approvalStates, approvalsLoaded, audioWindow, board, budget, commitAudioWindow, deliveryAsk, directorBusy, directorOpen, directorPrompt, directorShots, draftOpen, drafted, editOwnsTiming, filmFull, filmLine, filmSide, images, inspectShot, inspectorShot, intake, load, loadError, music, pendingPaid, playerSrc, previousStage, reserve, setAudioWindow, setBoard, setDirectorOpen, setDirectorShots, setDraftOpen, setFilmFull, setFilmLine, setFilmSide, setInspectorShot, setIntake, setPendingPaid, setStoryBands, setTitlesReady, shellStates, shotKinds, slug, spineBoard, spokenLines, step, storyBands, windowBusy } = useFilmShellData(props);
  return (
    <ApprovalsProvider value={{ states: approvalStates, loaded: approvalsLoaded }}>
    <PlayerProvider src={playerSrc} fallbackDuration={intake?.duration || project.duration || 0}>
      <div className={`shell ${stage === "film" ? "on-film" : ""} ${filmFull ? "film-full" : ""}`}>
        <TopBar
          project={project}
          stage={stage}
          budget={budget}
          stageStates={shellStates}
          next={
            stage === "film" || stage === "story" || stage === "track" || stage === "script" ? (
              <NextStepBar compact allowNote={stage === "story"} step={step} ready={approvalsLoaded} onAction={act} />
            ) : null
          }
          onNavigate={onNavigate}
          onSettings={onSettings}
          onBudgetChanged={() => {
            void load();
            onProjectsChanged();
          }}
          directorOpen={directorOpen}
          onDirector={() => {
            if (inspectorShot) {
              setDirectorShots([inspectorShot]);
              setInspectorShot(null);
              setDirectorOpen(true);
              return;
            }
            setDirectorOpen(!directorOpen);
          }}
        />
        <main className="shell-main">
          {loadError && <p role="alert">Could not refresh film data: {loadError}</p>}
          {stage === "story" && project.shots === 0 && project.spine !== "soundtrack" && (
            <div className="row-actions">
              <Button size="small" variant="quiet" onClick={() => setDraftOpen(true)}>
                Make a first draft
              </Button>
            </div>
          )}
          {draftOpen && <FirstDraftDialog slug={slug} onClose={() => setDraftOpen(false)} />}
          {drafted.map((item) => (
            <div className="next-step drafted" key={item.stage}>
              <p className="hint">{DRAFT_NAME[item.stage] ?? item.stage}: drafted, not yours.</p>
              <Button
                size="small"
                onClick={() =>
                  void api
                    .approve(slug, item.stage, {
                      expected_hash: item.expected_hash ?? "",
                      confirmed: true,
                      note: "the owner made the draft theirs",
                    })
                    .then(() => notifyProjectChanged({ slug }))
                }
              >
                Make it yours
              </Button>
            </div>
          ))}
          {stage !== "film" && stage !== "story" && stage !== "track" && stage !== "script" && (
            <NextStepBar
              step={step}
              ready={approvalsLoaded}
              onAction={act}
              back={previousStage ? { label: previousStage.label, onClick: () => onNavigate(previousStage.id) } : null}
            />
          )}
          <div className="stage-pad">
            <div className={stage === "images" ? "images-body" : undefined}>
              <StageView
                key={slug}
                filmSide={filmSide}
                filmLine={filmLine}
                music={music}
                filmFull={filmFull}
                onFilmFull={setFilmFull}
                onShowFilmPanel={() => setDirectorOpen(false)}
                deliveryAsk={deliveryAsk}
                onTitlesReady={setTitlesReady}
                slug={slug}
                stage={stage}
                intake={intake}
                audioWindow={audioWindow}
                windowLocked={project.shots > 0}
                onIntakeChange={setIntake}
                onInspect={inspectShot}
                pendingPaid={pendingPaid}
                onPendingConsumed={() => setPendingPaid(null)}
                reserve={reserve}
                onNavigate={onNavigate}
                images={images}
                board={board}
                onStoryBands={setStoryBands}
              />
            </div>
          </div>
        </main>
        {stage === "storyboard" && inspectorShot ? (
          <ShotInspector
            slug={slug}
            shotId={inspectorShot}
            board={board}
            images={images}
            music={music}
            kinds={shotKinds}
            proofIds={intake?.brief?.creative?.proof_shot_ids || []}
            reserve={reserve}
            timingOwned={editOwnsTiming}
            onSelect={inspectShot}
            onBoardChange={setBoard}
            onClose={() => setInspectorShot(null)}
          />
        ) : directorOpen ? (
          <Director
            key={slug}
            slug={slug}
            stage={stage}
            open
            onBusyChange={(busy) => {
              directorBusy.current = busy;
            }}
            prefill={directorPrompt}
            selectedShots={
              stage === "storyboard" ? (inspectorShot ? [inspectorShot] : directorShots) : []
            }
            onClose={() => setDirectorOpen(false)}
            onSettings={onSettings}
          />
        ) : stage === "film" ? (
          <aside className="film-side" aria-label="Film panel" ref={setFilmSide} />
        ) : null}
        {stage === "film" ? (
          <div className="film-line" ref={setFilmLine} />
        ) : (
        <Spine
          slug={slug}
          stage={stage}
          board={spineBoard}
          music={music}
          images={images}
          bands={stage === "story" ? storyBands : []}
          audioWindow={audioWindow}
          sourcePeaks={intake?.peaks || []}
          sourceDuration={intake?.source_duration || project.duration || 0}
          windowBusy={windowBusy}
          windowLocked={project.shots > 0}
          onAudioWindow={setAudioWindow}
          onAudioWindowCommit={commitAudioWindow}
          onBoardChange={setBoard}
          readOnly={stage === "storyboard" && editOwnsTiming}
          spokenLines={spokenLines}
        />
        )}
      </div>
    </PlayerProvider>
    </ApprovalsProvider>
  );
}

