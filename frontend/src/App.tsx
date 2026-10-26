import { useEffect, useRef, useState } from "react";
import { api, type ProjectSummary } from "./api";
import { readApiError } from "./api/errors";
import { useJobs } from "./jobs/store";
import { Pill, StatusDot, type PillTone, type StatusTone } from "./ui";
import { StoryboardStage } from "./stages/Storyboard";
import { StoryStage } from "./stages/Story";
import { ImagesStage } from "./stages/Images";
import { FilmStage } from "./stages/Film";
import { TrackStage } from "./stages/Track";
import { NewProduction } from "./NewProduction";
import { ToastTray } from "./ToastTray";
import { toast } from "./toast";

const STAGES = ["track", "story", "storyboard", "images", "film"] as const;
type Stage = (typeof STAGES)[number];

export function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [slug, setSlug] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("track");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selected = projects.find((p) => p.slug === slug) || null;

  const created = async (newSlug: string) => {
    setCreating(false);
    try {
      setProjects(await api.projects());
    } catch (e) {
      setError(String(e));
    }
    setSlug(newSlug);
    setStage("track");
  };

  useEffect(() => {
    api.projects().then(setProjects).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="app">
      <aside className="rail">
        <div className="kicker">Studio</div>
        <h1>mp3-to-videoclip</h1>
        <button className="new" onClick={() => setCreating(true)}>
          + New production
        </button>
        <ul>
          {projects.map((p) => (
            <li key={p.slug}>
              <button
                className={p.slug === slug ? "active" : ""}
                aria-current={p.slug === slug ? "true" : undefined}
                aria-disabled={!!p.error}
                disabled={!!p.error}
                title={p.error ?? undefined}
                onClick={() => setSlug(p.slug)}
              >
                {p.title}
                <div className="meta">
                  {p.error
                    ? "unreadable"
                    : `${p.archived ? "archive" : (p.kind || "live").replace("_", " ")}${p.duration ? ` · ${p.duration.toFixed(0)}s` : ""}`}
                </div>
                {p.error && <div className="meta error">{p.error}</div>}
              </button>
            </li>
          ))}
        </ul>
        {error && <p className="error">{error}</p>}
      </aside>

      <main className="main">
        {creating ? (
          <NewProduction onCreated={created} onCancel={() => setCreating(false)} />
        ) : selected ? (
          selected.archived ? (
            <ArchivedFilm project={selected} />
          ) : (
            <>
              <div className="tabs">
                {STAGES.map((s) => (
                  <button
                    key={s}
                    className={s === stage ? "active" : ""}
                    aria-pressed={s === stage}
                    onClick={() => setStage(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
              <StageView key={selected.slug} slug={selected.slug} stage={stage} />
            </>
          )
        ) : (
          <p className="empty">Select a production or start a new one.</p>
        )}
      </main>

      <Director
        key={creating || selected?.archived ? "none" : (slug ?? "none")}
        slug={creating || selected?.archived ? null : slug}
        stage={stage}
        archived={!!selected?.archived}
      />
      <JobTray />
      <ToastTray />
    </div>
  );
}

function ArchivedFilm({ project }: { project: ProjectSummary }) {
  return (
    <>
      <h2>{project.title}</h2>
      <p className="sub">
        Finished film, read-only. The archive keeps the delivered render and its stills exactly as
        they were signed off.
      </p>
      <div className="card">
        <h3>Delivered film</h3>
        <div className="pre">{project.render ?? "No render recorded."}</div>
      </div>
      <div className="card">
        <h3>Stills</h3>
        <div className="pre">{project.still_count} stills preserved in the archive.</div>
      </div>
    </>
  );
}

function StageView({ slug, stage }: { slug: string; stage: Stage }) {
  if (stage === "track") return <TrackStage slug={slug} />;
  if (stage === "story") return <StoryStage slug={slug} />;
  if (stage === "storyboard") return <StoryboardStage slug={slug} />;
  if (stage === "images") return <ImagesStage slug={slug} />;
  return <FilmStage slug={slug} />;
}

function Director({
  slug,
  stage,
  archived,
}: {
  slug: string | null;
  stage: Stage;
  archived: boolean;
}) {
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const stopRef = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!slug) return;
    api
      .chat(slug)
      .then((d) => setMessages((d.messages as any[]).map((m) => ({ role: m.role, text: m.content || "" }))))
      .catch(() => setMessages([]));
  }, [slug]);

  const send = async () => {
    if (!slug || !text.trim() || busy) return;
    const message = text.trim();
    setText("");
    setMessages((m) => [...m, { role: "user", text: message }]);
    setBusy(true);
    setError(null);
    const controller = new AbortController();
    stopRef.current = controller;
    try {
      const res = await fetch(`/api/projects/${slug}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, stage }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        const error = await readApiError(res);
        toast(error.message);
        throw error;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let assistant = "";
      let buffer = "";
      const consume = (line: string) => {
        if (!line.trim()) return;
        const event = JSON.parse(line);
        if (event.kind !== "text") return;
        assistant += event.text;
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { role: "assistant", text: assistant };
          return copy;
        });
      };
      setMessages((m) => [...m, { role: "assistant", text: "" }]);
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) consume(line);
      }
      buffer += decoder.decode();
      if (buffer.trim()) consume(buffer);
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError(String(e));
    } finally {
      stopRef.current = null;
      setBusy(false);
    }
  };

  const stop = () => {
    stopRef.current?.abort();
  };

  return (
    <aside className="director">
      <header>
        <h2>Director</h2>
        <div className="meta">
          {archived ? "archive · read-only" : slug ? `project ${slug} · ${stage}` : "no project"}
        </div>
      </header>
      <div className="messages">
        {messages.map((m, i) => (
          <div className="msg" key={i}>
            <div className="who">{m.role}</div>
            <div className="body">{m.text}</div>
          </div>
        ))}
        {error && <p className="error">{error}</p>}
        {!messages.length && (
          <p className="empty">
            {archived
              ? "This film is delivered; the director does not change archives."
              : "Ask the director to change the film."}
          </p>
        )}
      </div>
      {!archived && (
        <div className="composer">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
            }}
            placeholder="Make the middle darker…"
          />
          <button
            onClick={busy ? stop : send}
            disabled={!slug || (!busy && !text.trim())}
            aria-label={busy ? "Stop the director" : "Send the message"}
          >
            {busy ? "Stop" : "Send"}
          </button>
        </div>
      )}
    </aside>
  );
}

const JOB_STATUS: Record<string, { tone: StatusTone; pill: PillTone; label: string }> = {
  queued: { tone: "you", pill: "neutral", label: "Queued" },
  running: { tone: "run", pill: "you", label: "Running" },
  succeeded: { tone: "done", pill: "keep", label: "Done" },
  failed: { tone: "err", pill: "redo", label: "Failed" },
  cancelled: { tone: "idle", pill: "neutral", label: "Cancelled" },
  needs_budget: { tone: "you", pill: "you", label: "Needs budget" },
  interrupted: { tone: "err", pill: "redo", label: "Interrupted" },
};

function jobProgress(job: { progress: { done: number; total: number; unit: string } }) {
  const { done, total, unit } = job.progress;
  // The backend cannot report real progress yet. Never invent a percentage.
  return total > 0 ? `${done} of ${total} ${unit}`.trim() : "";
}

function JobTray() {
  const { jobs, connection } = useJobs();
  const visible = jobs.slice(0, 8);
  return (
    <footer className="tray" aria-label="Background jobs">
      {visible.length ? (
        visible.map((job) => {
          const status = JOB_STATUS[job.status] || {
            tone: "idle" as const,
            pill: "neutral" as const,
            label: job.status,
          };
          const progress = jobProgress(job);
          return (
            <span className="job-chip" key={job.id} title={job.error || undefined}>
              <StatusDot tone={status.tone} />
              <span className="job-name">{job.kind.replaceAll("_", " ")}</span>
              <Pill tone={status.pill}>{status.label}</Pill>
              {progress && <span className="job-progress">{progress}</span>}
              {!progress && job.status === "running" && (
                <span className="job-progress">working…</span>
              )}
              {job.cost_usd > 0 && (
                <span className="job-progress">${job.cost_usd.toFixed(2)}</span>
              )}
            </span>
          );
        })
      ) : (
        <span>{connection === "retrying" ? "Jobs reconnecting…" : "No jobs yet."}</span>
      )}
      {visible.length > 0 && connection === "retrying" && (
        <span className="job-connection">reconnecting…</span>
      )}
    </footer>
  );
}