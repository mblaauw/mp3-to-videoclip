import { useCallback, useEffect, useState } from "react";
import {
  api,
  type ApprovalState,
  type Budget,
  type ImageShot,
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
    };
  }
  return result;
}

function imageFacts(shots: ImageShot[]): ImageFacts {
  const paid = shots.filter((shot) => shot.paid);
  return {
    total: paid.length,
    selected: paid.filter((shot) => shot.selected !== null).length,
    kept: paid.filter((shot) => shot.review?.verdict === "accept").length,
    missing: paid.filter((shot) => shot.selected === null).length,
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

function StageView({ slug, stage }: { slug: string; stage: Stage }) {
  if (stage === "track") return <TrackStage slug={slug} />;
  if (stage === "story") return <StoryStage slug={slug} />;
  if (stage === "storyboard") return <StoryboardStage slug={slug} />;
  if (stage === "images") return <ImagesStage slug={slug} />;
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
    <PlayerProvider
      src={project.audio_url || `/api/projects/${project.slug}/audio`}
      fallbackDuration={project.duration || 0}
    >
      <FilmShellContent
        project={project}
        stage={stage}
        onNavigate={onNavigate}
        onProjectsChanged={onProjectsChanged}
      />
    </PlayerProvider>
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
  const [editOwnsTiming, setEditOwnsTiming] = useState(false);
  const [revision, setRevision] = useState(0);
  const [directorOpen, setDirectorOpen] = useState(() => window.innerWidth > 1180);

  const load = useCallback(async () => {
    const [approvalResult, imageResult, budgetResult, boardResult, trackResult, editResult] =
      await Promise.allSettled([
        api.approvals(slug, APPROVAL_STAGES),
        api.images(slug),
        api.budget(slug),
        api.storyboard(slug),
        api.track(slug),
        api.edit(slug),
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
  }, [slug]);

  useEffect(() => {
    void load();
  }, [load, revision]);

  useEffect(() => {
    const changed = () => setRevision((value) => value + 1);
    window.addEventListener(PROJECT_CHANGED, changed);
    return () => window.removeEventListener(PROJECT_CHANGED, changed);
  }, []);

  const facts = imageFacts(images);
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
  const projectFacts: ProjectFacts = { ...project, stage_states: shellStates };
  const step = nextStep(stage, projectFacts, approvals, facts, budget || {});

  const act = async (action: NextAction) => {
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
    if (action.target === "pictures") {
      if (stage !== "images") onNavigate("images");
      scrollTo(".images-body");
    }
  };

  return (
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
        onDirector={() => setDirectorOpen((open) => !open)}
      />
      <main className="shell-main">
        <NextStepBar step={step} ready={approvalsLoaded} onAction={act} />
        <div className="stage-pad">
          <div className={stage === "images" ? "images-body" : undefined}>
            <StageView key={slug} slug={slug} stage={stage} />
          </div>
        </div>
      </main>
      {directorOpen && (
        <Director
          key={slug}
          slug={slug}
          stage={stage}
          open
          onClose={() => setDirectorOpen(false)}
          onSettings={() => toast("Settings is coming with the director pass.")}
        />
      )}
      <Spine
        slug={slug}
        stage={stage}
        board={board}
        music={music}
        images={images}
        readOnly={editOwnsTiming}
        onBoardChange={setBoard}
      />
    </div>
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
