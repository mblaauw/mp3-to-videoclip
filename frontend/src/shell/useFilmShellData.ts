import { scrollBehavior } from "../ui";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ApprovalState, type AudioWindow, type Budget, type EditPayload, type EditSummary, type ImageShot, type IntakePayload, type Music, type ProjectSummary, type Storyboard } from "../api";
import { applyEditBoard } from "../film/editTimeline";
import { jobLine } from "../jobs/JobBanner";
import { useJobs } from "../jobs/store";
import { toast } from "../toast";
import { type DirectorPrompt } from "../director/chat";
import { nextStep, type ApprovalMap, type ImageFacts, type NextAction, type ProjectFacts, type Stage, type StageState } from "./nextStep";
import { notifyProjectChanged, useProjectChanged } from "./projectEvents";
import { useSpokenLines } from "../script/useSpokenLines";
import { STAGES } from "./stages";
import { SHOT_KINDS } from "../shotKinds";
import { type PaidRequest, APPROVED, APPROVAL_STAGES, approvalMap, imageFacts, derivedStates } from "./shellState";
import { directorDefault, rememberDirector } from "./directorDrawer";


export type FilmShellContentProps = {
  project: ProjectSummary;
  stage: Stage;
  onNavigate: (stage: Stage) => void;
  onProjectsChanged: () => void;
  onSettings: () => void;
};

export function useFilmShellData({
  project,
  stage,
  onNavigate,
  onProjectsChanged,
  onSettings,
}: FilmShellContentProps) {
  const slug = project.slug;
  const { jobs } = useJobs();
  const [approvals, setApprovals] = useState<ApprovalMap>({});
  const [approvalStates, setApprovalStates] = useState<Record<string, ApprovalState>>({});
  const [approvalsLoaded, setApprovalsLoaded] = useState(false);
  const [draftOpen, setDraftOpen] = useState(false);
  const [images, setImages] = useState<ImageShot[]>([]);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [board, setBoard] = useState<Storyboard | null>(null);
  const [hasModelKey, setHasModelKey] = useState<boolean | undefined>(undefined);
  const [storyBands, setStoryBands] = useState<{ start: number; end: number }[]>([]);
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
  const [directorOpen, setDirectorOpenState] = useState(() => directorDefault(stage));
  const directorBusy = useRef(false);
  const setDirectorOpen = (open: boolean) => {
    setDirectorOpenState(open);
    rememberDirector(stage, open);
  };
  const [filmSide, setFilmSide] = useState<HTMLElement | null>(null);
  const [filmLine, setFilmLine] = useState<HTMLElement | null>(null);
  const [filmFull, setFilmFull] = useState(false);
  const [deliveryAsk, setDeliveryAsk] = useState(0);
  const [titlesReady, setTitlesReady] = useState(false);
  const [directorPrompt, setDirectorPrompt] = useState<DirectorPrompt | null>(null);

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
      setHasModelKey(
        Boolean(settingsResult.value.role_keys?.writer),
      );
    }
  }, [slug, project.shots]);

  useEffect(() => {
    void load();
    return () => { loadEpoch.current += 1; };
  }, [load, revision]);

  useProjectChanged(slug, () => setRevision((value) => value + 1));

  useEffect(() => {
    if (stage !== "storyboard") setInspectorShot(null);
    if (stage !== "film") {
      setFilmFull(false);
      setDeliveryAsk(0);
    }
    // Each stage reopens as you left it, but a reply being written is never cut off.
    if (!directorBusy.current) setDirectorOpenState(directorDefault(stage));
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
      const detail = (
        event as CustomEvent<{
          text?: string;
          send?: boolean;
          task?: string;
          role?: DirectorPrompt["role"];
        }>
      ).detail;
      setInspectorShot(null);
      setDirectorOpen(true);
      setDirectorPrompt({
        text: detail?.text || "",
        at: Date.now(),
        send: detail?.send,
        task: detail?.task,
        role: detail?.role,
      });
    };
    window.addEventListener("studio:ask-director", ask);
    return () => window.removeEventListener("studio:ask-director", ask);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the drawer's setter never changes the listener's job
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
    ? derivedStates(project, approvals, facts)
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
  const spokenLines = useSpokenLines(slug, project.spine);
  const drafted = Object.values(approvalStates).filter(
    (item) => item.via === "draft" && item.state === "approved",
  );
  const projectFacts: ProjectFacts = {
    ...project,
    stage_states: shellStates,
    titles_review_ready: titlesReady,
    prompt_version: intake?.prompt_version ?? null,
    profile_version: intake?.brief?.creative?.profile_version ?? 0,
    has_message: intake ? Boolean(intake.intent?.message?.trim()) : undefined,
    has_cta: intake
      ? Boolean(intake.intent?.cta?.text?.trim() || intake.intent?.cta?.url?.trim())
      : undefined,
    has_model_key: hasModelKey,
    has_storyboard: project.shots > 0,
    sound_cues: project.sound_cues,
    sound_sounding: project.sound_sounding,
    placeholder_shot_ids: board?.placeholder_shot_ids,
    permission_pending: (intake?.brief?.characters || [])
      .filter((character) => character.permission_confirmed === false)
      .map((character) => character.id),
  };
  const step = nextStep(stage, projectFacts, approvals, facts, budget || {});
  const baseAudio = project.audio_url || `/api/projects/${slug}/audio`;
  const committedWindow = intake?.audio_window || null;
  // Film is where the voiceover is heard; Track keeps listening to the music alone.
  const playerSrc =
    (stage === "film" || stage === "sound") && project.film_audio_url
      ? project.film_audio_url
      : committedWindow && project.kind !== "music_video"
        ? `${baseAudio}?v=${committedWindow.start}-${committedWindow.end}-${committedWindow.fade_in}-${committedWindow.fade_out}`
        : baseAudio;
  const spineBoard = board && editPayload ? applyEditBoard(board, editPayload) : board;

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
    if (action.target === "lyrics") {
      scrollTo("#track-lyrics");
      document.querySelector<HTMLElement>("#track-lyrics")?.focus({ preventScroll: true });
      return;
    }
    if (action.target === "changes") {
      if (stage !== "story") onNavigate("story");
      scrollTo("#story-changes", 180);
      return;
    }
    if (action.target === "brief") {
      if (stage !== "story") onNavigate("story");
      window.setTimeout(() => {
        window.dispatchEvent(new CustomEvent("studio:story-part", { detail: "concept" }));
      }, 0);
      scrollTo(".brief-card", 180);
      return;
    }
    if (action.target === "approval") {
      if (!document.querySelector(".signoff")) onNavigate(stage);
      scrollTo(".signoff");
      return;
    }
    if (action.target === "preview" || action.target === "render") {
      if (stage !== "film") onNavigate("film");
      setDeliveryAsk(Date.now());
      return;
    }
    if (action.target === "make-missing") {
      if (!action.paid) return;
      setPendingPaid(action.paid);
      if (stage !== "images") onNavigate("images");
      return;
    }
    if (action.target === "pictures") {
      if (stage !== "images") onNavigate("images");
      scrollTo(".images-body");
      return;
    }
    if (action.target === "world") {
      if (stage !== "story") onNavigate("story");
      window.setTimeout(() => {
        window.dispatchEvent(new CustomEvent("studio:story-part", { detail: "world" }));
      }, 0);
      return;
    }
    if (action.target === "settings") {
      onSettings();
      return;
    }
    if (action.target === "director") {
      setDirectorOpen(true);
      return;
    }
    if (action.target === "placeholders") {
      if (stage !== "storyboard") onNavigate("storyboard");
      window.setTimeout(() => {
        window.dispatchEvent(new CustomEvent("studio:show-unfinished-shots"));
      }, 0);
      return;
    }
    if (action.target === "board") {
      scrollTo(".storyboard-head");
    }
  };

  const stageIndex = STAGES.findIndex((item) => item.id === stage);
  const previousStage = stageIndex > 0 ? STAGES[stageIndex - 1] : null;

  return { act, approvalStates, approvalsLoaded, audioWindow, board, budget, commitAudioWindow, deliveryAsk, directorBusy, directorOpen, directorPrompt, directorShots, draftOpen, drafted, editOwnsTiming, filmFull, filmLine, filmSide, images, inspectShot, inspectorShot, intake, load, loadError, music, pendingPaid, playerSrc, previousStage, reserve, setAudioWindow, setBoard, setDirectorOpen, setDirectorShots, setDraftOpen, setFilmFull, setFilmLine, setFilmSide, setInspectorShot, setIntake, setPendingPaid, setStoryBands, setTitlesReady, shellStates, shotKinds, slug, spineBoard, spokenLines, states, step, storyBands, windowBusy };
}

function scrollTo(selector: string, delay = 60) {
  window.setTimeout(() => {
    document
      .querySelector(selector)
      ?.scrollIntoView({ behavior: scrollBehavior(), block: "center" });
  }, delay);
}
