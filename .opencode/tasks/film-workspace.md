# Film workspace — plan

**Approved** by the owner on 30 Oct 2026 with the recommended D1–D5.

**Objective:** make Film a real editing workspace, as tried in the prototype
(`.opencode/scratch/film-workspace-prototype/`, 30 Oct 2026): a dominant viewer, one
panel that follows the selection, a tall timeline made of the stills, and one next
action. Items 1, 2 and part of 4 of the design list; base `main` at `3fbe3ea`.

## What the code showed

- `stages/Film.tsx` is 1,100 lines: the preview, delivery card, cut list, files
  tab and samples dialog in one component. Each of the 38 shots mounts its own
  `TransitionEditor`.
- The shell's grid already has one right-hand slot, shared by `ShotInspector` and
  the Director. The Film panel can use that slot.
- Dragging a boundary on the Spine already writes the cut, through
  `editBoundaryLimits`/`moveEditBoundary`. The prototype had no drag; the build must
  keep it.
- `PUT /edit` takes `If-Match`, so saves can detect conflicts. `history.restore`
  only returns to the newest *different* snapshot, so a second undo toggles back:
  it cannot be a multi-step undo.
- A styled join with no written reason is reported as a **hard** finding, and today's
  editor demands a reason. The prototype's one-click joins would fail that rule. It is
  only reported; nothing blocks a render on it.
- Report notes are engine wording. `density_target` also fires when a section has
  no target ("against a 0.0/10s target"), which is noise.
- Any cut change makes the titles review stale, because it binds the cut. That is
  correct, so the screen must say so plainly.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | Must a hand-picked join have a written reason? | No. The panel writes "Set by hand" and offers an optional note. The rule stays for the Editor, with no schema change. |
| D2 | Where is the Director closed by default? | Film only for now, remembering your last choice per stage. Story and Storyboard are where you talk to it most. It opens in the panel's slot, replacing the panel until closed. |
| D3 | What happens to the long cut list? | Keep it as a read-only "Cut list" tab beside "Rendered files", without its editors. It is the one place that reads as a whole report with reasons. |
| D4 | Must every title sample be opened before approving? | Yes, as an extra gate in the screen. The server's approval rule stays the same. |
| D5 | Default timeline zoom? | Whole film fitted to the window. The shortest shots are then about 11 px wide, so joins keep a 10 px target, with zoom on `+`/`-`. Please check this one against the prototype. |

## Tasks (one commit each, one PR)

1. **Layout.** A Film grid with the viewer taking the remaining space, a taller timeline
   row and the panel slot. The Director follows D2. `F` gives full view with a thin
   scrub line; portrait films fit the same viewer. Split `Film.tsx` into `film/`
   modules with no behaviour change first.
2. **Timeline.** A new `film/FilmTimeline.tsx`, leaving the 900-line Spine to the
   other stages; shared waveform and transport code is extracted, not copied. Stills
   sized by duration, sections, waveform, titles row, note markers, zoom. A seam:
   click selects, drag past 4 px retimes, shift-click adds. `[` and `]` step between joins.
3. **Panel and joins.** `film/FilmPanel.tsx` shows the overview, join or shot from one
   selection state. Joins apply at once, singly or in bulk, then play that join with
   sound. Add `setEditMotion` beside `setEditTransition` for camera moves. Saves queue
   so that two quick changes can't race, using `If-Match`.
4. **Undo.** A session stack of earlier cuts, in memory. `⌘Z` saves the previous cut
   back through `PUT /edit`, with a toast naming the change. On a 409 conflict: reload
   and clear the stack, and say so. Director changes keep their own undo.
5. **Notes.** Skip `density_target` when no target is set. Frontend copy keyed on
   report codes turns notes into plain sentences. Markers open the note and jump to it.
6. **One next action.** Move the next step into the top bar on Film. Gates collapse to
   one line. Preview and titles reviews open in the panel: the real stills grouped by
   title window, each jumping the Player to its frame. After a cut change it reads
   "The cut changed. Check the titles again", with the button. Files, downloads and all
   attestations keep working.
7. **Finish.** Layout below 1,180 px, a keyboard pass without clashes (Space, M, L, `,`,
   `.` are taken), focus and contrast, the Film screenshot and docs.

## Not changing

Timing, money, render and approval hashes; the edit schema; the golden contract; other
stages' layout. Only `edits.py`'s noise rule changes on the backend, plus the optional
"Set by hand" default sent by the frontend.

## Acceptance

- `pytest`, `ruff`, frontend `tsc`/tests/build and renderer tests pass. New pure tests
  cover selection, undo, join limits, save ordering and note wording.
- On a **scratch copy** of Tree of Love, with no production change and $0 spend:
  - set a join and see it in the Player with real transitions and titles;
  - bulk-change joins, undo several steps, and drag a boundary;
  - see a stale titles message after a cut change, then check, approve and render a
    final from the new screen.
- Every existing Film function remains reachable: preview approval, titles approval,
  rendered files, playing and downloading, ratings, seeding a first cut, the renderer
  setup card, a film with no titles, and read-only archived films.
- Viewer at least 950 px wide at 1440×900 with the Director closed. No sideways page
  scroll at 768 px.

## Risks

- **Timeline performance.** 79 shots (Zero Bars) must scrub smoothly; tested there.
  Thumbnails are a later item, so full stills are loaded for now.
- **Many saves.** Each join writes a history snapshot. Bulk changes save once.
- **Scope.** Director proposal cards, lyric-to-section links and a type-scale cleanup
  are separate work.

## Progress

- T1–T6 committed, one each. T7: the narrow layouts, focus release after mouse
  clicks so Space plays, 55 unused CSS rules removed, docs updated.
- Found while building: the stills approval hash includes the whole cut
  (`production.py`), so every cut change un-approves the stills. Hashes were out of
  scope, so Film now offers that sign-off in one click when every still is kept.
- `docs/screenshots/film-cut-1440.webp` is removed, not replaced: this repo is
  public and a current screenshot would show a large frame of an unreleased film.
  The owner decides whether to publish one or use neutral stills.
