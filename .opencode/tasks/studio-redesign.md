# Studio redesign — phased implementation

Authorized: 2026-10-26, owner asked to implement the complete Studio redesign.
Source: `studio-redesign-handover.zip` (README, 01–05, tokens, prototype,
screenshots), with `05-update-42a33cf.md` overriding 01–04 where they differ.
Base: `main` at `42a33cf` (T0–T5 merged).
P0 branch: `studio-redesign/p0-correctness`, merged as PR #24 (`1a3800e`).
P1 branch: `studio-redesign/p1-foundations`, merged as PR #25 (`71406aa`).
P2 branch: `studio-redesign/p2-shell`.

## Objective

Replace the old rail/tabs Studio with the handover design: the song as a shared
spine, one next step per stage, pictures at picture size, one-click approvals,
a role-aware director drawer, readable cut, inline ratings and a settings dialog.

One PR per phase. Every phase ends with:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
npm run build --prefix frontend
uv run studio   # app starts and the affected screens are checked
```

No paid provider call in any phase. Money, timing, rendering and approval-hash
logic stay authoritative in the existing engine modules.

## Decisions

- **Ratings:** keep all four T5 rating artifacts — brief, concepts, storyboard,
  edit — as compact inline controls. Do not collapse to the three spots named in
  the handover.
- **Credits:** add a credits confirmation card to Story before brief approval;
  keep the full `CreditsEditor` on Film for later changes. The signature gate is
  not relaxed and no credit is invented.
- **Browser verification:** do not add Playwright. Use the OpenCode browser tool
  for the phase sweeps and record the evidence. If committed browser tests are
  wanted later, that is a separate dependency decision.
- **Design assets:** commit the handover docs, tokens and proposed screenshots
  under `docs/design/studio-redesign/`; do not commit the prototype's mock media.
- **API typing:** generate the OpenAPI schema, add response models for the routes
  the redesign touches, and keep explicit types for legacy untyped routes.
- **Job progress:** use SSE for status and an honest indeterminate bar until the
  backend can report real per-job progress. Do not invent progress or cost.
- **Plain lyrics:** extend `Lyrics` with untimed lines; never invent timestamps.
- **`Shot.change`:** dropped; `05-update-42a33cf.md` does not require it.

## Phases

| Phase | Scope | Status |
| --- | --- | --- |
| P0 | K13 vocal promo/advert brief approval; K2 real blocking stage | Complete (PR #24, `1a3800e`) |
| P1 | Tokens/font, UI primitives, SSE jobs, API types, error codes | Complete (PR #25, `71406aa`) |
| P2 | Shell, routes, library, top bar, next step, budget/jobs, spine, director drawer | Complete (PR pending) |
| P3 | Track and Story, Brief card, excerpt band, lyrics, credits card, one-click approval | Not started |
| P4 | Storyboard cards/table/inspector, Images contact sheet/lightbox, priced actions | Not started |
| P5 | Film Cut tab, checklist, credits editor, settings, director tool cards, history | Not started |
| P6 | Empty/loading/error states, responsive and accessibility pass | Not started |

## P0 — correctness

### Scope

- K13: `production.effective_upstream` must return `analysis` for `brief` on a
  promo or advert, regardless of vocal/instrumental mode. A vocal advert has no
  lyrics artifact, and that must not block story approval.
- K2: `_approval` must name the stage that actually blocks an unavailable
  artifact (`blocking_stage`), instead of the generic
  "artifact has not been created" message.
- Add regression tests that create a vocal advert, write its brief and approve
  it, and that a music video without lyrics reports `lyrics` as the blocker.

### Constraints

- Do not change approval hashing, note requirements, budgets, timing or pixels.
- The existing guided-flow policy and the signature gate stay as they are.
- No provider or model call.

### Acceptance

- A vocal advert can be created through `POST /api/projects`, its brief patched
  and approved through `POST /approvals/brief`.
- A music video without `work/lyrics.json` returns an unavailable brief state
  with `blocking_stage: "lyrics"` and a message that names lyrics.
- `pytest`, `ruff`, format check and frontend build are green; the app starts.

## Evidence

P0 verified on `studio-redesign/p0-correctness` at the final working tree:

- `uv run pytest -q`: **907 passed, 1 skipped** (104.69 s). This includes three
  new regressions in `tests/test_api_kind_upstream.py`: a vocal advert can
  approve its brief; a vocal music video without lyrics reports
  `blocking_stage: "lyrics"`; a missing storyboard reports its own stage.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 210 files already
  formatted.
- `npm run build --prefix frontend`: clean, 54 modules.
- `uv run studio --projects-dir /tmp/opencode/t4-player --port 8924`:
  `/api/health` returned `{"ok":true,...}` and
  `/api/projects/production/approvals?stages=brief` returned a normal missing
  state, so the app still starts and serves approvals.
- No paid provider call was made; no production under `projects/` was modified.

P0 shipped in PR #24, squash-merged as `1a3800e` on 26 Oct 2026. CI (`check`)
passed in 4m46s before the merge.

## P1 — foundations

### Scope

- Copy the handover tokens to `frontend/src/styles/tokens.css`, self-host
  Schibsted Grotesk 5.3.0, and keep the old screen variables as aliases so no
  stage breaks while it is rebuilt.
- Add token-only `ui/` primitives and use them in the jobs tray.
- Replace the 3-second jobs polling with one `/api/events` EventSource, a jobs
  store with reconnect/backoff, and honest indeterminate progress.
- Generate `frontend/src/api/schema.d.ts` from the app's OpenAPI document with
  `npm run api:types`; add response models for the routes touched and alias
  those generated types in `api.ts`.
- K11: every 4xx/5xx is `{detail, code}`; the frontend throws a typed `ApiError`
  and maps stable codes to copy.

### Constraints

- No money, timing, rendering or approval-hash change.
- No paid provider call.
- No new dependency beyond `@fontsource-variable/schibsted-grotesk@5.3.0` and
  `openapi-typescript` 7.x.

### Acceptance

- Existing screens render with the new font and tokens.
- A queued job reaches the tray over SSE; polling is gone; no progress is
  invented.
- `npm run api:types` is reproducible and `npm run build` type-checks.
- Every tested API failure returns `{detail, code}`.

## P1 evidence

P1 verified on `studio-redesign/p1-foundations` at the final working tree:

- `uv run pytest -q`: **915 passed, 1 skipped** (102.84 s). New coverage:
  eight envelope cases in `tests/test_api_errors.py` (including a hidden 500)
  and a JSON `hello` parse in `tests/test_api_routes.py`.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 219 files already
  formatted.
- `npm run api:types`: regenerated from the app OpenAPI document; `JobOut`,
  `JobDetailOut`, `JobProgress`, `CancelOut`, `ApprovalStateOut`, `ApprovalsOut`
  and `ApprovalOut` are generated types now used by `api.ts`.
- `npm run build --prefix frontend`: clean, 67 modules; the two Schibsted
  Grotesk woff2 files are emitted into `dist`.
- Live Studio on port 8931 with `/tmp/opencode/t4-player`: the browser reported
  the Schibsted font loaded, the neutral `rgb(27, 28, 31)` surround, and no
  console errors. A local analysis upload produced a queued job that appeared in
  the tray as `analysis · Done` through SSE. The first live probe exposed that
  `sse-starlette` was sending Python dict reprs; the stream now emits JSON and
  the regression parses the `data:` line.
- Error envelope spot checks: `POST .../chat` with no body returned
  `{"detail":"message required","code":"bad_request"}`; missing projects, jobs,
  validation failures, stale/invalid approvals and the missing director key all
  returned their stable codes.
- No paid provider call was made; test uploads went to the `/tmp` fixture, not
  `projects/`.
- Browser evidence was collected before the browser tool was temporarily removed
  from the session catalog and again after it returned. No Playwright dependency
  was added.

P1 shipped in PR #25, squash-merged as `71406aa` on 26 Oct 2026. CI (`check`)
passed in 4m15s before the merge.

## P2 — shell, library, spine

### Scope

- Hash routes `#/` (library), `#/:slug/:stage` and `#/archive/:slug`; remove the
  left rail.
- `TopBar` with the mark, title/breadcrumb, stepper, budget chip/popover, jobs
  popover, director toggle and settings entry.
- `NextStepBar` backed by one pure `nextStep(stage, project, approvals, images,
  budget)` function with executable tests for every rule.
- Library with poster mosaics, cheap stage states, next-step copy, *New film*
  modal, MP3 drop target, *Delivered* section and a read-only archive player.
- `ProjectSummary` adds `poster_stills`, `stage_states`, `next_step`,
  `remaining_usd`, `updated_at`, `audio_url`, `shots`, `music_mode`,
  `has_analysis` and `has_lyrics`.
- One `PlayerProvider` (single `<audio>`, shared time) and a `Spine` with
  waveform, filmstrip, sections and playhead. Boundary dragging moved out of
  `Timeline.tsx`, which is deleted; Storyboard now owns cut editing.
- Film's Remotion `LivePlayer` follows the shared time and play state.
- Director drawer restyled; open by default above 1180 px, overlay below.
- K12: `GET /budget` reports `spent_usd`, `reserved_usd` and `paid_stills`
  alongside `committed_usd`.
- Read-only archive media routes so the library never exposes filesystem paths.

### Decisions

- Library summaries stay cheap: approval records plus artifact mtimes, never full
  gate hashes per card. Approval endpoints remain authoritative.
- Inside a production the top bar's stage states are derived from the loaded
  approval states, so the stepper and the next-step bar cannot disagree. The
  library keeps the cheap summary heuristic.
- Archive render and stills are addressed by `/archive/render` and
  `/archive/stills/<index>`; the render is served with byte-range support for the
  video player.
- `nextStep` is plain TypeScript under `frontend/src/shell/nextStep.ts`; its 28
  rules run under Node's native TypeScript stripping
  (`npm test --prefix frontend`), so no test dependency was added.
- `POST /budget` records a new absolute cap, as the engine already did. The
  popover therefore computes `current cap + amount` and labels the action *Add to
  budget*; it never lowers the cap by treating the amount as the total.
- No progress is invented: running jobs with no reported units keep an
  indeterminate bar and the copy says "working…".

### Acceptance

- At 1440, 900 and 390 px the library and every stage show the top bar,
  next-step bar (where applicable) and the spine, with no page-level horizontal
  overflow.
- Playing in Track and switching to Film preserves the shared time.
- Moving a boundary on the spine updates the Storyboard and its approval state.
- Every route renders without a console error or a request with status ≥ 400.
- Archive playback and stills work without exposing a path.

## P2 evidence

P2 verified on `studio-redesign/p2-shell` at the final working tree:

- `uv run pytest -q`: **919 passed, 1 skipped** (123.22 s). New coverage in
  `tests/test_api_library.py`: summary stage states/next step, poster image
  routes, K12 spend/reserve/paid-still split, archive summary and read-only
  render/still routes.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 220 files already
  formatted.
- `npm run build --prefix frontend`: clean, 80 modules. `npm test --prefix
  frontend`: **28 passed**.
- Live Studio on a `/tmp/opencode` fixture (a copy of `zero-bars`, with the two
  frozen films symlinked read-only) served the library and every stage. The
  direct OpenCode browser tab is 1000×700, so 1440×900 and 390×844 were measured
  through a same-origin iframe harness; there was no page-level horizontal
  overflow at any size, the spine sat at the viewport bottom, and the library
  grid was 3 / 2 / 1 columns at 1440 / 900 / 390.
- The director is a 380 px static column at 1440 and a full-height overlay at
  900 and 390 (`position: fixed`, 380 px and 390 px wide), with no overflow.
- Playback evidence: seeking the shared audio to 60.0 s moved the Remotion player
  to frame 1440 (24 fps); playing from Track and switching to Film kept the time
  and the player within two frames. Moving the first Storyboard boundary one
  frame right changed `a001` from 114 to 115 frames and `a002` to start at 115
  through the API, and the table and approval state followed.
- Budget evidence: the popover showed 82 paid stills, $2.88 spent, $0 reserved
  and $5.12 of $8.00 left; adding $1.00 produced a $9.00 cap, $6.12 remaining and
  a new history entry. No paid provider call was made.
- Route sweep (library, Track, Story, Storyboard, Images, Film, archive): no
  console errors and no requests with status ≥ 400. Archive render and stills
  returned 200/206; media `failed` entries were aborted range streams after the
  browser buffered enough, not HTTP errors.
- Fixture limitation: copying `zero-bars` without preserving mtimes made the
  cheap library heuristic call already-approved stages "changed"; the shell's
  authoritative approval states stayed "approved". This confirms why the
  library uses the cheap summary and the film shell uses the approval endpoints.
- No production under `projects/` was modified; all mutations happened in the
  `/tmp` fixture. No Playwright dependency was added.

## Next

P3 — Track and Story: facts row, editable section names, plain-text lyrics,
brief card, excerpt band, credits card and one-click approval.
