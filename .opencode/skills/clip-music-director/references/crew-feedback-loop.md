# Crew feedback loop (the two bounded lanes)

Detail for the `film-director`. The one-line rule stays in `SKILL.md`; this file
is the shape, the owners and the stopping condition.

## What it is not

Not a new stage, gate, artifact or schema. Nothing here is written into
`work/approvals.json` or bound to bytes: the lanes produce **text findings** that
feed the draft's own owner before the existing user gates. A lane never replaces
brief, storyboard, proof or stills approval, and it never spends.

## Lane 1 — story

1. `short-film-writer` returns the concept/sequence arc and shot intents (text).
2. The director dispatches **two independent read-only checks in parallel**:
   - `visual-critic` in **story mode** — judge the chosen mode, not an obligatory
     plot: causality/payoff for narrative; visual progression/coherence/contrast
     for abstraction or performance. No invented musical meaning.
   - `music-editor` — the story's **music binding**: does it land on reviewed
     events, and does it claim structure nobody measured or the user reviewed?
3. Findings go back to the **writer**, who makes **one** bounded revision and
   names what changed.
4. The director accepts the revision, or records an explicit blocker. There is no
   second revision by default; a second pass needs a stated reason.

## Lane 2 — storyboard

1. `visual-director` returns the board, prompt and reference draft.
2. The director dispatches **two independent read-only checks in parallel**:
   - `visual-critic` in **board mode** — visual-story progress, coverage,
     continuity, screen direction, accidental repetition, musical binding.
   - `post-editor` — **render feasibility**: can the planned transition, handle
     or effect actually execute on the local renderer?
3. Findings go back to the **visual-director**, who makes **one** bounded
   revision, names the changed shots, and keeps prompt hashes stable for shots
   nobody flagged.
4. The director integrates the revision; the user still approves the board.

## The extra music check

`music-editor` adds a board **timing check** only when the board's music bindings
actually change. It is not a standing member of every board review, and the same
bytes are never re-reviewed twice.

## Report shape (the critic)

A fixed text report per finding — never prose:

| Field | Meaning |
| --- | --- |
| evidence | what was actually read or seen, with the file/byte scope |
| consequence | what breaks or is lost if it ships |
| proposed fix | the smallest change that answers it |
| severity | blocker / should-fix / note |

Claim **pixel inspection only** for images actually read; a text-only review of a
draft is labelled as such. Coverage is explicit: inspected, unreadable, not
reviewed. "Unavailable" is never a pass.

## Budget

The crew is seven roles; no new agent. Normally at most **two review lanes** and
**three items** in flight, and the `film-director` is the only dispatcher,
approver and spender. Specialists never nest and never spend.
