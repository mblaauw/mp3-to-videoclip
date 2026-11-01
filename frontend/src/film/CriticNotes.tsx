import { useEffect, useState } from "react";
import { api, type Critique } from "../api";
import { useProjectChanged } from "../shell/projectEvents";
import { Button } from "../ui";

const SEVERITY: Record<string, string> = {
  must_fix: "Must fix",
  should_fix: "Should fix",
  consider: "Consider",
};

const ASK =
  "Review the newest render against the brief. Look at frames from every section, then save your notes.";

/** What the Critic said about the newest render. Advice: nothing here opens a gate. */
export function CriticNotes({ slug, onSeek }: { slug: string; onSeek: (frame: number) => void }) {
  const [critique, setCritique] = useState<Critique | null>(null);
  const load = () => {
    void api.critique(slug).then((value) => setCritique(value.critique), () => undefined);
  };
  // The first read only depends on which film this is.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [slug]);
  useProjectChanged(slug, load);

  const ask = () =>
    window.dispatchEvent(
      new CustomEvent("studio:ask-director", {
        detail: { text: ASK, send: true, role: "critic", task: "review" },
      }),
    );

  return (
    <details className="panel-notes critic-notes" open={Boolean(critique?.notes.length)}>
      <summary>
        The Critic{critique ? `: ${critique.notes.length} ${critique.notes.length === 1 ? "note" : "notes"}` : ""}
      </summary>
      {critique ? (
        <>
          <p>{critique.verdict}</p>
          <p className="hint">
            On {critique.render}.
            {critique.current ? "" : " The cut has changed since, so some notes may no longer apply."}
          </p>
          <ul>
            {critique.notes.map((note, index) => (
              <li key={index}>
                <b>{SEVERITY[note.severity] ?? note.severity}</b>
                {note.shot_id ? ` · ${note.shot_id}` : ""}
                {note.frame !== undefined ? (
                  <>
                    {" · "}
                    <button type="button" className="link-button" onClick={() => onSeek(note.frame as number)}>
                      go there
                    </button>
                  </>
                ) : null}
                <div>{note.note}</div>
                {note.suggestion && <div className="hint">{note.suggestion}</div>}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="hint">Nothing yet. The Critic looks at frames of your newest render and changes nothing.</p>
      )}
      <div className="row-actions">
        <Button size="small" onClick={ask}>
          {critique ? "Ask for a new review" : "Ask the Critic"}
        </Button>
      </div>
    </details>
  );
}
