import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ApprovalState,
  type AudioWindow,
  type Budget,
  type ImageShot,
  type IntakePayload,
  type Music,
  type ProjectSummary,
  type Storyboard,
} from "../api";
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
import { notifyProjectChanged, PROJECT_CHANGED } from "./projectEvents";
import { goLibrary } from "./route";
import { TopBar } from "./TopBar";
import { SHOT_KINDS } from "../shotKinds";

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

function imageFacts(shots: ImageShot[], reserve: string): ImageFacts {
  const paid = shots.filter((shot) => shot.paid);
  const missing = paid.filter((shot) => shot.selected === null);
  return {
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
    document.querySelector(selector)?.scrollIntoView({ behavior: "smooth", block: "center" });
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
      />
    );
  return <FilmStage slug={slug} />;
}

export function FilmShell({
  project,
  stage,
  onNavigate,
  onProjectsChanged,
}: {
  project: ProjectSummary;
  stage: Stage;
  onNavigate: (stage: Stage) => void;
  onProjectsChanged: () => void;
}) {
  return (
    <FilmShellContent
      project={project}
      stage={stage}
      onNavigate={onNavigate}
      onProjectsChanged={onProjectsChanged}
    />
  );
}

function FilmShellContent({
  project,
  stage,
  onNavigate,
  onProjectsChanged,
}: {
  project: ProjectSummary;
  stage: Stage;
  onNavigate: (stage: Stage) => void;
  onProjectsChanged: () => void;
}) {
  const slug = project.slug;
  const { jobs } = useJobs();
  const [approvals, setApprovals] = useState<ApprovalMap>({});
  const [approvalsLoaded, setApprovalsLoaded] = useState(false);
  const [images, setImages] = useState<ImageShot[]>([]);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [board, setBoard] = useState<Storyboard | null>(null);
  const [music, setMusic] = useState<Music | null>(null);
  const [intake, setIntake] = useState<IntakePayload | null>(null);
  const [audioWindow, setAudioWindow] = useState<AudioWindow | null>(null);
  const [windowBusy, setWindowBusy] = useState(false);
  const [editOwnsTiming, setEditOwnsTiming] = useState(false);
  const [reserve, setReserve] = useState("0.05");
  const [shotKinds, setShotKinds] = useState<typeof SHOT_KINDS>(SHOT_KINDS);
  const [revision, setRevision] = useState(0);
  const [inspectorShot, setInspectorShot] = useState<string | null>(null);
  const [pendingPaid, setPendingPaid] = useState<PaidRequest | null>(null);
  const [directorOpen, setDirectorOpen] = useState(() => window.innerWidth > 1180);
  const [directorPrompt, setDirectorPrompt] = useState<{ text: string; at: number } | null>(null);

  const load = useCallback(async () => {
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
      project.shots > 0 ? api.edit(slug) : Promise.resolve({ present: false }),
      api.intake(slug),
      api.settings(),
    ]);
    if (approvalResult.status === "fulfilled") {
      setApprovals(approvalMap(approvalResult.value.stages));
    }
    setApprovalsLoaded(true);
    if (imageResult.status === "fulfilled") setImages(imageResult.value.shots);
    if (budgetResult.status === "fulfilled") setBudget(budgetResult.value);
    if (boardResult.status === "fulfilled") {
      setBoard("shots" in boardResult.value ? boardResult.value : null);
    }
    if (trackResult.status === "fulfilled") setMusic(trackResult.value.music);
    if (editResult.status === "fulfilled") setEditOwnsTiming(editResult.value.present);
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
  }, [slug]);

  useEffect(() => {
    void load();
  }, [load, revision]);

  useEffect(() => {
    const changed = () => setRevision((value) => value + 1);
    window.addEventListener(PROJECT_CHANGED, changed);
    return () => window.removeEventListener(PROJECT_CHANGED, changed);
  }, []);

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

  const facts = imageFacts(images, reserve);
  const authoritative = approvalsLoaded && Object.keys(approvals).length > 0;
  const states = authoritative
    ? derivedStates(project, approvals)
    : (project.stage_states as Partial<Record<Stage, StageState>> | undefined);
  const analysisRunning = jobs.some(
    (job) =>
      job.project === slug &&
      job.kind === "analysis" &&
      ["queued", "running"].includes(job.status),
  );
  const shellStates = analysisRunning ? { ...states, track: "running" as const } : states;
  const projectFacts: ProjectFacts = {
    ...project,
    stage_states: shellStates,
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

  const act = async (action: NextAction) => {
    if (action.approve) {
      const expected = approvals[action.approve]?.expected_hash;
      if (!expected) {
        toast("The current version is not ready to approve yet.");
        return;
      }
      try {
        await api.approve(slug, action.approve, { expected_hash: expected, confirmed: true });
        toast(action.approve === "brief" ? "Story approved." : "Approved.");
        notifyProjectChanged();
        onProjectsChanged();
      } catch {
        // request() already surfaced the error.
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
        toast("The song is measured.");
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
      if (!document.querySelector(".approvals")) onNavigate(stage);
      scrollTo(".approvals");
      return;
    }
    if (action.target === "preview") {
      if (stage !== "film") onNavigate("film");
      scrollTo(".live-preview");
      return;
    }
    if (action.target === "render") {
      if (stage !== "film") onNavigate("film");
      scrollTo(".render-card");
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

  return (
    <PlayerProvider src={playerSrc} fallbackDuration={intake?.duration || project.duration || 0}>
      <div className="shell">
        <TopBar
          project={project}
          stage={stage}
          budget={budget}
          stageStates={shellStates}
          onNavigate={onNavigate}
          onSettings={() => toast("Settings is coming with the director pass.")}
          onBudgetChanged={() => {
            void load();
            onProjectsChanged();
          }}
          directorOpen={directorOpen}
          onDirector={() => {
            if (inspectorShot) {
              setInspectorShot(null);
              setDirectorOpen(true);
              return;
            }
            setDirectorOpen((open) => !open);
          }}
        />
        <main className="shell-main">
          <NextStepBar step={step} ready={approvalsLoaded} onAction={act} />
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
                onInspect={setInspectorShot}
                pendingPaid={pendingPaid}
                onPendingConsumed={() => setPendingPaid(null)}
                reserve={reserve}
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
            onSelect={setInspectorShot}
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
            onClose={() => setDirectorOpen(false)}
            onSettings={() => toast("Settings is coming with the director pass.")}
          />
        ) : null}
        <Spine
          slug={slug}
          stage={stage}
          board={board}
          music={music}
          images={images}
          audioWindow={audioWindow}
          sourcePeaks={intake?.peaks || []}
          sourceDuration={intake?.source_duration || project.duration || 0}
          windowBusy={windowBusy}
          windowLocked={project.shots > 0}
          onAudioWindow={setAudioWindow}
          onAudioWindowCommit={commitAudioWindow}
          readOnly={editOwnsTiming}
          onBoardChange={setBoard}
        />
      </div>
    </PlayerProvider>
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
}: {
  projects: ProjectSummary[];
  loading: boolean;
  error: string | null;
  onOpen: (slug: string, stage: string) => void;
  onArchive: (slug: string) => void;
  onCreated: (slug: string) => void;
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
      <Library
        projects={projects}
        loading={loading}
        error={error}
        onOpen={onOpen}
        onArchive={onArchive}
        onCreated={onCreated}
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
