import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { readApiError } from "../api/errors";
import { usePlayerClock } from "../spine/player";
import { quietLine, type Writing } from "../shell/directorActivity";
import { type FilmUsage, type TurnUsage } from "../shell/modelCost";
import type { Stage } from "../shell/nextStep";
import { notifyProjectChanged } from "../shell/projectEvents";
import { type ToolItem, UNDO_ARTIFACT, contentText } from "./ToolRows";
import { type Role, type ChatItem, type StreamEvent, type DirectorPrompt, modelLabel } from "./chat";

export type DirectorProps = {
  slug: string;
  stage: Stage;
  open: boolean;
  prefill?: DirectorPrompt | null;
  selectedShots?: string[];
  onClose: () => void;
  onSettings: () => void;
  /** Lets the shell keep the drawer open while a reply is being written. */
  onBusyChange?: (busy: boolean) => void;
};

export function useDirector({
  slug,
  stage,
  prefill = null,
  selectedShots = [],
  onBusyChange,
}: DirectorProps) {
  const player = usePlayerClock();
  const defaultRole: Role = ["story", "storyboard", "images"].includes(stage)
    ? "writer"
    : "editor";
  const [items, setItems] = useState<ChatItem[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    onBusyChange?.(busy);
  }, [busy, onBusyChange]);
  const [error, setError] = useState<string | null>(null);
  const [role, setRoleOnly] = useState<Role>(defaultRole);
  /** Everyone's messages in order, to read. The roles' own threads stay as they are. */
  const [both, setBoth] = useState(false);
  const setRole = (next: Role) => {
    setBoth(false);
    setRoleOnly(next);
  };
  const [historyFor, setHistoryFor] = useState<Role | null>(null);
  // Undefined until the answer arrives, so nothing warns about a model not asked about yet.
  const [canSee, setCanSee] = useState<boolean | null | undefined>(undefined);
  const [providerLabel, setProviderLabel] = useState("");
  const [limit, setLimit] = useState<number | null>(null);
  const [filmUsage, setFilmUsage] = useState<FilmUsage | null>(null);
  const [models, setModels] = useState<Record<Role, string>>({
    writer: "the configured Writer",
    editor: "the configured Editor",
    critic: "the configured Critic",
  });
  const [writing, setWriting] = useState<Writing | null>(null);
  const [quietSeconds, setQuietSeconds] = useState(0);
  const [stalled, setStalled] = useState<string | null>(null);
  const [stuck, setStuck] = useState(true);
  const [unseen, setUnseen] = useState(false);
  const lastHeard = useRef(0);
  const lastAsked = useRef<{ message: string; task?: string } | null>(null);
  const stopRef = useRef<AbortController | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const seq = useRef(0);
  const listRef = useRef<HTMLDivElement>(null);
  const roleRef = useRef(role);
  roleRef.current = role;
  const busyRef = useRef(busy);
  busyRef.current = busy;

  useEffect(() => {
    // Switching threads mid-reply would drop the streaming answer.
    if (!busyRef.current) setRole(defaultRole);
    setError(null);
    setStalled(null);
    // A stage change changes who answers; each role keeps its own thread.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stage]);

  useEffect(() => {
    let current = true;
    setCanSee(undefined);
    api
      .directorModel(slug, role)
      .then((value) => {
        if (!current) return;
        setModels((before) => ({ ...before, [role]: modelLabel(value.model) }));
        setProviderLabel(value.provider_label);
        setCanSee(value.can_see);
      })
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [slug, role]);

  useEffect(() => {
    if (!prefill?.text || prefill.send) return;
    setText(prefill.text);
    const element = composerRef.current;
    if (element) {
      element.focus();
      element.setSelectionRange(prefill.text.length, prefill.text.length);
    }
  }, [prefill?.at, prefill?.send, prefill?.text]);

  // A job from a button is the Writer's, and waits for that thread and any reply in progress.
  const sentPrompt = useRef<number | null>(null);
  useEffect(() => {
    if (!prefill?.send || sentPrompt.current === prefill.at) return;
    const wanted = prefill.role ?? "writer";
    if (role !== wanted) {
      if (!busy) setRole(wanted);
      return;
    }
    if (busy || historyFor !== wanted) return;
    sentPrompt.current = prefill.at;
    void send(prefill.text, prefill.task);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill?.at, prefill?.send, role, busy, historyFor]);

  useEffect(() => {
    window.dispatchEvent(new CustomEvent("studio:writer-busy", { detail: busy }));
    return () => {
      if (busy) window.dispatchEvent(new CustomEvent("studio:writer-busy", { detail: false }));
    };
  }, [busy]);

  useEffect(() => {
    let live = true;
    setHistoryFor(null);
    api
      .chat(slug, both ? undefined : role)
      .then((data) => {
        if (!live) return;
        const restored: ChatItem[] = [];
        for (const raw of data.messages as {
          role: string;
          content?: unknown;
          name?: string;
        }[]) {
          if (raw.role === "user") {
            restored.push({ kind: "user", text: contentText(raw.content) });
          } else if (raw.role === "assistant") {
            const value = contentText(raw.content);
            if (value.trim()) restored.push({ kind: "assistant", text: value });
          } else if (raw.role === "tool" && raw.name) {
            seq.current += 1;
            restored.push({
              kind: "tool",
              id: seq.current,
              tool: raw.name,
              args: "",
              result: contentText(raw.content),
              done: true,
              undone: false,
              undoError: null,
              past: true,
            });
          }
        }
        setItems(restored);
        setHistoryFor(role);
      })
      .catch(() => {
        if (!live) return;
        setItems([]);
        setHistoryFor(role);
      });
    return () => {
      live = false;
    };
  }, [slug, role, both]);

  const scrollToEnd = useCallback((smooth = false) => {
    const element = listRef.current;
    if (!element) return;
    element.scrollTo({ top: element.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    setUnseen(false);
  }, []);

  // Follow the conversation only while the reader is at the bottom; someone
  // scrolling back to re-read an answer is not yanked down by the next token.
  const stuckRef = useRef(true);
  const hasWriting = writing !== null;
  const quiet = busy ? quietLine(quietSeconds) : null;
  useEffect(() => {
    if (stuckRef.current) scrollToEnd();
    else setUnseen(true);
  }, [items, busy, hasWriting, quiet, stalled, scrollToEnd]);

  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(() => {
      setQuietSeconds((Date.now() - lastHeard.current) / 1000);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [busy]);

  const onScroll = () => {
    const element = listRef.current;
    if (!element) return;
    const near = element.scrollHeight - element.scrollTop - element.clientHeight < 48;
    stuckRef.current = near;
    setStuck(near);
    if (near) setUnseen(false);
  };

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
    // Any tool that is not a read may have written the film.
    if (event.tool && !event.tool.startsWith("get_") && event.tool !== "ask_user") {
      notifyProjectChanged({ slug, source: "director", artifact: UNDO_ARTIFACT[event.tool] });
    }
  };

  const appendAssistant = (chunk: string, options?: string[]) => {
    setItems((current) => {
      if (!chunk && !options) return current;
      const copy = [...current];
      const last = copy[copy.length - 1];
      if (last?.kind === "assistant") {
        copy[copy.length - 1] = {
          ...last,
          text: last.text + chunk,
          ...(options ? { options } : {}),
        };
      } else {
        copy.push({ kind: "assistant", text: chunk, role: roleRef.current, options });
      }
      return copy;
    });
  };

  const send = async (override?: string, task?: string, keepGoing = false) => {
    if (both) setBoth(false);
    setLimit(null);
    const message = (override ?? text).trim();
    if (!message || busy) return;
    if (override === undefined) setText("");
    setItems((current) => [
      // Answering a question retires its quick replies.
      ...current.map((item) =>
        item.kind === "assistant" && item.options ? { ...item, options: undefined } : item,
      ),
      { kind: "user", text: message },
    ]);
    stuckRef.current = true;
    setStuck(true);
    setBusy(true);
    setError(null);
    setStalled(null);
    setWriting(null);
    setQuietSeconds(0);
    lastHeard.current = Date.now();
    lastAsked.current = { message, task };
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
          ...(keepGoing ? { continue: true } : {}),
          ...(task ? { task } : {}),
          context: {
            stage,
            time: Math.max(0, Number(player.current()) || 0),
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
        if (event.kind === "progress") {
          const tool = event.tool;
          if (tool) setWriting({ tool, chars: Number(event.payload?.chars) || 0 });
          return;
        }
        if (event.kind !== "done") setWriting(null);
        if (event.kind === "text") appendAssistant(event.text || "");
        else if (event.kind === "done") {
          const used = event.payload?.usage as TurnUsage | undefined;
          if (used) {
            setItems((current) => {
              const copy = [...current];
              const last = copy[copy.length - 1];
              if (last?.kind === "assistant") copy[copy.length - 1] = { ...last, usage: used };
              return copy;
            });
            api.modelUsage(slug).then(setFilmUsage, () => undefined);
          }
          if (event.payload?.limit) setLimit(Number(event.payload.steps) || 0);
          const failure = event.payload?.error;
          if (typeof failure === "string" && failure) {
            if (event.payload?.stalled) setStalled(failure);
            else setError(failure);
          }
        } else if (event.kind === "tool") {
          if (event.result) addToolResult(event);
          else addToolStart(event);
        } else if (event.kind === "ask") {
          const question = event.text || String(event.payload?.question || "");
          const options = Array.isArray(event.payload?.options)
            ? (event.payload?.options as unknown[]).map((value) => String(value)).filter(Boolean)
            : [];
          setItems((current) => {
            const copy = [...current];
            for (let index = copy.length - 1; index >= 0; index -= 1) {
              const item = copy[index];
              if (item.kind === "tool" && item.tool === "ask_user" && !item.done) {
                // The question itself is shown as the reply; drop the tool row.
                copy.splice(index, 1);
                break;
              }
            }
            return copy;
          });
          appendAssistant(question, options.length ? options : undefined);
        }
      };
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        lastHeard.current = Date.now();
        setQuietSeconds(0);
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
      setWriting(null);
      setQuietSeconds(0);
      composerRef.current?.focus();
    }
  };

  const stop = () => {
    stopRef.current?.abort();
    stopRef.current = null;
    setBusy(false);
    setWriting(null);
    setQuietSeconds(0);
  };

  const undo = async (item: ToolItem) => {
    const artifact = UNDO_ARTIFACT[item.tool];
    if (!artifact) return;
    setItems((current) =>
      current.map((entry) =>
        entry.kind === "tool" && entry.id === item.id ? { ...entry, undoError: null } : entry,
      ),
    );
    try {
      await api.restoreHistory(slug, artifact);
      setItems((current) =>
        current.map((entry) =>
          entry.kind === "tool" && entry.id === item.id ? { ...entry, undone: true } : entry,
        ),
      );
      notifyProjectChanged({ slug, source: "director", artifact });
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

  const model = models[role];
  const missingKey = /no llm key|llm key|model key|api key|no key|unauthor/i.test(error || "");

  // Group consecutive tool calls so a turn reads: question → activity → answer.
  const blocks: ({ type: "item"; item: ChatItem; index: number } | { type: "tools"; items: ToolItem[]; key: string })[] = [];
  items.forEach((item, index) => {
    if (item.kind === "tool") {
      const last = blocks[blocks.length - 1];
      if (last && last.type === "tools") last.items.push(item);
      else blocks.push({ type: "tools", items: [item], key: `tools-${item.id}` });
    } else {
      blocks.push({ type: "item", item, index });
    }
  });
  const lastAssistant = [...items].reverse().find((item) => item.kind === "assistant");
  const lastWasTool = items[items.length - 1]?.kind === "tool";

  return { blocks, both, busy, canSee, composerRef, error, filmUsage, items, lastAsked, lastAssistant, lastWasTool, limit, listRef, missingKey, model, onScroll, player, providerLabel, quiet, role, scrollToEnd, send, setBoth, setRole, setText, stalled, stop, stuck, text, undo, unseen, writing };
}
