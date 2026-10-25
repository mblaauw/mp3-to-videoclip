import { useEffect, useState } from "react";
import { api, type Job, type ProjectSummary } from "./api";
import { StoryboardStage } from "./stages/Storyboard";
import { StoryStage } from "./stages/Story";
import { ImagesStage } from "./stages/Images";
import { FilmStage } from "./stages/Film";
import { TrackStage } from "./stages/Track";

const STAGES = ["track", "story", "storyboard", "images", "film"] as const;
type Stage = (typeof STAGES)[number];

export function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [slug, setSlug] = useState<string | null>(null);
  const [stage, setStage] = useState<Stage>("track");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.projects().then(setProjects).catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="app">
      <aside className="rail">
        <div className="kicker">Studio</div>
        <h1>mp3-to-videoclip</h1>
        <ul>
          {projects.map((p) => (
            <li key={p.slug}>
              <button
                className={p.slug === slug ? "active" : ""}
                onClick={() => setSlug(p.slug)}
              >
                {p.title}
                <div className="meta">
                  {p.archived ? "archive" : "live"}
                  {p.duration ? ` · ${p.duration.toFixed(0)}s` : ""}
                </div>
              </button>
            </li>
          ))}
        </ul>
        {error && <p className="error">{error}</p>}
      </aside>

      <main className="main">
        {slug ? (
          <>
            <div className="tabs">
              {STAGES.map((s) => (
                <button key={s} className={s === stage ? "active" : ""} onClick={() => setStage(s)}>
                  {s}
                </button>
              ))}
            </div>
            <StageView slug={slug} stage={stage} />
          </>
        ) : (
          <p className="empty">Select a production.</p>
        )}
      </main>

      <Director slug={slug} stage={stage} />
      <JobTray />
    </div>
  );
}

function StageView({ slug, stage }: { slug: string; stage: Stage }) {
  if (stage === "track") return <TrackStage slug={slug} />;
  if (stage === "story") return <StoryStage slug={slug} />;
  if (stage === "storyboard") return <StoryboardStage slug={slug} />;
  if (stage === "images") return <ImagesStage slug={slug} />;
  return <FilmStage slug={slug} />;
}

function Director({ slug, stage }: { slug: string | null; stage: Stage }) {
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
    try {
      const res = await fetch(`/api/projects/${slug}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, stage }),
      });
      if (!res.ok || !res.body) throw new Error(await res.text());
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let assistant = "";
      setMessages((m) => [...m, { role: "assistant", text: "" }]);
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        for (const line of chunk.split("\n")) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.kind === "text") {
            assistant += event.text;
            setMessages((m) => {
              const copy = [...m];
              copy[copy.length - 1] = { role: "assistant", text: assistant };
              return copy;
            });
          }
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="director">
      <header>
        <h2>Director</h2>
        <div className="meta">{slug ? `project ${slug} · ${stage}` : "no project"}</div>
      </header>
      <div className="messages">
        {messages.map((m, i) => (
          <div className="msg" key={i}>
            <div className="who">{m.role}</div>
            <div className="body">{m.text}</div>
          </div>
        ))}
        {error && <p className="error">{error}</p>}
        {!messages.length && <p className="empty">Ask the director to change the film.</p>}
      </div>
      <div className="composer">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
          }}
          placeholder="Make the middle darker…"
        />
        <button onClick={send} disabled={busy || !slug}>
          {busy ? "…" : "Send"}
        </button>
      </div>
    </aside>
  );
}

function JobTray() {
  const [jobs, setJobs] = useState<Job[]>([]);
  useEffect(() => {
    let alive = true;
    const tick = () =>
      api
        .jobs()
        .then((j) => alive && setJobs(j.slice(0, 8)))
        .catch(() => {});
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);
  return (
    <footer className="tray">
      {jobs.length ? (
        jobs.map((j) => (
          <span key={j.id} className={`chip ${j.status}`}>
            {j.kind} · {j.status}
          </span>
        ))
      ) : (
        <span>No jobs yet.</span>
      )}
    </footer>
  );
}