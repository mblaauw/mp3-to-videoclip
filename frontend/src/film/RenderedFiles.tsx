import { filmLabel } from "../filmFiles";
import { JobBanner } from "../jobs/JobBanner";
import { Button } from "../ui";
import type { FilmData } from "./useFilmData";

function films(name: string): string {
  return name.replace(/^.*-v(\d+)\.mp4$/, "v$1");
}

export function RenderedFiles({ film }: { film: FilmData }) {
  const { slug, selected, setSelected, signatureRequired, busy, rendering, render, checklist, files } = film;
  const src = selected
    ? `/api/projects/${slug}/film/${selected.kind}/${encodeURIComponent(selected.name)}`
    : null;
  return (
        <div className="film-files">
          <section className="card player">
            <header className="files-head">
              <h2>Screen</h2>
              {selected && (
                <span className="hint">
                  {filmLabel(selected, signatureRequired)} · {selected.name}
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
                No renders yet. A preview is local and free; delivery in the panel queues one.
              </p>
            )}
            <JobBanner slug={slug} kinds={["render"]} className="in-card" />
            <div className="row-actions">
              <Button
                size="small"
                disabled={busy !== null || rendering}
                onClick={() => void render("preview")}
              >
                {busy === "preview" ? "Queueing…" : "Render a new preview"}
              </Button>
              <Button
                size="small"
                variant="quiet"
                disabled={!checklist?.can_final || busy !== null || rendering}
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
                <p className="hint">Only a current verified final is ready for delivery.</p>
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
                        {filmLabel(file, signatureRequired)}
                      </span>
                      <span className="file-name">
                        {films(file.name)}
                        <em>{file.name}</em>
                      </span>
                      <Button
                        size="small"
                        onClick={() => {
                          setSelected(file);
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
  );
}
