import { AutoTextarea, Button, Markdown, StatusDot } from "../ui";
import { CloseIcon } from "../ui/icons";
import { writingLine } from "./directorActivity";
import { filmUsageLine, usageLine } from "./modelCost";
import { stageLabel } from "./stages";
import { ToolGroup, CopyButton } from "../director/ToolRows";
import { ROLE_NAME, SUGGESTIONS, clock } from "../director/chat";
import { type DirectorProps, useDirector } from "../director/useDirector";

export function Director(props: DirectorProps) {
  const { slug, stage, open, selectedShots = [], onClose, onSettings } = props;
  const { blocks, both, busy, canSee, composerRef, error, filmUsage, items, lastAsked, lastAssistant, lastWasTool, limit, listRef, missingKey, model, onScroll, player, providerLabel, quiet, role, scrollToEnd, send, setBoth, setRole, setText, stalled, stop, stuck, text, undo, unseen, writing } = useDirector(props);
  return (
    <aside className={`director ${open ? "open" : "closed"}`} aria-label="Director">
      <header>
        <div className="director-heading">
          <h2>Director</h2>
          <div className="director-model">
            {ROLE_NAME[role]} · {model}
            {providerLabel && <span className="director-gateway">{providerLabel}</span>}
          </div>
          {filmUsageLine(filmUsage) && (
            <div className="director-sight">This film so far: {filmUsageLine(filmUsage)}</div>
          )}
          {(canSee === false || canSee === null) && (
            <div className="director-sight">
              {canSee === false
                ? "This model can't see pictures, so it can't check framing or judge stills."
                : "This model hasn't confirmed it can see pictures. Check any framing it claims."}
            </div>
          )}
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
          disabled={busy && role !== "writer"}
          onClick={() => setRole("writer")}
          title="Story, storyboard and picture prompts"
        >
          Writer
        </button>
        <button
          type="button"
          className={role === "editor" ? "on" : ""}
          aria-pressed={role === "editor"}
          disabled={busy && role !== "editor"}
          onClick={() => setRole("editor")}
          title="Timing, cut, motion and transitions"
        >
          Editor
        </button>
        <button
          type="button"
          className={role === "critic" ? "on" : ""}
          aria-pressed={role === "critic"}
          disabled={busy && role !== "critic"}
          onClick={() => setRole("critic")}
          title="Reviews a cut against the brief; changes nothing"
        >
          Critic
        </button>
      </div>
      {/* What the list shows, apart from who answers: one role's thread, or all of them to read. */}
      <div className="thread-view">
        <span>{both ? "Every role's messages, in order" : `The ${ROLE_NAME[role]}'s thread`}</span>
        <button type="button" className="link" disabled={busy} aria-pressed={both} onClick={() => setBoth(!both)}>
          {both ? `Show only the ${ROLE_NAME[role]}` : "Show every role"}
        </button>
      </div>
      <div className="messages" aria-live="polite" ref={listRef} onScroll={onScroll}>
        {blocks.map((block) =>
          block.type === "tools" ? (
            <ToolGroup key={block.key} items={block.items} slug={slug} onUndo={(value) => void undo(value)} />
          ) : block.item.kind === "user" ? (
            <div className="msg user" key={`m-${block.index}`}>
              <div className="body">{block.item.text}</div>
            </div>
          ) : (
            <div className="msg assistant" key={`m-${block.index}`}>
              <div className="who">
                {block.item.kind === "assistant" && block.item.role ? ROLE_NAME[block.item.role] : "Director"}
                {block.item.kind === "assistant" && usageLine(block.item.usage) && (
                  <span className="msg-usage">{usageLine(block.item.usage)}</span>
                )}
                {block.item.kind === "assistant" && block.item.text && (
                  <CopyButton text={block.item.text} />
                )}
              </div>
              {block.item.kind === "assistant" && (
                <Markdown className="body" text={block.item.text} />
              )}
              {block.item.kind === "assistant" &&
                block.item.options &&
                block.item === lastAssistant && (
                  <div className="quick-replies" role="group" aria-label="Quick answers">
                    {block.item.options.map((option) => (
                      <button
                        type="button"
                        key={option}
                        disabled={busy}
                        onClick={() => void send(option)}
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                )}
            </div>
          ),
        )}
        {busy && writing ? (
          <div className="director-activity">
            <StatusDot tone="run" /> {writingLine(role === "writer" ? "Writer" : "Editor", writing)}
          </div>
        ) : (
          busy &&
          !lastWasTool &&
          items[items.length - 1]?.kind !== "assistant" && (
            <div className="director-activity">
              <StatusDot tone="run" /> Thinking…
            </div>
          )
        )}
        {quiet && (
          <div className="director-quiet" role="status">
            <p>{quiet}</p>
            <Button size="small" onClick={stop}>
              Stop
            </Button>
          </div>
        )}
        {stalled && (
          <div className="director-error" role="alert">
            <p>{stalled}</p>
            {!busy && limit !== null && (
              <div className="tool-actions">
                <span className="tool-summary">Stopped after {limit} steps.</span>
                <Button size="small" onClick={() => void send("Keep going", undefined, true)}>
                  Keep going
                </Button>
              </div>
            )}
            {!busy && lastAsked.current && (
              <Button
                size="small"
                onClick={() => {
                  const asked = lastAsked.current;
                  if (asked) void send(asked.message, asked.task);
                }}
              >
                Ask again
              </Button>
            )}
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
        {!items.length && !busy && !error && !stalled && (
          <div className="director-empty">
            <p>
              Ask for a change.{" "}
              {selectedShots.length
                ? "The stage, the playhead and the selected shot travel with the message."
                : "The stage and the playhead travel with the message."}
            </p>
            <div className="quick-replies" role="group" aria-label="Suggestions">
              {SUGGESTIONS[stage].map((suggestion) => (
                <button
                  type="button"
                  key={suggestion}
                  onClick={() => {
                    setText(suggestion);
                    composerRef.current?.focus();
                  }}
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
      {unseen && !stuck && (
        <button type="button" className="director-jump" onClick={() => scrollToEnd(true)}>
          ↓ Latest
        </button>
      )}
      <div className="composer">
        <div className="context" aria-label="Sent with your message">
          <span className="chip">{stageLabel(stage)}</span>
          <span className="chip">at {clock(player.seconds)}</span>
          {selectedShots.map((shot) => (
            <span className="chip shot" key={shot}>
              {shot}
            </span>
          ))}
        </div>
        <div className="composer-row">
          <AutoTextarea
            ref={composerRef}
            value={text}
            minRows={1}
            maxRows={10}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void send();
              }
            }}
            placeholder={`Ask the ${ROLE_NAME[role]}…`}
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
        <p className="composer-hint">Enter sends · Shift+Enter adds a line</p>
      </div>
    </aside>
  );
}
