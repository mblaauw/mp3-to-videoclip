import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type ApprovalState,
  type AudioWindow,
  type Budget,
  type EditPayload,
  type EditSummary,
  type ImageShot,
  type IntakePayload,
  type Music,
  type ProjectSummary,
  type Storyboard,
} from "../api";
import { ApprovalsProvider } from "../ApprovalBar";
import { applyEditBoard } from "../film/editTimeline";
import { jobLine } from "../jobs/JobBanner";
import { useJobs } from "../jobs/store";
import { PlayerProvider } from "../spine/player";
import { Spine } from "../spine/Spine";
import { ImagesStage } from "../stages/Images";
import { FilmStage } from "../stages/Film";
import { StoryStage } from "../stages/Story";
import { StoryboardStage } from "../stages/Storyboard";
import { TrackStage } from "../stages/Track";
import { toast } from "../toast";
import { Director } from "./Director";
import { ArchiveFilm } from "./ArchiveFilm";
import { Library } from "./Library";
import { NextStepBar } from "./NextStepBar";
import { ShotInspector } from "../storyboard/ShotInspector";
import {
  nextStep,
  type ApprovalFacts,
  type ApprovalMap,
  type ImageFacts,
  type NextAction,
  type ProjectFacts,
  type Stage,
  type StageState,
} from "./nextStep";
import { notifyProjectChanged, useProjectChanged } from "./projectEvents";
import { goLibrary } from "./route";
import { STAGES } from "./stages";
import { TopBar } from "./TopBar";
import { scrollBehavior } from "../ui";
import { SHOT_KINDS } from "../shotKinds";

const APPROVED: Record<string, string> = {
  brief: "Story approved",
  storyboard: "Storyboard approved",
  proof: "Style check approved",
  stills: "All stills approved",
  preview: "Preview approved",
  graphics: "Titles approved",
};

const APPROVAL_STAGES = [
  "analysis",
  "lyrics",
  "brief",
  "storyboard",
  "proof",
  "preview",
  "stills",
  "graphics",
];

function approvalMap(states: ApprovalState[]): ApprovalMap {
  const result: ApprovalMap = {};
  for (const state of states) {
    result[state.stage] = {
      state: state.state,
      error: state.error,
      blocking_stage: state.blocking_stage,
      expected_hash: state.expected_hash,
      reason: state.reason,
    };
  }
  return result;
}

function imageFacts(shots: ImageShot[], reserve: string, proofIds: string[]): ImageFacts {
  const paid = shots.filter((shot) => shot.paid);
  const missing = paid.filter((shot) => shot.selected === null);
  const proof = shots.filter((shot) => proofIds.includes(shot.id) && !shot.local);
  return {
    proof_total: proof.length,
    proof_kept: proof.filter(
      (shot) => shot.selected !== null && !shot.stale && shot.review?.verdict === "accept",
    ).length,
    proof_missing_ids: proof.filter((shot) => shot.selected === null).map((shot) => shot.id),
    proof_stale_ids: proof
      .filter((shot) => shot.selected !== null && shot.stale)
      .map((shot) => shot.id),
    total: paid.length,
    selected: paid.filter((shot) => shot.selected !== null).length,
    kept: paid.filter((shot) => shot.review?.verdict === "accept").length,
    missing: missing.length,
    missing_ids: missing.map((shot) => shot.id),
    reserve_usd: reserve,
  };
}

function approvalWord(value: ApprovalFacts | undefined): StageState {
  if (!value) return "you";
  if (value.state === "approved") return "done";
  if (value.state === "stale") return "changed";
  if (value.state === "unavailable") return "not_ready";
  return "you";
}

/**
 * The top bar and the next-step bar must agree. Approval endpoints are
 * authoritative; the library summary stays a cheap mtime heuristic only.
 */
function derivedStates(
  project: ProjectSummary,
  approvals: ApprovalMap,
): Partial<Record<Stage, StageState>> {
  const base = { ...(project.stage_states || {}) } as Partial<Record<Stage, StageState>>;
  base.story = approvalWord(approvals.brief);
  base.storyboard =
    base.story === "done" ? approvalWord(approvals.storyboard) : "not_ready";
  if (base.storyboard !== "done") {
    base.images = "not_ready";
  } else if (approvals.stills?.state === "approved") {
    base.images = "done";
  } else if (approvals.stills?.state === "stale" || approvals.proof?.state === "stale") {
    base.images = "changed";
  } else {
    base.images = "you";
  }
  base.film =
    base.film === "done" ? "done" : base.images === "done" ? "you" : "not_ready";
  return base;
}

function scrollTo(selector: string, delay = 60) {
  window.setTimeout(() => {
    document
      .querySelector(selector)
      ?.scrollIntoView({ behavior: scrollBehavior(), block: "center" });
  }, delay);
}

type PaidRequest = NonNullable<NextAction["paid"]>;

function StageView({
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
}: {
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
}) {
  if (stage === "track") return <TrackStage slug={slug} />;
  if (stage === "story")
    return (
      <StoryStage
        slug={slug}
        intake={intake}
        audioWindow={audioWindow}
        windowLocked={windowLocked}
        onIntakeChange={onIntakeChange}
      />
    );
  if (stage === "storyboard") return <StoryboardStage slug={slug} onInspect={onInspect} />;
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
  return <FilmStage slug={slug} onNavigate={onNavigate} />;
}

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

function FilmShellContent({
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
  const slug = project.slug;
  const { jobs } = useJobs();
  const [approvals, setApprovals] = useState<ApprovalMap>({});
  const [approvalStates, setApprovalStates] = useState<Record<string, ApprovalState>>({});
  const [approvalsLoaded, setApprovalsLoaded] = useState(false);
  const [images, setImages] = useState<ImageShot[]>([]);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [board, setBoard] = useState<Storyboard | null>(null);
  const [music, setMusic] = useState<Music | null>(null);
  const [intake, setIntake] = useState<IntakePayload | null>(null);
  const [audioWindow, setAudioWindow] = useState<AudioWindow | null>(null);
  const [windowBusy, setWindowBusy] = useState(false);
  const [editOwnsTiming, setEditOwnsTiming] = useState(false);
  const [editPayload, setEditPayload] = useState<EditPayload | null>(null);
  const [reserve, setReserve] = useState("0.05");
  const [shotKinds, setShotKinds] = useState<typeof SHOT_KINDS>(SHOT_KINDS);
  const [revision, setRevision] = useState(0);
  const [inspectorShot, setInspectorShot] = useState<string | null>(null);
  const [directorShots, setDirectorShots] = useState<string[]>([]);
  const [pendingPaid, setPendingPaid] = useState<PaidRequest | null>(null);
  const [directorOpen, setDirectorOpen] = useState(() => window.innerWidth > 1180);
  const [directorPrompt, setDirectorPrompt] = useState<{ text: string; at: number } | null>(null);

  const loadEpoch = useRef(0);
  const [loadError, setLoadError] = useState<string | null>(null);
  const load = useCallback(async () => {
    const epoch = ++loadEpoch.current;
    const [
      approvalResult,
      imageResult,
      budgetResult,
      boardResult,
      trackResult,
      editResult,
      intakeResult,
      settingsResult,
    ] = await Promise.allSettled([
      api.approvals(slug, APPROVAL_STAGES),
      api.images(slug),
      api.budget(slug),
      api.storyboard(slug),
      api.track(slug),
      project.shots > 0 ? api.edit(slug) : Promise.resolve({ present: false } as EditSummary),
      api.intake(slug),
      api.settings(),
    ]);
    if (epoch !== loadEpoch.current) return;
    const failure = [approvalResult, imageResult, budgetResult, boardResult, trackResult, editResult, intakeResult, settingsResult].find((result) => result.status === "rejected");
    setLoadError(failure?.status === "rejected" ? String(failure.reason) : null);
    if (failure?.status === "rejected") toast(`Could not refresh film data: ${String(failure.reason)}`);
    if (approvalResult.status === "fulfilled") {
      setApprovals(approvalMap(approvalResult.value.stages));
      setApprovalStates(
        Object.fromEntries(approvalResult.value.stages.map((item) => [item.stage, item])),
      );
    }
    setApprovalsLoaded(true);
    if (imageResult.status === "fulfilled") setImages(imageResult.value.shots);
    if (budgetResult.status === "fulfilled") setBudget(budgetResult.value);
    if (boardResult.status === "fulfilled") {
      setBoard("shots" in boardResult.value ? boardResult.value : null);
    }
    if (trackResult.status === "fulfilled") setMusic(trackResult.value.music);
    if (editResult.status === "fulfilled") {
      setEditOwnsTiming(editResult.value.present);
      setEditPayload(editResult.value.present ? editResult.value.edit ?? null : null);
    }
    if (intakeResult.status === "fulfilled") {
      setIntake(intakeResult.value);
      setAudioWindow((current) => current ?? intakeResult.value.audio_window);
    }
    if (settingsResult.status === "fulfilled") {
      const value = Number(settingsResult.value.image_reserve_usd || 0.05);
      setReserve((value > 0 ? value : 0.05).toFixed(2));
      const kinds = settingsResult.value.shot_kinds;
      if (kinds && kinds.length) setShotKinds(kinds);
    }
  }, [slug, project.shots]);

  useEffect(() => {
    void load();
    return () => { loadEpoch.current += 1; };
  }, [load, revision]);

  useProjectChanged(slug, () => setRevision((value) => value + 1));

  useEffect(() => {
    if (stage !== "storyboard") setInspectorShot(null);
  }, [stage]);

  useEffect(() => {
    const pick = (event: Event) => {
      if (stage !== "storyboard") return;
      const id = (event as CustomEvent<string>).detail;
      if (typeof id === "string" && id) setInspectorShot(id);
    };
    window.addEventListener("studio:select-shot", pick);
    return () => window.removeEventListener("studio:select-shot", pick);
  }, [stage]);

  useEffect(() => {
    if (inspectorShot && board && !board.shots.some((shot) => shot.id === inspectorShot)) {
      setInspectorShot(null);
    }
  }, [board, inspectorShot]);

  useEffect(() => {
    const ask = (event: Event) => {
      const detail = (event as CustomEvent<{ text?: string }>).detail;
      setInspectorShot(null);
      setDirectorOpen(true);
      setDirectorPrompt({ text: detail?.text || "", at: Date.now() });
    };
    window.addEventListener("studio:ask-director", ask);
    return () => window.removeEventListener("studio:ask-director", ask);
  }, []);

  const imageJob = jobs.find(
    (job) =>
      job.project === slug && job.kind === "images" && ["queued", "running", "stopping"].includes(job.status),
  );
  const facts: ImageFacts = {
    ...imageFacts(images, reserve, intake?.brief?.creative?.proof_shot_ids || []),
    running: !!imageJob,
    running_line: imageJob ? jobLine(imageJob) : undefined,
  };
  const authoritative = approvalsLoaded && Object.keys(approvals).length > 0;
  const states = authoritative
    ? derivedStates(project, approvals)
    : (project.stage_states as Partial<Record<Stage, StageState>> | undefined);
  const analysisRunning = jobs.some(
    (job) =>
      job.project === slug &&
      job.kind === "analysis" &&
      ["queued", "running", "stopping"].includes(job.status),
  );
  const shellStates = analysisRunning ? { ...states, track: "running" as const } : states;
  const inspectShot = (id: string) => {
    setInspectorShot(id);
    setDirectorShots([id]);
  };
  const projectFacts: ProjectFacts = {
    ...project,
    stage_states: shellStates,
    prompt_version: intake?.prompt_version ?? null,
    profile_version: intake?.brief?.creative?.profile_version ?? 0,
    has_message: intake ? Boolean(intake.intent?.message?.trim()) : undefined,
    has_cta: intake
      ? Boolean(intake.intent?.cta?.text?.trim() || intake.intent?.cta?.url?.trim())
      : undefined,
  };
  const step = nextStep(stage, projectFacts, approvals, facts, budget || {});
  const baseAudio = project.audio_url || `/api/projects/${slug}/audio`;
  const committedWindow = intake?.audio_window || null;
  const playerSrc =
    committedWindow && project.kind !== "music_video"
      ? `${baseAudio}?v=${committedWindow.start}-${committedWindow.end}-${committedWindow.fade_in}-${committedWindow.fade_out}`
      : baseAudio;
  const spineBoard = board && editPayload ? applyEditBoard(board, editPayload) : board;

  const saveCutBoundary = async (next: EditPayload): Promise<boolean> => {
    try {
      const saved = await api.saveEdit(slug, next, editPayload);
      setEditPayload(saved.present ? saved.edit ?? next : null);
      setEditOwnsTiming(saved.present);
      notifyProjectChanged();
      onProjectsChanged();
      return true;
    } catch (error) {
      toast(`Could not save the cut: ${String(error)}`);
      return false;
    }
  };

  const commitAudioWindow = async (window: AudioWindow): Promise<boolean> => {
    const previous = intake?.audio_window || null;
    setWindowBusy(true);
    try {
      const updated = await api.updateIntake(slug, { audio_window: window });
      setIntake(updated);
      setAudioWindow(updated.audio_window);
      notifyProjectChanged();
      onProjectsChanged();
      return true;
    } catch {
      setAudioWindow(previous);
      return false;
    } finally {
      setWindowBusy(false);
    }
  };

  const act = async (action: NextAction, note?: string) => {
    if (action.approve) {
      const expected = approvals[action.approve]?.expected_hash;
      if (!expected) {
        toast("The current version is not ready to approve yet.", "info");
        return;
      }
      try {
        await api.approve(slug, action.approve, {
          expected_hash: expected,
          confirmed: true,
          ...(note ? { note } : {}),
        });
        toast(`${APPROVED[action.approve] || "Approved"}.`, "done");
        notifyProjectChanged({ slug });
        onProjectsChanged();
      } catch {
        // request() already surfaced the error; reload in case the stage moved on.
        setRevision((value) => value + 1);
      }
      return;
    }
    if (action.to) {
      onNavigate(action.to);
      return;
    }
    if (action.target === "analysis") {
      try {
        await api.analyze(slug);
        notifyProjectChanged();
        onProjectsChanged();
        toast("The song is measured.", "done");
      } catch {
        // request() already surfaced the error.
      }
      return;
    }
    if (action.target === "changes") {
      if (stage !== "story") onNavigate("story");
      scrollTo("#story-changes", 180);
      return;
    }
    if (action.target === "brief") {
      if (stage !== "story") onNavigate("story");
      scrollTo(".brief-card", 180);
      return;
    }
    if (action.target === "approval") {
      if (!document.querySelector(".signoff")) onNavigate(stage);
      scrollTo(".signoff");
      return;
    }
    if (action.target === "preview") {
      if (stage !== "film") onNavigate("film");
      scrollTo(".live-preview");
      return;
    }
    if (action.target === "render") {
      if (stage !== "film") onNavigate("film");
      scrollTo(".delivery-card");
      return;
    }
    if (action.target === "make-missing") {
      if (!action.paid) return;
      setPendingPaid(action.paid);
      if (stage !== "images") onNavigate("images");
      scrollTo(".images-body", 180);
      return;
    }
    if (action.target === "pictures") {
      if (stage !== "images") onNavigate("images");
      scrollTo(".images-body");
    }
  };

  const stageIndex = STAGES.findIndex((item) => item.id === stage);
  const previousStage = stageIndex > 0 ? STAGES[stageIndex - 1] : null;

  return (
    <ApprovalsProvider value={{ states: approvalStates, loaded: approvalsLoaded }}>
    <PlayerProvider src={playerSrc} fallbackDuration={intake?.duration || project.duration || 0}>
      <div className="shell">
        <TopBar
          project={project}
          stage={stage}
          budget={budget}
          stageStates={shellStates}
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
            setDirectorOpen((open) => !open);
          }}
        />
        <main className="shell-main">
          {loadError && <p role="alert">Could not refresh film data: {loadError}</p>}
          <NextStepBar
            step={step}
            ready={approvalsLoaded}
            onAction={act}
            back={previousStage ? { label: previousStage.label, onClick: () => onNavigate(previousStage.id) } : null}
          />
          <div className="stage-pad">
            <div className={stage === "images" ? "images-body" : undefined}>
              <StageView
                key={slug}
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
            prefill={directorPrompt}
            selectedShots={
              stage === "storyboard" ? (inspectorShot ? [inspectorShot] : directorShots) : []
            }
            onClose={() => setDirectorOpen(false)}
            onSettings={onSettings}
          />
        ) : null}
        <Spine
          slug={slug}
          stage={stage}
          board={spineBoard}
          music={music}
          images={images}
          audioWindow={audioWindow}
          sourcePeaks={intake?.peaks || []}
          sourceDuration={intake?.source_duration || project.duration || 0}
          windowBusy={windowBusy}
          windowLocked={project.shots > 0}
          onAudioWindow={setAudioWindow}
          onAudioWindowCommit={commitAudioWindow}
          onBoardChange={setBoard}
          edit={stage === "film" ? editPayload : null}
          onEditChange={stage === "film" ? saveCutBoundary : undefined}
          readOnly={stage === "storyboard" && editOwnsTiming}
        />
      </div>
    </PlayerProvider>
    </ApprovalsProvider>
  );
}

export function LibraryShell({
  projects,
  loading,
  error,
  onOpen,
  onArchive,
  onCreated,
  onSettings,
  onRetry,
}: {
  projects: ProjectSummary[];
  loading: boolean;
  error: string | null;
  onOpen: (slug: string, stage: string) => void;
  onArchive: (slug: string) => void;
  onCreated: (slug: string) => void;
  onSettings: () => void;
  onRetry: () => void;
}) {
  return (
    <div className="shell library-shell">
      <TopBar
        project={null}
        stage={null}
        budget={null}
        onNavigate={() => goLibrary()}
        onSettings={onSettings}
        onBudgetChanged={() => {}}
        directorOpen={false}
        onDirector={() => {}}
      />
      <Library
        projects={projects}
        loading={loading}
        error={error}
        onOpen={onOpen}
        onArchive={onArchive}
        onCreated={onCreated}
        onRetry={onRetry}
      />
    </div>
  );
}

export function ArchiveShell({
  project,
  onBack,
  onSettings,
}: {
  project: ProjectSummary;
  onBack: () => void;
  onSettings: () => void;
}) {
  return (
    <div className="shell library-shell">
      <TopBar
        project={null}
        stage={null}
        budget={null}
        onNavigate={() => goLibrary()}
        onSettings={onSettings}
        onBudgetChanged={() => {}}
        directorOpen={false}
        onDirector={() => {}}
      />
      <ArchiveFilm project={project} onBack={onBack} />
    </div>
  );
}
