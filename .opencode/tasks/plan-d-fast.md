# Make it fast — plan

**Proposed** 1 Nov 2026 for owner approval; base `main` at `c1414a3`.

**Objective:** a changed shot shows in a real render in seconds, a full preview takes
about a minute, a full base a few minutes, and the library opens without reading a
single byte of any MP3. The chunk renderer from `.opencode/tasks/render-speed.md`
stays the design: this plan runs its chunks across several browsers, previews at half
size, serves stills beside a code-only bundle, stops decoding films twice, and makes
every read a read. Phase D of `docs/design/studio-assessment-2026-10-31.md`. No
quality default of a final changes; nothing here costs money.

## What the code showed

- **One browser, one tab, chunks in a row.** `remotion.py:32` sets
  `CHUNK_CONCURRENCY = 1` for the reason at `remotion.py:30-31` (more tabs cycle every
  200 ms); `request()` passes it at `remotion.py:178-181`. `render.mjs:415-505`
  `renderChunks` opens one browser (`render.mjs:433`) and renders the chunk list in a
  plain loop (`render.mjs:442`). The assessment measured two browsers at 1.9× on four
  cores; render-speed's record shows about 14.5 fps in one tab.
- **The machine lock is taken per subprocess, inside `invoke`.** `_one_render_at_a_time`
  (`remotion.py:246-266`) wraps `_run_streaming` at `remotion.py:225`. `flock` on a second
  handle of the same file blocks in the same process, so K workers must share one lock
  taken higher up, in `_render_silent` (`remotion.py:740-817`), not K locks. `_run_streaming`
  (`remotion.py:309-345`) drives one process, one progress file and one `_StallWatch`.
- **Every confirmation starts a browser.** `check_movies` (`remotion.py:608-647`) decodes
  each chunk small (`framecheck.small_frames`, `framecheck.py:27-47`), flags suspects
  (`framecheck.py:49-69`) and confirms them with `_fresh_frames` (`remotion.py:581-600`),
  a separate `stills` Node run. In it, `renderStills` (`render.mjs:508-535`) calls
  `renderStill` without `puppeteerInstance`, so each still opens its own browser. A
  one-frame flash is a suspect by design (`tests/test_framecheck.py:58,145`), and the
  edit that planned it is in `inputs["shots"][i]["edit"]` (`remotion.py:478-480`) but
  never consulted.
- **The film is decoded twice to count frames.** `render._count_frames`
  (`render.py:144-167`) decodes every frame at 16×9; it runs at `remotion.py:890` on the
  silent base and again inside `_validate_output` (`render.py:550`). Yet `_require_even_timing`
  (`remotion.py:701-737`) already lists every packet's `pts_time` with `ffprobe` during the
  join, so the count is known there for free.
- **A failed final leaks its store.** `_render_silent` makes a `fresh-` directory when
  `reuse` is false (`remotion.py:753`) and removes it only after success
  (`remotion.py:816-817`). Any exception keeps it; only the broken-frame message at
  `remotion.py:810-813` keeps it on purpose. A second attempt starts from nothing.
- **The bundle key hashes every asset.** `bundleKey` (`render.mjs:172-183`) digests
  `src/`, the lockfile and every file of the asset root, and `ensureBundle` passes that
  root as `publicDir` (`render.mjs:186-207`), so a newly selected still is an 18 s
  rebundle. `BaseFilm.jsx:254` already draws `span.src ?? staticFile(span.image)`: the
  Player passes a URL per span (`services/preview.py:121-124`). `refuseRemoteAsset`
  (`render.mjs:236-239`) governs only Remotion's own `onDownload`, not what `<Img>` loads.
  `RENDER_PERFORMANCE.md` §T10 refused code-only reuse because assets lived inside the
  served bundle; serving them from a loopback server owned by the renderer is the change
  of serving model that record asked for. `request.mjs:132` still requires `assetRoot`,
  and the golden pins the request's top-level keys (`tests/golden/contract.json`).
- **Previews render at full size and die on a missing still.** `render_preview`
  (`services/render.py:204-240`) passes the project as is and never
  `preview_placeholders`; `resolved_assets` raises before any browser when a selected
  still is missing (`production/assets.py:152-155`). The legacy animatic already shows the
  pattern: a project copy at `PREVIEW_DIMENSIONS` (`preview.py:35,204-205`) and placeholder
  plates (`preview.py:228-235,252`). The Player draws placeholders
  (`services/preview.py:118-129`, `BaseFilm.jsx:325-336`). Chunk keys include the canvas
  and the placeholder flag (`chunks.py:119,122`); `_validate_output` compares dimensions
  with the project it is handed (`render.py:559-564`); `check_preview_binding` binds
  movie bytes, storyboard, proof, brand and renderer, not the canvas
  (`production/approvals.py:127-139`).
- **No GPU raster.** `render.mjs:292` sets `chromiumOptions: {headless: true}` and no `gl`.
  T9 tested only the hardware encoder, which gave nothing (`RENDER_PERFORMANCE.md`).
- **Every `load_project` hashes the MP3.** `production/project.py:48-52` verifies the
  source unless `verify_source=False`; `storage.file_hash` reads the whole file
  (`storage.py:147-152`); the read snapshot memoises per operation and thread only
  (`storage.py:21-24,77-115`), never across requests. `GET /api/projects`
  (`api/projects.py:227`) is `async def` on the event loop and loads each film at
  `api/projects.py:271`, then `load_board` loads it again (`api/projects.py:278`,
  `production/board.py:58`): two full hashes per film per refresh. `GET /{slug}`
  (`api/projects.py:463-516`) does the same. `@read_endpoint` (`read_snapshots.py:18-32`)
  covers only approvals, film and images routes; `api/track.py` calls `load_project` nine
  times without it. The director already uses `verify_source=False` (`context.py:155`).
- **Library state is a guess.** `_changed_since` compares mtimes with the approval time
  plus one second (`api/projects.py:74-84`); `_stage_states` builds every word from it
  (`api/projects.py:148-209`); `tests/test_api_library.py:167` simulates change by bumping an
  mtime 60 s. Approvals are written in `approve` (`production/approvals.py:415`); every
  engine mutation passes `state_mutation` (`storage.py:255-263`); the watcher sends
  `project.changed` so views reload (`jobs/watch.py:1-14`).
- **Numbers to beat.** Tree of Love, the Editor's cut, one render at a time: full render
  7 min 16 s, one shot changed 34 s, two lengths changed 66 s (`render-speed.md`,
  acceptance record). The assessment's synthetic 10 s film: cold 107 s with an 18 s bundle,
  two browsers 40 s against 77 s, 960×540 3.0×.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | How many browsers, and who guards memory? | K = cores ÷ 2, at most 4, never more than the pending chunks, and one fewer for every 600 MB short of free memory at start (about 400 MB per Chrome measured). `STUDIO_RENDER_WORKERS` overrides it until the Settings panel of Phase H owns it. A worker that dies fails the render and names itself; nothing retries silently. |
| D2 | May a failed final resume? | Yes, from its own store only. The `fresh-` store is named by the final's visual key; a retry of the same final reuses chunks with receipts from that store and nothing else. Chunks from previews, bases or another cut never reach a final, which is what render-speed D2 protects. Any other failure cleans the store, except the broken-frame case, which keeps it as evidence as today. |
| D3 | GPU raster by default? | Off. `STUDIO_RENDER_GL=angle` turns it on, the benchmark below measures it on the Mac, and only a measured gain of 1.3× or more with SSIM at or above 0.999 against software on the primitives gallery makes it a default, in a later commit the owner sees. |
| D4 | Preview size? | 960×540 for every preview (540×960 portrait); bases and finals untouched. The viewer labels it "half-size preview". A preview approval still means "watched with the music"; it never meant pixels. Previews stop sharing chunks with bases, which is the cost. |
| D5 | Who serves the stills beside a code-only bundle? | `render.mjs` itself: a loopback `http` server on an ephemeral port, bound to the selected publication directory (immutable, content-addressed names), that sets `src` on every span, pane and plate at run time. The bundle key hashes code and the lockfile only. The flag is a CLI argument, so the request body, its hash and the golden stay the same. |
| D6 | Where does exact library state live? | `work/stage-state.json`: per stage the approval hash, the current hash and a fingerprint (path, size, mtime in ns) of the files that hash reads. `approve` writes it; `state_mutation` removes it; the library recomputes only films whose fingerprints changed, in the thread pool, and writes the result back. No gate ever reads it. |

## Tasks (one commit each, two PRs)

**PR D1, the renderer.**

1. **Count packets, clean the store.** `_require_even_timing` returns its packet count
   and `_render_silent` uses it instead of `_count_frames` (`remotion.py:890`);
   `render._count_frames` becomes an `ffprobe -count_packets` read, with the decoded count
   kept as `_decoded_frames` for tests and for finals in `_validate_output`. The `fresh-`
   store follows D2: named by key, cleaned in a `finally` except on the broken-frame
   failure, resumed by the same final. Tests: a packet count equals the decoded count on
   the fixture; a failed fake final leaves no store; a retried one reuses its receipts.
   0.5 day.
2. **Timeline-aware scan, one browser to confirm.** `framecheck.planned_windows(inputs,
   fps)` lists the frames inside every `dip_to_black` and `dip_to_white` handle, every
   `flash` accent and every crop cut from the compiled shots; `check_movies` reports
   suspects inside them as `expected` and confirms the rest. `renderStills` opens one
   browser with `openBrowser` and passes `puppeteerInstance` to every `renderStill`.
   Tests: a planted glitch beside a dip is still caught, a flash is no longer rendered
   again, and the report names the expected frames. 1 day.
3. **Parallel chunk workers (D1).** `render.mjs --bundle-only` builds or checks the
   bundle and exits. `_render_silent` takes the machine lock once (the lock moves out of
   `invoke` behind a re-entrant guard), bundles once, splits the missing chunks into K
   lists longest-first, and runs K `render.mjs` processes at once through a `_run_many`
   that sums their progress files, keeps one `_StallWatch` per worker, honours Stop, and
   ends every worker when one fails. The Film progress reads "12 of 38 shots, 4
   browsers". The receipts, the join and the check are unchanged. Tests with a fake
   renderer: disjoint lists cover every chunk, one failure ends the rest, progress sums.
   2 days.
4. **Half-size previews with placeholders (D4).** `render_preview` renders a project
   copy at 960×540; `resolved_assets` gains `placeholders=True`, returning a placeholder
   plate from `preview._placeholder_plate` for a missing or stale still and the list of
   ids, which `render_preview` passes as `preview_placeholders`. A preview with
   placeholders renders and plays but is not `approval_ready`, and the report names the
   shots. The viewer shows "half-size preview" and the placeholder count. Tests: the
   request carries the half canvas, placeholder ids and the plate; a full-size base
   request is byte-identical to before. 1 day.
5. **Served stills beside a code-only bundle (D5).** `render.mjs --serve-assets` starts
   the loopback server, injects `src` for shots, split panes and the brand plate, and keys
   the bundle on code only; Python passes the flag for base, preview, final and stills.
   The server refuses anything outside its directory and any non-loopback client.
   `implementation_hash` changes once, as for every renderer change. Tests in the renderer:
   the key ignores the asset root, a served request renders the same frame hash as a
   bundled one, a path outside the root is refused. 1.5 days.
6. **GPU raster flag (D3).** `render.mjs --gl <mode>` sets `chromiumOptions.gl`; Python
   reads `STUDIO_RENDER_GL` and records the mode in the render report. Default off.
   0.5 day.
7. **Benchmark, acceptance and docs.** The protocol below, run twice per row, written
   into `docs/RENDER_PERFORMANCE.md` as the new top section, with `docs/ARCHITECTURE.md`
   and `docs/RENDERER.md` updated for workers, served assets and half-size previews.
   0.5 day.

**PR D2, the reads.**

8. **Stop hashing the MP3.** `storage.file_hash_cached(path)` keyed by resolved path,
   size, mtime in ns and inode, bounded and locked, process-wide; `load_project` uses it to
   verify the source, so a verification is a `stat` after the first read. `GET /api/projects`
   and `GET /{slug}` move to the thread pool under a `read_snapshot` per film and load
   views with `verify_source=False`; every remaining GET in `api/track.py`,
   `api/story.py`, `api/storyboard.py` and `api/projects.py` takes `@read_endpoint`.
   Approval, generation and render paths keep hashing bytes. Tests: a library listing of
   five films reads zero source bytes (a counting `file_hash`), a replaced source is still
   refused where it matters. 1 day.
9. **Exact library state (D6).** `work/stage-state.json` written by `approve`, removed
   by `state_mutation`, refreshed by `_stage_states` only for films whose fingerprints
   moved; `_changed_since` and the one-second slack go. `tests/test_api_library.py` changes
   a real artifact instead of an mtime. 1 day.

Total about 9 days; D1 about 7, D2 about 2.

## Not changing

Chunk keys and receipts, the stream-copy join, the broken-frame rule (find, confirm,
replace, fail twice), render-speed D1 (finals stay PNG) and D2 beyond the bounded resume
of D2 above, every approval hash, the render request body and the golden contract, the
encoder, pixel format and quality of bases and finals, the legacy FFmpeg path, the Player,
stills and source audio, money and image generation. No paid call, no browser download,
no provider or browser call in unit tests.

## Acceptance

- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, frontend `tsc`,
  tests and build, and `npm test --prefix renderers/remotion` pass; the app starts and a
  fresh clone installs the pinned renderer as before.
- **Benchmark protocol**, on a **scratch copy of Tree of Love** (38 shots, the Editor's
  cut, 1080p24, today 7 min 16 s), on the owner's 8-core Mac with nothing else running,
  one render at a time, each row run twice and the slower time reported, cold rows after
  clearing `work/remotion-chunks` and the renderer's `.cache`:

  | Row | Today | Target |
  | --- | --- | --- |
  | Full 1080p base, cold, K = 1 | 7 min 16 s | the baseline for this machine |
  | Full 1080p base, cold, K = 2 and K = 4 | | under 3 min at K = 4 |
  | Full 960×540 preview, cold, K = 4 | | under 1 min 30 s |
  | One shot's camera changed, base and preview | 34 s | under 20 s |
  | A new still selected: bundle phase | 18 s | under 1 s, log says bundle-cached |
  | Frame scan, with and without planned windows; confirmation runs | | fewer browser starts, same broken frames found |
  | Frame counting per render | about 12 s | under 1 s |
  | `--gl angle` against software at K = 1, with SSIM on five look-heavy frames | | reported, decides D3 |
  | Peak memory per Chrome and total at K = 4 | | reported |
  | `GET /api/projects` with every film present, and `GET /{slug}`, in ms | | under 300 ms and no source bytes read |

- Parity: the K = 4 film has the exact frame count, even packet timing, and SSIM at or
  above 0.999 against the K = 1 film on twenty sampled frames including a transition and
  a look; the served-asset render matches the bundled one the same way; the half-size
  preview plays through its joins in QuickTime and the browser.
- A missing still renders a preview with the placeholder plate and the shot named; a
  killed final retries from its own store; a planted glitch is still found with the
  planned windows active.
- The real films' bytes, approvals and renders unchanged; every number above goes into
  the acceptance record with the machine and commit.

## Risks

- **Several browsers at once was the hour-long hang** of 30 Oct (editor-first-cut
  record). D1's memory guard, the per-worker watchdog and the Stop path are the defences;
  the first K = 4 run is watched, not left.
- **A glitch inside a planned window passes unseen.** Windows are short (flashes a few
  frames, dips at most a handle) and named in the report; the owner can turn the skip off
  per render if a film shows one.
- **Served assets change how Chrome loads pictures.** A loopback fetch per still instead
  of a bundled file; the parity row and the renderer tests cover it, and the approvals
  bound to the renderer revision ask for a check again once, as every renderer change does.
- **Half-size previews lose chunk sharing with bases**, so the first base after a preview
  is a full render. Expected and stated in Film.
- **An mtime-keyed hash cache can be fooled** by a same-size rewrite within one
  nanosecond tick; the inode and size are in the key, source audio is immutable by rule,
  and every money and approval path still hashes bytes.
- **GPU raster may differ by a pixel** between the Mac and the Player; D3 keeps it off
  until measured, and finals stay on software until the owner says otherwise.
- **One film, one machine.** The targets come from two-browser and half-size
  measurements on a synthetic film; the benchmark decides, not the plan.

## Out of scope

Headless Chrome and the portable browser decision, a non-browser renderer, hardware
encoding, JPEG finals (render-speed D1), cleaning old chunks and bundles, the shell's
duplicated fetches and resource cache (Phase G4), pixel golden tests in `npm test`
(Phase G6), the Settings panel that will own the worker count (Phase H), and any change
to what a preview or final looks like.
