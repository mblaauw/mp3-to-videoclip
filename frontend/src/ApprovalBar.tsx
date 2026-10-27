import { createContext, useContext, type ReactNode } from "react";
import type { ApprovalState } from "./api";
import { Pill, type PillTone } from "./ui";

/**
 * Approval *status* for a stage, read from the shell's one approvals snapshot.
 *
 * Approving happens in exactly one place — the sticky next-step bar (or, for the
 * preview and titles, the attested checklist on Film). This strip only says
 * where each gate stands, when it was signed and with which note, so a page no
 * longer shows a second, competing Approve button.
 */

export type ApprovalsSnapshot = {
  states: Record<string, ApprovalState>;
  loaded: boolean;
};

const ApprovalsContext = createContext<ApprovalsSnapshot>({ states: {}, loaded: false });

export function ApprovalsProvider({
  value,
  children,
}: {
  value: ApprovalsSnapshot;
  children: ReactNode;
}) {
  return <ApprovalsContext.Provider value={value}>{children}</ApprovalsContext.Provider>;
}

export function useApprovals(): ApprovalsSnapshot {
  return useContext(ApprovalsContext);
}

const NAME: Record<string, string> = {
  analysis: "Analysis",
  lyrics: "Lyrics",
  brief: "Story",
  storyboard: "Storyboard",
  proof: "Style check",
  preview: "Preview",
  stills: "All stills",
  graphics: "Titles",
};

const STATE: Record<ApprovalState["state"], { tone: PillTone; word: string }> = {
  approved: { tone: "keep", word: "Approved" },
  stale: { tone: "old", word: "Changed since approval" },
  missing: { tone: "you", word: "Not approved yet" },
  unavailable: { tone: "neutral", word: "Not ready" },
};

function when(at: string | null | undefined): string | null {
  if (!at) return null;
  const date = new Date(at);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** A compact, read-only sign-off line for the given gates. */
export function ApprovalBar({ stages }: { slug?: string; stages: string[] }) {
  const { states, loaded } = useApprovals();
  const items = stages.map((stage) => states[stage]).filter(Boolean) as ApprovalState[];
  if (!loaded || !items.length) return null;
  return (
    <div className="signoff" aria-label="Approval status">
      {items.map((item) => {
        const look = STATE[item.state] || STATE.missing;
        const stamp = item.state === "approved" ? when(item.at) : null;
        const note = item.state === "approved" ? item.note : null;
        // "Not ready" needs no engine wording here: the bar says what to do next.
        const why = item.state === "stale" ? item.reason : null;
        return (
          <div className={`signoff-item ${item.state}`} key={item.stage}>
            <span className="signoff-name">{NAME[item.stage] || item.stage}</span>
            <Pill tone={look.tone}>{look.word}</Pill>
            {stamp && <span className="signoff-meta">{stamp}</span>}
            {note && (
              <span className="signoff-note" title={note}>
                “{note}”
              </span>
            )}
            {why && (
              <span className="signoff-meta" title={why}>
                {why}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
