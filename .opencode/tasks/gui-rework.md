# GUI-first rework — task record

**Objective:** turn mp3-to-videoclip into one local GUI app (`uv run studio`) that owns the
LLM director, the paid generation and the render. One PR per phase, kept runnable, no
OpenCode crew and no user-facing CLI.

**Authority:** implementation brief supplied 25 Oct 2026 (reviewed revision `4e3b299`).
Decisions D1–D8 are in that brief and are authoritative. Three answers given 25 Oct
override it where they disagree:

- **zero-bars migrates** to schema 3 (it is the one live production: 79 shots, 240 s,
  82 stills, 16 accepts / 2 rejects, no render). The two finished films stay frozen.
- **Remotion Player assumed workable.** If the 79-shot composition cannot play smoothly,
  stop and ask before choosing a proxy fallback.
- **One PR per phase**: commit, push, merge, then start the next phase.

## Constraints

- Never delete anything under `projects/`, `backups/` or `archive/`. `projects/` is
  gitignored: the metadata snapshot in `backups/` is its only rollback besides the
  `pre-gui-rework` tag on code.
- No live paid call in tests. Source audio and generated stills are immutable.
- One commit per numbered task in the brief.
- Every phase ends with `pytest` and `ruff` green and an app that starts.

## Schema 3 semantics (decided during Phase 2)

Schema 3 is the native form of the guided workflow v2, not a new, weaker flow. The
engine therefore treats `schema_version == 3` exactly like `workflow_version == 2`:
the v2 prompt layout, character identity separate from description, reference
import receipts, accepted proof/stills reviews, preflight before storyboard
approval, and a required production budget. This was a real migration defect:
without it every migrated still failed its input-hash check and the film could not
be rendered, while cumulative budget admission silently had no cap. Approval
hashes intentionally exclude the administrative budget history, so a top-up
cannot invalidate a reviewed story.

## Deviation from the brief (recorded, reversible)

Phase 1's delete table removes the current Studio (`serve.py`, `studio_ui*`, `human_*`)
and the approval machinery before the replacement exists in Phase 4. That would leave no
working app — and no way to advance zero-bars — for the 2–3 weeks of Phases 2–3. So:

- Phase 1 deletes only what nothing else imports: the agent runtime, the second agent
  runtime (`spine/plans/context/evals/mcp/tools`), the static page generators and the
  dead one-off modules.
- `serve.py` and the approval paths stay, working, until the commit in Phase 4 that lands
  the new frontend. That frontend is now merged (PR #10); deleting the old server and
  its UI is the next slice. Phase 1's ≤ 11,000-line target is measured after that
  deletion, not at Phase 1 merge.

## Status

| Phase | State |
| --- | --- |
| 0 · safety net | **done** — tag `pre-gui-rework`, metadata snapshot (610 files), golden contract test |
| 1 · delete and migrate | **functionally complete on `gui-rework/phase-1-delete-migrate`.** Done: crew config and loop removed; second agent runtime removed (106 tests); `.opencode/skills` kept for Phase 3; read-only archive reader; static page generators and one-off tools deleted (`dashboard`, `inspector`, `intake`, `calibration`, `edits`); docs replaced with README + `docs/ARCHITECTURE.md` + 60-line `AGENTS.md`; B13 skeleton defaults unified; `studio` launcher added; feedback queue removed. Remaining modules (`flow`, `operations`, `sources`, `human_*`, `studio`, `studio_ui*`, `reviews`, `appdata`, `backup`, `signature`) are imported by the interim Studio/CLI and cannot be deleted until their replacements land in Phases 2-4 (recorded deviation). Legacy model branches move with them. `src/` 21,124 -> 17,371. |
| 2 · backend skeleton | **merged as PR #9** (merge `388fb27`, 25 Oct 2026). Done: FastAPI app and launcher; config/settings; job runner + SSE; projects, settings, track, story, storyboard, images, film, jobs, director, budget and approvals routers; domain staleness, schema 3 models and migration; zero-bars migrated; services layer; engine-budget bridge; director LLM adapter/tools/context/turn loop; Vite + React frontend with editable stage workspaces, approvals and paid-image controls. Gate: every route has an API test (28 route tests, no provider call); zero-bars detail opens in ~27 ms and the library in ~23 ms locally; B4/B6/B7 were waived by the owner. |
| 3 · director | **started inside Phase 2** — LLM adapter, tool dispatch, turn loop, stage-aware guides. Still open: compaction and the recorded fake-provider probe. |
| 4 · frontend | **merged as PR #10** (merge `80b09fc`, 25 Oct 2026). Phase 2 landed the library, five stages, director panel, job tray, approvals and image thumbnails/estimate/generate. This branch adds MP3 intake, schema-3 creation, LRC import, the adaptive skeleton button, ambient storyboard empty state, film playback, proof-shot selection, the waveform timeline with draggable/keyboard boundaries, the Remotion Player preview, error toasts, the source-audio endpoint and the 390/900/1280 keyboard pass. Remaining, as the next slice: delete the interim Studio (`serve.py`, `studio_ui*`, `human_ui.py`, `sources.py`) and port the approval metadata still imported by `api/approvals.py` from `human_actions`; `operations`, `flow`, `reviews`, `signature` and `backup` stay until their Phase 5 replacements. |
| 5 · render cleanup | not started |
| 6 · polish | not started |

## Live production state (zero-bars)

Schema 3, cap $8.00, committed $2.8843815, remaining $5.1156185 (the earlier
“$3.26 committed” figure came from per-task cent rounding in the app; the engine
commitment is now the single source). The migration changed the project document,
so the three recorded approvals were invalidated even though brief, board and
stills were untouched. On the owner's instruction they were re-approved in order
(brief → storyboard → proof) with notes recording that the content was unchanged
from the approved revision. All 79 selected stills now resolve and the gates pass.
A live one-shot image quote was taken for `a001-blue-face` at $0.05 (no
authorization, no generation). The director key is configured in the user's
settings file; a live Track-stage chat turn answered correctly.


## Phase 2 gate evidence (25 Oct 2026)

- `tests/test_api_routes.py`, `test_api_images.py`, `test_api_approvals.py` and
  `test_api_archive.py` exercise every route, including the NDJSON director
  stream, the SSE hello, job list/get/cancel and all error branches; the paid
  services are faked, so no provider call is made.
- `tests/test_job_runner.py` pins per-project serialisation, cross-project
  overlap, cancel-suppresses-success and the queued → started → succeeded event
  order.
- Local timings on `zero-bars`: `GET /api/projects` 23 ms, `GET
  /api/projects/{slug}` 27 ms (the expensive verified status moved behind
  `?verify=true`), scoped proof approvals 45 ms.
- Fixed while testing: unvalidated storyboard/lyrics/brief writes, secrets
  returned by `GET /api/settings`, a budget top-up that could go below committed
  spend or accept negative/zero, blocking analysis on the event loop, an
  unvalidated render kind, an SSE stream that waited 10 s to notice a closed tab,
  and a runner that serialised every project because it awaited jobs inline.
- The brief's B4/B6/B7 regression definitions are not in the repository. The
  owner waived them on 25 Oct 2026 and accepted the route/timing gate as Phase 2.

## Phase 4 intake slice (25 Oct 2026)

- `POST /api/projects` takes an MP3 body plus title/aspect/mode/budget query
  parameters, probes it, creates a schema-3 project through the engine intake and
  migration, adds the first cap entry and queues a free local analysis job.
- The origin guard now accepts the actual loopback port and the Vite dev port,
  not only 8000; browser writes on a random `uv run studio` port were previously
  rejected. The audio upload is the one non-JSON write the guard admits.
- Intake form with drag/drop, title, starting budget, 16:9/9:16 and vocal/
  instrumental. The new production is selected and opens in Track; Track polls
  until the analysis job lands.
- LRC import (`domain/lyrics.py`) keeps only the user's explicit `[mm:ss.xx]`
  tags and closes the last segment at the track duration; no positions are
  invented. Story exposes direction and style so a fresh brief can be approved.
- Storyboard empty state is a 200 marker (no console 404) and can create the
  adaptive timing skeleton without asking the user to certify measured evidence
  in a guided production.
- Film stage plays previews and finals through `GET /film/{kind}/{name}` with
  range support and inline disposition, auto-refreshes the file list while a
  render runs, and keeps the budget and approval gates. Proof shots are chosen in
  Storyboard through `POST /proof-shots`; the domain appends them to the brief,
  so changing the selection invalidates the brief and downstream approvals.
- End-to-end in a throwaway projects directory: upload a generated 3 s MP3 →
  project created → analysis succeeded (~117 BPM estimate) → LRC imported →
  brief approved → adaptive skeleton → proof shot selected → board approved →
  a 3 s preview played in the app (`readyState 4`). No paid call.

## Phase 4 UI slice (25 Oct 2026)

- **Timeline.** `Timeline.tsx` draws the measured `fine_windows` level envelope
  (or the 1 Hz energy fallback) under the shot band. A boundary drag resizes both
  adjacent shots, so every later cut stays at its frame; the API still validates
  the whole board before writing. Sliders are keyboard operable: arrows move one
  frame, shift moves ten, Home/End go to the clamped limits. A save in flight is
  guarded by a ref, so a fast keyboard repeat cannot race two PATCHes.
- **Player spike.** `@remotion/player` 4.0.536 and `remotion` 4.0.536 are pinned
  in `frontend/package.json`; the Player is a lazy chunk. Against the 79-shot
  `zero-bars` board it was interactive in ~800 ms, kept one still mounted, and
  played the source audio in sync (2.886 s at the 3 s check). The composition is
  an honest approximation: shot order, durations, dissolves, selected stills and
  audio; camera motion and transitions remain the renderer's authority.
- **Error toasts.** Every non-2xx API response raises a `studio-toast` event; the
  tray is `role="status" aria-live="polite"`, keeps the last three messages and
  dismisses each after 7 s. Inline stage errors remain for context.
- **Responsive and keyboard.** At 390 the page scrolls naturally instead of
  trapping the stage in a small inner scroll box; the storyboard table scrolls
  inside its card; the file input is focusable and the drop zone shows focus; all
  stages, sliders, table fields, approvals and the Director are reachable by Tab.
  The library, all five stages and the intake form were swept at 390, 900 and
  1280 with **no console errors and no HTTP responses >= 400**.
- **Intake hardening.** An unreadable MP3 is now a clean 400 (“the file is not a
  readable MP3”) instead of an uncaught ffprobe 500, and no half-production is
  left behind. The source audio is served at `GET /audio` with range support.
- **Tests.** `test_proof_shots_are_validated_and_saved`,
  `test_storyboard_boundary_update_keeps_later_cuts_in_place`,
  `test_track_read_lyrics_write_and_local_analysis` (audio bytes) and the
  unreadable-upload domain/API tests cover the new backend edges; the frontend is
  pinned by `npm run build` plus the browser sweep.

## Next slice: delete the interim Studio (not started)

The new app is the working replacement, but the old server is still imported by
its own surface and by the approval metadata path. Do this as one branch with the
suite green at every step:

1. Port the still-needed decision contract out of `human_actions`: `_body`,
   `stage_name` and `approve_stage` move to `domain/approvals.py` (or the API
   router); `api/approvals.py` stops importing `human_actions`.
2. Move `studio.ORDER` / `studio.approval_state` (used by `appdata.approvals`) to
   the domain, or retire `appdata.approvals` together with the old projection.
3. Delete `serve.py`, `studio_ui.py`, `studio_ui_flow.py`, `human_ui.py`,
   `sources.py` and `studio.py`; remove `clip serve` / `clip studio` and the
   `--actions` redirect text from `cli.py`.
4. Triage the old-surface tests before deleting them:
   `test_studio_browser.py`, `test_studio_actions.py`, `test_studio.py`,
   `test_live_layer.py`, `test_workflow_projection.py`. Port the still-true
   engine assertions first: guided policy/marker rules, atomic story approval,
   artifact path guards, quote authorization/cap/upload consent, preview-watched
   and graphics attestations. `test_guided_flow.py` keeps its non-HTTP tests.
5. Keep `flow.py`, `operations.py`, `reviews.py`, `signature.py` and `backup.py`
   until their Phase 5 replacements; keep `cli.py` for the engine commands that
   have no GUI yet (transcribe, listen, backup, sign, render maintenance).

Acceptance: no import of a deleted module; `uv run studio` starts and the five
stages still approve/authorize; `uv run clip serve` is gone; suite green; the
project count and hashes are unchanged.

## Acceptance per phase

- **0:** tag exists; snapshot restores metadata; golden passes. ✅
- **1:** no import of a deleted module; golden unchanged; archive lists both finished films;
  zero-bars imports to schema 3 and opens; suite < 3 min.
- **2:** every route tested; zero-bars opens < 150 ms; B4/B6/B7 regression tests.
- **3:** probe recorded; fake-provider session import → board → mocked batch → one
  regeneration; Stop < 1 s.
- **4:** every route zero console errors; 390/900/1280; keyboard-only path; Player spike. ✅ (measured above; interim-Studio deletion tracked separately)
- **5:** no Chrome read; preview + final on a clean runner; `timing.mjs` parity.
- **6:** fresh clone → `uv sync` → `uv run studio` → film, no terminal.

## Open questions

- Remotion Player at 79 shots: measured at ~800 ms to interactive with one still
  mounted; no reason to change the approach.
- YouTube audio bitrate in the brief (384 kbps) to be checked against the live spec in
  Phase 5; harmless if generous.
