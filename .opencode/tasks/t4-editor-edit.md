# T4 — Editor prompts, edit list and renderer primitives

Authorized: 2026-10-26, owner said "continue and do the whole of T4".

Branch: `director/t4-edit-primitives`
Phase record: `.opencode/tasks/gui-rework.md`
Spec: `.opencode/scratch/t1/writer-editor-brief.md`, T4 and *Editing instructions*

## Objective

Ship the Editor's structured cut and the renderer vocabulary it needs:

1. Rewrite `director/prompts/editor/*.md` around the technique library and the
   edit report.
2. Add `work/edit.json`, move timing and motion into it, and keep the storyboard
   as the content source.
3. Add shared Remotion primitives for transitions, accents, split layouts, text
   animation and grade presets; keep the four sliders as overrides.
4. Compute the edit report in Python and show it in Film and to the Editor.
5. Refuse more than three flashes in any one-second window in the renderer.
6. Unit-test each primitive and add a two-second visual sample in
   `docs/primitives/`.

## Constraints

- No paid provider call in tests or implementation.
- Legacy productions without `work/edit.json` keep their original storyboard
  timing, `Shot.transition` contract and approval hashes.
- The storyboard remains content-only; once an edit exists, timing and motion
  writes go through the edit and the Storyboard timeline is read-only.
- One PR for T4, with the app runnable and Python, Remotion and frontend checks
  green.

## Decisions

- `EditDecisionList` owns sections, shot order/spans, motion, transitions,
  accents, text and grade; `check_board` requires exact coverage and one decision
  per storyboard shot.
- `RenderShot` carries the matching `EditShot` and `Grade`, so MP4 and Player use
  one payload.
- The effective board is derived; stored storyboard timing is not rewritten.
- Edit transitions are a separate enum from the legacy `Shot.transition` list.
  `tests/test_timing_parity.py` keeps pinning the legacy contract.
- Preview and stills hashes bind the edit only when it exists; no-edit hashes are
  unchanged.
- The report treats coverage, transition handles/reasons and flash rate as hard;
  density, repetition, reading time, hold ratio and ad checks are warnings.
- Native split panes are passed to the Player and MP4 when every pane still is
  current; the precomposed local plate remains the fallback.
- The report is read through `get_edit`/`GET /edit`; `update_edit`/`PUT /edit`
  writes the cut. The Editor prompt always follows the write with the report.

## Acceptance

- Energetic fixture edit uses at least five different techniques with stated
  reasons.
- Its report has no hard findings and holds are under 50% of shots unless a
  section plan names a hold.
- Every primitive has a unit test and a two-second visual sample.
- The Player preview receives and draws edit text, grade, accents, transitions
  and native split panes.
- Renderer refuses four flashes in a one-second window.
- Tests and lint green; frontend builds; app starts.

## Work log

- Added edit models and `edits.py` (seed, save, effective board, report, flash
  rule, summary).
- Wired effective assets into preview/MP4 payloads; guarded `update_shots`;
  bound edit into preview/stills hashes.
- Added `GET/PUT /edit`, `POST /edit/seed`, `get_edit` and `update_edit`.
- Added Film cut report/seed/JSON save and the Storyboard read-only timeline.
- Extended `timing.mjs`, `BaseFilm.jsx` and `request.mjs`; added the renderer
  unit suite.
- Rewrote the six Editor prompt files and added the edit report to context.
- Added 21 two-second samples, manifest and gallery in `docs/primitives/`.

## Evidence

Python: 892 passed, 1 skipped; `ruff check .` and `ruff format --check .` clean.
Remotion: 24 tests passed. Frontend: `tsc -b && vite build` clean. Primitive
samples: 21 clips, each 2.000 s, ffprobe-verified and checked by contact sheet.

Live app: `uv run studio --port 8921` served `/api/projects` and the built
frontend. A disposable 10-shot production with an edit was served on port 8922;
the Film page showed 10 shots, 9 cuts, 30% holds, 1 flash, no hard findings and
16 reasoned techniques, and the Player DOM rendered the shots, warm-night grade
and edit payload. No paid provider call was made.

PR: pending final commit and push.

## Safe stops

- Live paid Writer/Editor evaluation still requires explicit spend authorization.
- Zero Bars delivery remains content-blocked: 68 of 79 shots lack a current
  accepted review, credits are unconfirmed, and no preview/base/final renders
  exist.

## Status

Implementation complete pending final revision checks, app start and PR review.
