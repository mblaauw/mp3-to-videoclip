import type { ProjectSummary } from "../api";
import { Button } from "../ui";
import { LeftIcon } from "../ui/icons";

function clock(seconds: number | null | undefined): string {
  const value = Math.max(0, Math.round(seconds || 0));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

export function ArchiveFilm({
  project,
  onBack,
}: {
  project: ProjectSummary;
  onBack: () => void;
}) {
  const stills = project.poster_stills || [];
  return (
    <main className="library-main archive-main">
      <div className="archive">
        <Button variant="quiet" size="small" onClick={onBack}>
          <LeftIcon /> Library
        </Button>
        <div className="archive-head">
          <div>
            <h1>{project.title}</h1>
            <p>
              Delivered film · {clock(project.duration)} · read-only. The archive keeps the
              render and its stills exactly as they were signed off.
            </p>
          </div>
        </div>
        <div className="archive-screen">
          {project.render ? (
            <video
              controls
              playsInline
              preload="metadata"
              aria-label={`${project.title} delivered film`}
              src={`/api/projects/${project.slug}/archive/render`}
            />
          ) : (
            <p className="empty">No render was recorded for this archive.</p>
          )}
        </div>
        {!!stills.length && (
          <div className="archive-stills">
            {stills.map((src, index) => (
              <a
                key={`${src}-${index}`}
                href={`/api/projects/${project.slug}/archive/stills/${index}`}
                target="_blank"
                rel="noreferrer"
              >
                <img src={src} alt={`Preserved still ${index + 1}`} loading="lazy" />
              </a>
            ))}
          </div>
        )}
        <p className="hint">{project.still_count} stills preserved in the archive.</p>
      </div>
    </main>
  );
}
