import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { readApiError } from "../api/errors";
import { usePlayer } from "../spine/player";
import { Button, StatusDot } from "../ui";
import { CloseIcon } from "../ui/icons";
import { stageLabel } from "./stages";
import type { Stage } from "./nextStep";
import { notifyProjectChanged } from "./projectEvents";

type Role = "writer" | "editor";

type ChatItem =
  | { kind: "user" | "assistant"; text: string }
  | {
      kind: "tool";
      id: number;
      tool: string;
      args: string;
      result: string;
      done: boolean;
      undone: boolean;
      undoError: string | null;
    };

type StreamEvent = {
  kind: string;
  text?: string;
  tool?: string;
  arguments?: string;
  result?: string;
  payload?: Record<string, unknown>;
};

const TOOL_LABEL: Record<string, string> = {
  get_project: "Read the project",
  get_brief: "Read the story",
  get_storyboard: "Read the storyboard",
  get_edit: "Read the cut",
  update_edit: "Rewrote the cut",
  get_music_summary: "Read the music",
  get_lyrics: "Read the lyrics",
  get_treatments: "Read the concepts",
  update_treatments: "Rewrote the concepts",
  get_images: "Looked at the pictures",
  update_brief: "Changed the story",
  update_shots: "Changed the storyboard",
  create_storyboard: "Made the storyboard",
  generate_images: "Made pictures",
  transcribe_lyrics: "Transcribed lyrics",
  render: "Queued a render",
  set_proof_shots: "Changed the style check",
  ask_user: "Asked you",
};

const UNDO_ARTIFACT: Record<string, string> = {
  update_brief: "brief",
  update_shots: "storyboard",
  update_edit: "edit",
  update_treatments: "treatments",
};

const MONEY_TOOLS = new Set(["generate_images", "transcribe_lyrics"]);

function modelLabel(model: unknown): string {
  const raw = String(model || "");
  const name = raw.split("/").pop() || raw;
  return name
    .split("-")
    .map((part) => {
      if (/^gpt$/i.test(part)) return "GPT";
      if (/^deepseek$/i.test(part)) return "DeepSeek";
      if (/^ai$/i.test(part)) return "AI";
      return part ? part[0].toUpperCase() + part.slice(1) : part;
    })
    .join(" ");
}

function clock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

function parse(value: string): Record<string, unknown> | null {
  try {
    const data = JSON.parse(value) as unknown;
    return typeof data === "object" && data ? (data as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function summaryFor(tool: string, result: string): string {
  const data = parse(result);
  if (!data) return result && !result.startsWith("{") ? result.slice(0, 160) : "Done";
  if (typeof data.error === "string") return `Could not: ${data.error}`;
  if (data.needs_budget === true) {
    const decision = data.decision as Record<string, unknown> | undefined;
    return `Needs ${
      decision?.suggested_usd ? `$${Number(decision.suggested_usd).toFixed(2)} more` : "more budget"
    } before this can run.`;
  }
  if (typeof data.needs_confirmation === "string") return data.needs_confirmation;
  if (Array.isArray(data.changed)) {
    const ids = data.changed as string[];
    return ids.length
      ? `Saved ${ids.length} shot${ids.length === 1 ? "" : "s"}: ${ids.slice(0, 4).join(", ")}${
          ids.length > 4 ? "…" : ""
        }`
      : "No shot changed.";
  }
  if (Array.isArray(data.proof_shot_ids)) {
    return `Style check: ${(data.proof_shot_ids as string[]).join(", ")}`;
  }
  if (typeof data.status === "string" && data.status === "queued") {
    const job = data.job_id ? ` · job ${String(data.job_id).slice(0, 8)}` : "";
    return `Queued${job}`;
  }
  if (data.estimate && typeof data.estimate === "object") {
    const estimate = data.estimate as Record<string, unknown>;
    const tasks = Number(estimate.tasks || 0);
    const reserve = Number(estimate.reserve_usd || 0);
    return `${tasks} still${tasks === 1 ? "" : "s"} · $${reserve.toFixed(2)} reserved`;
  }
  if (data.report && typeof data.report === "object") {
    const report = data.report as Record<string, unknown>;
    const hard = Array.isArray(report.hard) ? report.hard.length : 0;
    const counts = (report.counts || {}) as Record<string, unknown>;
    const label = tool === "get_edit" ? "Read" : "Cut saved";
    return `${label} · ${Number(counts.shots || 0)} shots · ${
      hard ? `${hard} hard finding${hard === 1 ? "" : "s"}` : "no hard findings"
    }`;
  }
  if (tool === "update_brief") return "Story saved.";
  if (tool === "update_treatments") return "Concepts saved.";
  if (tool === "create_storyboard") return "Storyboard made.";
  if (tool === "get_storyboard" && Array.isArray(data.shots)) {
    return `Read ${(data.shots as unknown[]).length} shots.`;
  }
  if (tool === "get_brief") return "Read the story.";
  if (data.storyboard && typeof data.storyboard === "object") {
    const board = data.storyboard as Record<string, unknown>;
    return `Storyboard saved · ${Array.isArray(board.shots) ? board.shots.length : 0} shots`;
  }
  if (data.ask_user) return String(data.ask_user);
  if (tool.startsWith("get_")) return "Read.";
  return "Done.";
}

function argumentSummary(tool: string, args: string): string {
  const data = parse(args);
  if (!data) return "";
  if (tool === "generate_images") {
    const ids = Array.isArray(data.shot_ids) ? (data.shot_ids as string[]) : [];
    return ids.length
      ? `${ids.length} shot${ids.length === 1 ? "" : "s"} · ${ids.slice(0, 3).join(", ")}${
          ids.length > 3 ? "…" : ""
        }`
      : "";
  }
  if (tool === "update_shots") {
    const changes = Array.isArray(data.changes) ? data.changes.length : 0;
    return changes ? `${changes} change${changes === 1 ? "" : "s"}` : "";
  }
  if (tool === "update_edit" || tool === "create_storyboard") {
    const edit = (data.edit || data) as Record<string, unknown>;
    const shots = Array.isArray(edit.shots) ? edit.shots.length : null;
    return shots ? `${shots} shots` : "";
  }
  if (tool === "render") return String(data.kind || "preview");
  if (tool === "set_proof_shots" && Array.isArray(data.shot_ids)) {
    return (data.shot_ids as string[]).join(", ");
  }
  if (tool === "update_treatments" && Array.isArray(data.concepts)) {
    return `${(data.concepts as unknown[]).length} concepts`;
  }
  return "";
}

function ToolCard({
  item,
  onUndo,
}: {
  item: Extract<ChatItem, { kind: "tool" }>;
  onUndo: (item: Extract<ChatItem, { kind: "tool" }>) => void;
}) {
  const data = parse(item.result);
  const failed = typeof data?.error === "string";
  const money = MONEY_TOOLS.has(item.tool) && !failed;
  const label = TOOL_LABEL[item.tool] || item.tool.replace(/_/g, " ");
  const args = argumentSummary(item.tool, item.args);
  const summary = item.done ? summaryFor(item.tool, item.result) : "Working…";
  const undoable = !!UNDO_ARTIFACT[item.tool];
  return (
    <article className={`tool-card ${failed ? "failed" : ""} ${money ? "money" : ""}`}>
      <header>
        <span className={`tool-dot ${item.done ? "done" : "run"}`} aria-hidden="true" />
        <b>{label}</b>
        {args && <span className="tool-args">{args}</span>}
        <span className="tool-state">{item.done ? (failed ? "Failed" : "Done") : "Running"}</span>
      </header>
      <p className="tool-summary">{summary}</p>
      {(item.args || item.result) && (
        <details className="tool-detail">
          <summary>Details</summary>
          {item.args && (
            <>
              <span>Asked for</span>
              <pre>{item.args.slice(0, 4000)}</pre>
            </>
          )}
          {item.result && (
            <>
              <span>Result</span>
              <pre>{item.result.slice(0, 6000)}</pre>
            </>
          )}
        </details>
      )}
      {undoable && item.done && !failed && (
        <div className="tool-actions">
          <Button
            size="small"
            variant="quiet"
            disabled={item.undone}
            onClick={() => onUndo(item)}
          >
            {item.undone ? "Undone" : "Undo"}
          </Button>
          {item.undoError && <span className="tool-error">{item.undoError}</span>}
        </div>
      )}
    </article>
  );
}

export function Director({
  slug,
  stage,
  open,
  prefill = null,
  selectedShots = [],
  onClose,
  onSettings,
}: {
  slug: string;
  stage: Stage;
  open: boolean;
  prefill?: { text: string; at: number } | null;
  selectedShots?: string[];
  onClose: () => void;
  onSettings: () => void;
}) {
  const player = usePlayer();
  const defaultRole: Role = ["story", "storyboard", "images"].includes(stage)
    ? "writer"
    : "editor";
  const [items, setItems] = useState<ChatItem[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [role, setRole] = useState<Role>(defaultRole);
  const [gateway, setGateway] = useState("opencode");
  const [models, setModels] = useState<{ writer: string; editor: string }>({
    writer: "the configured Writer",
    editor: "the configured Editor",
  });
  const stopRef = useRef<AbortController | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const seq = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setRole(defaultRole);
    setError(null);
    // A stage change changes who answers; the conversation stays.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        setModels({
          writer: modelLabel(settings.writer_model),
          editor: modelLabel(settings.editor_model),
        });
        setGateway(settings.gateway === "direct" ? "direct" : "opencode");
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!prefill?.text) return;
    setText(prefill.text);
    const element = composerRef.current;
    if (element) {
      element.focus();
      element.setSelectionRange(prefill.text.length, prefill.text.length);
    }
  }, [prefill?.at, prefill?.text]);

  useEffect(() => {
    api
      .chat(slug)
      .then((data) =>
        setItems(
          (data.messages as { role: string; content?: string }[])
            .filter((message) => message.role === "user" || message.role === "assistant")
            .map((message) => ({
              kind: message.role === "user" ? ("user" as const) : ("assistant" as const),
              text: message.content || "",
            })),
        ),
      )
      .catch(() => setItems([]));
  }, [slug]);

  useEffect(() => {
    const element = listRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [items, busy]);

  const addToolStart = (event: StreamEvent) => {
    seq.current += 1;
    setItems((current) => [
      ...current,
      {
        kind: "tool",
        id: seq.current,
        tool: event.tool || "tool",
        args: event.arguments || "",
        result: "",
        done: false,
        undone: false,
        undoError: null,
      },
    ]);
  };

  const addToolResult = (event: StreamEvent) => {
    setItems((current) => {
      const copy = [...current];
      for (let index = copy.length - 1; index >= 0; index -= 1) {
        const item = copy[index];
        if (item.kind === "tool" && item.tool === (event.tool || "tool") && !item.done) {
          copy[index] = { ...item, result: event.result || "", done: true };
          return copy;
        }
      }
      seq.current += 1;
      copy.push({
        kind: "tool",
        id: seq.current,
        tool: event.tool || "tool",
        args: "",
        result: event.result || "",
        done: true,
        undone: false,
        undoError: null,
      });
      return copy;
    });
    if (event.tool && UNDO_ARTIFACT[event.tool]) notifyProjectChanged();
  };

  const appendAssistant = (chunk: string) => {
    setItems((current) => {
      if (!chunk) return current;
      const copy = [...current];
      const last = copy[copy.length - 1];
      if (last?.kind === "assistant") {
        copy[copy.length - 1] = { ...last, text: last.text + chunk };
      } else {
        copy.push({ kind: "assistant", text: chunk });
      }
      return copy;
    });
  };

  const send = async () => {
    if (!text.trim() || busy) return;
    const message = text.trim();
    setText("");
    setItems((current) => [...current, { kind: "user", text: message }]);
    setBusy(true);
    setError(null);
    const controller = new AbortController();
    stopRef.current = controller;
    try {
      const response = await fetch(`/api/projects/${slug}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          stage,
          role,
          context: {
            stage,
            time: Math.max(0, Number(player.time) || 0),
            ...(selectedShots.length ? { selected_shots: selectedShots } : {}),
          },
        }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        const apiError = await readApiError(response);
        setError(apiError.message);
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      const consume = (line: string) => {
        if (!line.trim()) return;
        let event: StreamEvent;
        try {
          event = JSON.parse(line) as StreamEvent;
        } catch {
          return;
        }
        if (event.kind === "text") appendAssistant(event.text || "");
        else if (event.kind === "tool") {
          if (event.result) addToolResult(event);
          else addToolStart(event);
        } else if (event.kind === "ask") {
          const question = event.text || String(event.payload?.question || "");
          setItems((current) => {
            const copy = [...current];
            for (let index = copy.length - 1; index >= 0; index -= 1) {
              const item = copy[index];
              if (item.kind === "tool" && item.tool === "ask_user" && !item.done) {
                copy[index] = {
                  ...item,
                  done: true,
                  result: JSON.stringify({
                    ask_user: question,
                    options: event.payload?.options || [],
                  }),
                };
                break;
              }
            }
            return copy;
          });
          appendAssistant(question);
        }
      };
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
    } catch (caught) {
      if ((caught as Error).name !== "AbortError") setError(String(caught));
    } finally {
      stopRef.current = null;
      setBusy(false);
    }
  };

  const stop = () => {
    stopRef.current?.abort();
    stopRef.current = null;
    setBusy(false);
  };

  const undo = async (item: Extract<ChatItem, { kind: "tool" }>) => {
    const artifact = UNDO_ARTIFACT[item.tool];
    if (!artifact) return;
    setItems((current) =>
      current.map((entry) =>
        entry.kind === "tool" && entry.id === item.id
          ? { ...entry, undoError: null }
          : entry,
      ),
    );
    try {
      await api.restoreHistory(slug, artifact);
      setItems((current) =>
        current.map((entry) =>
          entry.kind === "tool" && entry.id === item.id
            ? { ...entry, undone: true }
            : entry,
        ),
      );
      notifyProjectChanged();
    } catch (caught) {
      setItems((current) =>
        current.map((entry) =>
          entry.kind === "tool" && entry.id === item.id
            ? { ...entry, undoError: String(caught) }
            : entry,
        ),
      );
    }
  };

  const model = role === "writer" ? models.writer : models.editor;
  const missingKey = /no llm key|llm key|model key|api key|unauthor/i.test(error || "");

  return (
    <aside className={`director ${open ? "open" : "closed"}`} aria-label="Director">
      <header>
        <div className="director-heading">
          <h2>Director</h2>
          <div className="director-model">
            {role === "writer" ? "Writer" : "Editor"} · {model}
            {gateway === "direct" && <span className="director-gateway">Direct API</span>}
          </div>
        </div>
        <button type="button" className="icon-btn" aria-label="Close director" onClick={onClose}>
          <CloseIcon />
        </button>
      </header>
      <div className="role-row" role="group" aria-label="Who answers">
        <button
          type="button"
          className={role === "writer" ? "on" : ""}
          aria-pressed={role === "writer"}
          onClick={() => setRole("writer")}
        >
          Ask the Writer
        </button>
        <button
          type="button"
          className={role === "editor" ? "on" : ""}
          aria-pressed={role === "editor"}
          onClick={() => setRole("editor")}
        >
          Ask the Editor
        </button>
      </div>
      <div className="messages" aria-live="polite" ref={listRef}>
        {items.map((item, index) =>
          item.kind === "tool" ? (
            <ToolCard key={`tool-${item.id}`} item={item} onUndo={(value) => void undo(value)} />
          ) : (
            <div className={`msg ${item.kind === "user" ? "user" : "assistant"}`} key={index}>
              <div className="who">{item.kind}</div>
              <div className="body">{item.text}</div>
            </div>
          ),
        )}
        {busy && (
          <div className="director-activity">
            <StatusDot tone="run" /> Working…
          </div>
        )}
        {error && (
          <div className="director-error" role="alert">
            {missingKey ? (
              <>
                <p>The director has no model key.</p>
                <p className="hint">Add the key in Settings, then ask again.</p>
              </>
            ) : (
              <>
                <p>Something went wrong while asking the director.</p>
                <details>
                  <summary>Copy details</summary>
                  <pre>{error}</pre>
                </details>
              </>
            )}
            <Button size="small" onClick={onSettings}>
              Open settings
            </Button>
          </div>
        )}
        {!items.length && !busy && !error && (
          <p className="empty">Ask for a change. The stage and playhead travel with the message.</p>
        )}
      </div>
      <div className="composer">
        <div className="context" aria-label="Sent with your message">
          <span className="chip">{stageLabel(stage)}</span>
          <span className="chip">{clock(player.time)}</span>
          {selectedShots.map((shot) => (
            <span className="chip shot" key={shot}>
              {shot}
            </span>
          ))}
        </div>
        <div className="composer-row">
          <textarea
            ref={composerRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
            rows={1}
            placeholder="Ask for a change…"
            aria-label="Message the director"
          />
          <Button
            variant={busy ? "default" : "primary"}
            onClick={busy ? stop : () => void send()}
            disabled={!busy && !text.trim()}
          >
            {busy ? "Stop" : "Send"}
          </Button>
        </div>
      </div>
    </aside>
  );
}
