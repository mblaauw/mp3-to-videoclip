import { useState, type DragEvent as ReactDragEvent } from "react";
import type { ProjectSummary } from "../api";
import { NewProduction } from "../NewProduction";
import { Button, StatusDot, type StatusTone } from "../ui";
import { PlusIcon } from "../ui/icons";
import { stageLabel } from "./stages";
import type { Stage } from "./nextStep";

const STAGE_ORDER = ["track", "story", "storyboard", "images", "film"] as const;

const NEXT_LABEL: Record<string, string> = {
  track: "Measure the song",
  story: "Approve the story",
  storyboard: "Approve the storyboard",
  images: "Review the pictures",
  film: "Render the final",
};

const STATE_TONE: Record<string, StatusTone> = {
  done: "done",
  you: "you",
  changed: "changed",
  not_ready: "idle",
  running: "run",
};

function clock(seconds: number | null | undefined): string {
  const value = Math.max(0, Math.round(seconds || 0));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

function nextLabel(project: ProjectSummary): string {
  if (!project.next_step) return "Delivered";
  const state = project.stage_states?.[project.next_step];
  if (state === "changed") return `${NEXT_LABEL[project.next_step] || "Review"} again`;
  return NEXT_LABEL[project.next_step] || `Continue to ${stageLabel(project.next_step as Stage)}`;
}

function Poster({ project }: { project: ProjectSummary }) {
  const images = project.poster_stills || [];
  return (
    <div className={`poster ${images.length === 1 ? "one" : ""}`}>
      {images.length ? (
        images.map((src, index) => (
          <img key={`${src}-${index}`} src={src} alt="" loading="lazy" />
        ))
      ) : (
        <div className="empty-art">No pictures yet</div>
      )}
    </div>
  );
}

function Progress({ project }: { project: ProjectSummary }) {
  return (
    <div className="progress" aria-hidden="true">
      {STAGE_ORDER.map((stage) => {
        const state = project.stage_states?.[stage] || "not_ready";
        return <i key={stage} className={state} />;
      })}
    </div>
  );
}

function FilmCard({
  project,
  onOpen,
}: {
  project: ProjectSummary;
  onOpen: (slug: string, stage: string) => void;
}) {
  if (project.error) {
    return (
      <div className="film-card broken" title={project.error}>
        <div className="poster one">
          <div className="empty-art">Unreadable</div>
        </div>
        <h3>{project.title}</h3>
        <p className="hint">{project.error}</p>
      </div>
    );
  }
  return (
    <button
      type="button"
      className="film-card"
      onClick={() => onOpen(project.slug, project.next_step || "film")}
    >
      <Poster project={project} />
      <Progress project={project} />
      <h3>{project.title}</h3>
      <div className="facts">
        <span>{clock(project.duration)}</span>
        <span>
          {project.music_mode === "instrumental" || project.music_mode === "music-led"
            ? "Instrumental"
            : `${project.shots || 0} shots`}
        </span>
        {project.remaining_usd && <span>${project.remaining_usd} left</span>}
      </div>
      <div className="todo">
        <StatusDot tone={STATE_TONE[project.stage_states?.[project.next_step || ""] || "you"]} />
        <span>{nextLabel(project)}</span>
      </div>
    </button>
  );
}

export function Library({
  projects,
  loading,
  error,
  onOpen,
  onArchive,
  onCreated,
}: {
  projects: ProjectSummary[];
  loading: boolean;
  error: string | null;
  onOpen: (slug: string, stage: string) => void;
  onArchive: (slug: string) => void;
  onCreated: (slug: string) => void;
}) {
  const [newFile, setNewFile] = useState<File | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const active = projects.filter((project) => !project.archived);
  const delivered = projects.filter((project) => project.archived);
  const summary = `${active.length} in progress${delivered.length ? `, ${delivered.length} delivered` : ""}.`;

  const startNew = (file: File | null = null) => {
    setNewFile(file);
    setNewOpen(true);
  };

  const drop = (event: ReactDragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files?.[0];
    if (file) startNew(file);
  };

  return (
    <main className="library-main">
      <div className="library">
        <div className="library-head">
          <div className="grow">
            <h1>Your films</h1>
            <p>{loading ? "Loading the library…" : summary}</p>
          </div>
          <Button variant="primary" onClick={() => startNew()}>
            <PlusIcon /> New film
          </Button>
        </div>
        {error && <p className="error">{error}</p>}
        {!loading && !active.length && !delivered.length && (
          <p className="empty">No films yet. Drop an MP3 below to start one.</p>
        )}
        <div className="film-grid">
          {active.map((project) => (
            <FilmCard key={project.slug} project={project} onOpen={onOpen} />
          ))}
          <div
            className={`new-card ${dragging ? "dragging" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={drop}
            onClick={() => startNew()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") startNew();
            }}
          >
            Drop an MP3 to start a new film
          </div>
        </div>
        {!!delivered.length && (
          <section className="library-section">
            <h2>Delivered</h2>
            <div className="film-grid">
              {delivered.map((project) => (
                <button
                  type="button"
                  className="film-card"
                  key={project.slug}
                  onClick={() => onArchive(project.slug)}
                >
                  <Poster project={project} />
                  <h3>{project.title}</h3>
                  <div className="facts">
                    <span>{clock(project.duration)}</span>
                    <span>{project.render || "Final render"}</span>
                    {project.updated_at && (
                      <span>Delivered {new Date(project.updated_at).toLocaleDateString()}</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
      {newOpen && (
        <div className="modal-scrim" role="presentation" onMouseDown={() => setNewOpen(false)}>
          <div
            className="modal-panel"
            role="dialog"
            aria-modal="true"
            aria-label="New film"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <NewProduction
              initialFile={newFile}
              onCreated={(slug) => {
                setNewOpen(false);
                onCreated(slug);
              }}
              onCancel={() => setNewOpen(false)}
            />
          </div>
        </div>
      )}
    </main>
  );
}
