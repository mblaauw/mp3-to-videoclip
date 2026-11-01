# Open it up — plan

**Proposed** 1 Nov 2026 for owner approval; base `main` at `c1414a3`.

**Objective:** the app stops being one producer pair's tool. The 25 s opening and 40 s
credits become one selectable package, "joint-v1 25/40", that stays byte-identical for
every existing film; a music video may open with a short title, close with an end card
or carry no titles at all, in landscape or portrait, in a neutral palette, with the
names from the brand kit; a final ships as a package (poster, contact sheet, chapters,
captions, measured loudness where asked, vertical and square variants); and the app
says honestly what this computer can and cannot do. Phase F of the 31 Oct assessment.
Decision 1 is given: the signature is a preset, default for the owner's films, optional
for everything else.

## What the code showed

**The signature.**

- `validate_spec` refuses anything but 16:9, an opening other than 25 s, credits other
  than 40 s and a film under 65 s (`signature.py:115-133`). The names are literals
  (`signature.py:18-20`); `_identity` returns them when a spec has no `brand`
  (`signature.py:27-38`) and `film_brand` returns `None` for the original pair
  (`signature.py:41-46`), so a new film by the owner records no brand and leans on the
  literals. `draft_spec` hard-codes 25, 40 and 4 seconds (`signature.py:49-72`).
  `config.py:33-34` holds the same two names as settings defaults.
- `kinds.py:57-58` calls the package an "editable settings default" and sets
  `signature_required=True` for music videos; promo and advert are `False`
  (`kinds.py:85`, `:109`); `requires_signature` reads the recorded flag first
  (`production/project.py:65-77`), so a music video without titles is one flag.
- `plan_titles` already takes any `intro_seconds` (one frame minimum) and any credits
  tail, but requires at least one credit card and always ends with a lockup
  (`titles.py:51-57`, `:76-104`); the identity beat is only drawn for `design ==
  joint-v1` (`titles.py:85-93`). Zero intro and zero cards are the two cases it refuses.
- `Titles.jsx` scales the ten joint phases by `intro_seconds / 25` (`Titles.jsx:238`,
  `timing.mjs:1022-1030`, `JOINT_INTRO_PHASES` at `:1002-1013`), so a 5 s opening today
  would be the 25 s choreography squeezed five times, not a design. The palette comes
  from `brand.json` when the spec has none (`graphics.py:460-480`; `BrandPackage`
  colours at `models.py:1108-1111`) and `Titles.jsx:25-31` only holds the pink and
  purple fallback; a neutral palette is therefore a brand package, not a renderer
  change. `title_assets` still requires the filmstrip mark (`remotion.py:974-979`).
- Brief approval validates the spec when a signature is required and the flow is not
  guided (`production/approvals.py:318-323`); the brief stage hash includes the spec's
  digest (`production/approvals.py:192-193`); the titles review binds the resolved
  spec, the windows, the renderer revision and the sample bytes (`signature.py:338-356`).
  Any package must leave a spec without a `package` key validating and rendering exactly
  as today, or existing films' brief hashes and reviews move.
- The golden pins the titled request built from `_title_spec()`
  (`tests/test_contract_golden.py:142-158`); that spec has no package key and must keep
  producing the same windows and the same `titles_input`.
- Portrait: `Project.aspect` allows 9:16 (`models.py:103`) with a 864×1536 picture
  (`models.py:138`, `profiles.py:82`) and intake accepts it (`domain/intake.py:86-87`),
  but New film always sends 16:9 (`NewProduction.tsx:148`) while `README.md:91` still
  promises the choice. Text sizes are height-relative and margins width-relative
  (`BaseFilm.jsx:78-83`, `:96`, `:108`), so portrait text is large and tight, and
  `Titles.jsx` has no portrait layout.

**Delivery.**

- A final is the silent base plus the original audio muxed with `-c:a aac -b:a 192k
  -movflags +faststart` and no sample-rate flag (`remotion.py:896-924`); the validator
  checks h264, yuv420p, aac, frames and faststart (`render.py:543-600`). Video encoder
  flags are Remotion's (`render.mjs:349-365`, `colorSpace: "bt709"` at `:356` and
  `:456`); `ffmpegOverride` is wired (`render.mjs:364`) and today returns the arguments
  unchanged (`diagnostics.mjs:26-37`), which is the hook for `-g 48`. Chunks are
  stream-copy joined, so every shot already opens on a keyframe; `-g 48` matters inside
  long shots and for platform re-encodes.
- Capture: previews and bases are JPEG at quality 95 (`remotion.py:29`,
  `services/render.py:80`, `:223`); finals pass no capture and stay PNG
  (`services/render.py:145-202`). The render-speed record keeps finals PNG until the
  owner has watched a JPEG film (D1 there) and measured 130 MB against 99 MB for one cut.
- `GET /exports` lists the MP4s in `renders/` and `previews/` through `describe`
  (`api/film.py:272-285`, `domain/exports.py:36+`); nothing else is listed, and the
  Library's poster is a still, not a film frame (`api/projects.py:44`, `:128`).
- Chapters have their source: `EditSection` carries id, frames and a feel
  (`models.py:960-972`), and `cut_material` names sections from `music.json` through the
  section map (`edits.py:871-882`). Captions have theirs in `lyric-timing.json`
  (`domain/lyric_timing.py:18`), line starts and ends only; Phase B5 turns them into
  caption layers and SRT and VTT, which this phase packages.
- Nothing measures loudness. FFmpeg's `loudnorm` with a measured first pass is the
  standard two-pass path; the report sidecar is where the numbers belong.

**Portability.**

- `lyric_tools.status` refuses anything but macOS on arm64 (`lyric_tools.py:63-64`);
  the lock pins `mlx`, `mlx-metal` and `parakeet-mlx` (`lyric_tools.lock.txt:32-33`,
  `:43`) and the worker loads `mlx-community/parakeet-tdt-0.6b-v3`
  (`lyric_tools_worker.py:13`, `:27`), while Demucs already runs with `-d cpu`
  (`lyric_tools_worker.py:40`). Only the word recogniser is Apple-only.
  `docs/ARCHITECTURE.md:72` records the limit.
- `setup.status()` returns booleans for node, npm, chrome, ffmpeg, ffprobe, the
  renderer and the frontend (`setup.py:36-46`), with a Chrome candidate list and
  `REMOTION_CHROME` (`setup.py:22-33`); `GET /api/setup` serves it (`api/setup.py`).
  Film shows a setup card; the Library shows nothing. The headless-shell decision is
  recorded open twice (`gui-rework.md:304`; render-speed D6: "adds about 20 % at most,
  and needs a consented download").
- Upload: `MAX_SOURCE_BYTES = 25_000_000` (`domain/intake.py:19`); the handler checks
  `content-length`, then buffers the whole body before checking again
  (`api/projects.py:384-394`); `README.md:90` states the limit. A 320 kbit/s MP3 passes
  25 MB at about ten minutes, so the limit mostly bites long tracks and DJ mixes.

**Dependencies.** F1's brand kit fields live in Phase H's settings (names, logo, palette,
font, "signature package on or off"); F1 can land on today's `brand_name` and
`brand_partner` and move when H does. F2's captions come from Phase B5. F2's vertical
variants crop a 16:9 still to 9:16, which is only sharp enough with Phase C1's 2× still.
Portrait safe areas are shared with Phase C11; whichever lands first carries them. F3's
CPU lyric timing is what Phase I2 needs for narration alignment.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | What does a 0 to 5 s opening show? | A `title-v1` package: the title and an optional second line, one fade in and out, nothing else. Names and the mark belong in the end card, not before the first picture. |
| D2 | What is the end card, and may a music video have no titles? | `title-v1` closes with one card of 0 to 10 s: lockup or logo, up to four credit lines, no roll. "None" is allowed for every kind; it sets `signature_required=false` at intake, exactly as promo and advert do today. |
| D3 | What do new music videos on your machine default to? | The joint 25/40 package, from the brand kit in Settings. A fresh install defaults to `title-v1` with no names until the kit is filled. The two literals stay in the code only as the legacy identity of specs that record no brand. |
| D4 | Loudness target for promo and advert? | Opt-in, −14 LUFS integrated and −1 dBTP true peak, the streaming norm, measured and applied in two passes with the numbers in the report. Music videos are never normalised: the master is the mix. |
| D5 | Capture for finals? | PNG stays the default until you have watched a JPEG final, as the render-speed record asks. Add `q90` as a per-render choice in the delivery panel, named in the report, so the comparison can happen on a real final. |
| D6 | Pin Remotion's headless shell? | No. Keep a local Chrome or Chromium required, say so on the Library, and record the decision. The shell is a 150 MB download per platform that needs consent, saves at most 20 %, and the candidate list plus `REMOTION_CHROME` already covers Mac and Linux. Revisit when someone without Chrome appears. |
| D7 | Lyric timing beyond Apple Silicon? | Try a CPU path in a two-day box: the same Parakeet TDT 0.6B v3 through an ONNX runtime under a second pinned lock, judged against the two songs of the track-listening record. If its word times are not within 0.2 s of the MLX path, ship a documented refusal ("needs an Apple Silicon Mac") instead, and Phase I2 relies on provider timestamps. |
| D8 | The upload limit? | 50 MB, streamed to a temp file with a running count so nothing buffers, and a 413 that names the size and the limit. This takes the upload item out of Phase G5. |

## Tasks (one commit each, one PR)

### PR F-1, titles as a preset (about a week)

1. **Packages in the engine.** `signature.PACKAGES`: `joint-v1` (25 / 40 / 4 s, design
   joint-v1, names and filmstrip required, 65 s minimum, 16:9 only, the rules of
   `validate_spec` today), `title-v1` (opening 0 to 5 s, end card 0 to 10 s, names
   optional, any aspect, no minimum) and `none`. The spec gains `package`; a spec
   without the key is `joint-v1`, byte-identical, so no existing brief hash or titles
   review moves. `draft_spec(title, brand, package)` fills the package's defaults;
   `validate_spec` checks the package's own rules; `plan_titles` allows a zero-length
   opening (no intro window) and zero cards (an `end_card` window instead of cards and
   lockup) and keeps today's layout for `joint-v1`. New films always record `brand` in
   the spec, taken from Settings, so the literals in `signature.py:18-20` serve only
   specs that already have none; `kinds.py:57` says "opening and end card from the brand
   kit; the 25/40 package is one option". Files: `signature.py`, `titles.py`, `kinds.py`,
   `domain/intake.py`, `config.py`, `tests/test_titles.py`, `tests/test_signature_iteration.py`. 1.5 days.
2. **The renderer draws the packages.** `Titles.jsx` gains `TitlePart` (title and line,
   one fade, portrait-aware) and `EndCardPart` (lockup or logo and up to four lines);
   `timing.mjs` learns the `title` and `end_card` window kinds with their fades;
   `title_assets` requires the filmstrip mark only for `joint-v1` and accepts `logo:
   null` otherwise; a `neutral` brand package (near-black, off-white, white accent, grey
   secondary) ships beside the existing ones. Portrait layouts: title and card sizes
   from `min(width, height)`, safe insets of 5 % in landscape and 12 % top and bottom in
   portrait, the joint intro refusing 9:16 as today. The golden stays byte-identical
   because its spec has no package. Files: `Titles.jsx`, `timing.mjs`, `request.mjs`,
   `remotion.py`, `branding.py`, `titles.test.mjs`, `tests/test_timing_parity.py`,
   `docs/RENDERER.md`. 1.5 days.
3. **The Studio offers it.** New film: "Titles: 25/40 signature · Short title and end
   card · None" with the default from the brand kit (Phase H; before it, from
   `brand_name`), and 16:9 or 9:16 again as `README.md:91` promises. Story's credits card
   becomes end-card lines or a roll by package; Film's titles review shows the package's
   windows; `deliveryWorkflow.ts` and `nextStep.ts` gate by package, so a film with no
   titles goes straight from the cut to the final. Files: `NewProduction.tsx`,
   `story/FilmFacts.tsx`, `film/DeliveryPanel.tsx`, `film/deliveryWorkflow.ts`,
   `nextStep.ts`, `api/projects.py`. 1 day.

### PR F-2, the delivery package (about a week)

4. **Package files from a verified final.** New `delivery.py` in the engine, pure
   FFmpeg and the edit, no renderer: a poster frame (the owner's chosen frame, else the
   first frame after the opening at median luminance) as PNG and JPEG; a 20-frame
   contact sheet; `chapters.txt` in the platform form (`00:00 Intro`) and an
   `.ffmetadata` file from the edit's sections, named from the section map and the
   section's feel; SRT and VTT from Phase B5's caption lines, or from `lyric-timing.json`
   lines with a start and an end when B5 has not run. Every file is a new sidecar beside
   the final (`<final>.poster.png`, `.contact.png`, `.chapters.txt`, `.srt`, `.vtt`) with
   a `package.json` listing their hashes; the final itself is never rewritten.
   `GET /exports` lists them under the film; the delivery panel offers them and the
   Library poster prefers the film's own frame. Files: `delivery.py`, `api/film.py`,
   `domain/exports.py`, `film/DeliveryPanel.tsx`, `api/projects.py`. 1.5 days.
5. **Encoder and mux options.** `ffmpegOverride` adds `-g 48` on the base kind;
   `remotion.py`'s mux takes `audio: {sample_rate: source | 48000, loudness: None |
   {target_lufs, true_peak}}`: two-pass `loudnorm` (measure, then apply with the
   measured values), with `input_i`, `input_tp`, `input_lra`, `target` and `output_i`
   written to the report, and the validator accepting the chosen rate. Loudness is a
   per-render choice for promo and advert and greyed for music videos with its reason
   (D4). The final capture choice `png | jpeg90` (D5) sits beside it and is named in the
   report. Files: `render.mjs`, `diagnostics.mjs`, `remotion.py`, `render.py`,
   `services/render.py`, `api/film.py`, `film/DeliveryPanel.tsx`. 1.5 days.
6. **Vertical and square from the same cut.** `services.render.render_variant(root,
   aspect)` compiles the approved final's shots with a per-shot reframe (the edit
   motion's anchor as the crop centre, `layerRect` covering the new canvas) and the
   package's portrait or square titles, to `renders/<slug>-final-9x16-v001.mp4` or
   `-1x1-`, with its own report naming `variant_of` and the final's hash. It is not an
   approval stage: it derives from inputs that are already approved and current. The
   Film viewer gets an aspect toggle so the Player shows the reframe before the render;
   the report warns when a reframe cuts the anchor's neighbourhood. Sharpness depends on
   Phase C1's 2× still; the variant works without it and says so. Files:
   `services/render.py`, `remotion.py`, `timing.mjs`, `BaseFilm.jsx`, `api/film.py`,
   `stages/Film.tsx`. 1.5 days.

### PR F-3, this computer (about half a week)

7. **Lyric timing on CPU (D7).** `lyric_tools.lock.cpu.txt` and a worker branch that
   loads the same model through an ONNX runtime; `status()` reports `backend: mlx | cpu`
   and a time estimate ("about three times slower"); tested against the two songs of
   the track-listening record. If the box closes without parity, the commit is the
   documented refusal and the sentence in Track and in the docs. Files: `lyric_tools.py`,
   `lyric_tools_worker.py`, `docs/ARCHITECTURE.md`. 2 days, boxed.
8. **A doctor line.** `setup.status()` grows `lyric_tools`, `depth_tools` (Phase C5) and
   a `missing` list with one plain sentence and the platform's install command per tool,
   no download; the Library shows one line when a render tool is missing ("This computer
   can't render yet: Chrome is missing · Open settings"), and Phase H's "This computer"
   section reuses the same list. The headless-shell decision (D6) is recorded in
   `docs/RENDERER.md` and the open notes in `gui-rework.md` and `creative-profile.md`
   are closed. Files: `setup.py`, `api/setup.py`, `shell/Library.tsx`, docs. 0.5 day.
9. **The upload.** Limit 50 MB; the body streams to a temporary file with a running
   count and stops at the limit; 413 says the size and the limit; `README.md` updated.
   Files: `domain/intake.py`, `api/projects.py`, `tests/test_api_intake.py`. 0.5 day.

## Not changing

Existing specs and their films: a spec without `package` is `joint-v1` and validates,
plans and renders byte for byte as today; the golden contract; every existing approval;
delivered finals, which gain sidecars and are never rewritten; the money journal, which
this phase does not touch; the FFmpeg legacy path; stage order and gates; the Player and
the MP4 as one composition.

## Acceptance

- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
  `npm test --prefix renderers/remotion`, frontend `tsc`, `npm test` and `npm run build`
  pass. `tests/test_contract_golden.py` passes without regeneration.
- `tests/test_timing_parity.py` pins the new window kinds and their fades;
  `titles.test.mjs` pins `TitlePart` and `EndCardPart` alpha curves and the portrait
  insets; new Python tests cover each package's validation, a zero-length opening, an
  end card without cards, a spec without `package` producing today's windows and
  `titles_input` byte for byte, chapters and captions from fixtures, the loudness report
  fields with a fake FFmpeg, the variant reframe rectangles, `setup.status()` with each
  tool absent, and a 50 MB upload accepted while 51 MB is refused without buffering.
- On a **scratch copy of Tree of Love**, real films only read, $0: a titles check before
  and after the branch writes the same `.request.json`, and the existing graphics review
  still validates; the package files are produced from its verified final and the
  chapters read as the song's sections; a 9:16 variant and a 1:1 variant from the same
  cut play in the Player and render, and the owner looks at three framings.
- On a **synthetic music video and promo**, no key, $0: `title-v1` at 9:16 opens on a
  title and closes on an end card in the Player and the review stills; a film with no
  titles goes from the cut to the final; the promo's loudness report is within 1 LU of
  the target and the file probes at 48 kHz when asked; `ffprobe` shows a keyframe
  interval of at most 48 frames inside a long shot; a `q90` final is produced and named
  in its report.
- Lyric timing on CPU: word times within 0.2 s of the MLX result on the two record
  songs, or the documented refusal in its place.
- The doctor line appears with `REMOTION_CHROME` pointing nowhere and disappears when
  it is set.
- No paid call of any kind in this phase, in tests or by hand.

## Risks

- **A wrong default blocks approvals.** `validate_spec` runs at brief approval for every
  signature film; a package rule that misreads an old spec would stop the owner's own
  films. The byte-identical test on the scratch copy is the guard.
- **Variants crop people.** A 9:16 frame keeps about a third of a 16:9 still. The anchor
  is the Editor's, the report warns, and the owner looks before publishing.
- **Normalised audio is new bytes.** The record that a final's decoded audio is
  bit-identical to its base no longer holds for a normalised promo; the report says so,
  and music videos keep the mix untouched.
- **Chapters inherit section names.** "Section 3" is honest but not a chapter title;
  Phase B's section naming and the Editor's feel improve it over time.
- **The CPU path may be too slow or inexact**, which is why it is boxed and a refusal
  is an acceptable result.
- **F1 lands before H.** Two settings strings serve as the brand kit until H's panel
  exists; the move is a rename, not a format change.

## Out of scope

Phase H's settings panel itself, Phase B's captions and section naming, Phase C's 2×
stills and portrait text in the edit, narrative films' mixer (Phase I6, which reuses
the loudness path), a hosted lyric-timing option, pinning or downloading any browser,
multi-language captions, platform uploads, and any change to the FFmpeg legacy path.
