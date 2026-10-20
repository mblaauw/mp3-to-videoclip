# Story feedback lane

Detail for the `short-film-writer` and the `film-director`. The rule stays
one-line in `SKILL.md`; this is who checks what, and when to stop.

## The lane

1. The writer returns concept/sequence arc and shot intents as a text draft.
2. Two **independent read-only checks** run in parallel:
   - `visual-critic`, story mode — narrative: central question, causal development
     and earned payoff. Non-narrative: coherence, evolving visual relationships,
     contrast and musical intent, never an invented protagonist requirement.
   - `music-editor` — does the story bind to **reviewed** music events, and does
     it claim structure, tempo or emotion nobody measured or the user reviewed?
3. Findings return to the writer for **one** bounded revision. The writer names
   what changed and does not start an open-ended rewrite loop.
4. The director accepts the revision or records an explicit blocker. There is no
   default second revision; another pass needs a stated reason.

## What the checks are not

- Not a gate: brief approval stays the user's decision, bound to content hashes.
- Not a schema or artifact: findings are text, and nothing is written to
  `work/approvals.json`.
- Not a paid step: no upload, no provider call, no generation.

## Honesty

The critic reviews the **draft text**, not pixels, and says so. A finding without
evidence, a stated consequence, the smallest proposed fix and a severity is not a
finding. Coverage is explicit, and "could not assess" is never a pass.
