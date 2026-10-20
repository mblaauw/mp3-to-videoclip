# Production loop

The agent-operated loop for one MP3→videoclip film. `AGENTS.md` is the authority; `clip`
artifacts and content-bound approvals are the record. This file is the loop, not a second
state store: no database, scheduler or daemon. Read order: `AGENTS.md` → this file → the
stage skill → `docs/PRODUCTION_WORKFLOW_V2.md`.

## Crew

| id | job | may write |
| --- | --- | --- |
| `film-director` | single canonical state, paid coordination, all gates | canonical artifacts, via `clip` |
| `music-editor` | measurement, edit proposals, the board timing check | analysis and proposal drafts |
| `short-film-writer` | conceits/sequence arcs; causality only for narrative | drafts returned as text |
| `visual-director` | style fidelity, board, camera, prompts, references | brief/board/prompt files |
| `visual-critic` | read-only review of story, board and actual pixels | nothing; structured text reports |
| `post-editor` | movement, keyframes, transitions, effects, grade — a plan | motion/grade drafts |
| `film-finisher` | local render, composited graphics, verification | timeline/graphics/render outputs |

`film-director` is the lead and **only** paid coordinator. Specialists never nest;
`visual-critic` and `short-film-writer` have no shell and no edit. Read-only means
read-only — a verdict in a reply is not a file — and these rules are discipline,
not a security sandbox.

Before creative work read `.opencode/skills/clip-music-director/references/music-first-direction.md`.
Narrative is optional. Bring `music-editor` and `post-editor` in before board lock
and generation; integrate a sequence treatment into the existing brief. Each shot
needs an attention plan, not compulsory motion/beat cuts. The finisher executes;
judge decoded output, not intent. Remotion renders; FFmpeg encodes/muxes/probes.

## Feedback loop

Two bounded lanes run **before** user gates; no new stage/artifact or committee:

- **Story:** `short-film-writer` draft → `visual-critic` (chosen mode) and `music-editor`
  (binding) in parallel → the writer's **one** revision → director accepts or blocks.
- **Board:** `visual-director` draft → `visual-critic` (story, continuity) and
  `post-editor` (feasibility) → the `visual-director`'s **one** revision → director integrates.

`music-editor` adds a timing check only when bindings change. The critic reports
evidence, consequence, fix and severity, claiming pixel inspection only for images read.
`film-director` alone dispatches, approves and spends; two lanes, three items in flight.

## The loop

1. Read what exists and is validated: `work/approvals.json`, `work/reviews.json`
   (per-image verdicts), quotes, authorizations, tasks, storyboard and budget.
   `work/reviews/` is graphics review material, not the verdict record.
2. Name the next **missing requirement or blocker** — one requirement, not a wish list.
3. Dispatch one bounded owner for it, stating mode and owned files.
4. Inspect the result creatively *and* technically: tests or a clean preflight are not
   creative acceptance. Commit through the `clip` gates, or name the missing evidence.
5. Continue ready authorized requirements; stop at a real gate, blocker or budget.

Stage skills are capabilities to load as needed, not a strict arrow sequence:
`clip-music-analysis`, `clip-story`, `clip-storyboard`, `clip-art-direction`,
`clip-image-prompts`, `clip-image-production`, `clip-visual-review`,
`clip-edit-graphics`, `clip-delivery`. Story and art direction are settled
**before** brief approval; board and prompts are settled **before** storyboard
approval. Only the director writes canonical state, and parallel writers never
edit the same brief, board or approval file.

## Gates (each is a user decision)

- Story and art direction exist and are reviewed **before** brief approval.
- Board, prompts and deliberate coverage exist **before** storyboard approval.
- A three-shot proof, then a real local preview on the actual music, then
  explicit preview approval, then a small reviewed rollout, then the full set.
- Opening overlay (25 s) and credit package (40 s) are mandatory, inside the music, with
  the shared joint identity and factual roles; composite over the film, never ship the base.
- Archive (`clip backup`) before handing over the film. Approval is the user's:
  explicit delegation lets the director confirm a bounded step it has actually
  inspected and never creates new budget.

## Review surfaces and background work

- `clip dashboard P --stage board|stills|delivery` renders the beatmap/shot review page
  (sections, timeline, measured activity, graphics windows, shot list). `clip studio`
  renders the cross-project index; `clip adopt` registers a local derivative;
  `clip shot-edit` changes one shot's transition/dissolve/camera/grade and reports the
  approvals it invalidated. All are review aids or validated edits: none approves,
  uploads or spends. Approve through `clip approve` against the hash the page shows.
- No meter, bar grid or downbeat appears without an approved `work/music-grid.json`;
  measured beats and tempo stay labelled estimates, and an invalid grid fails closed.
- Long local work writes a receipt under `work/operations/`; `clip progress P
  [--reconcile]` reads it, `clip spine` indexes it as a run and `clip serve` streams it
  read-only over loopback. After a dispatch: acknowledge → validate outputs → inspect →
  commit through the gate or name the blocker → continue. Quiet is not failure,
  completion is not approval, and a receipt never authorises a retry, charge or selection.

## Money and evidence

Quotes, authorizations, task UUIDs, reservations and costs stay in project files; a lost
paid request is recovered by UUID, never resubmitted, and unknown billing keeps its
reservation until the user verifies it. Original plus one correction, then diagnose.
Missing audio evidence is never invented and unreviewed lyrics stay drafts. Upstream
recipes authorize no model, format, scope or spend; prompts are not budget enforcement.

## Style calibration

The default is the user-approved benchmark in `profiles.STYLE_BENCHMARK`; reuse it, never
buy another control or auto-upload it, and vary scene/content/optics separately — matching
prompt text is not pixel proof. A change is **one** control through `clip style-test`
quote/run/recover with prompt, settings, schema, request, cost and hash; the user judges
it and the director never auto-accepts it.

## Limits, playback and evidence

- At most three independent items in flight; normally two review lanes, no committee.
- Continuous playback with audio is a distinct checkpoint: samples, preflight and
  `ffprobe` are **not** watching. A delegated proxy export must be declared unwatched,
  never a pass.
- One review session per round, at most 15 image occurrences including references
  (practically 6–8); complete coverage, never "unavailable" as a pass.
- Editing, graphics and render work is local (Remotion for new films, FFmpeg for
  encode/mux/probe and legacy); no paid call belongs in editing or verification.

Engineering mode: use `/deliver` and the ordinary build workflow with focused
tests, not a crew spawn. Approved task/PR completion is a checkpoint, not a stop.
