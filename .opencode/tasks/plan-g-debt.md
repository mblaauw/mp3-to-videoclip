# Phase G: pay down the debt — plan

**Proposed** 1 Nov 2026 for owner approval; base `main` at `c1414a3`.

**Objective:** one schema in the engine, one renderer, one compositor behind the CLI,
a CLI that is a table, a report and an approval that read as lists of rules, and a
frontend whose reads are shared, whose types are hand-owned, whose big files are
split by concern and whose styles have no override layer. Phase G runs behind
Phases A to I (roadmap order A, H, B, D, C, E, I, F, G), so every task here is
ordered so that nothing blocks another phase, and three tasks are pulled forward
because another phase edits the same file. Nothing in this plan changes a
production, a hash, the money journal or the picture; the one golden regeneration
is expected to be byte-identical and the commit must say so.

## What the code showed

**Schema branches and why the version fields cannot simply be deleted.**

- `models.py:97` declares `schema_version: Literal[1, 3] = 1`; `:112` `workflow_version:
  Literal[2] | None`, `:117` `prompt_version: Literal[2] | None`, `:120`
  `renderer_backend`, `:128-132` the `uses_remotion` property, `:139-162` a serializer
  that drops the fields only when `None`. `models.py:54` sets `extra="forbid"` on
  every model: a field removed from `Project` makes every `project.json` that still
  carries it unreadable.
- Every Studio film carries all three flags. `production/intake.py:163-186` writes
  `schema_version=3` together with `workflow_version=2`, `prompt_version=2` and
  `renderer_backend="remotion"`; `domain/intake.py:147` then calls `migrate`, which
  returns at `domain/migrate.py:52-53` because the document is already schema 3, so
  nothing strips them. The migrated `zero-bars` is the opposite case: `LEGACY_KEYS`
  at `domain/migrate.py:20-25` removed them.
- Every stage hash binds the project document: `production/approvals.py:220` is
  `digest({"project": project_payload(project), "upstream": parent, "content": value})`
  and `production/project.py:85-95` pops only `renderer_backend` and `budget`. So
  `workflow_version` and `prompt_version` are inside every approval of every film
  made in the Studio. Removing them from the model or the file would un-approve
  every live film, which AGENTS.md forbids without a stated reason. `api/track.py:221`
  rewrites `project.json` from `model_dump()` on a music-mode change, so the fields
  must survive a round trip through the model as well. Conclusion: the branches go,
  the two fields stay as inert provenance that is parsed and written back when
  present and read by nothing.
- The branch helpers and every caller: `production/project.py:55-62`
  `creative_workflow` (callers `image_specs.py:228,235,308`,
  `approvals.py:95,179,205,259,325,341,355,381`, `board.py:182`, `preflight.py:70,167`);
  `project.py:80-82` `prompt_look_first` (`image_specs.py:173,272,280`);
  `budget.py:77-96` `workflow_version`, `schema_version`, `strict_paid`
  (`budget.py:126,153,233,258,289,322,507-508`); `preflight.py:14-17`
  `strict_workflow`; direct `prompt_version` reads at `cli.py:555`, `api/story.py:131`,
  `approvals.py:327`, `director/prompts.py:157`; direct `workflow_version` reads at
  `cli.py:785`, `preflight.py:190`; `uses_remotion` at `edits.py:167`, `render.py:634`,
  `approvals.py:138`, `remotion.py:143`. For a schema-3 document every one of these
  takes the creative, strict, Remotion branch.
- The migrated film and the native films already disagree. `director/prompts.py:157`
  (`structured = project.get("prompt_version") == 2`), `production/approvals.py:327`
  and `api/story.py:131`, which feeds `frontend/src/shell/nextStep.ts:246` and
  `frontend/src/story/WorldPart.tsx:33`, treat `zero-bars` as an unstructured story
  (no `profile` task, no profile card, no profile check at brief approval) while a
  film made the same day in the Studio is structured. `tests/test_director_prompts.py:163-166`
  pins the unstructured path by popping the field. Flattening to schema 3 removes
  the disagreement; `zero-bars`' approved brief is not re-hashed by it because the
  field is absent from its document either way.
- `flow.py` has no schema branch. It branches on the `work/guided-flow.json` marker
  (`flow.py:38-57`), written for every Studio film at `production/intake.py:201`, and
  read at `generation.py:139,417,689`, `approvals.py:57,67,192,320`, `board.py:201`,
  `signature.py:163` and `api/film.py:31`. It stays.
- `budget.py:151-166` reads a schema-3 cap from `project.json` and refuses when a
  `work/production-budget.json` with a different cap also exists; `:233-246` writes
  only the schema path; `domain/migrate.py:72-76` deletes that legacy file after
  copying it to `history/`, so no schema-3 folder has one unless placed by hand.
  `correction_policy` at `:320-325` returns the inactive `(False, 2)` only for a
  non-strict project, and `check_capacity` at `:268-275` returns `None` only when
  `require_budget` found no record on a non-strict project.
- Sub-artifact literals are not the project schema and stay: `StoryPlacement`
  (`models.py:438`), `Treatments` (`:452`), `Storyboard` `Literal[1, 3]` (`:689`),
  `EditDecisionList` (`:1014`), `derivations.py:108`, `image_specs.py:150`,
  `operations.py:311`.

**Frozen films are read by the archive reader only, with one exception.**

- `domain/archive.py:41-45` owns every folder whose `project.json` is not schema 3
  and reads raw JSON (`:34-39`), never `Project`. `api/projects.py:239-251` lists
  them and `:472-478` opens them through it; `api/film.py:289-322` serves their
  newest render and stills; `api/_helpers.py:28-31` answers 409 on every stage
  route; `jobs/runner.py:93-97` refuses jobs for them. `tests/test_archive.py` (six
  tests, including the hash-of-the-tree proof at `:85-90` and the local two-films
  test at `:93-108`) and `tests/test_api_archive.py:12-33` pin all of it.
- The exception: `tests/test_creative_production.py:35,251-261` reads the local
  schema-1 pilot `projects/kortjakje` through `P.stage_hash` and `P.image_spec`,
  skipped where the folder is absent. It is the only engine path that still needs a
  schema-1 `Project`.

**The FFmpeg render path is reachable from the CLI only.**

- `render.py:634-646` hands every `uses_remotion` project to `remotion.render_base`;
  `:647-775` is the zoompan plate and assembly path for a schema-1 project with no
  backend flag, which the Studio never loads (`jobs/runner.py:95`, `api/_helpers.py:30`).
  Its callers: `cli.py:28` (`render`, `sheet`), `preview.py:26` (the CLI animatic,
  `cli.py:26`) and `services/render.py:12` (`_render`, always Remotion for schema 3).
- `remotion.py` itself depends on the probe and mux helpers in `render.py`:
  `R._binary`, `R._run`, `R._count_frames`, `R._validate_output`, `R._validate_shots`,
  `R.audio_seconds`, `R.AUDIO_BITRATE` (`remotion.py:545,678,714,840,1076`);
  `audio.py:83,114`, `production/intake.py:14`, `production/__init__.py:31` import
  `audio_seconds` and `probe`; `framecheck.py:14` imports `_binary`. Those are
  FFmpeg helpers, not the FFmpeg renderer.
- `tests/test_render.py` (13 tests, 14 `R.render(` calls), `tests/test_camera_path.py`
  (5) and `tests/test_preview.py` (5) exercise the zoompan path and the animatic
  only; `tests/test_timing_parity.py:151-156,189-204` compares `timing.mjs` with
  `render._MOVES`, `render.ZOOM_RANGE` and the `_zoompan` expression string, so the
  camera vocabulary needs a home outside `render.py` (`models.py:578` already
  declares the five moves as `Shot.camera`).
- `docs/RENDERER.md:1-10,104-111` and `README.md:168` describe the two backends.

**The golden fixture already takes the creative path.**

- `tests/test_contract_golden.py:44-60` builds the project with `workflow_version=2`,
  `prompt_version=2`, `renderer_backend="remotion"` and no `schema_version`, so it is
  a schema-1 document on the workflow-2 branch. `tests/golden/contract.json` holds
  `prompts`, `timing`, `remotion_request`, `remotion_titled_request` and none of the
  version fields. `creative_workflow` and `prompt_look_first` are true for workflow 2
  and for schema 3 alike, so a schema-3 fixture is expected to produce identical
  bytes.

**`graphics.py` is a compositor the Studio no longer composes with.**

- 2,566 lines. The Studio needs `resolve_font` (`remotion.py:125`, the renderer
  revision), `resolve_palette`, `load_spec`, `_load_project`, `_timing_board`
  (`titles.py:134-146`), `intro_phase_samples`, `_preflight_samples`, `resolve_design`,
  `implementation_revision` (`signature.py:277-360` `prepare_titles_review`, which
  renders review stills with `remotion.render_stills`), `validate_layout` and
  `ComposeError` (`services/preview.py:169`).
- `compose` (`graphics.py:1914-2157`), the alpha track builder (`_build_track`
  `:1843`, `_write_overlay` `:1604`, `_validate_overlay`, `_cache_integrity`,
  `track_key`, `element_key`), `preflight_frames` (`:2303`) and `main` (`:2474`) are
  reached from `cli.py:854` (`render` without `--base-only`), from
  `signature.prepare_review` (`:192-232`, only caller `cli.py:876-880`), from
  `remotion.overlay_clip` (`remotion.py:1004-1075`, only caller `compose`) and from
  `services/render.py:168`, which composites only when the recorded titles review has
  no `method`, that is one prepared by the CLI; the Studio writes
  `method: composition-v1` (`signature.py:338,346`) and `validate_review` `:404-408`
  takes that branch first.
- Measured here: `uv run pytest -q` 1,532 passed, 2 skipped in 284.5 s (368 s in the
  assessment); `tests/test_graphics.py` (10 tests) and `tests/test_graphics_cache.py`
  (22 tests) alone take 147.4 s. The ten slowest tests in the suite are all
  compose, overlay-cache and base-preflight tests. Across the two files `compose`
  is called 22 times, `preflight_frames` 10 (`test_graphics_cache.py:414,564,603,628,665`,
  the old base-sampling method), `track_key` 10. They share the schema-1 fixture in
  `tests/conftest.py:121-183`. The pure tests (sfx fit, caption fit, scrim, mark,
  palette defaults, subtitle, bundled font, key stability) do not need a base movie.

**`cli.py` is an if-chain over a table it already has.**

- `parser()` (`cli.py:45-125`) declares 34 subcommands: `doctor`, `schema`, `init` and
  a 31-entry name-to-help table at `:89-120`. `execute` (`:336-886`) is 550 lines
  with 32 `if cmd ==` branches; `approve` and `authorize` are refused in `main`
  (`:891-894`) and their help already says "Moved to the Studio" (`:92,104`). Ruff's
  C901 reports `execute` at 71 and `parser` at 29 (the assessment's 127 counted by
  AST). Branch bodies hold logic of their own: `render` `:821-882` (the only
  `prepare_review` call), `sheet` `:775-820` with a `workflow_version == 2` branch at
  `:785`, `skeleton` `:539-588` with `prompt_version == 2` at `:555`.
- Tests call `parser().parse_args([...])` in 12 files; by subcommand: `skeleton` 10,
  `render` 7, `sheet` 4, `schema` 4, `preview` 4, `budget` 4, `restage` 3, `prompts` 3,
  `status`, `quote-transcription`, `progress`, `costs`, `backup` 2 each, and one each
  for `transcribe`, `select`, `recover`, `quote-music`, `preflight`, `locate`, `init`,
  `import-lyrics`, `events`, `doctor`. `tests/test_cli_monitoring.py` and
  `tests/test_quality_cli.py` are the CLI's own tests; the rest use the CLI as a
  shortcut to an engine function.
- Studio routes that cover a subcommand (`src/mp3_to_videoclip/api/`): `POST
  /api/projects` (`init`), `POST /analyze` (`analyze`), `GET /approvals` and
  `GET /api/projects/{slug}` (`status`), `POST /approvals/{stage}` (`approve`),
  `PUT /lyrics` (`import-lyrics`), `POST /storyboard/skeleton` (`skeleton`),
  intake's `init_events` (`events`), `GET /images` and the Images prompt view
  (`prompts`, `preflight`), `POST /render` kind `preview` (`preview`),
  `POST /images/estimate` and `/images/generate` (`quote`, `authorize`, `generate`),
  `POST /images/select` (`select`), `POST /images/review` (`review`), the Images
  contact sheet (`sheet`), `POST /render` (`render`), `GET`/`POST /budget` (`costs`,
  `budget`), the Spine and Film timeline (`locate`).

**`edits.report`, `approvals.approve` and `tools._dispatch`.**

- `edits.py:397-776` `report` is 379 lines, C901 43, and emits 19 finding codes
  (`coverage`, `flash_rate`, `opening_transition`, `transition_reason`,
  `transition_handle`, `transition_repetition`, `hold_ratio`, `hold_ratio_total`,
  `density_target`, `energy_density`, `long_static_shot`, `motion_repetition`,
  `travel_repetition`, `framing_repetition`, `reading_time`, `text_reading_time`,
  `crop_soft`, `section_no_feel`, `ad_check`) with block comments at `:589,606,663,687`
  marking the families. `tests/test_edits.py` has 19 tests, six on the report
  (`:269,287,323,453,475,497`); `frontend/src/film/cutNotes.ts` keys on the codes.
- `production/approvals.py:281-416` `approve` is 135 lines, C901 41: attestation rules
  `:292-298`, then per-stage checks `lyrics` `:300-316`, `brief` `:317-350`,
  `storyboard` `:351-359`, `analysis`, `preview`, `graphics` `:370-380`, reviews
  `:381-394`, then the write.
- `director/tools.py:380-560` `_dispatch` is 24 `if name ==` branches (`:390-540`),
  C901 33, behind `dispatch` `:370-377`.

**Frontend.**

- A shared read cache exists: `frontend/src/api/resources.ts` dedupes in-flight GETs
  by path and invalidates by slug and an artifact dependency table (`:4-16`);
  `api.ts:715-751` routes every project GET, `/api/projects`, `/api/settings` and
  `/api/setup` through it; `shell/projectEvents.ts:46` invalidates per change before
  dispatching `studio:project-changed`. The server names the artifact for
  request-made changes (`app.py:220-230`); job and disk changes carry none
  (`jobs/watch.py:145`), which clears every key of the film.
- The cache dedupes only reads that overlap in time and holds no value, so every
  consumer keeps its own copy: `FilmShell.tsx:343-362` fires eight reads per change
  (approvals, images, budget, storyboard, track, edit, intake, settings) into 28
  `useState` slots; `stages/Images.tsx:111-120` five (images, budget, brief,
  storyboard, track); `film/useFilmData.ts:87-94` six (exports, edit summary,
  checklist, storyboard, images, graphics review); `story/useStoryData.ts:67-71`
  three. `images`, `storyboard`, `track` and `budget` are read by two or three
  consumers each.
- `api.ts` is 1,105 lines: `Schemas[...]` is used six times (`ApprovalOut`,
  `ApprovalStateOut`, `ApprovalsOut`, `JobDetailOut`, `JobOut`, `ProjectSummary`) and
  71 types are hand-written; `api/schema.d.ts` is 4,077 generated lines;
  `npm run api:types` (`package.json:11`) needs `uv run` and `scripts/dump_openapi.py`.
- `shell/Director.tsx` 943 lines (16 `useState`, 10 `useEffect`; tool rows and
  summaries `:138-298`, the drawer from `:322`, `send` `:573-686`, `stop` `:687`,
  `undo` `:695-724`); `stages/Images.tsx` 886 (13/6; load `:111-139`, style check
  `:471-528`, toolbar `:529`, lightbox inline from about `:600`); `shell/FilmShell.tsx`
  789 (28/6; `FilmShellContent` `:294-720`, `LibraryShell` `:721`, `ArchiveShell`
  `:765`).
- Thirteen stylesheets, 7,006 lines, imported in order at `main.tsx:4-16` with
  `styles/polish.css` (920 lines) last as the override layer; `styles.css` (502) sits
  beside `styles/tokens.css` (90) and `ui/ui.css` (295). No ESLint configuration;
  `npm test` is `node --test tests/*.test.ts` over 16 files and 119 `test(` cases;
  `npm run build` is `tsc -b && vite build` and CI checks the committed `dist`
  (`.github/workflows/check.yml:32-39`).

**Money and upload.**

- `api/images.py:157` passes `reserve_usd` with a `"0.05"` default;
  `services/generation.py:20` repeats it; `generation.py:145-147` turns it into the
  per-shot allowance, `:238` records it per task and `:255-256` stores
  `reserve_total_usd` beside `published_pricing: info.get("x-pricing")`, which
  nothing reads. The pricing shape is `{"currency", "measured": [{"configuration",
  "price"}]}` (`tests/test_production.py:57-60`).
- `api/projects.py:383-394` trusts `Content-Length` when present, then
  `await request.body()` buffers the whole upload and checks the size afterwards;
  `domain/intake.create_from_upload` (`domain/intake.py:64-80`) already takes a
  `source: Path`.

**Renderer tests and CI.**

- `renderers/remotion/package.json` has `test` (eight `tests/*.test.mjs`, pure) and
  `smoke` (`tests/smoke-render.mjs`, one real 160x90 render that needs Chrome).
  `.github/workflows/check.yml:40-43` runs `npm test` only. `src/request.mjs:78-95`
  finds Chrome from `REMOTION_CHROME`, `CHROME_PATH` or five fixed paths including
  `/usr/bin/google-chrome`. Nothing compares pixels; `tests/test_timing_parity.py`
  has three tests, the third on the FFmpeg constants, and none on `editCamera` or
  the transition functions.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | May the engine stop reading schema-1 documents at all, so `projects/kortjakje` (the pilot) is an archive like the two finished films? | Yes. The archive reader already lists and plays all three; `tests/test_creative_production.py:252` is deleted with the path it proves. Nothing under `projects/` changes. |
| D2 | The FFmpeg renderer and the CLI animatic: delete outright, or move under `legacy/`? | Delete. No Studio path reaches them, no live film can use them after D1, and the Remotion path has its own cold-render evidence. The probe, mux and verify helpers move to `ffmpeg.py` and stay. |
| D3 | A titles review made by the old compositor (`method` absent): keep `graphics.compose` reachable from the Studio's final render for it, or refuse and ask to check the titles again? | Refuse with "this titles review was made by the old compositor; check the titles again". Please confirm no live film holds such a review (`work/graphics-review.json` without `"method"`); if one does, that film re-checks its titles once. |
| D4 | `workflow_version` and `prompt_version` stay in `Project` as inert fields so every hash holds, or are stripped with a one-time re-approval of every live film? | Inert fields, parsed and written back when present, read by nothing; new films stop writing them. No re-approval. |
| D5 | Delete these 20 subcommands: `init`, `analyze`, `status`, `approve`, `authorize`, `import-lyrics`, `skeleton`, `events`, `prompts`, `preview`, `quote`, `generate`, `select`, `review`, `sheet`, `render`, `costs`, `budget`, `preflight`, `locate`; keep `doctor`, `schema`, `backup`, `quote-transcription`, `transcribe`, `quote-music`, `listen`, `music-map`, `recover`, `resolve-task`, `restage`, `reference-import`, `adopt`, `progress`? | Yes. Each deleted one has a Studio route or screen (listed above). `schema` stays because it is the only printer of the JSON schemas and costs nothing. |
| D6 | The compose and overlay-cache tests: move with the code and mark `slow` (excluded by default, run in CI), or delete? | Move and mark. They are the only proof of the compositor the CLI still offers, so they run in CI; the default suite drops about 140 s. |
| D7 | Reservation from published pricing: which published number, and what is the floor? | The highest `measured[].price` in the model's `x-pricing` times 1.5, floored by the settings value (today's `0.05`); with no published pricing the settings value stands. The basis is written into the quote. |
| D8 | Pixel golden tests need Chrome. In `npm test`, or a separate `npm run pixels` run after `smoke` in CI and skipped where no Chrome is found? | Separate script. `npm test` stays pure so it runs anywhere; CI runs `smoke` and `pixels` after it. Phase C regenerates the goldens with its reason in the commit. |
| D9 | Delete the OpenAPI type generator (six of 77 types used), or type all of `api.ts` from it? | Delete it. The hand-written types are the ones the screens read; the generator needs a running app and a Python step and has drifted. |

## Tasks (one commit each, one PR)

Three PRs of about a week each. Order within a PR is the commit order.

### G-1. Engine legacy (PR 1, about 6.5 days)

Land tasks 1 and 2 before Phase D (which rewrites render workers in `remotion.py`
and `services/render.py`), and task 3 before Phase E and Phase I1 (which add fields
to `Project`).

1. **FFmpeg helpers out of the renderer.** New `ffmpeg.py` with `probe`,
   `audio_seconds`, `_count_frames`, `_validate_output`, `_is_faststart`, `_run`,
   `_binary`, `_max_threads`, `_validate_shots` and `AUDIO_BITRATE`; `remotion.py`,
   `audio.py`, `framecheck.py`, `production/intake.py` and `production/__init__.py`
   import from it. The camera vocabulary (`_MOVES`, `ZOOM_RANGE`) moves to `models.py`
   beside `Shot.camera`; `tests/test_timing_parity.py:151-156,189-204` compare
   `timing.mjs` with those constants and drop the zoompan string check. Files:
   `render.py`, `ffmpeg.py`, `remotion.py`, `audio.py`, `framecheck.py`, `models.py`,
   `production/`, `tests/test_timing_parity.py`, `tests/test_render.py` (probe and
   audio tests move to `tests/test_ffmpeg.py`). 1 day.
2. **Delete the zoompan path and the animatic (D2).** `render.py` loses the plate
   cache, assembly, brand overlay and the `render` entry; `services/render.py:12`
   and `cli.py` call `remotion.render_base` directly; `preview.py` and
   `render.contact_sheet` go (`sheet` goes in G-2.2, so `cli.py` keeps a stub that
   refuses until then). Delete `tests/test_render.py` (what is left after task 1),
   `tests/test_camera_path.py`, `tests/test_preview.py`. `CameraPath` stays in
   `models.py` because the storyboard and `timing.mjs` carry it. 1 day.
3. **Schema 3 only (D1, D4).** `Project.schema_version: Literal[3] = 3`;
   `workflow_version` and `prompt_version` become inert (`Literal[2] | None`,
   serialised when present, no reader); `renderer_backend` likewise inert and
   excluded from the payload as today; intake stops writing all three; `uses_remotion`
   and `renderer_binding`'s empty branch go. Delete `creative_workflow`,
   `prompt_look_first`, `budget.strict_paid`, `budget.workflow_version`,
   `budget.schema_version`, `preflight.strict_workflow` and collapse every caller
   listed above to the creative branch: `_legacy_image_spec`, `legacy_brief_hash`,
   the four-reference cap, the non-creative storyboard hash at `approvals.py:95`,
   the `prompt_version` checks at `approvals.py:327` and `director/prompts.py:157`,
   `budget.read_budget`'s legacy file read (the refusal of a conflicting
   `work/production-budget.json` stays, money logic stays strict),
   `correction_policy`'s inactive branch, `check_capacity`'s `None` return,
   `summary["workflow_version"]`. `api/story.py:131` returns `prompt_version: 2` as a
   constant until G-3.3 removes the frontend reads. `domain/migrate.py` stays as the
   one reader of a schema-1 dict and `domain/intake.py:147` stops calling it.
   `director/context.py:168` keeps printing the schema. Tests: delete or rewrite
   `tests/test_budget.py:198,290`, `tests/test_workflow_v2.py:63,343`,
   `tests/test_native_size.py:148-170`, `tests/test_director_prompts.py:163`,
   `tests/test_creative_production.py:252,263,483`, `tests/test_production_defaults.py:162`,
   `tests/test_generation_concurrency.py:402`, `tests/test_remotion_adapter.py:520-545`,
   `tests/test_api_intake.py:68`; `tests/test_migration.py` stays. Proof: on scratch
   copies of `zero-bars` and Tree of Love, `P.stage_hash` for every recorded stage is
   identical before and after, and `uv run studio` opens both. 2 days.
4. **Golden on a schema-3 fixture.** `tests/test_contract_golden.py:44-60` builds
   `schema_version=3` without the three flags; `UPDATE_GOLDEN=1` regenerates
   `tests/golden/contract.json`; the commit states "regenerated on a schema-3
   fixture; prompts, timing and both Remotion requests are byte-identical because
   the workflow-2 fixture already took the creative path". If any byte differs the
   task stops and the difference is reported before anything is committed.
   0.5 day.
5. **The compositor behind the CLI (D3, D6).** New package `legacy/` with
   `legacy/graphics_compose.py` holding `compose`, `_plan_parts`, `_build_track`,
   `_write_overlay`, `_validate_overlay`, `_validate_track`, `_cache_integrity`,
   `element_key`, `track_key`, `_overlay_frame`, `_part_frames`, `_validate_base`,
   `_unique_output`, `_preflight_base_facts`, `_base_frame`, `preflight_frames`,
   `_stamp_label`, `main`, plus `remotion.overlay_clip` and `graphics_clip` and
   `signature.prepare_review` with the `method`-less branch of `validate_review`.
   `graphics.py` keeps the constants, fonts, palette, spec loading and validation,
   the frame drawers, `intro_phase_samples`, `_preflight_samples` (renamed
   `preflight_picks`), `_load_project` and `_timing_board`; target under 1,200 lines.
   `services/render.py:168` refuses a `method`-less review with the D3 sentence and
   `api/film.py:55-104` reports it as not current. Only `cli.py` and the archive
   import `legacy`; a test asserts that no module under `api/`, `services/`,
   `director/` or `jobs/` imports it. Tests: the two compose tests of
   `tests/test_graphics.py` and the compose, track, overlay-cache and base-preflight
   tests of `tests/test_graphics_cache.py` move to `tests/legacy/test_graphics_compose.py`
   with `pytestmark = pytest.mark.slow`; `pyproject.toml` gains
   `markers = ["slow: compositor tests that render a base movie"]` and
   `addopts = "-m 'not slow'"`; CI adds `uv run pytest -m slow -q` as its own step.
   The pure tests stay in `tests/test_graphics.py`. 1.5 days.
6. **Docs and the record.** `docs/ARCHITECTURE.md` engine table (`remotion.py`,
   `ffmpeg.py`, `legacy/`, one schema), `docs/RENDERER.md:1-10,104-111`,
   `README.md:168`, this file's progress section. 0.5 day.

### G-2. CLI, report and small backend items (PR 2, about 7 days)

Land task 5 before Phase I2 (`narration.py` copies `generation.py`'s quote pattern)
and task 6 before Phase I7 (intake without an MP3). Land task 7 before Phase C,
which changes pixels and regenerates the goldens.

1. **A dispatch table.** `cli.py` keeps one `cmd_<name>(args, root, project)` per
   subcommand and a `COMMANDS = {name: Command(help, run, scope)}` table that both
   `parser()` and `execute()` read; `_project_scope` keys on the table; `execute`
   becomes about 20 lines. No behaviour change; every existing CLI test passes
   unchanged. 1 day.
2. **Delete the 20 subcommands (D5).** The table shrinks to 14 entries; `main` no
   longer special-cases `approve` and `authorize`. Tests that used a deleted
   command as a shortcut call the engine instead: the ten `skeleton` calls in
   `tests/test_pacing_integration.py` become `production.skeleton`, the seven
   `render` calls in `tests/test_signature_iteration.py` become `services.render`,
   `tests/test_quality_cli.py:42,68,185,197` and `tests/test_cli_monitoring.py:101,258`
   go or move with the function they prove; `tests/test_native_size.py`'s `init`
   tests become `production.init_project` tests. `cli.py` target under 450 lines.
   1.5 days.
3. **`edits.report` as finding families.** `report()` orchestrates
   `_coverage_findings`, `_flash_findings`, `_transition_findings`
   (`opening_transition`, `transition_reason`, `transition_handle`,
   `transition_repetition`), `_rhythm_findings` (`hold_ratio`, `hold_ratio_total`,
   `density_target`, `energy_density`, `long_static_shot`), `_repetition_findings`
   (`motion_repetition`, `travel_repetition`, `framing_repetition`),
   `_reading_findings` (`reading_time`, `text_reading_time`), `_crop_findings`,
   `_section_findings` and `_ad_findings`, each a pure function returning
   `(hard, warnings)` lists over the same inputs. Output byte-identical: a new test
   serialises the report of the energetic fixture (`tests/test_edits.py:287`) and the
   flash fixture (`:269`) before the split and pins them. 1 day.
4. **`approve` and `_dispatch` as tables.** `production/approvals.py`: per-stage
   validators `_check_lyrics`, `_check_brief`, `_check_storyboard`,
   `_check_analysis`, `_check_preview`, `_check_graphics`, `_check_reviews` in a dict;
   `approve` keeps the attestation rules (`:292-298`) and dispatches.
   `director/tools.py`: `TOOLS: dict[str, Callable]` with one function per tool;
   `_dispatch` becomes a lookup. No behaviour change; `tests/test_api_approvals.py`,
   `tests/test_director_tools.py` and the recorded probe are the net. 1 day.
5. **Reservation from published pricing (D7).** `generation.quote_images` computes
   `allowance = max(money(reserve), published_max * Decimal("1.5"))` and writes
   `reserve_basis: {"published_max_usd", "factor", "user_floor_usd"}` into the quote;
   `api/images.py:157` passes the settings value as the floor; the estimate card
   shows the basis. `budget.check_capacity` admits the larger number; nothing
   downstream of the journal changes. Tests in `tests/test_production.py` (published
   0.0006 keeps the 0.05 floor; a fixture priced 0.04 reserves 0.06) and
   `tests/test_api_images.py`. 0.5 day.
6. **Stream the upload.** `api/projects.py:383-394` writes `request.stream()` chunks
   to a temporary file under the reserved folder with a running byte count, answers
   413 the moment the count passes `intake.MAX_SOURCE_BYTES`, and hands the path to
   `create_from_upload`; the `Content-Length` pre-check stays. Test: a body over the
   limit without `Content-Length` is refused without being held in memory. 0.5 day.
7. **Pixel goldens and CI (D8).** `renderers/remotion/tests/pixels/` holds four
   480x270 PNGs rendered with `renderStill` from one fixture request: the midpoint
   of a dissolve, a whip, a look (grain, weave, drift at fixed values) and a title
   lockup. `npm run pixels` renders them again and compares SSIM on grayscale with
   a plain-JS implementation (no new dependency), threshold 0.98;
   `UPDATE_PIXELS=1` regenerates. `.github/workflows/check.yml` runs `npm run smoke`
   and `npm run pixels` after `npm test`, with `REMOTION_CHROME` set from the
   runner's Chrome. Parity: `tests/test_timing_parity.py` gains one test driving
   `editCamera` with a zoom, an anchor, a punch-in and a crop cut and asserting the
   endpoints against the `EditShot` values and `models.py` bounds, and one driving
   each transition at its handle boundaries against `timeline.py`'s handle frames.
   1.5 days.

### G-3. Frontend (PR 3, about 6.5 days)

Task 1 lands right after Phase A as its own small PR, before Phase H2 (the settings
panel reads through it) and before Phase I7 (the roadmap already places it before
the narrative screens). Task 2 lands before Phase H1 adds routes the generator would
not know. Tasks 3 and 4 wait for Phase A, which edits `Film.tsx`, `useFilmData.ts`,
`nextStep.ts`, `polish.css:883` and `film.css:1115`.

1. **One shell-level resource store.** `api/resources.ts` keeps the last value per
   key with subscribers; a `useResource(key, loader)` hook returns the shared value
   and refetches when the key is invalidated; the dependency table (`:4-16`) and the
   server's artifact hint (`app.py:220-230`) decide which keys a change touches.
   `FilmShell`, `Images`, `useFilmData` and `useStoryData` read through it instead
   of their own `Promise.allSettled`. Acceptance: after a `project.changed` with
   `artifact: images`, the network log shows one `/images`, one `/edit`, one
   `/preview`, one `/approvals`, one `/film`, one `/budget` and nothing else; a
   change with no hint fetches each resource once, not once per consumer.
   `tests/resources.test.ts` grows cases for subscribe, one fetch across two
   consumers and hinted invalidation. 2 days.
2. **Delete the generator (D9).** Remove `api/schema.d.ts`, `scripts/dump_openapi.py`,
   the `openapi-typescript` devDependency and the `api:types` script; hand-write the
   six types; `docs/ARCHITECTURE.md` presentation paragraph. 0.5 day.
3. **Split the three files by concern.** `shell/Director.tsx` into
   `director/ToolRows.tsx` (`:138-298`), `director/useTurn.ts` (`send`, `stop`,
   stream parsing `:573-694`), `director/undo.ts` (`:695-724` with `UNDO_ARTIFACT`),
   `director/suggestions.ts` (`:81-96`) and the drawer; `stages/Images.tsx` into
   `images/Lightbox.tsx`, `images/StyleCheck.tsx` (`:471-528`), `images/ContactSheet.tsx`
   and `images/useImagesData.ts`; `shell/FilmShell.tsx` into `shell/useFilmShellData.ts`
   (the reads, now from the store), `shell/LibraryShell.tsx`, `shell/ArchiveShell.tsx`
   (`:721-789`) and `shell/directorDrawer.ts` (`:159-178`). The `prompt_version`
   reads at `nextStep.ts:246` and `WorldPart.tsx:33` become a `structured` flag from
   the profile version. No behaviour change; `tsc`, tests and build, then a manual
   sweep of every screen at 1440 and 390. Target: no file over 500 lines. 2 days.
4. **Stylesheets into the token system.** Each rule in `styles/polish.css` moves next
   to the rule it overrides, in the owning stylesheet, then the file is deleted;
   `styles.css` is split between `tokens.css` and `ui.css`; unused rules are
   removed. Computed styles must not change outside Phase A's phone fixes: the
   acceptance is a before and after screenshot diff of the eight screens at 1440
   and 390 with zero differing pixels except where Phase A changed them. Target:
   eleven files, under 6,000 lines. 1.5 days.
5. **ESLint.** `eslint.config.js` with `@eslint/js` recommended, `typescript-eslint`
   recommended and `eslint-plugin-react-hooks`; `npm run lint` in CI before the
   build; what it finds is fixed or disabled per rule with a one-line reason.
   0.5 day.

## Not changing

The money journal's semantics (reservation before submit, recovery by UUID, no
resubmission); every approval hash of every live film; integer-frame timing; the
Remotion composition and `timing.mjs`; `domain/archive.py` and the archive routes;
`flow.py`'s guided marker; `domain/migrate.py`; the sub-artifact `schema_version: 1`
literals; `operations.py` receipts; Phase A's blocked-state copy and its Playwright
smoke tests (G adds none); `projects/`, `backups/` and `archive/`, which are only
read, and only on scratch copies where a write is needed for proof.

## Acceptance

- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, frontend
  `tsc`, tests and build, renderer `npm test`, `npm run smoke` and `npm run pixels`
  pass; `uv run studio` starts from a fresh clone and opens a live film and an
  archived film.
- The golden is regenerated once, in G-1.4, on a schema-3 fixture, and the commit
  states the reason and that the bytes are identical, as AGENTS.md requires. No
  other task touches `tests/golden/`.
- `tests/test_archive.py` and `tests/test_api_archive.py` pass unchanged; the
  tree-hash proof shows the archive reader still writes nothing; the Library lists
  the three frozen films on the owner's machine.
- On scratch copies of `zero-bars` and Tree of Love: every recorded stage hash is
  identical before and after G-1.3; a preview renders; the Director opens.
- Suite time: 284.5 s before (1,532 passed, 2 skipped, measured here); after G-1.5
  the default `uv run pytest` runs without the `slow` set and is expected under
  150 s, with the `slow` set reported separately from CI; the numbers go in the
  progress section.
- `grep -rn "workflow_version\|prompt_version\|uses_remotion\|creative_workflow\|
  strict_paid" src/` finds only the two inert field declarations and the migration;
  no module outside `cli.py` and `tests/legacy/` imports `legacy`.
- Ruff C901 at 25 reports none of `execute`, `report`, `approve`, `_dispatch`.
- Frontend: one fetch per resource per change, measured in the network log; no
  source file over 500 lines in `shell/`, `stages/`, `director/`; `polish.css` gone;
  `npm run lint` clean.
- Report, approval and tool outputs are byte-identical before and after G-2.3 and
  G-2.4, pinned by the new serialisation tests.

## Risks

- **A hash moves.** The proof in G-1.3 is on scratch copies of both live films, run
  before the commit; if a stage hash differs the field layout is wrong and the task
  stops. The inert fields are the guard, which is why D4 is a decision and not a
  detail.
- **A frozen film is read through the engine somewhere unlisted.** The grep above
  and the 409 on every stage route are the net; the kortjakje test is deleted on
  purpose (D1).
- **The golden differs.** It should not; if it does, the cause is a real change in
  the compiled prompt and the task reports it rather than regenerating.
- **CI Chrome.** `smoke` and `pixels` depend on a Chrome at one of the fixed paths or
  `REMOTION_CHROME`; the step must fail loudly, not skip silently, when it is missing
  on the runner.
- **Pixel goldens churn.** Phase C changes motion and look pixels by design; it
  regenerates the four files with the reason in its commit, so G-2.7 lands first.
- **The CSS fold changes a computed style.** The screenshot diff is the only honest
  check; the task is split by stylesheet so a diff points at one commit.
- **Deleted CLI tests hid engine coverage.** Each moved test keeps its assertion
  against the engine function; a test with no engine function left is listed in the
  commit as deleted with its reason.
- **Overlap with Phases A, D, E, H, I.** The ordering notes above are the mitigation;
  a G task that would conflict waits for the phase that owns the file.

## Out of scope

Blocked-state copy and Playwright smoke tests (Phase A); render parallelism and the
MP3 hashing on reads (Phase D); the settings panel and catalogue (Phase H); the
multi-provider adapter and retiring `opencode serve` (Phase E); the signature as a
preset (Phase F); the narrative kind (Phase I); any change to `flow.py`'s guided
policy; thumbnails for the Film timeline; a rewrite of `remotion.py`'s lock and cache
layers; deleting `domain/migrate.py`.
