import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { readApiError } from "../api/errors";
import { usePlayer } from "../spine/player";
import { toast } from "../toast";
import { Button, StatusDot } from "../ui";
import { CloseIcon } from "../ui/icons";
import { stageLabel } from "./stages";
import type { Stage } from "./nextStep";

function modelLabel(model: unknown): string {
  const raw = String(model || "");
  const name = raw.split("/").pop() || raw;
  return name
    .split("-")
    .map((part) => {
      if (/^gpt$/i.test(part)) return "GPT";
      if (/^ai$/i.test(part)) return "AI";
      return part ? part[0].toUpperCase() + part.slice(1) : part;
    })
    .join(" ");
}

function clock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

export function Director({
  slug,
  stage,
  open,
  onClose,
  onSettings,
}: {
  slug: string;
  stage: Stage;
  open: boolean;
  onClose: () => void;
  onSettings: () => void;
}) {
  const player = usePlayer();
  const [messages, setMessages] = useState<{ role: string; text: string }[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<{ writer: string; editor: string }>({
    writer: "the configured Writer",
    editor: "the configured Editor",
  });
  const stopRef = useRef<AbortController | null>(null);

  const writer = ["story", "storyboard", "images"].includes(stage);
  const role = writer ? "Writer" : "Editor";
  const model = writer ? models.writer : models.editor;

  useEffect(() => {
    api
      .settings()
      .then((settings) => {
        setModels({
          writer: modelLabel(settings.writer_model),
          editor: modelLabel(settings.editor_model),
        });
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    api
      .chat(slug)
      .then((data) =>
        setMessages(
          (data.messages as { role: string; content?: string }[]).map((message) => ({
            role: message.role,
            text: message.content || "",
          })),
        ),
      )
      .catch(() => setMessages([]));
  }, [slug]);

  const send = async () => {
    if (!text.trim() || busy) return;
    const message = text.trim();
    setText("");
    setMessages((current) => [...current, { role: "user", text: message }]);
    setBusy(true);
    setError(null);
    const controller = new AbortController();
    stopRef.current = controller;
    try {
      const response = await fetch(`/api/projects/${slug}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, stage }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        const apiError = await readApiError(response);
        toast(apiError.message);
        throw apiError;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let assistant = "";
      let buffer = "";
      const consume = (line: string) => {
        if (!line.trim()) return;
        const event = JSON.parse(line);
        if (event.kind !== "text") return;
        assistant += event.text;
        setMessages((current) => {
          const copy = [...current];
          copy[copy.length - 1] = { role: "assistant", text: assistant };
          return copy;
        });
      };
      setMessages((current) => [...current, { role: "assistant", text: "" }]);
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

  return (
    <aside className={`director ${open ? "open" : "closed"}`} aria-label="Director">
      <header>
        <div className="director-heading">
          <h2>Director</h2>
          <div className="director-model">
            {role} · {model}
          </div>
        </div>
        <button type="button" className="icon-btn" aria-label="Close director" onClick={onClose}>
          <CloseIcon />
        </button>
      </header>
      <div className="messages">
        {messages.map((message, index) => (
          <div className={`msg ${message.role === "user" ? "user" : "assistant"}`} key={index}>
            <div className="who">{message.role}</div>
            <div className="body">{message.text}</div>
          </div>
        ))}
        {busy && (
          <div className="director-activity">
            <StatusDot tone="run" /> Working…
          </div>
        )}
        {error && (
          <div className="director-error">
            <p>{error}</p>
            {/key|config/i.test(error) && (
              <Button size="small" onClick={onSettings}>
                Open settings
              </Button>
            )}
          </div>
        )}
        {!messages.length && !busy && !error && (
          <p className="empty">Ask for a change. The stage and playhead travel with the message.</p>
        )}
      </div>
      <div className="composer">
        <div className="context" aria-label="Sent with your message">
          <span className="chip">{stageLabel(stage)}</span>
          <span className="chip">{clock(player.time)}</span>
        </div>
        <div className="composer-row">
          <textarea
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
