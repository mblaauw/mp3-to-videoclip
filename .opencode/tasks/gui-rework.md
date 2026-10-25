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
- `serve.py` and the approval paths stayed, working, until the new frontend landed
  (PR #10). The Phase 4 cleanup then deleted the old server, its Python UI and the
  decision helpers the Studio no longer uses.

## Status

| Phase | State |
| --- | --- |
| 0 · safety net | **done** — tag `pre-gui-rework`, metadata snapshot (610 files), golden contract test |
| 1 · delete and migrate | **functionally complete on `gui-rework/phase-1-delete-migrate`.** Done: crew config and loop removed; second agent runtime removed (106 tests); `.opencode/skills` kept for Phase 3; read-only archive reader; static page generators and one-off tools deleted (`dashboard`, `inspector`, `intake`, `calibration`, `edits`); docs replaced with README + `docs/ARCHITECTURE.md` + 60-line `AGENTS.md`; B13 skeleton defaults unified; `studio` launcher added; feedback queue removed. The interim Studio (`serve.py`, `studio_ui*`, `human_ui.py`, `sources.py`, `studio.py`, `appdata.py`, `human_actions.py`) was deleted in the Phase 4 cleanup. Remaining after Phase 5: `flow`, `operations`, `reviews`, `signature`, `backup` and the engine-only `cli.py` for the Phase 6/legacy pass. `src/` 21,124 -> 17,371 before that cleanup, now 16,802 Python lines after Phase 5. |
| 2 · backend skeleton | **merged as PR #9** (merge `388fb27`, 25 Oct 2026). Done: FastAPI app and launcher; config/settings; job runner + SSE; projects, settings, track, story, storyboard, images, film, jobs, director, budget and approvals routers; domain staleness, schema 3 models and migration; zero-bars migrated; services layer; engine-budget bridge; director LLM adapter/tools/context/turn loop; Vite + React frontend with editable stage workspaces, approvals and paid-image controls. Gate: every route has an API test (28 route tests, no provider call); zero-bars detail opens in ~27 ms and the library in ~23 ms locally; B4/B6/B7 were waived by the owner. |
| 3 · director | **merged as PR #12** (merge `21c6ff5`, 25 Oct 2026). Phase 2 built the LLM adapter, tool dispatch, turn loop and stage-aware guides; this slice adds bounded prompt history, the recorded fake-provider probe, library-correct tool roots, domain-validated proof selection and a browser Stop. |
| 4 · frontend | **merged as PR #10** (merge `80b09fc`, 25 Oct 2026) and **cleaned up as PR #11** (merge `a3aefc8`, 25 Oct 2026). Phase 2 landed the library, five stages, director panel, job tray, approvals and image thumbnails/estimate/generate. Phase 4 added MP3 intake, schema-3 creation, LRC import, the adaptive skeleton button, ambient storyboard empty state, film playback, proof-shot selection, the waveform timeline with draggable/keyboard boundaries, the Remotion Player preview, error toasts, the source-audio endpoint and the 390/900/1280 keyboard pass. The cleanup added image reviews, preview/stills/graphics attestations and the final-render stills gate, then deleted the interim server and its old-surface tests. |
| 5 · render cleanup | **merged as PR #13** (merge `6916a6c`, 25 Oct 2026). One `BaseFilm` and `timing.mjs` now drive both the MP4 renderer and the live Player; renderer approvals no longer read the browser binary; a Studio preview job writes its own review report; schema-3 projects render with Remotion even after migration drops the legacy backend flag; preview and final were rendered cold on a copied production. `flow`, `operations`, `reviews`, `signature`, `backup` and the engine-only `cli.py` remain for the Phase 6/legacy pass. |
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

## Phase 4 closure: reviews and attestations (25 Oct 2026)

Found while planning the deletion: the new GUI could select a still but could
not record the accepted review `proof`/`stills` approval requires, and the
approval bar had no way to send `preview_watched`/`inspected`, so a new film
could never pass those gates.

- `POST /images/review` records a verdict, note and inspection acknowledgement
  against the exact version; `GET /images` returns the selected version's latest
  review. Stale input hashes are refused, alias shots resolve their owner, and
  the UI shows a verdict badge plus per-shot accept/reject/uncertain controls.
- `proof` and `stills` approval bars now appear on Images; a reviewed proof set
  and a reviewed full set both pass end to end in the browser.
- The approval bar sends `preview_watched` (preview), `inspected` (graphics) and
  `acknowledge_uncertain` (lyrics); preview/graphics Approve stays disabled until
  the matching box is checked. Verified preview approval in the browser.
- Engine validation errors from an approval now return HTTP 400 instead of a 200
  body with `error`, so the stage shows a toast and keeps the decision visible.
- A final render now requires the `stills` approval in both the API pre-check and
  `services.render.render_final`; the Film card says where that approval lives.

## Phase 4 cleanup (25 Oct 2026)

Merged as PR #11 (merge `a3aefc8`, 25 Oct 2026):

1. `domain/approvals.py` now owns `stage_name`, `_body` and `approve_stage`;
   `api/approvals.py` no longer imports `human_actions`. Engine validation errors
   return 400, not a 200 error body.
2. `studio.ORDER` / `studio.approval_state` went with `appdata` and the old
   projection; the new API computes approval state directly.
3. Deleted `serve.py`, `studio_ui.py`, `studio_ui_flow.py`, `human_ui.py`,
   `sources.py`, `studio.py`, `appdata.py` and `human_actions.py`; removed the
   `clip serve` / `clip studio` commands and updated the approve/authorize redirect
   to `uv run studio`.
4. Deleted the old-surface tests (`test_studio_browser.py`,
   `test_studio_actions.py`, `test_studio.py`, `test_live_layer.py`,
   `test_workflow_projection.py`). Kept the guided-policy tests in
   `test_guided_flow.py` and moved the still-true review coverage to
   `test_api_images.py` (full proof chain, full stills set, alias owner, stale
   inputs) and `test_api_approvals.py` (preview watch attestation). Added a
   project-slug path guard and its test.
5. Kept `flow.py`, `operations.py`, `reviews.py`, `signature.py`, `backup.py` and
   the engine-only `cli.py` beyond Phase 5 for the Phase 6/legacy pass.

Evidence: full suite green after the deletion; `uv run studio` starts and serves;
`uv run clip` no longer offers `serve` or `studio`; no import of a deleted module;
the zero-bars approvals and assets were not touched (the live Player check was
read-only).

## Phase 3 director close-out (25 Oct 2026)

- **Compaction.** `director/conversation.py` bounds a turn to 60 messages and
  keeps the most recent 24 from a user-turn boundary. Older user request
  snippets and tool names become a short summary appended to the system prompt;
  tool outputs and assistant prose are dropped. The JSONL log is never rewritten.
  The server prompt is rebuilt with the current project state every turn.
- **Recorded fake-provider probe.** `tests/test_director_probe.py` creates a real
  schema-3 production through `domain.intake`, approves the brief, then a scripted
  provider drives `get_project → create_storyboard → set_proof_shots →
  generate_images → generate_images(regenerate) → done`. The image service and
  runner are fakes; the turn loop and tools are real. It asserts the board covers
  the project, the proof selection is recorded, the first batch is not a
  regeneration, the second is, both quotes are authorized and both jobs queue.
  The scripted turn completes in under 1 s (no network, no paid call).
- **Stop.** The composer shows a Stop button while a turn runs; aborting the
  fetch returns the button in 15 ms in the browser. `run_turn` also closes in
  under 1 s when its stream is closed mid-turn (the server path on disconnect).
- **Zoom.** The director's tool root now follows the configured projects
  directory instead of hardcoded `./projects`; the search path is tested from a
  different working directory. `set_proof_shots` goes through
  `production.set_proof_ids`, so the same count/known-ID rules apply in chat.
- **Chat errors and streaming.** Missing messages and a missing LLM key are HTTP
  400/503 instead of 200 bodies the stream parser ignored. The composer buffers
  NDJSON lines across network chunks and shows the API detail as a toast.
- **Live evidence.** The owner's configured provider answered a real Track-stage
  chat correctly in the earlier Phase 4 session; the fake probe above is the
  repeatable record.

## Phase 5 render close-out (25 Oct 2026, PR #13)

- **One composition.** `renderers/remotion/src/BaseFilm.jsx` is imported by both
  `index.jsx` (MP4) and `frontend/src/baseFilm.ts` (Player). The Player also runs
  `timing.mjs` for allocation, visible layers, camera, grade and transitions; it
  no longer keeps a second zoom/pan approximation. Vite dedupes React and Remotion
  so the shared file uses the frontend's single runtime.
- **Preview payload.** `GET /preview` returns the renderer's own shot fields,
  selected-still URLs and source audio. Missing stills keep their allocated span
  and show the same placeholder marking; stale stills are counted in the card.
  Film no longer rebuilds shots from three independent responses.
- **Browser parity evidence.** On a 4-shot board, seeking to local frame 57
  produced `width 1298.07`, `height 730.165`, `left -9.03529`, `top -5.08235` —
  exactly `cameraAtFrame`/`layerRect` at frame 3 of an 18-frame zoom. On a board
  with `wipe_left` and a 3-frame handle, frame 31 showed the outgoing and incoming
  layers with `clip-path: inset(0 74.0741% 0 0)`. The rendered frame 31 sampled
  incoming on the left and outgoing on the right; frame 33 was fully incoming.
  Zero-bars: 79 shots, Player interactive in 1.32 s with one image mounted, no
  console errors, audio present.
- **No Chrome read.** `implementation_hash()` hashes renderer source, lockfile,
  adapter and font bytes, never the Chrome binary. A test changes and removes
  `REMOTION_CHROME`; the revision stays identical. Local Node/Chrome are checked
  when a render starts, not when an approval is compared.
- **Preview gate.** The Studio preview job writes `work/preview-review.json`
  (movie bytes, storyboard, proof, brand, renderer revision) so the preview
  approval is available immediately after the job. The test renders through the
  service, approves with the watch attestation and calls `require_approval`.
- **Native schema 3.** `init_project` writes schema 3 from the start, and the
  budget rewrite changes only `budget`, preserving backend/signature/source
  fields. Previously the app's migration plus budget write stripped
  `renderer_backend`, so a new film silently fell back to the FFmpeg path (and a
  short film failed on the brand duration). Schema 3 without the flag now selects
  Remotion; an explicit backend still wins for schema 1.
- **Cold renders.** On a copied production with no Remotion caches, the GUI job
  path produced a preview and a final: 72 frames, 24 fps, 1920x1080, H264
  yuv420p, AAC 44.1 kHz, 3.000 s each, full decode with no errors. The preview
  report bound the new bytes and the preview approval passed. A second copied
  board with a wipe, fade and post effects rendered a 72-frame preview; sampled
  pixels at the dissolve frames matched the shared transition function.
- **Python ↔ timing parity.** `tests/test_timing_parity.py` loads the actual ESM
  with Node and compares zoom/camera moves, graphics constants, brand constants,
  post-effect bounds, transition literals, allocation acceptance/total frames and
  legacy camera endpoints with `render.py`, `graphics.py` and `models.py`.

## Acceptance per phase

- **0:** tag exists; snapshot restores metadata; golden passes. ✅
- **1:** no import of a deleted module; golden unchanged; archive lists both finished films;
  zero-bars imports to schema 3 and opens; suite < 3 min.
- **2:** every route tested; zero-bars opens < 150 ms; B4/B6/B7 regression tests.
- **3:** probe recorded; fake-provider session import → board → mocked batch → one
  regeneration; Stop < 1 s. ✅ (probe in `tests/test_director_probe.py`; browser Stop 15 ms)
- **4:** every route zero console errors; 390/900/1280; keyboard-only path; Player spike. ✅
- **5:** no Chrome read; preview + final on a clean runner; `timing.mjs` parity. ✅ (browser frame 57 and wipe frame 31 matched; cold preview/final 72 frames each; parity test in `tests/test_timing_parity.py`)
- **6:** fresh clone → `uv sync` → `uv run studio` → film, no terminal.

## Open questions

- Remotion Player at 79 shots: measured at 1.32 s to interactive with one still
  mounted after the shared composition; no reason to change the approach.
- YouTube audio bitrate in the brief (384 kbps) remains a presentation note, not
  a timing or approval input.
