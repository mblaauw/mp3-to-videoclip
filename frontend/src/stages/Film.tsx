import { Suspense, lazy, useEffect, useState } from "react";
import { api, type Budget, type EditSummary, type GraphicsReview } from "../api";
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
  const [cut, setCut] = useState<EditSummary | null>(null);
  const [cutText, setCutText] = useState("");
  const [cutBusy, setCutBusy] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  const applyCut = (value: EditSummary) => {
    setCut(value);
    if (value.present && value.edit) {
      setCutText(JSON.stringify(value.edit, null, 2));
    } else {
      setCutText("");
    }
  };

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
    api
      .edit(slug)
      .then(applyCut)
      .catch(() => setCut(null));
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
  }, [slug, revision]);

  const seedCut = async () => {
    setCutBusy("seed");
    setError(null);
    try {
      const value = await api.seedEdit(slug);
      applyCut(value);
      setRevision((current) => current + 1);
      setMessage("Timing now lives in the edit list; the storyboard keeps content.");
    } catch (e) {
      setError(String(e));
    } finally {
      setCutBusy(null);
    }
  };

  const saveCut = async () => {
    setCutBusy("save");
    setError(null);
    try {
      const parsed = JSON.parse(cutText) as unknown;
      const value = await api.saveEdit(slug, parsed);
      applyCut(value);
      setRevision((current) => current + 1);
      setMessage(value.report.ok ? "Cut saved; the report has no hard findings." : "Cut saved; fix the hard findings.");
    } catch (e) {
      setError(`Cut not saved: ${String(e)}`);
    } finally {
      setCutBusy(null);
    }
  };

  const refreshCut = async () => {
    setCutBusy("report");
    setError(null);
    try {
      applyCut(await api.edit(slug));
      setRevision((current) => current + 1);
    } catch (e) {
      setError(String(e));
    } finally {
      setCutBusy(null);
    }
  };

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

      <div className="card">
        <h3>Cut report</h3>
        {cut?.present ? (
          <>
            <p className="meta">
              {cut.report.counts.shots ?? 0} shots · {cut.report.counts.cuts ?? 0} cuts ·{" "}
              {cut.report.counts.holds ?? 0} holds (
              {Math.round((cut.report.counts.hold_ratio ?? 0) * 100)}%) ·{" "}
              {cut.report.counts.accents ?? 0} accents ·{" "}
              {cut.report.counts.flashes ?? 0} flashes ·{" "}
              {cut.report.hard.length === 0
                ? "no hard findings"
                : `${cut.report.hard.length} hard finding${cut.report.hard.length === 1 ? "" : "s"}`}
            </p>
            {(cut.report.hard.length > 0 || cut.report.warnings.length > 0) && (
              <div className="pre">
                {cut.report.hard.map((finding) => (
                  <div key={`hard-${finding.code}-${finding.shot_id ?? ""}-${finding.message}`}>
                    HARD {finding.code}: {finding.message}
                  </div>
                ))}
                {cut.report.warnings.map((finding) => (
                  <div key={`warn-${finding.code}-${finding.shot_id ?? ""}-${finding.message}`}>
                    warning {finding.code}: {finding.message}
                  </div>
                ))}
              </div>
            )}
            {cut.report.sections.length > 0 && (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Section</th>
                      <th>Frames</th>
                      <th>Energy</th>
                      <th>Cuts / 10s</th>
                      <th>Holds</th>
                      <th>Flashes</th>
                      <th>Plan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cut.report.sections.map((section) => (
                      <tr key={section.id}>
                        <td>{section.id}</td>
                        <td>
                          {section.start_frame}–{section.end_frame}
                        </td>
                        <td>{section.energy ?? "—"}</td>
                        <td>
                          {section.density_per_10s} / {section.target_density_per_10s}
                        </td>
                        <td>
                          {section.holds}/{section.shots}
                        </td>
                        <td>{section.flashes}</td>
                        <td>{section.techniques.join(", ") || section.feel}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {cut.report.techniques.length > 0 && (
              <p className="meta">
                Techniques:{" "}
                {cut.report.techniques
                  .map(
                    (item) =>
                      `${item.name} ×${item.count}${item.reasoned ? "" : " (no stated reason)"}`,
                  )
                  .join(" · ")}
              </p>
            )}
            <button onClick={refreshCut} disabled={cutBusy !== null}>
              {cutBusy === "report" ? "Reading…" : "Re-run report"}
            </button>{" "}
            <details>
              <summary>Edit JSON</summary>
              <textarea
                value={cutText}
                onChange={(event) => setCutText(event.target.value)}
                rows={16}
                spellCheck={false}
                style={{ width: "100%", fontFamily: "monospace" }}
              />
              <button onClick={saveCut} disabled={cutBusy !== null}>
                {cutBusy === "save" ? "Saving…" : "Save cut"}
              </button>
            </details>
          </>
        ) : (
          <>
            <p className="meta">
              Timing is still the storyboard's. Seed an edit to move order, spans, motion,
              transitions, accents, text timing and grade into <code>work/edit.json</code>.
            </p>
            <button onClick={seedCut} disabled={cutBusy !== null}>
              {cutBusy === "seed" ? "Seeding…" : "Move timing into an edit"}
            </button>
          </>
        )}
      </div>

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
