import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type CutSection,
  type CutShot,
  type CutSummary,
  type DeliveryChecklist,
  type DeliveryLine,
  type EditPayload,
  type FilmExports,
  type FilmFile,
  type GraphicsReview,
  type ImageShot,
  type Storyboard,
} from "../api";
import { draftError } from "../api/resources";
import type { BaseFilmInput, EditTransition } from "../baseFilm";
import { filmFiles, selectFilm } from "../filmFiles";
import { useJobs, useProjectJobs } from "../jobs/store";
import { notifyProjectChanged, useProjectChanged } from "../shell/projectEvents";
import { SHOW_EDIT_FILE } from "../shell/SettingsDialog";
import { setEditTransition } from "./editTimeline";
import { deliveryWorkflow } from "./deliveryWorkflow";

export type LiveState = {
  input: BaseFilmInput;
  audio: string;
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
  stale: number;
  titles: BaseFilmInput["titles"];
  titlesNote: string | null;
};

function reviewKey(value: GraphicsReview | null): string {
  if (!value) return "none";
  return `${value.available}:${value.current}:${value.samples?.length ?? 0}`;
}

/** Everything Film reads and does: its data, gates, renders and approvals. */
export function useFilmData(slug: string) {
  const [files, setFiles] = useState<FilmFile[]>([]);
  const [signatureRequired, setSignatureRequired] = useState<boolean | undefined>();
  const [selected, setSelected] = useState<FilmFile | null>(null);
  const [live, setLive] = useState<LiveState | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [graphics, setGraphics] = useState<GraphicsReview | null>(null);
  const [rendererReady, setRendererReady] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cut, setCut] = useState<CutSummary | null>(null);
  const [checklist, setChecklist] = useState<DeliveryChecklist | null>(null);
  const [checklistError, setChecklistError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [board, setBoard] = useState<Storyboard | null>(null);
  const [images, setImages] = useState<ImageShot[]>([]);
  const [revision, setRevision] = useState(0);
  const [previewAttested, setPreviewAttested] = useState(false);
  const [inspected, setInspected] = useState(false);
  const [samplesOpen, setSamplesOpen] = useState(false);
  const [sampleIndex, setSampleIndex] = useState(0);
  const [showEditFile, setShowEditFile] = useState(
    () => window.localStorage.getItem(SHOW_EDIT_FILE) === "1",
  );
  const graphicsKey = useRef("");
  const previewsKey = useRef("");

  const applyFiles = useCallback((value: FilmExports) => {
    previewsKey.current = value.previews.join("|");
    const all = filmFiles(value);
    setFiles(all);
    setSignatureRequired(value.signature_required);
    setSelected((current) => selectFilm(all, current));
  }, []);

  const loadEpoch = useRef(0);
  const load = useCallback(async () => {
    const epoch = ++loadEpoch.current;
    const [
      filesResult,
      cutResult,
      checklistResult,
      boardResult,
      imagesResult,
      graphicsResult,
    ] = await Promise.allSettled([
      api.exports(slug),
      api.editSummary(slug),
      api.checklist(slug),
      api.storyboard(slug),
      api.images(slug),
      api.graphicsReview(slug),
    ]);
    if (epoch !== loadEpoch.current) return;
    const failure = [filesResult, cutResult, checklistResult, boardResult, imagesResult, graphicsResult].find((result) => result.status === "rejected");
    setError(failure?.status === "rejected" ? String(failure.reason) : null);
    if (filesResult.status === "fulfilled") applyFiles(filesResult.value);
    if (cutResult.status === "fulfilled") setCut(cutResult.value);
    if (checklistResult.status === "fulfilled") {
      setChecklist(checklistResult.value);
      setChecklistError(null);
    } else {
      setChecklistError(String(checklistResult.reason));
    }
    if (boardResult.status === "fulfilled") {
      setBoard("shots" in boardResult.value ? boardResult.value : null);
    }
    if (imagesResult.status === "fulfilled") setImages(imagesResult.value.shots);
    if (graphicsResult.status === "fulfilled") {
      setGraphics(graphicsResult.value);
      graphicsKey.current = reviewKey(graphicsResult.value);
    }
    setLoaded(true);
  }, [applyFiles, slug]);

  useEffect(() => {
    void load();
    return () => { loadEpoch.current += 1; };
  }, [load]);

  // Renders are background jobs; the server announces when one finishes (and
  // when any file behind this view changes), so nothing here polls.
  useProjectChanged(slug, () => {
    setShowEditFile(window.localStorage.getItem(SHOW_EDIT_FILE) === "1");
    setRevision((value) => value + 1);
    void load();
  });
  const renderJobs = useProjectJobs(slug, "render");
  const { jobs } = useJobs();
  const rendering = renderJobs.length > 0;

  useEffect(() => {
    let cancelled = false;
    api
      .preview(slug)
      .then((payload) => {
        if (cancelled) return;
        if (!payload.available) {
          setLive(null);
          setLiveError(
            payload.reason ?? "The storyboard must exist before a live preview can play.",
          );
          return;
        }
        const scale = Math.min(1, 1280 / payload.width);
        setLive({
          input: {
            shots: payload.shots,
            preview_banner: payload.preview_banner,
            preview_placeholders: payload.preview_placeholders,
            brand_plate: payload.brand_plate ?? null,
            brand_duration_frames: payload.brand_duration_frames,
          },
          audio: payload.audio,
          durationInFrames: payload.durationInFrames,
          fps: payload.fps,
          width: Math.round(payload.width * scale),
          height: Math.round(payload.height * scale),
          stale: payload.stale_shots.length,
          titles: payload.titles ?? null,
          titlesNote: payload.titles_note ?? null,
        });
        setLiveError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setLiveError("The live preview could not be read. Check the storyboard and stills.");
      });
    return () => {
      cancelled = true;
    };
  }, [slug, revision]);

  const seedCut = async () => {
    setBusy("seed");
    setError(null);
    setNotice(null);
    try {
      await api.seedEdit(slug);
      setCut(await api.editSummary(slug));
      setNotice("The Editor cut the film. Timing now comes from the cut.");
      setRevision((value) => value + 1);
      notifyProjectChanged();
      await load();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(null);
    }
  };

  /** Save a whole cut made elsewhere (a moved boundary). */
  const saveCut = async (next: EditPayload): Promise<boolean> => {
    setError(null);
    try {
      await api.saveEdit(slug, next, cut?.edit ?? undefined);
      setCut(await api.editSummary(slug));
      notifyProjectChanged();
      return true;
    } catch (caught) {
      setError(draftError(caught));
      return false;
    }
  };

  const saveTransition = async (shotId: string, change: Partial<EditTransition>, base: EditPayload): Promise<boolean> => {
    setBusy(`join:${shotId}`);
    setError(null);
    try {
      await api.saveEdit(slug, setEditTransition(base, shotId, change), base);
      setCut(await api.editSummary(slug));
      setNotice(`Saved the join into ${shotId}.`);
      notifyProjectChanged();
      await load();
      return true;
    } catch (caught) {
      setError(draftError(caught));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const render = async (kind: "preview" | "titles" | "base" | "final") => {
    setBusy(kind);
    setError(null);
    setNotice(
      `${
        kind === "final"
          ? "Final render"
          : kind === "titles"
            ? "Titles check"
            : kind === "base"
              ? "Base render"
              : "Preview"
      } queued. Progress shows below; the file appears in Rendered files when it is done.`,
    );
    try {
      await api.render(slug, kind);
      notifyProjectChanged();
      await load();
    } catch (caught) {
      setError(draftError(caught));
      setNotice(null);
    } finally {
      setBusy(null);
    }
  };

  const approvePreview = async (line: DeliveryLine) => {
    if (!line.expected_hash || !previewAttested) return;
    setBusy("preview-approval");
    setError(null);
    try {
      await api.approve(slug, "preview", {
        expected_hash: line.expected_hash,
        note: "",
        confirmed: true,
        preview_watched: true,
      });
      setPreviewAttested(false);
      setNotice("Preview approved.");
      notifyProjectChanged();
      await load();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(null);
    }
  };

  const approveTitles = async (line: DeliveryLine) => {
    if (!line.expected_hash || !inspected) return;
    setBusy("titles-approval");
    setError(null);
    try {
      await api.approve(slug, "graphics", {
        expected_hash: line.expected_hash,
        note: "",
        confirmed: true,
        inspected: true,
      });
      setInspected(false);
      setSamplesOpen(false);
      setNotice("Titles approved.");
      notifyProjectChanged();
      await load();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(null);
    }
  };

  const boardById = useMemo(
    () => new Map((board?.shots || []).map((shot) => [shot.id, shot])),
    [board],
  );
  const imageById = useMemo(
    () => new Map(images.map((image) => [image.id, image])),
    [images],
  );

  const groups = useMemo(() => {
    if (!cut?.present) return [];
    const sections: { section: CutSection; shots: CutShot[] }[] = cut.sections.map(
      (section) => ({
        section,
        shots: cut.shots.filter((shot) => shot.section_id === section.id),
      }),
    );
    const placed = new Set(sections.flatMap((group) => group.shots.map((shot) => shot.shot_id)));
    const orphan = cut.shots.filter((shot) => !placed.has(shot.shot_id));
    if (orphan.length) {
      sections.push({
        section: {
          id: "between",
          name: "Between sections",
          feel: "",
          start_frame: orphan[0].start_frame,
          end_frame: orphan[orphan.length - 1].start_frame + orphan[orphan.length - 1].duration_frames,
          techniques: [],
        },
        shots: orphan,
      });
    }
    return sections.filter((group) => group.shots.length > 0);
  }, [cut]);

  const line = (id: string) => checklist?.lines.find((item) => item.id === id) || null;
  const titlesLine = line("titles");
  const stillsDone = line("stills")?.state === "done";
  const samples = graphics?.samples || [];
  const canApproveTitles =
    !!titlesLine &&
    titlesLine.state !== "done" &&
    titlesLine.state !== "optional" &&
    !!titlesLine.expected_hash &&
    graphics?.current !== false &&
    inspected;
  const finalHint = checklist
    ? checklist.can_final
      ? "Every gate is approved. The final render is a local job."
      : `Still needed: ${checklist.outstanding.join(" · ")}`
    : "Reading the delivery gates…";
  const workflow = deliveryWorkflow(
    files,
    checklist,
    graphics,
    jobs.filter((job) => job.project === slug && job.kind === "render"),
  );

  return {
    slug,
    files,
    signatureRequired,
    selected,
    setSelected,
    live,
    liveError,
    graphics,
    rendererReady,
    setRendererReady,
    busy,
    notice,
    error,
    cut,
    checklist,
    checklistError,
    loaded,
    board,
    images,
    previewAttested,
    setPreviewAttested,
    inspected,
    setInspected,
    samplesOpen,
    setSamplesOpen,
    sampleIndex,
    setSampleIndex,
    showEditFile,
    rendering,
    boardById,
    imageById,
    groups,
    titlesLine,
    stillsDone,
    samples,
    canApproveTitles,
    finalHint,
    workflow,
    load,
    seedCut,
    saveCut,
    saveTransition,
    render,
    approvePreview,
    approveTitles,
  };
}

export type FilmData = ReturnType<typeof useFilmData>;
