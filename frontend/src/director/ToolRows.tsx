import { useEffect, useState } from "react";
import { api } from "../api";
import { Button } from "../ui";

export type ToolItem = {
  kind: "tool";
  id: number;
  tool: string;
  args: string;
  result: string;
  done: boolean;
  undone: boolean;
  undoError: string | null;
  /** Restored from the saved conversation: shown, never undoable. */
  past?: boolean;
};

const TOOL_LABEL: Record<string, string> = {
  get_film_frames: "Looked at the film",
  save_critique: "Saved the review",
  write_storyboard: "Wrote the storyboard",
  update_voice_lines: "Placed the voice lines",
  get_project: "Read the project",
  get_brief: "Read the story",
  get_storyboard: "Read the storyboard",
  get_edit: "Read the cut",
  update_edit: "Rewrote the cut",
  update_edit_shots: "Changed shots in the cut",
  get_cut_material: "Read what to cut on",
  get_music_summary: "Read the music",
  get_lyrics: "Read the lyrics",
  get_treatments: "Read the concepts",
  update_treatments: "Rewrote the concepts",
  get_idea: "Read your idea",
  sort_idea: "Sorted your idea",
  place_story: "Put the story on the song",
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

export const UNDO_ARTIFACT: Record<string, string> = {
  update_brief: "brief",
  update_shots: "storyboard",
  update_edit: "edit",
  update_edit_shots: "edit",
  update_treatments: "treatments",
  sort_idea: "brief",
};

const MONEY_TOOLS = new Set(["generate_images", "transcribe_lyrics"]);

function parse(value: string): Record<string, unknown> | null {
  try {
    const data = JSON.parse(value) as unknown;
    return typeof data === "object" && data ? (data as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

export function contentText(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) =>
        part && typeof part === "object" && "text" in part ? String((part as { text: unknown }).text) : "",
      )
      .filter(Boolean)
      .join("\n");
  }
  return "";
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
    return "Queued · progress shows in the jobs tray";
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

/** The Director only prices stills. This is the owner's click on that price. */
function BuyStills({ slug, estimate }: { slug: string; estimate: { quote_id: string; reserve_usd: string; tasks: number } }) {
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const buy = async () => {
    setState("busy");
    setError(null);
    try {
      const started = await api.generateImages(slug, {
        quote_id: estimate.quote_id,
        note: "bought from the Director's price",
        uploads_confirmed: false,
      });
      if (started.needs_budget) throw new Error("The budget has no room for this.");
      setState("done");
    } catch (caught) {
      setError(String(caught));
      setState("idle");
    }
  };
  return (
    <div className="tool-actions">
      <Button size="small" variant="primary" disabled={state !== "idle"} onClick={() => void buy()}>
        {state === "done" ? "Started" : `Buy ${estimate.tasks} stills · $${estimate.reserve_usd}`}
      </Button>
      {error && <span className="tool-error">{error}</span>}
    </div>
  );
}

/** What a write changed, field by field, read when someone opens the details. */
function BeforeAfter({ slug, id }: { slug: string; id: string }) {
  const [fields, setFields] = useState<Record<string, { before: unknown; after: unknown }> | null>(null);
  useEffect(() => {
    let live = true;
    api.decision(slug, id).then(
      (value) => {
        if (live) setFields(value.before_after);
      },
      () => {
        if (live) setFields(null);
      },
    );
    return () => {
      live = false;
    };
  }, [slug, id]);
  if (!fields) return null;
  return (
    <>
      <span>Before and after</span>
      {Object.entries(fields).map(([field, change]) => (
        <pre key={field}>
          {field}
          {"\n- "}
          {JSON.stringify(change.before)}
          {"\n+ "}
          {JSON.stringify(change.after)}
        </pre>
      ))}
    </>
  );
}

function ToolRow({
  item,
  slug,
  onUndo,
}: {
  item: ToolItem;
  slug: string;
  onUndo: (item: ToolItem) => void;
}) {
  const data = parse(item.result);
  const failed = typeof data?.error === "string";
  const money = MONEY_TOOLS.has(item.tool) && !failed;
  const label = TOOL_LABEL[item.tool] || item.tool.replace(/_/g, " ");
  const args = argumentSummary(item.tool, item.args);
  const summary = item.done ? summaryFor(item.tool, item.result) : "Working…";
  const undoable = !!UNDO_ARTIFACT[item.tool] && !item.past;
  const reading = item.tool.startsWith("get_");
  return (
    <li className={`tool-row ${failed ? "failed" : ""} ${money ? "money" : ""} ${reading ? "read" : ""}`}>
      <span className={`tool-dot ${item.done ? "done" : "run"}`} aria-hidden="true" />
      <div className="tool-main">
        <div className="tool-line">
          <b>{label}</b>
          {args && <span className="tool-args">{args}</span>}
        </div>
        {!reading && <p className="tool-summary">{summary}</p>}
        {typeof data?.reason === "string" && data.reason && (
          <p className="tool-reason">{data.reason}</p>
        )}
        {Array.isArray(data?.changed_fields) && data.changed_fields.length > 0 && (
          <p className="tool-fields">{(data.changed_fields as string[]).slice(0, 6).join(", ")}</p>
        )}
        {item.tool === "propose_alternatives" && !failed && !item.past && (
          <div className="tool-options" role="group" aria-label="Choose one">
            {((data?.options as string[]) || []).map((option, index) => (
              <Button
                key={option}
                size="small"
                variant="quiet"
                onClick={() =>
                  window.dispatchEvent(
                    new CustomEvent("studio:ask-director", {
                      detail: {
                        text: `Use option ${index + 1} for ${String(data?.target)}: ${option}\nReason: owner chose option ${index + 1}.`,
                      },
                    }),
                  )
                }
              >
                {option}
              </Button>
            ))}
          </div>
        )}
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
            {typeof data?.decision_id === "string" && (
              <BeforeAfter slug={slug} id={data.decision_id} />
            )}
          </details>
        )}
        {data?.needs_owner === true && !item.past && (
          <BuyStills
            slug={slug}
            estimate={data.estimate as { quote_id: string; reserve_usd: string; tasks: number }}
          />
        )}
        {undoable && item.done && !failed && (
          <div className="tool-actions">
            <Button size="small" variant="quiet" disabled={item.undone} onClick={() => onUndo(item)}>
              {item.undone ? "Undone" : "Undo"}
            </Button>
            {item.undoError && <span className="tool-error">{item.undoError}</span>}
          </div>
        )}
      </div>
      {!item.done && <span className="tool-state">Running</span>}
      {item.done && failed && <span className="tool-state failed">Failed</span>}
    </li>
  );
}

/** Consecutive tool calls read as one compact activity log, not a wall of cards. */
export function ToolGroup({
  items,
  slug,
  onUndo,
}: {
  items: ToolItem[];
  slug: string;
  onUndo: (item: ToolItem) => void;
}) {
  const running = items.some((item) => !item.done);
  const writes = items.filter((item) => !item.tool.startsWith("get_"));
  const reads = items.length - writes.length;
  const [open, setOpen] = useState(false);
  // Reads alone fold away; writes, money and failures always stay visible.
  const shown = open ? items : items.filter((item) => !item.tool.startsWith("get_") || !item.done);
  return (
    <div className={`tool-group ${running ? "running" : ""}`}>
      {shown.length > 0 && (
        <ul>
          {shown.map((item) => (
            <ToolRow key={`tool-${item.id}`} item={item} slug={slug} onUndo={onUndo} />
          ))}
        </ul>
      )}
      {reads > 0 && (
        <button type="button" className="tool-toggle" onClick={() => setOpen((value) => !value)}>
          {open ? "Hide what it read" : `Read ${reads} thing${reads === 1 ? "" : "s"} first`}
        </button>
      )}
    </div>
  );
}

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="msg-copy"
      aria-label="Copy this reply"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        } catch {
          setCopied(false);
        }
      }}
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}
