import { useEffect, useState } from "react";
import { api, type Brief, type Budget, type Job, type ProjectSummary, type Storyboard } from "./api";

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

      <Director slug={slug} />
      <JobTray />
    </div>
  );
}

function StageView({ slug, stage }: { slug: string; stage: Stage }) {
  if (stage === "track") return <Track slug={slug} />;
  if (stage === "story") return <Story slug={slug} />;
  if (stage === "storyboard") return <StoryboardView slug={slug} />;
  if (stage === "images") return <Images slug={slug} />;
  return <Film slug={slug} />;
}

function Track({ slug }: { slug: string }) {
  const [data, setData] = useState<{ music: any; lyrics: any } | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.track(slug).then(setData).catch(() => setData(null));
  }, [slug]);
  const run = async () => {
    setBusy(true);
    try {
      await api.analyze(slug);
      setData(await api.track(slug));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <h2>Track</h2>
      <p className="sub">Music measurement and lyrics. Local analysis; no upload.</p>
      <div className="card">
        <h3>Analysis</h3>
        {data?.music ? (
          <div className="pre">{JSON.stringify(data.music, null, 2).slice(0, 2000)}</div>
        ) : (
          <p className="empty">No analysis yet.</p>
        )}
        <button onClick={run} disabled={busy}>{busy ? "Analyzing…" : "Run analysis"}</button>
      </div>
      <div className="card">
        <h3>Lyrics</h3>
        {data?.lyrics ? (
          <div className="pre">{JSON.stringify(data.lyrics, null, 2).slice(0, 2000)}</div>
        ) : (
          <p className="empty">Paste lyrics or transcribe (paid).</p>
        )}
      </div>
    </>
  );
}

function Story({ slug }: { slug: string }) {
  const [brief, setBrief] = useState<Brief | null>(null);
  useEffect(() => {
    api.brief(slug).then(setBrief).catch(() => setBrief(null));
  }, [slug]);
  return (
    <>
      <h2>Story</h2>
      <p className="sub">Treatment, look and characters. Ask the director to revise.</p>
      <div className="card">
        <h3>Treatment</h3>
        <div className="pre">{brief?.treatment || "No treatment yet."}</div>
      </div>
      <div className="card">
        <h3>Look</h3>
        <div className="pre">{brief?.creative?.look || "No creative look yet."}</div>
      </div>
      <div className="card">
        <h3>Characters</h3>
        {(brief?.characters || []).map((c) => (
          <div key={c.id} className="pre">
            {c.id}: {c.identity || c.description}
          </div>
        ))}
        {!brief?.characters?.length && <p className="empty">No characters.</p>}
      </div>
    </>
  );
}

function StoryboardView({ slug }: { slug: string }) {
  const [board, setBoard] = useState<Storyboard | null>(null);
  useEffect(() => {
    api.storyboard(slug).then(setBoard).catch(() => setBoard(null));
  }, [slug]);
  return (
    <>
      <h2>Storyboard</h2>
      <p className="sub">Integer-frame timeline; stable shot IDs.</p>
      <div className="card">
        {board ? (
          <table>
            <thead>
              <tr><th>Shot</th><th>Frames</th><th>Purpose</th><th>Camera</th></tr>
            </thead>
            <tbody>
              {board.shots.map((s) => (
                <tr key={s.id}>
                  <td>{s.id}</td>
                  <td>{s.start_frame}–{s.start_frame + s.duration_frames}</td>
                  <td>{s.purpose}</td>
                  <td>{s.camera}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="empty">No storyboard yet.</p>
        )}
      </div>
    </>
  );
}

function Images({ slug }: { slug: string }) {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    api.images(slug).then(setStatus).catch(() => setStatus(null));
  }, [slug]);
  return (
    <>
      <h2>Images</h2>
      <p className="sub">Versions per shot; select the one to render.</p>
      <div className="card">
        <div className="pre">{status ? JSON.stringify(status, null, 2).slice(0, 3000) : "No stills yet."}</div>
      </div>
    </>
  );
}

function Film({ slug }: { slug: string }) {
  const [exports, setExports] = useState<string[]>([]);
  const [budget, setBudget] = useState<Budget | null>(null);
  useEffect(() => {
    api.exports(slug).then((d) => setExports(d.exports)).catch(() => setExports([]));
    api.budget(slug).then(setBudget).catch(() => setBudget(null));
  }, [slug]);
  return (
    <>
      <h2>Film</h2>
      <p className="sub">Render, credits and exports.</p>
      <div className="card">
        <h3>Budget</h3>
        <div className="pre">
          cap {budget?.cap_usd ?? "—"} · committed {budget?.committed_usd ?? "—"} · remaining{" "}
          {budget?.remaining_usd ?? "—"}
        </div>
      </div>
      <div className="card">
        <h3>Exports</h3>
        {exports.length ? (
          exports.map((e) => <div key={e} className="pre">{e}</div>)
        ) : (
          <p className="empty">No renders yet.</p>
        )}
      </div>
    </>
  );
}

function Director({ slug }: { slug: string | null }) {
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
        body: JSON.stringify({ message }),
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
        <div className="meta">{slug ? `project ${slug}` : "no project"}</div>
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