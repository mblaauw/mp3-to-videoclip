# Board feedback lane

Detail for the `visual-director` and the `film-director`. The rule stays one-line
in `SKILL.md`; this is who checks what, and what "one revision" means.

## The lane

1. The visual-director returns the storyboard, prompt and reference draft.
2. Two **independent read-only checks** run in parallel:
   - `visual-critic`, board mode — visual-story progress (does each cut add
     information?), coverage, shot-scale contrast, continuity, screen direction,
     accidental repetition, and whether the board binds to reviewed music events.
   - `post-editor` — render feasibility: can the planned transition, handle,
     camera path or effect actually execute on the local renderer, and does the
     board's hold/movement plan hold up shot by shot?
3. Findings return to the **visual-director** for **one** bounded revision. The
   director names the changed shots and keeps prompt hashes **stable** for shots
   nobody flagged, so an unrelated rework does not invalidate settled prompts.
4. The director integrates the revision; the user still approves the storyboard.

## The music check is conditional

`music-editor` adds a board **timing/event-binding** check only when music
bindings actually change. It is not a standing member of every board review, and
the same bytes are never re-reviewed twice.

## What the lane is not

- Not a gate, schema or artifact; findings are text only.
- Not a paid step and not a generation trigger.
- Not render feasibility by the critic, and not visual judgement by the
  post-editor: each returns only its own lane.

## Stopping condition

One revision, then the director accepts, blocks or integrates. A second revision
needs a stated reason and the director's decision, never an automatic loop.
