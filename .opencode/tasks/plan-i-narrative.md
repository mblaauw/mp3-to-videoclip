# Phase I: narrative films, the voice is the spine — plan

**Proposed** 1 Nov 2026 for owner approval; base `main` at `c1414a3`.

**Objective:** make the app able to produce a film where a narrator leads and the
music, if any, follows. Today every path assumes a song exists first: intake
refuses anything but an MP3, the film's length is the recording's length, analysis
measures it, the spine draws it, the Player and every render use it. After this
phase a fourth kind, `narrative` ("Story film"), starts from a script instead of a
song. The narration takes, their pauses, an optional music bed and ambience are
mixed into one derived WAV, `work/audio/soundtrack.wav`, and that file becomes the
clock. Everything downstream of the clock stays as it is. Part 2 of
`docs/design/studio-assessment-2026-10-31.md` specifies the phase; the owner's
answers of 1 Nov 2026 stand: Runware is the only provider, the narrator is MiniMax
speech through Runware with `English_Magnetic_Male_2` as the default voice, there
is no local voice, ElevenLabs is scaffolded behind the same `Voice` interface and
listed only when a key is present, the $0 draft path is a read-rate estimate, one
`narrative` kind carries structure templates, shots bind to lines and frames are
re-derived from the kept takes, clips come after depth parallax, and invented
facts are allowed only when the brief declares the world fictional and every
claim is listed.

Two worked examples set the bar and are the acceptance material:

- **The Museum of Tomorrow**, pilot **"The Last House Key"**, 2:00. A curator in
  the year 2300 explains an object from our century, sometimes wrong, sometimes
  funny, sometimes touching. Five beats: hook 0:00 to 0:08, world 0:08 to 0:35,
  develop 0:35 to 1:15, reveal 1:15 to 1:45, payoff 1:45 to 2:00, so the budgets
  are 8, 27, 40, 30 and 15 s. The world is fictional, so the Writer may invent,
  and every invention is listed.
- **One Place, 500 Years.** One street corner, one fixed framing, five eras. A
  constant and a change per era. The places and dates are real, so they are
  checked against the owner's supplied facts like advert claims are today.

Nothing here makes those films. It makes the tool able to, with the first paid
takes under an authorised cap.

## What the code showed

**Everything that assumes a song.**

- `production/intake.py:86-92` resolves the source, refuses anything but `.mp3`,
  probes it and reads `source_duration` from it; `:102` derives the film
  `duration` from the window or the recording; `:188-189` copies it to
  `media/song.mp3`; `:163-187` writes `source_sha256`, `duration`, `source_duration`
  and `audio_window` into `Project` in one constructor. `_intake_window`
  (`:205-241`) is the excerpt contract per kind and needs the recording's length.
- `models.py:100-102`: `Project.source` defaults to `media/song.mp3`,
  `source_sha256` is required, `duration` is `gt=0`. `music_mode` is
  `Literal["vocal", "instrumental", "music-led"] | None` (`:106`), `kind` is
  `Kind | None` (`:107`) with `Kind = Literal["music_video", "promo", "advert"]`
  (`:13`). The serializer at `:133-153` pops `kind`, `source_duration`,
  `audio_window` and friends when `None`: that is the pattern every new field
  follows so legacy hashes hold.
- `production/project.py:47-52` `load_project` hashes `project.source` on every
  load unless `verify_source=False`. Eleven call sites read `project.source`
  directly (`audio.py:41`, `generation.py:283,816,837`, `api/track.py:34,97`,
  `api/story.py:118`, `production/intake.py:189`, `transcription.py:91,422`,
  `music_analysis.py:588`); all but `audio.py` are music-video paths
  (transcription, embedded lyrics, listening) that a narrative film never takes.
- `production/project.py:85-96` `project_payload` is folded into every stage hash
  (`production/approvals.py:220`) and carries `duration` and `source_duration`.
  For a film whose length changes with every re-recorded line, that would make
  the script's own approval stale when a take changes. See D2.
- `api/projects.py:367-394` `create_project` requires an `audio/mpeg` body
  (`:377-379`), a `.mp3` filename (`:380-382`) and a non-empty upload (`:391-392`)
  before anything else; `:440-446` queues
  the analysis job at creation. `frontend/src/NewProduction.tsx:99-100` refuses a
  non-MP3, `:202-204` is the file input, and `:134,291` disable submit without a
  file; `frontend/src/api.ts:755-780` sends the file as the request body.
- `director/context.py:168-174` prints `project.duration` and
  `source_duration or duration` plus the excerpt; it already tolerates no window.

**How the excerpt derives a WAV.** `audio.py:44-59` keys the file on
`source_sha256 + window + rate + channels` (`excerpt_key`), writes
`work/audio/excerpt-<key>.wav` through a `.partial.wav` and `os.replace`
(`:88-120`), measures the result against the window (`:116-119`) and
`render_audio` (`:124-128`) is the one function analysis, Player, preview, base and
final call: `services/analysis.py:19`, `services/render.py:76,120,192,218`,
`lyric_tools.py:300`. The soundtrack builder is this function with a different key
and a filter graph instead of `atrim`.

**What runs on the derived audio.** `analysis.py:281-283` beat-tracks it with
librosa and `:304` cuts `round(duration / 25)` sections by agglomerative
clustering; the warnings at `:331-339` already say tempo and sections are
estimates. On speech the tempo is meaningless and the section count is a number,
not the structure. `edits.cut_material` (`edits.py:865-910`) reads `music.json`
sections, lyric line starts, candidate changes and beats; `first_cut.suggest`
(`first_cut.py:79-89`) snaps joins to section starts, line starts minus two frames
and spectral changes through `pacing.snap_joins` (`pacing.py:218-249`), which takes
ordered tiers and is pure arithmetic. `pacing.plan_boundaries` (`:129`) plans
exact coverage from marked frames.

**Which approvals bind `music.json` and `lyrics.json`.** `STAGE_FILES` and
`UPSTREAM` in `production/project.py:17-40`: `analysis` is `work/music.json`,
`lyrics` is `work/lyrics.json`, `brief` depends on `lyrics`, `storyboard` on
`brief`. `effective_upstream` (`production/approvals.py:43-59`) moves the brief's
parent to `analysis` for promo, advert, instrumental and music-led films; that is
the hook for a kind whose brief has no measured parent at all. `stage_hash`
(`:170-220`) reads the stage file, folds in the upstream hash and
`project_payload`; `require_approval` (`:223-229`) walks `_required_parents`
(`:62-82`). The API's stage list is a tuple at `api/approvals.py:47-58`.

**How the spine and Player get audio.** `api/projects.py:48` declares `audio_url`
on the summary and `:317-321` points it at `/audio-excerpt` when a window exists,
else `/audio`; `api/track.py:28-52` serves both from `render_audio`.
`frontend/src/shell/FilmShell.tsx:482-486` builds `playerSrc` from it, one
`<audio>` element in `spine/player.tsx:67-89` owns time, `spine/Spine.tsx:97-125`
draws bars from `music.json` and the sections, and `services/preview.py:140-143`
hands the same URL to the Remotion Player (`frontend/src/LivePlayer.tsx:67`
passes `audio` as an input prop). The Spine shows no lyric lines today, so a
"line under the playhead" is a new element, not a change to an old one.

**How stage names are defined in the frontend.** `shell/stages.ts:3-9` is the
list of five, `shell/nextStep.ts:3` is the `Stage` union, `nextStep.ts:538-541`
dispatches a step per stage, `shell/FilmShell.tsx:227` mounts `TrackStage` for
`track`, `api/projects.py:21` is the backend `StageName` literal and
`_stage_states` (`:148-166`) computes `track` from the analysis file.

**How the Writer task is chosen.** `director/prompts.py:22-28` maps stage to role
(track is the Editor's), `:30-62` lists tasks and examples, `select_task`
(`:115-161`) goes brief → concepts → `script_ad`/`script_mv` → profile → revise
from the artifacts on disk, and `assemble` (`:172-235`) concatenates system,
`shared/truth.md`, `kinds/<kind>.md`, the style preset for the Writer, the task and
its example, and hashes the text. `kinds.py:38-113` is the code table the Writer's
prose mirrors; `styles.py:55-93` parses a preset's JSON-valued header
(`director/prompts/styles/clean-photographic.md:1-10` shows the shape:
`id`, `name`, `description`, `protected`, `model`, `settings`, `image_rules`).
`shared/truth.md` rule 1 forbids inventing facts; rule 5 forbids text in pixels.
`api/settings.py:25-27` serves presets, kinds and shot kinds to the Studio.

**How money is decided.** `shotkinds.is_paid` (`shotkinds.py:74-82`) is the only
paid-or-local decision; `localplate._compose` (`localplate.py:384-406`) dispatches
`split`, `upload`/`product` with an asset, `card`, `bridge`, `logo` and `end_card`,
and `localplate.render` (`:409-447`) keys the PNG on the shot definition, size,
sources and `LOCAL_PLATE_VERSION`. `production/assets.py:102-116` resolves a local
shot's asset path and `resolved_assets` (`:129-160`) attaches the plate.

**The journal pattern narration must copy.** `generation.quote_images`
(`generation.py:111-260`): approvals first, schema GET only (`:163-164`), the
`imageInference` const check at `:165-166`, the schema stored under
`work/schemas/<digest>.json` (`:167-168`), one UUID per task minted before any
request (`:209`), `validate_request` against the schema (`:231`), reservation per
task and `save_quote`. `authorize` (`:310-355`) demands the exact amount and a
note; `begin_task` (`:383-444`) refuses a known UUID, checks the cap and budget,
revalidates the input hash and writes `submitted` to `work/tasks.json` before the
chargeable call (`:443-444`). `finish_image` (`:453-502`) records the provider's
cost before download, quarantines changed bytes (`:480-486`), verifies the file
and indexes the asset. `recover` (`:749-787`) is by UUID and never resubmits.
`transcription.quote_runware` (`transcription.py:110-200`) is the existing
non-image sibling: it runs its own schema check for `textInference` at
`:150-156` because the one in `generation.py` is image-only.
- `providers.RunwareClient.submit` (`providers.py:295-310`) accepts any task type
  ending in `Inference` and forces `includeCost`; but `_completed` (`:269-283`)
  reads `imageURL` only, `_result` (`:286-293`) and `recover` (`:312-324`) treat a
  missing `imageURL` as pending, and `download` (`:344-377`) verifies the bytes
  with Pillow (`_image_format`, `:146-155`). A speech result carries an audio URL,
  so the client needs an audio completion and an audio download with its own
  verifier. `mediaStorage` (`:436-481`) and `textInference` (`:544-561`) show how a
  second task family was added without touching the image path.
- `config.py:23-36` holds the flat settings; `:47-48` and `:76-90` read
  `PROJECT_VEIL_RUNWARE_API` and `OPENAI_API_KEY` from the environment when the
  file has none. An `elevenlabs_api_key` follows the same two lines.

**Alignment of known text.** `domain/lyric_timing.py:102-143` saves per-line
`start`, `end`, `source` matched to the words by text; `lyric_tools.hear`
(`lyric_tools.py:236-249`) caches heard words by audio hash and lock hash and
`match_lines` (`:203`) aligns them to known lines; `status` (`:60-75`) refuses
anything but an Apple Silicon Mac with `uv`. A take aligned against its own line
is the same operation on a much easier input.

**Where captions and text live.** `EditTextStyle` is
`Literal["super", "title", "lower_third", "lyric", "card"]` (`models.py:793`),
mirrored by `EDIT_TEXT_STYLES` in `renderers/remotion/src/timing.mjs:492` and
checked at `:598`; `BaseFilm.jsx:68-142` styles each, `:144` draws a layer and
`:290-297` places text above grain and below the flash. Adding a value to a
literal changes no existing hash. Any change to `BaseFilm.jsx` changes
`implementation_hash()` (`remotion.py:115-135`), and `check_preview_binding`
(`approvals.py:146-149`) then asks every film to re-render and review its
preview; that happened for crop cuts and the look too.

**The mux.** `remotion.py:896-924` muxes the one audio file over the silent base
with `-c:a aac` and a `-t` cut; `render.py:543-600` validates frames, codec and
that the audio is at least as long as the source. `visual_identity`
(`remotion.py:100-112`) and the chunk key (`chunks.py:105-134`) never include
audio, so a rebuilt soundtrack re-muxes but never re-renders pictures.

**Storyboard and edit.** `Shot` (`models.py:566-598`) pops default-valued fields
so a `line_ids` list can join them unseen; `Storyboard.check_timeline` (`:696-712`)
demands contiguous frames; `EditDecisionList.check_board` (`:1036-1070`) demands
every shot exactly once over the full duration. `board.skeleton`
(`production/board.py:167`) writes `TODO` placeholders (`:225-226`).
`edits._seed_sections` (`edits.py:778`) seeds sections from `music.json`.

**Kinds and the signature.** `kinds.py:85,109` already create promo and advert
with `signature_required=False`, and `production/intake.py:199-200` skips the
signature package for them. A narrative film needs no Phase F1 to exist without
titles; F1 remains what makes a short opening or end card possible.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | Where does the mixer live: in the soundtrack build, or in the mux as Part 2 wrote it? | In the soundtrack build. The derived WAV is what the Player plays, so mixing there keeps Player and MP4 one programme, and the mux stays the unchanged `remotion.py:896` path. Measured loudness goes in the soundtrack receipt and from there into the render report. |
| D2 | Should `duration` and `source_duration` leave the project hash for soundtrack films, so re-recording a line does not un-approve the script? | Yes, only when `spine == "soundtrack"`. The soundtrack's own key binds into the `voice` stage, so storyboard, proof, preview and stills still go stale when a take changes, as Part 2 intends. Existing films never set `spine`, so their hashes do not move. |
| D3 | Approval order. | Brief, then `script`, then `voice`, then storyboard. The brief is approved before the words, like intent today; the brief hash does not contain the script, so writing lines never un-approves the brief. Concepts stay a button in Story, not a gate. |
| D4 | A line is edited after its take was kept. Does the take stay audible? | It stays in the mix and is marked stale (its `input_hash` no longer matches the line), the Script stage shows it, and the `voice` approval refuses while a stale take is kept. You can hear the old take; you cannot approve it. |
| D5 | First paid batch. | Authorise one capped batch on a throwaway projects folder: "The Last House Key", at most 25 lines and 2,000 characters, voice `English_Magnetic_Male_2`, model `minimax:speech@2.8`, cap **$3.00**, plus at most $0.10 of five-word casting samples. The batch stops if the first reported cost implies the cap would be exceeded. |
| D6 | Word timing on your Mac. | Align each take to its own line through the existing lyric tools when they are set up; otherwise captions are per line, which are exact by construction. No CPU path in this phase; that is Phase F3. |
| D7 | Burned-in captions by default for a story film? | No. SRT and VTT are always exported with a final; the `caption` text style is there for the Editor and for sound-off versions. |
| D8 | A clip shorter than its shot. | Hold its last frame. Looping is a per-shot flag for ambient clips, never the default, and never a stretch. |

## Tasks (one commit each, one PR)

Four steps, four PRs, in the order Part 2 gives. Screens (I7) are inside each
step rather than a fifth PR, so every step ends with an app you can use.

### Step 1, PR "I1 soundtrack spine": a 2:00 film plays in the Player from a script with no song (10 days)

1. **Kind, project and intake without an MP3.** (1.5 days)
   Files: `models.py`, `kinds.py`, `production/intake.py`, `production/project.py`,
   `api/projects.py`, `director/prompts/kinds/narrative.md`, `config.py`,
   `tests/test_kinds_intake.py`, `tests/test_intake.py`.
   `Kind` gains `"narrative"`; `kinds.py` gains the profile (label "Story film",
   lengths 60, 90, 120, 180, 300, default 120, structures speculative documentary,
   place across time, essay, fable, explainer, found footage; shot mix "painted
   scenes, plates, clips, date and title cards"; text density "dates, names, one
   closing line"; pacing "follows the narration; a hold is earned by the
   sentence"; `signature_required=False`; default style `painted-documentary-v1`,
   which exists as a file from Step 3 and as a placeholder header until then).
   `Project` gains `spine: Literal["song", "soundtrack"] | None = None`,
   `music_mode` gains `"narration-led"`, `source` and `source_sha256` become
   optional, `bed: str | None` names an optional `media/bed.mp3`; all four are
   popped when unset. `load_project` skips the source check when there is no
   source. `init_project` takes `source=None` for the narrative kind, writes
   `duration` from the requested length as a provisional value, `spine="soundtrack"`,
   `music_mode="narration-led"`, copies an MP3, if given, to `media/bed.mp3` as the
   bed, and writes an `Intent(kind="narrative", length_seconds=…, fictional=…)`;
   `Intent` gains `fictional: bool | None` and `structure: str | None`, popped when
   unset. `create_project` accepts no body when `kind == "narrative"` (the content
   type, filename and empty-body checks at `api/projects.py:377-382` and `:391-392`
   move under `kind != "narrative"`), takes `structure`, `fictional`, `voice` and does
   not queue analysis. Test: a narrative film created with no upload, a legacy
   project round-trips byte-identical, `project_payload` of a music video is
   unchanged.

2. **Script, beats, structures and the read-rate estimate.** (1.5 days)
   Files: `models.py`, new `structures.py`, new `production/script.py`,
   new `narration_timing.py`, `director/prompts/structures/*.md`,
   `tests/test_script.py`.
   `ScriptLine` (`id`, `text` 1 to 600 characters, `beat`, `target_seconds`,
   `pause_after` ≥ 0 default 0.5, `direction`, `claims[]` of `{text, invented}`)
   and `Script` (`schema_version`, `structure`, `reading_rate_wps`, `lines`,
   `notes`) with unique ids, beats that exist in the structure, and the rule that
   an `invented` claim is refused unless `brief.intent.fictional` is true.
   `structures.py` is the code table (id, label, beats with budgets and a rule per
   beat: "image before the first word" for a hook, "hold on the image after the
   sentence ends" for a reveal); the prose lives in
   `director/prompts/structures/<id>.md` with the same JSON-valued header as a
   style. Templates: `five-beat-2m` (8/27/40/30/15 s), `place-across-time` (one
   framing, N eras, a constant and a change per era), `essay`, `fable`.
   `production/script.py` writes `work/script.json` and `work/beats.json` (the
   template instance: beats, budgets, rules, length) under the state lock and
   refuses a beat whose lines' targets exceed its budget by more than 20 percent
   with a plain message. `narration_timing.estimate(root)` writes
   `work/narration-timing.json` with one entry per line, `source: "estimate"`,
   start and end from `words / reading_rate_wps` plus `pause_after`, no words. The
   rate is a constant per voice in `voices.py` (2.3 words per second until
   measured) and is copied into the script so a later rate change is visible.

3. **The soundtrack builder.** (2 days)
   Files: `audio.py`, new `production/soundtrack.py`, `services/analysis.py`,
   `analysis.py`, `api/track.py`, `tests/test_soundtrack.py`.
   `work/soundtrack.json` is the mix spec: `order` (line ids), `pauses`
   (per line, from the script unless overridden), `bed` (`path`, `gain_db`,
   `duck_db`, `attack_ms`, `release_ms`), `ambience[]` (path, span, gain), `fade_in`,
   `fade_out`, `target_lufs` (default −16). `audio.build_soundtrack(root, project)`
   keys the output on the kept takes' sha256 in order, the pauses, the bed hash and
   gain, the ducking, the fades, the ambience hashes, rate, channels and a
   `SOUNDTRACK_VERSION`, writes `work/audio/soundtrack-<key>.wav` through a
   `.partial.wav` like the excerpt, and a receipt
   `work/audio/soundtrack-<key>.json` with the measured duration and the two-pass
   `loudnorm` input and output values. A line with no kept take contributes
   silence of its estimated length, so Step 1 builds a silent (or bed-only)
   soundtrack. The filter graph: takes and `aevalsrc=0` pauses through `concat`,
   `sidechaincompress` with the narration as the key for the bed, `amix` for
   ambience, `afade`, then `loudnorm` with measured values. One engine function,
   `production/soundtrack.set_duration(root, seconds)`, updates `project.duration`
   and `source_duration` and is the only writer of either for a soundtrack film;
   `render_audio` returns the current soundtrack for `spine == "soundtrack"` and
   refuses with "build the soundtrack first" when none exists. `GET /audio` serves
   it. `analysis.analyze_narration(path, duration, timing)` replaces beat tracking
   with an RMS speech gate: `speech_segments`, `pauses`, `sections` are the beats
   from `beats.json` placed on the real line times, `estimated_tempo_bpm` is
   `None`, `beats` is empty, and the warnings say tempo is not meaningful on
   speech; `services.analysis.analyze_project` branches on the spine. The keys
   stay the same so the Spine, the Film timeline and `cut_material` read it
   unchanged. Tests: key changes with every input, silence length equals the
   estimate, a real FFmpeg mix of two synthetic takes and a bed measures the duck
   (bed RMS under speech at least 9 dB below bed RMS in a pause), the excerpt path
   is untouched.

4. **Approvals `script` and `voice`.** (1.5 days)
   Files: `production/project.py`, `production/approvals.py`, `api/approvals.py`,
   `frontend/src/ApprovalBar.tsx`, `tests/test_api_kind_upstream.py`,
   `tests/test_api_approvals.py`.
   `STAGE_FILES` gains `script: work/script.json` and `voice: work/soundtrack.json`;
   `UPSTREAM` gains `script: brief` and `voice: script`. `effective_upstream`
   returns `None` for a narrative brief, `voice` for a narrative storyboard, and
   `_required_parents` adds nothing else. `stage_hash("voice")` content is the
   soundtrack spec plus, per line, the kept take's version and sha256 verified
   against the file, plus the soundtrack key; it refuses with "re-record or
   un-keep the stale take" when any kept take's `input_hash` no longer matches
   its line (D4). `project_payload` drops `duration` and `source_duration` when
   `spine == "soundtrack"` (D2). `STAGES` in the API gains the two names. Tests:
   a music video's and an advert's stage hashes are byte-identical before and
   after; a narrative film approves brief, script and voice in order; changing a
   line un-approves script and voice but not brief; rebuilding the soundtrack
   un-approves voice and storyboard but not script.

5. **Shots bind to lines; frames come from the takes.** (1.5 days)
   Files: `models.py`, `production/board.py`, `edits.py`, `first_cut.py`,
   `pacing.py` (no arithmetic change; a `tiers` helper for narration), `timeline.py`,
   `tests/test_narration_board.py`.
   `Shot.line_ids: list[str]`, popped when empty, validated against the script
   when the project is a soundtrack film; a shot binds to consecutive lines of
   one beat. `board.skeleton_from_lines(root)` makes one shot per line group with
   `start_frame`/`duration_frames` derived from `narration-timing.json` through
   `pacing.plan_boundaries` and `snap_joins`, with the narration tiers in this
   order: sentence ends, phrase pauses, word onsets (word onsets exist only when
   words are timed). Hook beats get the picture one line-lead before the first
   word; reveal beats hold past the sentence end by the structure's rule.
   `board.retime_lines(root)` re-derives every bound shot's frames when the timing
   file changes and keeps unbound shots' durations; when an edit exists,
   `edits.retime_by_lines(root)` moves the edit spans so each join stays on the
   same line boundary and appends a report line naming what moved ("s004 +19
   frames: l007's take is 0.8 s longer"). `cut_material` adds `line_ids`,
   `sentence_ends` and `pauses` for a soundtrack film, and `first_cut` uses the
   narration tiers for it. Tests: a longer take moves only the shots after it,
   coverage and contiguity hold, the report line is written, a music video's
   material is unchanged.

6. **Screens for Step 1.** (2 days)
   Files: `frontend/src/NewProduction.tsx`, `frontend/src/api.ts`,
   `shell/stages.ts`, `shell/nextStep.ts`, `shell/FilmShell.tsx`, new
   `stages/Script.tsx` and `script/` parts (`BeatSheet.tsx`, `Lines.tsx`,
   `HearDraft.tsx`, `useScriptData.ts`), `spine/Spine.tsx`, `api/projects.py`
   (`StageName`, `_stage_states`), `api/script.py` (GET/PUT script, beats,
   timing, soundtrack build), `tests/test_api_script.py`, frontend tests.
   New film: a "Story film" kind that hides the drop zone, shows title, length,
   structure, genre line, "fictional world" toggle, narrator voice (from the
   settings default, read-only until Step 2), an optional music bed drop and
   budget, and submits with no file. `stagesFor(kind)` replaces Track with
   `script` ("Script") for narrative films; `Stage` gains `"script"`; FilmShell
   mounts `ScriptStage`; the next-step bar for Script says what is missing in the
   same voice as the other stages ("Write the script with the Writer", "Approve
   the script", "Build the soundtrack"). The Script stage: beat sheet with budgets
   and the estimate against them on the left; lines on the right, editable in
   place with pause and direction; *Hear a draft* builds the silent soundtrack
   and plays it in the Player with the lines as captions from the estimate. The
   Spine draws the narration waveform (silence in Step 1) and the line under the
   playhead. Library progress reads `script` where it read `track`.

### Step 2, PR "I2 voices and takes, I3 script and structures": the Writer fills the five-beat template, takes are journaled, the report shows budgets against real takes (10 days)

7. **`voices.py` and the `Voice` interface.** (1.5 days)
   Files: new `voices.py`, `config.py`, `api/settings.py`, new
   `src/mp3_to_videoclip/schemas/speech-runware-minimax.json`,
   `schemas/image-runware.json`, `tests/test_voices.py`.
   `Voice` is a small protocol: `id`, `provider`, `label`, `language`,
   `reading_rate_wps`, `build_request(line, settings, task_uuid) -> dict`,
   `expected_schema -> dict`, `parse_result(result) -> {url, cost, words?}`,
   `settings_from_direction(direction) -> dict`. `RunwareMiniMaxVoice` builds an
   `audioInference` request: `taskType`, `taskUUID`, `model`
   (`minimax:speech@2.8`), `positivePrompt` (the line text), `speech`
   (`voice`, `speed`, `pitch`, `emotion` where the schema allows), `outputType:
   "URL"`, `outputFormat: "MP3"`, `deliveryMethod: "async"`, `includeCost: true`.
   The committed schema files are the engine's own expectations, not the
   provider's document: task type const, required properties, the result URL key
   (`audioURL` or `imageURL`) and the cost key. `generation.schema_check(schema,
   expectation)` replaces the inline image check at `generation.py:165-166` and the
   transcription check at `transcription.py:150-156` with identical behaviour, so
   the live schema GET still decides and the request is still validated against
   it before any spend. `ElevenLabsVoice` implements the same protocol with a
   fake client only: request shape for `with-timestamps`, character-time parsing
   into words, tests, and a catalogue entry listed only when
   `settings.elevenlabs_api_key` or `ELEVENLABS_API_KEY` is set (`config.py`
   follows `:47-48` and `:87-90`). `voices.catalogue()` lists MiniMax voices from
   a committed table with `English_Magnetic_Male_2` first and recommended;
   `GET /api/settings` serves it with each provider's "ready" state.

8. **`narration.py`: voices as a journaled purchase.** (2.5 days)
   Files: new `narration.py`, `providers.py`, `services/narration.py`,
   `api/script.py`, `budget.py` (kind label only), `tests/test_narration.py`,
   `tests/test_providers.py`.
   `quote_lines(root, line_ids, voice_id, reserve, client)`: requires the `script`
   approval, refuses a line with an unresolved task, computes `input_hash` from
   text, voice id, settings and model, skips lines whose kept take already matches
   unless `regenerate`, mints one UUID per line, validates every request against
   the live schema, reserves per line from the schema's published pricing per
   1,000 characters when present, else `settings.speech_reserve_usd` (default
   $0.05 per line, the `image_reserve_usd` pattern at `config.py:36`), and
   `save_quote` with `kind: "narration"`. `authorize` is the existing function.
   `begin_take` mirrors `begin_task` (UUID refused if known, cap, budget,
   input-hash revalidation, `submitted` written before the request).
   `finish_take` records the provider cost before download, downloads to
   `work/narration/<line_id>/vNNN-<uuid>.mp3`, verifies it with `render.probe`
   (one audio stream, duration within 10 s of the estimate or a warning),
   quarantines changed bytes under `work/quarantine/`, writes the receipt
   (`provider`, `model`, `voice`, `settings`, `sha256`, `input_hash`,
   `duration`, `cost_usd`) into `work/narration.json` (the `assets.json` shape:
   versions per line, `kept` list, `selected`). `recover` by UUID never resubmits;
   an unknown cost keeps its reservation. `providers.py` gains
   `_audio_completed` and `download_audio` (ffprobe verification, same size cap,
   same `_atomic_write`), and `_result`/`recover` take the URL key from the
   request family so the image path is untouched. The job kind is `narration`,
   publishes `project.changed` per finished take like an image batch
   (`jobs/runner.py:36-41`). Tests with a fake client: quote, authorise, submit,
   pending then recovered, cost mismatch refused, quarantine, no resubmit, the
   image journal tests unchanged.

9. **Takes, keeping, timing and alignment.** (1.5 days)
   Files: `narration.py`, `narration_timing.py`, `production/soundtrack.py`,
   `lyric_tools.py`, `api/script.py`, `tests/test_narration_timing.py`.
   *Keep* and *Redo* per line: keeping a take selects it, rebuilds the soundtrack,
   recomputes `narration-timing.json` with `source: "measured"` (line start and
   end exact from the mix layout; word times absent) and runs
   `board.retime_lines` or `edits.retime_by_lines`. Several takes per line can be
   kept for comparison; one is selected into the mix. `narration_timing.align(root)`
   runs `lyric_tools.hear` on each selected take (cached by audio hash,
   `lyric_tools.py:228-233`) and `match_lines` against the line's own words,
   writing `source: "aligned"` with `words[]`; on a machine the tools refuse, the
   Script stage says "captions are per line on this computer" and nothing is
   guessed. `ElevenLabsVoice` results would write `source: "provider"` through the
   same function. The reading rate measured from the kept takes (words over
   speech seconds, pauses excluded) is written to `script.reading_rate_wps` and
   shown next to the constant it replaces.

10. **Writer tasks `script_narrative` and `narration_pass`, structures, context and tools.** (2 days)
    Files: `director/prompts.py`, `director/prompts/writer/script_narrative.md`,
    `writer/narration_pass.md`, `examples/script_narrative.md`,
    `prompts/kinds/narrative.md`, `prompts/structures/*.md`, `director/context.py`,
    `director/tools.py`, `director/mcp.py`, `tests/test_director_prompts.py`,
    `tests/test_director_tools.py`, `tests/evals/` (one narrative fixture).
    `STAGE_ROLE["script"] = "writer"`; `select_task` for the Script stage returns
    `script_narrative` without a script and `narration_pass` with one; for a
    narrative film the Story stage goes brief → profile → revise, with concepts
    still reachable from its button. `assemble` appends
    `structures/<id>.md` after the kind file for narrative tasks; its version joins
    the hash. `script_narrative` fills the template: one line per sentence or
    two, each with a beat, a `target_seconds` from the words at the stated rate,
    a `pause_after`, a direction, and `claims` with `invented: true` for anything
    not in the owner's facts; it refuses to invent unless the brief is fictional,
    and for a real place checks dates and names against the supplied facts like
    advert claims. `narration_pass` turns a direction ("slower, wry, land on
    'privacy'") into provider settings the voice supports and trims lines whose
    takes overran their budget. Tools: `get_script`, `write_script` (whole script,
    validated, refused after the `script` approval unless the owner asks for a
    revision, prompt provenance appended to `work/prompt-artifacts.jsonl`),
    `update_lines` (named lines), `get_narration` (takes, timing, budgets). The
    snapshot (`context.py:164-174`) adds the structure, each beat's budget against
    the estimate or the real takes, the lines with their times, and the voice; the
    `_music` line for a soundtrack film reports speech and pauses instead of tempo.
    The storyboard task learns `line_ids` and "what we see while this is said".

11. **The report: budgets against real takes.** (0.5 day)
    Files: `edits.py`, `production/script.py`, `frontend/src/film/cutNotes.ts`.
    `script_report(root)`: per beat the budget, the estimate, the measured span,
    the overrun in seconds and the lines that caused it; invented claims listed;
    stale takes; the measured reading rate. Shown in the Script stage, in the
    Editor's snapshot and in `GET /edit`'s report with plain-sentence notes.

12. **Screens for Step 2.** (2 days)
    Files: `script/VoiceCasting.tsx`, `script/RecordBar.tsx`,
    `script/TakesLightbox.tsx`, `script/takes.ts`, `stages/Script.tsx`,
    `spine/Spine.tsx`, `shell/SettingsDialog.tsx` (voice default and the
    ElevenLabs key row only; the full panel is Phase H), frontend tests.
    Voice casting in Script: the catalogue, *Hear one line · $0.0x* (a real take of
    the first line through the same journal), *Lock voice*; the voice id and
    settings bind into the brief through `intent.voice`. *Record with
    English_Magnetic_Male_2 · $0.12* quotes the unrecorded lines, shows the price
    and the note, and runs the job with per-take progress. The takes lightbox per
    line: play, waveform, *Keep* (K), *Redo* (R) with a direction field that is
    saved to the line and offered to `narration_pass`, stale marking, several
    kept takes side by side. The Spine shows the real narration waveform and the
    line under the playhead; clicking a line seeks to its start.

### Step 3, PR "I4 pictures, I6 mix and captions": one corner across five eras with the anchor as reference, the bed ducks under the voice, captions render from the timing file (8 days)

13. **Shot kinds `plate`, `era`, `document`, `date_card`, `title_card`.** (2 days)
    Files: `models.py`, `shotkinds.py`, `localplate.py`, `production/image_specs.py`,
    `production/assets.py`, `director/prompts/writer/storyboard.md`,
    `frontend/src/shotKinds.ts`, `tests/test_shot_kinds.py`.
    `plate` (an uploaded period or archival image, `asset` required, local, with a
    camera move from the edit); `era` (paid: compiled with the place anchor's
    reference image, the era's palette and light from the profile, and a fixed
    framing line "keep the camera, the horizon and the building line"); `document`
    (paid: a prop close-up, compiled like a scene with a `document` framing);
    `date_card` and `title_card` (local: the year or the title on the preset's
    palette, through `localplate`, keyed like a card). `is_paid` gains `era` and
    `document` and nothing else; `is_local` stays its negation. `LOCAL_PLATE_VERSION`
    is unchanged because existing kinds draw the same pixels; the new kinds have
    their own composers. The era compiler puts the anchor reference first in
    `references` so `proof` binds it through the shot's `input_hash`
   (`approvals.py:205-209`).

14. **Style presets.** (1 day)
    Files: `director/prompts/styles/painted-documentary.md`, `archival.md`,
    `illustrated.md`, `future-museum.md`, `kinds.py` (`style_presets` for
    narrative), `tests/test_director_prompts.py`.
    `painted-documentary-v1` (museum light, matte-painting depth, the house look
    for speculative documentary), `archival-v1` (period photographic and film
    textures by era, grain and colour per decade), `illustrated-v1` (cel, paper
    cut-out, ink), `future-museum-v1` as the worked example. Each with `image_rules`
    in the header as today, none protected.

15. **Creative profile `narrator`, `place` and `eras[]`.** (1 day)
    Files: `models.py`, `production/brief.py`, `director/prompts/writer/profile.md`,
    `director/tools.py`, `tests/test_production.py`.
    `Narrator` (persona, era, attitude, what they get wrong, voice id), `Place`
    (anchor description, fixed camera, `reference_id`) and `Era` (year, state,
    palette, light, what persists, what changed), all on `CreativeProfile`,
    popped when unset; `set_creative_profile` keeps `permission_confirmed`
    semantics for a narrator who is a real person (rule 4). The `era` shot kind
    binds an era by id.

16. **The mix: bed, ambience, fades, loudness.** (1.5 days)
    Files: `audio.py`, `production/soundtrack.py`, `services/render.py`,
    `render.py`, `api/script.py`, `tests/test_soundtrack.py`,
    `tests/test_render_service.py`.
    The Step 3 builder finishes the graph: `sidechaincompress` parameters from
    the spec, ambience per span, fades, two-pass `loudnorm` to the target with
    the measured input and output integrated loudness, true peak and range in the
    receipt. The render report copies the receipt's measured values and the
    soundtrack key, so the delivery checklist can show "−16.1 LUFS measured".
    The mux is unchanged (D1). Promo and advert may later opt in by setting a
    soundtrack spec; not wired here.

17. **Captions.** (1.5 days)
    Files: `models.py`, `renderers/remotion/src/timing.mjs`, `BaseFilm.jsx`,
    new `captions.py`, `api/film.py`, `services/render.py`,
    `director/prompts/editor/edit.md`, `renderers/remotion/tests/edit-primitives.test.mjs`,
    `tests/test_captions.py`.
    `EditTextStyle` and `EDIT_TEXT_STYLES` gain `caption` (bottom centre, box,
    portrait-safe); `captions.layers(root)` makes `EditText` items per line from
    `narration-timing.json` (word-timed lines may split on phrase pauses) that the
    Editor accepts into the cut; `captions.srt(root)` and `.vtt(root)` write
    sidecars from the same file; `GET /api/projects/<slug>/captions.{srt,vtt}` and
    the final's file list include them. Existing cuts render byte-identically.
    Regenerate `docs/primitives/` for the new style.

18. **Screens for Step 3.** (1 day)
    Files: `stages/Storyboard.tsx`, `stages/Images.tsx`, `film/FilmTimeline.tsx`,
    `film/FilmPanel.tsx`, `director/prompts/editor/edit.md`, `cutNotes.ts`.
    Storyboard groups shots by beat and by line for a soundtrack film and shows
    the line text on the card; Images shows takes (per line, with Keep) in a tab
    beside stills and the era anchor as the style check; Film's timeline gains a
    narration lane (line blocks with text, under the waveform) and a quiet bed
    lane; the Film panel shows the mix spec (bed gain, duck, fades) with a rebuild
    button and the measured loudness. The Editor's narration-led rules: cut on
    sentence ends, lead the image by half a second on a reveal, never cut
    mid-word, keep the bed below the voice.

### Step 4, PR "I5 clips": animation as a journaled asset version, after Phase C5 (5 days)

19. **Clips as a purchase, narrative parts only.** (2 days)
    Files: new `clips.py`, `services/clips.py`, `api/images.py`,
    `schemas/video-runware.json`, `tests/test_clips.py`.
    Phase C5 lands the asset version model (a clip version beside still versions
    in `work/assets.json`, `media: "clip"`, immutable, journaled by UUID). Here:
    `quote_clips(root, shot_ids, seconds, client)` prices per second from the
    schema's pricing or `settings.clip_reserve_usd_per_second`, builds a
    `videoInference` image-to-video request from the selected still, validates it
    against the live schema, and the Writer's `propose_motion` names which shots
    earn motion and why. The still stays the fallback.

20. **The clip layer in `BaseFilm`.** (2 days)
    Files: `renderers/remotion/src/BaseFilm.jsx`, `timing.mjs`, `request.mjs`,
    `remotion.py` (compile the clip beside the still), `chunks.py` (the clip hash
    enters the key through the compiled shot), `services/preview.py`,
    `renderers/remotion/tests/edit-primitives.test.mjs`, `tests/test_remotion_adapter.py`.
    `OffthreadVideo` in the MP4 and `<Video>` in the Player inside the same span,
    camera and grade; a clip shorter than its shot holds its last frame unless the
    shot sets `loop` (D8); never a stretch. Depth parallax from Phase C2 is the
    default motion for painted scenes without a clip.

21. **Screens for Step 4.** (1 day)
    Files: `stages/Images.tsx`, `images/PaidCard.tsx`, `film/FilmPanel.tsx`.
    *Animate this shot · $0.xx for N s* per shot with the price, the clip beside
    the still in the lightbox, the clip marked on the Film timeline.

Total about 33 days, inside the five to seven weeks Part 2 estimates.

## Not changing

- The hashes of every existing film: every new field on `Project`, `Intent`,
  `Shot`, `CreativeProfile` and `EditText` is serialised only when set, and the
  `project_payload` rule in D2 is gated on `spine`. `tests/test_contract_golden.py`
  is a music video and must pass unregenerated through all four PRs.
- Music videos, promos and adverts: intake, the excerpt, `music.json` and
  `lyrics.json` bytes, the brief chain, `seed_edit`'s faithfulness, the mux, the
  signature.
- Money: the journal pattern (reservation and UUID before the request, recovery
  by UUID, quarantine, unknown cost keeps its reservation), the exact-amount Studio
  authorisation, no Director-authorised spend, no paid call in tests, no live call
  without the owner's explicit authorisation (D5).
- The engine stays importable without the web layer: `narration.py`, `voices.py`,
  `audio.py`, `structures.py`, `captions.py` and `clips.py` import nothing from
  `api/` or `jobs/`.

## Acceptance

Every step: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
`cd renderers/remotion && npm test`, `cd frontend && npm run build` and the
frontend tests pass; `uv run studio` starts; `tests/test_archive.py` and
`tests/test_contract_golden.py` pass unchanged. All browser runs are on a
**throwaway projects folder** (`STUDIO_PROJECTS` pointed at a scratch directory);
`projects/`, `backups/` and `archive/` are only read.

**Step 1.** Done when a 2:00 five-beat film plays in the Player from a script
with no song. Concretely: create "The Last House Key" as a Story film with no MP3
and the `five-beat-2m` structure; paste a 25-line script in the Script stage;
the beat sheet shows the estimate against 8/27/40/30/15 s; *Hear a draft* builds
a silent soundtrack of the estimated length and the Player plays it with the
lines as captions; approve brief and script; a storyboard skeleton from lines
covers the film; a music video and an advert on the same folder behave exactly as
before, and their stage hashes are byte-identical before and after. New tests:
intake without a source, project serialisation unchanged for legacy, soundtrack
key and silence length, a real FFmpeg mix measuring the duck, approval chain
order, retime by lines with the report line.

**Step 2.** Done when the Writer fills the five-beat template for "The Last House
Key", takes are journaled and the report shows each beat's budget against the real
takes. Concretely, with the owner's authorisation of D5: one casting sample
(five words, `English_Magnetic_Male_2`), then one batch of at most 25 lines and
2,000 characters at `minimax:speech@2.8` under a **$3.00 cap** on the throwaway
folder; every take has a receipt with provider cost, sha256 and input hash; a
deliberately interrupted job recovers by UUID with no resubmission; the soundtrack
rebuilds on *Keep* and the Player plays the voice; the measured reading rate
replaces 2.3; the script report names every beat's overrun; on the owner's Mac
with the lyric tools set up, at least one line gets word times from alignment.
No model call and no provider call in tests; the Writer turn that writes the
script is one live turn on the scratch copy, reported with its tokens where the
gateway gives them.

**Step 3.** Done when a place film shows one corner across five eras with the
anchor as reference, the bed ducks under the voice and captions render from the
timing file. Concretely: "One Place, 500 Years" on the throwaway folder with the
anchor plate as the style check and five `era` shots compiled with it as the first
reference (the compiled prompts are inspected; the paid batch is a separate
owner authorisation, at most 6 stills); a bed MP3 and the Step 2 voice mixed with
measured ducking and −16 LUFS reported in the delivery checklist; SRT and VTT
beside the final with the line times; a `caption` layer visible in the Player and
in the MP4 at the same frame. Existing cuts render byte-identically without the
new style.

**Step 4.** Done when one shot carries a clip version beside its still, chosen
by the owner with the price shown, the Player and the MP4 show it at the same
frames, a short clip holds its last frame, and the still renders when the clip is
absent. Requires Phase C5; a capped batch of at most 2 clips with the per-second
price shown is a separate owner authorisation.

## Risks

- **The speech schema is assumed.** The request shape (`audioInference`,
  `positivePrompt`, `speech.voice`, async with polling, an audio URL) comes from
  the assessment's research, not from a fetched document. The live schema GET
  decides and `validate_request` runs before any spend, so a wrong assumption
  costs nothing but a day of rework in task 7.
- **No word times from MiniMax.** Captions are then per line, exact by
  construction; word-level needs the lyric tools on Apple Silicon (D6). The
  reveal-beat rule ("hold after the sentence ends") only needs line ends.
- **Cost per line is unknown until the first take.** The reservation is the
  published price or $0.05 per line; the provider's reported cost is the truth and
  the batch stops at the cap. D5 is the first measurement.
- **`duration` leaves the hash for soundtrack films (D2).** If the owner prefers
  the strict reading, every take change un-approves the script and the chain
  starts again at the words; the plan then needs a "re-approve script" shortcut.
- **`BaseFilm.jsx` changes stale every existing preview** through
  `implementation_hash` (tasks 17 and 20), as crop cuts and the look did. Film
  already offers the re-render and review in one place.
- **Speech through librosa.** Task 3 replaces beat tracking for the soundtrack
  spine; the `music.json` keys stay, so a screen that reads tempo shows "not
  measured". Energy on speech is the voice's loudness, which the Editor can use.
- **`Stage` is threaded through the frontend** (`nextStep.ts:3,538-541`,
  `stages.ts`, `api/projects.py:21`); a missed branch shows a music-video step on a
  story film. Frontend tests pin `stagesFor` and the Script step wording.
- **Scope.** Four PRs and about 33 days; Step 3's era consistency leans on Phase
  E5 (character sheet, edit mode, per-shot seeds). Without E5 the anchor reference
  alone decides consistency, which is the state the acceptance records.

## Out of scope

Lip-sync and on-screen performers speaking; music generation; sound-effects
generation beyond a bed and ambience you import; a local voice (the owner's
decision); live ElevenLabs calls (scaffold and tests only); the general asset
version model and depth parallax (Phases C5 and C2, dependencies of Step 4); the
settings panel (Phase H; this phase adds two keys and a default voice only); a CPU
alignment path (Phase F3); promo and advert voice-over through the mixer (the
spec exists, the screen does not); translations and multiple narrators; the Critic.
