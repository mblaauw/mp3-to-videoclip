import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type CutSection,
  type CutShot,
  type CutSummary,
  type DeliveryChecklist,
  type DeliveryLine,
  type GraphicsReview,
  type ImageShot,
  type Storyboard,
} from "../api";
import { ArtifactRating } from "../ArtifactRating";
import { RendererSetup } from "../RendererSetup";
import type { BaseFilmInput } from "../baseFilm";
import type { EditTransition } from "../baseFilm";
import { setEditTransition, TRANSITION_TYPES } from "../film/editTimeline";
import type { Stage } from "../shell/nextStep";
import { notifyProjectChanged, PROJECT_CHANGED } from "../shell/projectEvents";
import { SHOW_EDIT_FILE } from "../shell/SettingsDialog";
import { usePlayer } from "../spine/player";
import { CreditsCard } from "../story/CreditsCard";
import { ShotThumb } from "../storyboard/ShotThumb";
import { Button, ErrorState, LoadingState, useFocusTrap } from "../ui";
const LivePlayer = lazy(() => import("../LivePlayer"));

type FilmFile = { kind: "previews" | "renders"; name: string };

type LiveState = {
  input: BaseFilmInput;
  audio: string;
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
  stale: number;
};

function clock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

function duration(seconds: number): string {
  return `${seconds.toFixed(1)} s`;
}

function films(name: string): string {
  return name.replace(/^.*-v(\d+)\.mp4$/, "v$1");
}

function reviewKey(value: GraphicsReview | null): string {
  if (!value) return "none";
  return `${value.available}:${value.current}:${value.samples?.length ?? 0}`;
}

function TransitionEditor({
  shot,
  busy,
  onSave,
}: {
  shot: CutShot;
  busy: boolean;
  onSave: (change: Partial<EditTransition>) => Promise<void>;
}) {
  const [type, setType] = useState<EditTransition["type"]>(
    (shot.transition.type as EditTransition["type"]) || "cut",
  );
  const [frames, setFrames] = useState(shot.transition.frames);
  const [reason, setReason] = useState(shot.transition.reason || "");
  const [saving, setSaving] = useState(false);
  const named = type !== "cut";
  const canSave =
    named && reason.trim().length > 0 && !saving && !busy && frames >= 0 && frames <= 48;

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      await onSave({ type, frames, reason: reason.trim() });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="cut-transition-edit">
      <label>
        <span>Into {shot.shot_id}</span>
        <select
          aria-label={`Transition into ${shot.shot_id}`}
          value={type}
          disabled={saving}
          onChange={(event) => {
            const next = event.target.value as EditTransition["type"];
            setType(next);
            if (next !== "cut" && frames === 0) setFrames(6);
          }}
        >
          {TRANSITION_TYPES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Frames</span>
        <input
          aria-label={`Transition frames into ${shot.shot_id}`}
          type="number"
          min={0}
          max={48}
          value={frames}
          disabled={!named || saving}
          onChange={(event) => setFrames(Number(event.target.value))}
        />
      </label>
      {named && (
        <label className="reason">
          <span>Why this join</span>
          <input
            aria-label={`Reason for the join into ${shot.shot_id}`}
            value={reason}
            maxLength={240}
            disabled={saving}
            placeholder="Lift the chorus…"
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
      )}
      <Button size="small" disabled={!canSave} onClick={() => void save()}>
        {saving ? "Saving…" : "Save join"}
      </Button>
    </div>
  );
}

export function FilmStage({
  slug,
  onNavigate,
}: {
  slug: string;
  onNavigate: (stage: Stage) => void;
}) {
  const player = usePlayer();
  const [tab, setTab] = useState<"cut" | "files">("cut");
  const [previews, setPreviews] = useState<string[]>([]);
  const [exports, setExports] = useState<string[]>([]);
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
  const samplesRef = useRef<HTMLDivElement>(null);

  const applyFiles = useCallback((value: { exports: string[]; previews: string[] }) => {
    previewsKey.current = value.previews.join("|");
    setPreviews(value.previews);
    setExports(value.exports);
    setSelected((current) => {
      const all = [
        ...value.previews.map((name) => ({ kind: "previews" as const, name })),
        ...value.exports.map((name) => ({ kind: "renders" as const, name })),
      ];
      if (current && all.some((file) => file.kind === current.kind && file.name === current.name)) {
        return current;
      }
      return all[0] || null;
    });
  }, []);

  const load = useCallback(async () => {
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
    if (filesResult.status === "fulfilled") applyFiles(filesResult.value);
    if (cutResult.status === "fulfilled") setCut(cutResult.value);
    else setCut(null);
    if (checklistResult.status === "fulfilled") {
      setChecklist(checklistResult.value);
      setChecklistError(null);
    } else {
      setChecklist(null);
      setChecklistError(String(checklistResult.reason));
    }
    if (boardResult.status === "fulfilled") {
      setBoard("shots" in boardResult.value ? boardResult.value : null);
    }
    if (imagesResult.status === "fulfilled") setImages(imagesResult.value.shots);
    if (graphicsResult.status === "fulfilled") {
      setGraphics(graphicsResult.value);
      graphicsKey.current = reviewKey(graphicsResult.value);
    } else {
      setGraphics(null);
    }
    setLoaded(true);
  }, [applyFiles, slug]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    // Renders are background jobs. Poll only the cheap file and sample lists;
    // the full checklist re-hashes every accepted still and must not run on a timer.
    const id = window.setInterval(() => {
      void Promise.allSettled([api.exports(slug), api.graphicsReview(slug)]).then(
        ([filesResult, reviewResult]) => {
          if (filesResult.status === "fulfilled") {
            const changed =
              filesResult.value.previews.join("|") !== previewsKey.current;
            applyFiles(filesResult.value);
            if (changed) {
              void load();
              return;
            }
          }
          if (reviewResult.status === "fulfilled") {
            const next = reviewKey(reviewResult.value);
            if (next !== graphicsKey.current) {
              graphicsKey.current = next;
              setGraphics(reviewResult.value);
              void load();
            }
          }
        },
      );
    }, 5000);
    return () => window.clearInterval(id);
  }, [applyFiles, load, slug]);

  useEffect(() => {
    const refresh = () => {
      setShowEditFile(window.localStorage.getItem(SHOW_EDIT_FILE) === "1");
      setRevision((value) => value + 1);
      void load();
    };
    window.addEventListener(PROJECT_CHANGED, refresh);
    return () => window.removeEventListener(PROJECT_CHANGED, refresh);
  }, [load]);

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
        });
        setLiveError(null);
      })
      .catch(() => {
        if (cancelled) return;
        setLive(null);
        setLiveError("The live preview could not be read. Check the storyboard and stills.");
      });
    return () => {
      cancelled = true;
    };
  }, [slug, revision]);

  useFocusTrap(samplesOpen && (graphics?.samples?.length || 0) > 0, samplesRef);

  useEffect(() => {
    if (!samplesOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSamplesOpen(false);
      if (event.key === "ArrowRight") {
        setSampleIndex((index) =>
          Math.min(index + 1, Math.max((graphics?.samples?.length || 1) - 1, 0)),
        );
      }
      if (event.key === "ArrowLeft") setSampleIndex((index) => Math.max(index - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [samplesOpen, graphics?.samples?.length]);

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

  const saveTransition = async (shotId: string, change: Partial<EditTransition>) => {
    if (!cut?.edit) return;
    setBusy(`join:${shotId}`);
    setError(null);
    try {
      await api.saveEdit(slug, setEditTransition(cut.edit, shotId, change));
      setCut(await api.editSummary(slug));
      setNotice(`Saved the join into ${shotId}.`);
      notifyProjectChanged();
      await load();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(null);
    }
  };

  const render = async (kind: "preview" | "base" | "final") => {
    setBusy(kind);
    setError(null);
    setNotice(
      `${
        kind === "final" ? "Final render" : kind === "base" ? "Titles check" : "Preview"
      } queued. It appears in Rendered files when the job finishes.`,
    );
    try {
      await api.render(slug, kind);
      notifyProjectChanged();
      await load();
    } catch (caught) {
      setError(String(caught));
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

  const files: FilmFile[] = [
    ...previews.map((name) => ({ kind: "previews" as const, name })),
    ...exports.map((name) => ({ kind: "renders" as const, name })),
  ];
  const src = selected
    ? `/api/projects/${slug}/film/${selected.kind}/${encodeURIComponent(selected.name)}`
    : null;

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

  const fps = board?.fps || 24;
  const currentCutShot = cut?.shots.find(
    (shot) =>
      player.time >= shot.start_frame / fps &&
      player.time < (shot.start_frame + shot.duration_frames) / fps,
  );
  const currentBoardShot = currentCutShot
    ? boardById.get(currentCutShot.shot_id)
    : board?.shots.find(
        (shot) =>
          player.time >= shot.start_frame / fps &&
          player.time < (shot.start_frame + shot.duration_frames) / fps,
      );
  const currentPicture = currentBoardShot ? imageById.get(currentBoardShot.id) : undefined;
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

  return (
    <>
      <div className="stage-head film-head">
        <div>
          <h1>Film</h1>
          <p>
            Watch the cut, check the titles on real frames and render delivery. Everything
            runs on this computer.
          </p>
        </div>
        <div className="board-tabs" role="group" aria-label="Film view">
          <Button
            size="small"
            variant={tab === "cut" ? "primary" : "quiet"}
            aria-pressed={tab === "cut"}
            onClick={() => setTab("cut")}
          >
            Cut
          </Button>
          <Button
            size="small"
            variant={tab === "files" ? "primary" : "quiet"}
            aria-pressed={tab === "files"}
            onClick={() => setTab("files")}
          >
            Rendered files
          </Button>
        </div>
      </div>
      {error && (
        <ErrorState
          what="working on the film"
          error={error}
          compact
          onRetry={() => void load()}
        />
      )}
      {notice && <p className="message">{notice}</p>}

      <RendererSetup onReady={setRendererReady} />

      {!loaded ? (
        <LoadingState>Reading the film, its gates and the cut…</LoadingState>
      ) : tab === "cut" ? (
        <div className="film-cut">
          {rendererReady !== false && (
            <section className="delivery-card">
              <header>
                <div>
                  <h2>Ready to deliver</h2>
                  <p>
                    {checklist?.can_final
                      ? "All gates are approved."
                      : "Each line is a real gate; the final stays disabled until they pass."}
                  </p>
                </div>
                {checklist && (
                  <span className={`delivery-state ${checklist.can_final ? "ready" : ""}`}>
                    {checklist.can_final ? "Ready" : `${checklist.outstanding.length} to go`}
                  </span>
                )}
              </header>
              <ul className="check-list">
                {(checklist?.lines || []).map((item) => (
                  <li key={item.id} className={`check-item ${item.state}`}>
                    <span className="check-mark" aria-hidden="true">
                      {item.state === "done" ? "✓" : item.state === "optional" ? "–" : "•"}
                    </span>
                    <div className="check-copy">
                      <b>{item.label}</b>
                      <span>{item.detail}</span>
                      {item.state !== "done" && item.reason && item.id !== "stills" && (
                        <em>{item.reason}</em>
                      )}
                      {item.id === "preview" &&
                        item.state !== "done" &&
                        item.expected_hash && (
                          <span className="check-attest">
                            <label className="check-line">
                              <input
                                type="checkbox"
                                checked={previewAttested}
                                onChange={(event) => setPreviewAttested(event.target.checked)}
                              />
                              I watched it continuously with the actual music
                            </label>
                            <Button
                              size="small"
                              disabled={!previewAttested || busy !== null}
                              onClick={() => void approvePreview(item)}
                            >
                              {busy === "preview-approval" ? "Approving…" : "Approve preview"}
                            </Button>
                          </span>
                        )}
                      {item.id === "preview" && item.state !== "done" && !item.expected_hash && (
                        <span className="check-attest">
                          <Button
                            size="small"
                            variant="primary"
                            disabled={busy !== null}
                            onClick={() => void render("preview")}
                          >
                            {busy === "preview" ? "Queueing…" : "Watch preview"}
                          </Button>
                        </span>
                      )}
                      {item.id === "titles" && item.state !== "done" && item.state !== "optional" && (
                        <span className="check-attest">
                          {samples.length > 0 && (
                            <>
                              <button
                                type="button"
                                className="samples-strip"
                                onClick={() => {
                                  setSampleIndex(0);
                                  setSamplesOpen(true);
                                }}
                                aria-label="Open the graphics samples"
                              >
                                {samples.slice(0, 4).map((sample) => (
                                  <img key={sample.name} src={sample.url} alt="" loading="lazy" />
                                ))}
                              </button>
                              <label className="check-line">
                                <input
                                  type="checkbox"
                                  checked={inspected}
                                  onChange={(event) => setInspected(event.target.checked)}
                                />
                                I inspected every sample
                              </label>
                              <Button
                                size="small"
                                disabled={!canApproveTitles || busy !== null}
                                onClick={() => void approveTitles(item)}
                              >
                                {busy === "titles-approval" ? "Approving…" : "Approve titles"}
                              </Button>
                            </>
                          )}
                          <Button
                            size="small"
                            variant={samples.length ? "quiet" : "primary"}
                            disabled={!stillsDone || busy !== null}
                            title={
                              stillsDone
                                ? "Render a base and read the real title frames"
                                : "Approve every still first."
                            }
                            onClick={() => void render("base")}
                          >
                            {busy === "base" ? "Queueing…" : "Check titles"}
                          </Button>
                        </span>
                      )}
                    </div>
                    {item.id === "story" && item.state !== "done" && (
                      <Button size="small" variant="quiet" onClick={() => onNavigate("story")}>
                        Go to Story
                      </Button>
                    )}
                    {item.id === "storyboard" && item.state !== "done" && (
                      <Button
                        size="small"
                        variant="quiet"
                        onClick={() => onNavigate("storyboard")}
                      >
                        Go to Storyboard
                      </Button>
                    )}
                    {item.id === "stills" && item.state !== "done" && (
                      <Button size="small" variant="quiet" onClick={() => onNavigate("images")}>
                        Go to Images
                      </Button>
                    )}
                  </li>
                ))}
                {!checklist && (
                  <li className="check-item blocked">
                    {checklistError
                      ? "The delivery gates cannot be read yet. Make the story and storyboard first."
                      : "Reading the gates…"}
                  </li>
                )}
              </ul>
              <footer>
                <Button
                  variant="primary"
                  disabled={!checklist?.can_final || busy !== null}
                  onClick={() => void render("final")}
                >
                  {busy === "final" ? "Queueing…" : "Render final"}
                </Button>
                <span className="hint">{finalHint}</span>
              </footer>
            </section>
          )}

          <section className="cut-section">
            <header className="cut-head">
              <div>
                <h2>{cut?.present ? "The cut" : "The film cut"}</h2>
                <p>
                  {cut?.present
                    ? "How each shot arrives, what moves, and why. The cut owns timing."
                    : "The storyboard owns timing until the Editor cuts the film."}
                </p>
              </div>
              <ArtifactRating slug={slug} artifact="edit" />
            </header>

            {!board ? (
              <div className="card seed-cut">
                <h3>The storyboard comes first</h3>
                <p>
                  Film reads the cut from the approved storyboard. Make the storyboard,
                  then let the Editor cut it.
                </p>
                <div className="row-actions">
                  <Button variant="primary" onClick={() => onNavigate("storyboard")}>
                    Go to Storyboard
                  </Button>
                </div>
              </div>
            ) : !cut?.present ? (
              <div className="card seed-cut">
                <h3>Let the Editor cut it</h3>
                <p>
                  The film already plays with the storyboard's timing. Move order, spans,
                  motion, transitions, accents and grade into a cut to shape it.
                </p>
                <div className="row-actions">
                  <Button
                    variant="primary"
                    disabled={busy !== null}
                    onClick={() => void seedCut()}
                  >
                    {busy === "seed" ? "Cutting…" : "Make a first cut"}
                  </Button>
                  <Button variant="quiet" onClick={() => setTab("files")}>
                    Keep the storyboard timing
                  </Button>
                </div>
                <p className="hint">
                  Keeping it costs nothing and keeps every current approval valid.
                </p>
              </div>
            ) : (
              <>
                {cut.hard.length > 0 && (
                  <div className="cut-findings hard">
                    <b>
                      {cut.hard.length} hard finding{cut.hard.length === 1 ? "" : "s"}
                    </b>
                    {cut.hard.map((finding) => (
                      <span key={`${finding.code}-${finding.shot_id || ""}-${finding.message}`}>
                        {finding.shot_id ? `${finding.shot_id}: ` : ""}
                        {finding.message}
                      </span>
                    ))}
                  </div>
                )}
                {cut.warnings.length > 0 && (
                  <details className="cut-findings warning-details">
                    <summary>
                      {cut.warnings.length} warning{cut.warnings.length === 1 ? "" : "s"}
                    </summary>
                    {cut.warnings.map((finding) => (
                      <span key={`${finding.code}-${finding.shot_id || ""}-${finding.message}`}>
                        {finding.shot_id ? `${finding.shot_id}: ` : ""}
                        {finding.message}
                      </span>
                    ))}
                  </details>
                )}
                <div className="cut-facts">
                  <span>{cut.counts.shots ?? 0} shots</span>
                  <span>{cut.counts.cuts ?? 0} cuts</span>
                  <span>
                    {cut.counts.holds ?? 0} holds (
                    {Math.round((cut.counts.hold_ratio || 0) * 100)}%)
                  </span>
                  <span>{cut.counts.accents ?? 0} accents</span>
                  {cut.grade && <span>Grade: {cut.grade}</span>}
                </div>
                {cut.techniques.length > 0 && (
                  <div className="cut-techniques" aria-label="Techniques in this cut">
                    {cut.techniques.map((technique) => (
                      <span
                        className="technique"
                        key={technique.name}
                        title={technique.reasons.join(" · ") || undefined}
                      >
                        {technique.name}
                        {technique.count > 1 ? ` ×${technique.count}` : ""}
                      </span>
                    ))}
                  </div>
                )}
                {cut.notes && <p className="cut-notes">{cut.notes}</p>}

                <div className="cut-sections">
                  {groups.map((group) => (
                    <section className="cut-group" key={group.section.id}>
                      <header>
                        <h3>{group.section.name}</h3>
                        <span className="hint">
                          {clock(group.section.start_frame / fps)}–
                          {clock(group.section.end_frame / fps)} · {group.shots.length}{" "}
                          {group.shots.length === 1 ? "shot" : "shots"}
                        </span>
                      </header>
                      <div className="cut-list">
                        {group.shots.map((shot) => {
                          const source = boardById.get(shot.shot_id);
                          return (
                            <article className="cut-shot" key={shot.shot_id}>
                              {source ? (
                                <ShotThumb
                                  slug={slug}
                                  shot={source}
                                  image={imageById.get(source.id)}
                                  className="cut-thumb"
                                />
                              ) : (
                                <div className="cut-thumb shot-thumb" />
                              )}
                              <div className="cut-shot-body">
                                <div className="cut-shot-line">
                                  <b>{shot.shot_id}</b>
                                  <span>{clock(shot.start_frame / fps)}</span>
                                  <span>{duration(shot.seconds)}</span>
                                  <span className="cut-arrival">{shot.transition.label}</span>
                                  <span className="cut-motion">{shot.motion.label}</span>
                                </div>
                                <p className="cut-shot-job">
                                  {source?.message || source?.purpose || "No shot content."}
                                </p>
                                <div className="cut-shot-tags">
                                  {shot.accents.map((accent) => (
                                    <span className="accent" key={`${accent.frame}-${accent.type}`}>
                                      {accent.label}
                                    </span>
                                  ))}
                                  {shot.text.map((item) => (
                                    <span className="cut-text" key={item.id}>
                                      “{item.text}”
                                    </span>
                                  ))}
                                </div>
                                {shot.reasons.length > 0 && (
                                  <div className="cut-why">
                                    {shot.reasons.map((reason) => (
                                      <span key={`${reason.kind}-${reason.label}-${reason.reason}`}>
                                        <b>{reason.label}</b> {reason.reason}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {cut.edit && (
                                  <TransitionEditor
                                    key={`${shot.shot_id}-${shot.transition.type}-${shot.transition.frames}-${shot.transition.reason}`}
                                    shot={shot}
                                    busy={busy === `join:${shot.shot_id}`}
                                    onSave={(change) => saveTransition(shot.shot_id, change)}
                                  />
                                )}
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  ))}
                </div>

                {cut.edit && showEditFile && (
                  <details className="cut-json">
                    <summary>Edit file (read-only)</summary>
                    <pre>{JSON.stringify(cut.edit, null, 2)}</pre>
                  </details>
                )}
              </>
            )}
          </section>

          <section className="card live-preview">
            <header className="live-head">
              <div>
                <h3>Live preview</h3>
                <p className="hint">
                  Free, marked and local. Same timing, camera and transitions as the render.
                </p>
              </div>
              {currentBoardShot && (
                <div className="live-now">
                  <b>{currentBoardShot.id}</b>
                  <span>{currentBoardShot.message || currentBoardShot.purpose}</span>
                  {currentPicture?.stale && <em>Older prompt</em>}
                </div>
              )}
            </header>
            {live ? (
              <>
                <Suspense fallback={<p className="empty">Loading the player…</p>}>
                  <LivePlayer
                    input={live.input}
                    audio={null}
                    durationInFrames={live.durationInFrames}
                    fps={live.fps}
                    width={live.width}
                    height={live.height}
                    time={player.time}
                    playing={player.playing}
                  />
                </Suspense>
                <p className="hint">
                  {live.input.shots.filter((shot) => shot.src).length} of{" "}
                  {live.input.shots.length} stills loaded
                  {live.stale > 0
                    ? ` · ${live.stale} selected still${
                        live.stale === 1 ? " is" : "s are"
                      } older than the storyboard`
                    : ""}
                </p>
              </>
            ) : (
              <p className="empty">{liveError ?? "No storyboard yet."}</p>
            )}
          </section>

          <CreditsCard slug={slug} />
        </div>
      ) : (
        <div className="film-files">
          <section className="card player">
            <header className="files-head">
              <h2>Screen</h2>
              {selected && (
                <span className="hint">
                  {selected.kind === "renders" ? "final" : "preview"} · {selected.name}
                </span>
              )}
            </header>
            {src && selected ? (
              <>
                <video
                  key={src}
                  controls
                  playsInline
                  preload="metadata"
                  aria-label="Rendered film"
                  src={src}
                />
                <div className="film-meta">
                  <a href={src} download={selected.name}>
                    Download {selected.name}
                  </a>
                </div>
              </>
            ) : (
              <p className="empty">
                No renders yet. A preview is local and free; the checklist queues one.
              </p>
            )}
            <div className="row-actions">
              <Button
                size="small"
                disabled={busy !== null}
                onClick={() => void render("preview")}
              >
                {busy === "preview" ? "Queueing…" : "Watch a new preview"}
              </Button>
              <Button
                size="small"
                variant="quiet"
                disabled={!checklist?.can_final || busy !== null}
                onClick={() => void render("final")}
              >
                {busy === "final" ? "Queueing…" : "Render final"}
              </Button>
            </div>
          </section>

          <section className="files-section">
            <header className="files-head">
              <div>
                <h2>Rendered files</h2>
                <p className="hint">Newest first. Previews are marked; finals are delivery.</p>
              </div>
            </header>
            {files.length === 0 ? (
              <p className="empty">Nothing rendered yet.</p>
            ) : (
              <ul className="file-list">
                {files.map((file) => {
                  const href = `/api/projects/${slug}/film/${file.kind}/${encodeURIComponent(
                    file.name,
                  )}`;
                  const active =
                    selected?.kind === file.kind && selected?.name === file.name;
                  return (
                    <li key={`${file.kind}/${file.name}`} className={active ? "active" : ""}>
                      <span className={`file-kind ${file.kind}`}>
                        {file.kind === "renders" ? "final" : "preview"}
                      </span>
                      <span className="file-name">
                        {films(file.name)}
                        <em>{file.name}</em>
                      </span>
                      <Button
                        size="small"
                        onClick={() => {
                          setSelected(file);
                          setTab("files");
                        }}
                      >
                        Play
                      </Button>
                      <a className="file-download" href={href} download={file.name}>
                        Download
                      </a>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      )}

      {samplesOpen && samples.length > 0 && (
        <div
          className="samples-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="Graphics samples"
          ref={samplesRef}
        >
          <header>
            <b>{samples[sampleIndex]?.name || "Sample"}</b>
            <span>
              {sampleIndex + 1} of {samples.length}
            </span>
            <button
              type="button"
              className="lightbox-close"
              aria-label="Close the samples"
              onClick={() => setSamplesOpen(false)}
            >
              ×
            </button>
          </header>
          <div className="samples-stage">
            <img src={samples[sampleIndex]?.url} alt={`Graphics sample ${sampleIndex + 1}`} />
          </div>
          <footer>
            <Button
              size="small"
              variant="quiet"
              onClick={() => setSampleIndex((index) => Math.max(index - 1, 0))}
            >
              ←
            </Button>
            <Button
              size="small"
              variant="quiet"
              onClick={() =>
                setSampleIndex((index) => Math.min(index + 1, samples.length - 1))
              }
            >
              →
            </Button>
            <label className="check-line">
              <input
                type="checkbox"
                checked={inspected}
                onChange={(event) => setInspected(event.target.checked)}
              />
              I inspected every sample
            </label>
            {titlesLine && (
              <Button
                size="small"
                variant="primary"
                disabled={!canApproveTitles || busy !== null}
                onClick={() => void approveTitles(titlesLine)}
              >
                {busy === "titles-approval" ? "Approving…" : "Approve titles"}
              </Button>
            )}
            <Button size="small" variant="quiet" onClick={() => setSamplesOpen(false)}>
              Close
            </Button>
          </footer>
        </div>
      )}
    </>
  );
}
