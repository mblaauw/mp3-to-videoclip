import { Suspense, lazy, useEffect, useState } from "react";
import { api, type Budget, type GraphicsReview } from "../api";
import { ApprovalBar } from "../ApprovalBar";
import { RendererSetup } from "../RendererSetup";
import type { BaseFilmInput } from "../baseFilm";

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

export function FilmStage({ slug }: { slug: string }) {
  const [previews, setPreviews] = useState<string[]>([]);
  const [exports, setExports] = useState<string[]>([]);
  const [selected, setSelected] = useState<FilmFile | null>(null);
  const [live, setLive] = useState<LiveState | null>(null);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [graphics, setGraphics] = useState<GraphicsReview | null>(null);
  const [rendererReady, setRendererReady] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    api
      .exports(slug)
      .then((d) => {
        setPreviews(d.previews);
        setExports(d.exports);
        setSelected((current) => {
          const all = [
            ...d.previews.map((name) => ({ kind: "previews" as const, name })),
            ...d.exports.map((name) => ({ kind: "renders" as const, name })),
          ];
          if (current && all.some((f) => f.kind === current.kind && f.name === current.name)) {
            return current;
          }
          return all[0] || null;
        });
      })
      .catch(() => {
        setPreviews([]);
        setExports([]);
      });
    api
      .budget(slug)
      .then(setBudget)
      .catch(() => setBudget(null));
    api
      .graphicsReview(slug)
      .then(setGraphics)
      .catch(() => setGraphics(null));
  };

  useEffect(() => {
    load();
    // A render is a background job; keep watching until its file appears.
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [slug]);

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
      .catch((e) => {
        if (cancelled) return;
        setLive(null);
        setLiveError(`Live preview unavailable: ${String(e)}`);
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const render = async (kind: "preview" | "base" | "final") => {
    setBusy(kind);
    setError(null);
    setMessage(
      `${kind === "final" ? "Final" : kind === "base" ? "Base" : "Preview"} queued; it appears here when the job finishes.`,
    );
    try {
      await api.render(slug, kind);
      load();
    } catch (e) {
      setError(String(e));
      setMessage(null);
    } finally {
      setBusy(null);
    }
  };

  const src = selected
    ? `/api/projects/${slug}/film/${selected.kind}/${encodeURIComponent(selected.name)}`
    : null;
  const files: FilmFile[] = [
    ...previews.map((name) => ({ kind: "previews" as const, name })),
    ...exports.map((name) => ({ kind: "renders" as const, name })),
  ];

  return (
    <>
      <h2>Film</h2>
      <p className="sub">Watch the render, check the budget and download the export.</p>
      {error && <p className="error">{error}</p>}
      {message && <p className="message">{message}</p>}

      <div className="card live-preview">
        <h3>Live preview</h3>
        {live ? (
          <>
            <Suspense fallback={<p className="empty">Loading the player…</p>}>
              <LivePlayer
                input={live.input}
                audio={live.audio}
                durationInFrames={live.durationInFrames}
                fps={live.fps}
                width={live.width}
                height={live.height}
              />
            </Suspense>
            <p className="meta">
              {live.input.shots.filter((shot) => shot.src).length} of {live.input.shots.length}{" "}
              stills loaded · same timing, camera and transitions as the render
              {live.stale > 0
                ? ` · ${live.stale} selected still${live.stale === 1 ? " is" : "s are"} older than the storyboard`
                : ""}
            </p>
          </>
        ) : (
          <p className="empty">{liveError ?? "No storyboard yet."}</p>
        )}
      </div>

      <div className="card player">
        <h3>Screen</h3>
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
              <span>
                {selected.kind === "renders" ? "final" : "preview"} · {selected.name}
              </span>
              <a href={src} download={selected.name}>
                download
              </a>
            </div>
          </>
        ) : (
          <p className="empty">No renders yet. A preview is local and free.</p>
        )}
        {files.length > 0 && (
          <div className="files">
            {files.map((file) => (
              <button
                key={`${file.kind}/${file.name}`}
                className={
                  selected?.kind === file.kind && selected?.name === file.name ? "active" : ""
                }
                onClick={() => setSelected(file)}
              >
                {file.kind === "renders" ? "final" : "preview"} ·{" "}
                {file.name.replace(/^.*-v(\d+)\.mp4$/, "v$1")}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h3>Budget</h3>
        <div className="pre">
          cap {budget?.cap_usd ?? "—"} · committed {budget?.committed_usd ?? "—"} · remaining{" "}
          {budget?.remaining_usd ?? "—"}
        </div>
      </div>

      <RendererSetup onReady={setRendererReady} />

      {graphics?.available && (
        <div className="card">
          <h3>Graphics review</h3>
          <p className="meta">
            {graphics.current
              ? "These preflight frames are current. Inspect every sample, then approve graphics."
              : graphics.reason || "The graphics review is stale; render a current base."}
          </p>
          {graphics.warning && <p className="meta">{graphics.warning}</p>}
          <div className="versions">
            {(graphics.samples || []).map((sample) => (
              <figure className="version" key={sample.name}>
                <a href={sample.url} target="_blank" rel="noreferrer">
                  <img src={sample.url} alt={`Graphics preflight ${sample.name}`} loading="lazy" />
                </a>
                <figcaption className="meta">{sample.name}</figcaption>
              </figure>
            ))}
          </div>
          {!graphics.samples?.length && <p className="empty">No reviewed samples are present.</p>}
        </div>
      )}

      <div className="card">
        <h3>Render</h3>
        <button
          onClick={() => render("preview")}
          disabled={busy !== null || rendererReady === false}
        >
          {busy === "preview" ? "Queueing…" : "Render preview"}
        </button>{" "}
        <button
          onClick={() => render("base")}
          disabled={busy !== null || rendererReady === false}
        >
          {busy === "base" ? "Queueing…" : "Render base"}
        </button>{" "}
        <button
          onClick={() => render("final")}
          disabled={busy !== null || rendererReady === false}
        >
          {busy === "final" ? "Queueing…" : "Render final"}
        </button>
        <p className="meta">
          Preview is free and marked. A base carries the stills edit without graphics and
          creates the review samples above. A final composes the approved graphics onto that
          base and needs both the stills and graphics approvals.
        </p>
      </div>

      <ApprovalBar slug={slug} stages={["preview", "graphics"]} />
    </>
  );
}
