---
name: clip-storyboard
description: Stage 3 of an MP3-to-videoclip production. Turn an approved brief into a decisive-still storyboard with per-shot job, change, must-show, framing, state, reference IDs, music binding, frame interval and transition. Use for shot lists, coverage, proof-shot selection and preflight. Never writes animation or forced beat cuts.
---

# Stage 3 — Storyboard

**Job:** a board of **decisive stills** that performs the approved concept through
the music. **Position:** after the story/look brief is approved, alongside prompt development.
Links: `../clip-music-director/SKILL.md`,
`../clip-music-director/references/production-gates.md`,
`../../../docs/PRODUCTION_WORKFLOW_V2.md`, `../../../docs/CREATIVE_WORKFLOW.md`.
Template: `references/shot-contract.md`. Code: `models.py` (`Shot`,
`Storyboard`), `timeline.py`, `preflight.py`, `production.py`.

## Inputs

- Approved `brief.json` and reviewed music events/timings.
- Identity/wardrobe/prop references available (bind them, do not invent them).
- Early music-editor/post-editor input and the brief's sequence treatment:
  `../clip-music-director/references/music-first-direction.md`.

## The per-shot contract (all fields)

| Field | Meaning |
|---|---|
| `id` | stable identity, not position; keeps its meaning if order changes |
| `purpose` | the **job** this still does in the chosen visual sequence |
| the **change** | what is different from the previous shot / what it advances |
| subject + action | who/what and what they are doing, in the shot |
| `must_show` | required visible elements (load-bearing details) |
| `framing` | wide / medium / close_up / detail, chosen for the job |
| wardrobe/prop `state` | `character_states` / `state_requirements` resolved per shot |
| `reference_ids` | only the immutable refs this shot actually needs |
| music binding | `event_ids` (reviewed events) — the shot's musical position |
| frame interval | `start_frame` + `duration_frames`, contiguous and exact |
| transition | `dissolve_frames` (shorter than both neighbours) or a clean cut |

See `references/shot-contract.md` for the template and an example.

## Coverage and timing

- Derive the board from music and plan **deliberate coverage**: shot-scale and
  composition contrast; details/expressions where useful. Action/reaction pairs
  and axial geography apply when interactions require them, not to every abstraction.
- Each cut or repetition needs a **visual or musical function**, not mandatory
  semantic novelty. An intentional unchanged-image reprise can work through its
  changed musical context. Cut/merge purposeless shots, not meaningful stillness.
- Motifs may evolve or deliberately recur. Judge neighboring shots and musical
  placement; reject **accidental** monotony, not repeated compositions as a class.
- Timing follows the music, not one universal range. For an energetic mix propose
  **typical 4–6-second holds with earned 1.5–3-second inserts, and only motivated
  long holds**; calmer passages may hold longer. There is **no fixed "N panels"**
  rule. Never infer a meter and never force a cut on every beat.

```sh
uv run clip skeleton PROJECT --timing adaptive --seconds 5 --min-seconds 1.5 --max-seconds 7
```

- Use evidenced events/phrases/beats or justified anticipation/counterpoint; no
  automatic beat snapping. Rebalance the **exact** source frame count. Timing
  buckets are proposals, not rules; every shot needs an attention/reading plan.
- **Edit count is not new-image count.** A purposeful native crop alias
  (`asset_shot_id`) adds coverage without a new generation; do not buy an image
  for every edit. Exact timing and crop aliases are part of this stage.
- Choose exactly three **risk proof IDs** (or all if fewer), including the
  hardest recurring interaction/wardrobe requirement — not three safe portraits,
  recorded in the brief's `creative.proof_shot_ids`.

## Exit gate

`clip preflight PROJECT --shots ...` and `clip prompts PROJECT --shots ...` show
the compiled prompts, refs/hashes, states, purpose, must_show, framing and frame
intervals with no blocking conflicts, and the **user approves the storyboard**.
The 6–8-shot rollout is directing guidance, not an automatic code gate.

## Feedback lane (one bounded revision)

Before the director integrates the draft, the `visual-critic` reviews its
visual-story progress, continuity and coverage, and the `post-editor` reviews
render feasibility, independently. Their findings return to the **visual-director**,
who makes **one** bounded revision, names the changed shots and keeps prompt
hashes stable for shots nobody flagged; the director then integrates it. The
`music-editor` adds a timing check only when music bindings change. Two read-only
checks, not a committee and not a new gate: see `references/board-feedback.md`.
The user still approves the storyboard.
Output: complete/partial/blocked; draft identity, named changed shots, preflight/prompt checks and remaining findings. Director alone integrates canonical state.

## Boundaries

- A still captures one decisive instant. `motion_prompt` is **deferred planning
  only** — it does not animate rain, smoke, people, eyes or doors. Camera paths
  move a crop; `post-editor` co-designs attention/movement BEFORE board lock (see
  `../clip-edit-graphics/references/remotion-motion.md`), not encoded here.
- No new image generation for a re-used (aliased) shot; each edit still gets a
  stable ID and exact allocated frames. No cycles/chains.
- Do not restage a previously paid/locked production automatically.
