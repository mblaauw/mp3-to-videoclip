# Make it musical — plan

**Proposed** 1 Nov 2026 for owner approval; base `main` at `c1414a3`.

**Objective:** let the Director hear the song and let the automatic cut follow it.
One song map, built from what the app already measures, reaches the Writer on every
task, the Editor through a tool, the Film screen through a route and the planner
through `cut_material`. Sections come from the music rather than from the clock.
The first cut lands on downbeats and beats, plans its density per section from
energy, and makes more or fewer cuts with crop cuts instead of new pictures. Timed
lyrics become captions the Editor can choose, with SRT and VTT beside the final.
Phase B of `docs/design/studio-assessment-2026-10-31.md`; nothing here costs money.

## What the code showed

- **Sections come from the clock, not the music.** `analysis.py:303` asks
  `librosa.segment.agglomerative` for `round(duration / 25)` segments, every one labelled
  `unreviewed` (`analysis.py:317`). The 1 s energy curve (`analysis.py:291-295`), beats
  (`analysis.py:282-284`) and candidate changes (`analysis.py:84-136`, on a 2 s step with
  a 6 s minimum gap) are all there, but the candidate changes are capped at the same
  `round(duration / 25)` (`analysis.py:132`).
- **The deep pass measures what the cut needs and nobody reads it.** `deep_analysis.py`
  returns a tempogram tempo with its octave rival (`deep_analysis.py:189`), kick-band
  downbeats with scored bar lengths of 2, 3 and 4 (`deep_analysis.py:377-446`), a
  Krumhansl key with runner-up (`deep_analysis.py:449`), checkerboard novelty sections with
  a 6 s separation and a 0.25 floor (`deep_analysis.py:538-609`) and bass and vocal-band
  onsets (`deep_analysis.py:730-731`). Its only consumer is `section_map._detected_edges`
  (`domain/section_map.py:111-118`), which uses the section times as snap targets when
  the owner proposes sections from lyric tags.
- **The deep pass runs almost never.** The upload job runs `analyze_project` only
  (`api/projects.py:443-448`, `services/analysis.py:10-21`). `deep_analyze_project`
  (`services/analysis.py:24-31`) runs once, on `POST /section-map/propose`, and only when
  `work/music-deep.json` is missing (`api/track.py:176-180`). The CLI has `analyze --deep`
  (`cli.py:498-512`). A film whose owner never pressed "Propose" has no deep file.
- **`music.json` is the root of the approval chain.** `STAGE_FILES["analysis"]` is
  `work/music.json` and `lyrics` depends on `analysis` (`production/project.py:17-33`);
  `stage_hash` digests the file and its upstream (`production/approvals.py:171-234`), so
  brief, storyboard, proof, stills and preview all hang from its bytes. `section_map.py:3-6`
  and `music_notes.py:3-5` were written as layers beside it for exactly this reason, and
  `intake.py:406` deletes both music files when the excerpt changes. Rewriting
  `music.json` for a finished film would un-approve its whole chain.
- **The name `music_map` is taken.** `music_map.py:13` `build_music_map` merges the paid
  listening draft for music-led films into `work/music-map.json` (`music_map.py:159-161`,
  CLI `music-map` at `cli.py:724-727`). The new object needs another name.
- **The Writer gets tempo and twelve labels.** `director/context.py:84-109` `_music` emits
  the tempo, at most twelve section labels and the warnings. Nothing in `context.py`
  mentions lyrics at all; the only task-specific block is the treatment's passage times
  for `storyboard` (`context.py:238-240`). Lyrics reach a model only when it calls
  `get_lyrics` (`director/tools.py:432-449`). The treatment is clipped to 420 characters
  (`context.py:212`) and the look to 360 (`context.py:215`). The snapshot is rebuilt per
  turn with the task name (`api/director.py:201`).
- **Every tool already goes to both roles.** `loop.py:79` passes `TOOLS` whole; the MCP
  bridge excludes only the paid and job tools (`director/mcp.py:29-34`); the prompts name
  tools by hand (`editor/edit.md:15` says to call `get_cut_material` first;
  `writer/place.md:8` and `writer/profile.md:15` name `get_music_summary`).
  `tests/test_director_mcp.py:26` pins the exposed names.
- **The planner has beats and ignores them.** `edits.cut_material` (`edits.py:865-910`)
  reads `music.json` through `section_map.apply` and returns sections, lines, changes and
  beats; `first_cut.suggest` snaps joins through `pacing.snap_joins` with three tiers,
  sections, lines led by two frames, changes (`first_cut.py:79-89`, `LINE_LEAD` at
  `first_cut.py:20`), and never splits or merges: the join count is the storyboard's
  (`first_cut.py:78`). `pacing.snap_joins` (`pacing.py:218-250`) is the right place for
  more tiers; it is pure, ordered by evidence and never adds a join.
- **Density is judged after the fact.** `EditSection.density_per_10s` defaults to 0
  (`models.py:967`), so `density_target` is silent for every seeded or suggested cut
  (`edits.py:525-533`) and `energy_density` falls back to words in the feel or the event
  map (`edits.py:534-545`, `edits.py:208-230`). The report never sees downbeats.
- **Every storyboard shot appears exactly once in a cut** (`models.py:1036-1050`
  `check_board`), so a quiet section cannot lose a shot; it can only lose crop cuts and
  hold longer. Crop cuts are the way to more cuts (`models.py:874-888`, zoom to 1.6, soft
  warning above 1.4 at `edits.py:128`).
- **Captions already have a home.** `EditText` carries style `lyric`, 160 characters and
  absolute frames (`models.py:791-914`); a shot holds at most eight text layers
  (`models.py:926`) and each must lie inside its shot (`models.py:946-951`).
  `lyric_timing.view` gives every sung line its start, an end for tapped and automatic
  lines, and a source (`domain/lyric_timing.py:61-93`). The Film panel has no text-layer
  control (`film/FilmPanel.tsx`); text comes only from the Editor. No SRT or VTT exists
  anywhere in `src/`, `frontend/` or the renderer.
- **The report copy map has no case for new codes** (`frontend/src/film/cutNotes.ts`
  covers `hold_ratio` to `text_reading_time`), and the golden pins compiled image
  prompts, not the Director's prompt files (`tests/test_contract_golden.py:166`), so prompt
  edits do not touch it.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | What is the song map called, and where does it live? | A new `song_map.py` with `song_map(root)`, cached in `work/song-map.json` keyed by the hashes of its inputs. `music_map.py` and `work/music-map.json` stay as they are for music-led films. The route is `GET /song-map` and the tool `get_song_map`, as the assessment names them. |
| D2 | Where do sections from the music live, so no approval changes? | In the song map only. `music.json` is never rewritten and `analysis.py` is unchanged, so every existing hash holds. `section_map.apply` takes the song map's sections as its base when the owner has not saved a map; the owner's layer stays on top and *Reset* returns to the song map's sections. The count-based sections remain the fallback when the deep file is missing or finds fewer than two boundaries. |
| D3 | Should the deep pass be part of the standard analysis job? | Yes. The upload job and *Measure again* run the quick pass, write `music.json`, then run the deep pass as a second phase of the same job. Track opens on the quick result; the song map upgrades itself when the deep file lands. Measure the deep pass on a four-minute track first; above 60 s it becomes its own job behind the quick one. |
| D4 | In what order does a join take the grid? | Section start, sung line (led by two frames), downbeat, candidate change snapped to its nearest downbeat, beat. Downbeats and beats are led by one frame so the picture is there when the hit lands. The beat tier is only offered when the best bar-length score is at least 1.1, because a score near 1.0 means the phase was not found (`deep_analysis.py:436-441`). |
| D5 | What does "merge when quiet" mean, given every shot appears once? | Drop crop cuts and stretch joins toward the long hold in quiet sections. A true merge removes a storyboard shot and belongs to a Storyboard tool, not the cut. |
| D6 | Which lines become captions, and what goes in the sidecar? | *Captions* in Film offers Off, All sung lines and Named sections only (hook, chorus, refrain). The Editor can choose any subset through `set_captions`. SRT and VTT always carry every timed line, whether burned in or not. The per-shot text limit rises from 8 to 24 so a long shot can carry its lines; a cut without text serialises exactly as before. |

## Tasks (one commit each, two PRs)

**PR B1, the song map.**

1. **Song map engine.** New `song_map.py`: `song_map(root) -> dict` merging `music.json`,
   `music-deep.json`, `section-map.json`, `music-notes.json` and `lyric-timing.json` into
   tempo (with the octave rival), key and runner-up, beats per bar from the best bar-length
   candidate, downbeats and beats as integer frames through `timeline.frame_number`, the
   bar grid, sections with name, frames, energy from the energy curve, an energy word
   (quiet, middle, full, banded as `first_cut._bands`), the first sung line and its frame,
   candidate changes snapped to the nearest downbeat within one second, and a 20-point
   energy sparkline. Sections are the checkerboard boundaries, with D2's fallback. Every
   field carries the source file it came from and the warnings stay attached. Cached to
   `work/song-map.json` with the input hashes; rebuilt when any input changes. Pure, no
   model, no network. Tests on the existing analysis fixtures and on a film with no deep
   file. 2 days.
2. **Sections from the music under the owner's layer (D2).** `section_map.apply`,
   `_measured_starts` and `reset` read their base from the song map; `edits._seed_sections`
   and `cut_material` follow without change. Track shows the base sections with the note
   "from the music" and the same *Propose* and *Reset* buttons. A test proves that
   `stage_hash` for every stage of a fixture with recorded approvals is byte-identical
   before and after. 1 day.
3. **Serve it and inject it.** `GET /api/projects/{slug}/song-map` under `@read_endpoint`;
   `get_song_map` in `director/tools.py` for both roles and through the MCP bridge
   (`test_director_mcp` names updated); `context.py` replaces `_music` with a compact
   song-map block for every task: one line of tempo, key and bars, one line per section
   (name, time, energy word, first sung line, density target), the sparkline as twenty
   digits; `cut_material` gains downbeats, beats, bar frames and each section's energy
   word and target. `editor/edit.md` v4 and `editor/music.md` v4 name `get_song_map` and
   say what a downbeat and a bar are worth. 1 day.
4. **Lyrics and the treatment into the Writer.** For `concepts`, `script_mv`, `script_ad`,
   `import` and `storyboard` the snapshot lists the sung lines with their times
   (`mm:ss text`, source noted) or, with no times yet, the lines alone. The treatment is no
   longer clipped at 420 characters; a cap of 4,000 with a note protects the budget. The
   snapshot's size is measured on Tree of Love and recorded. `test_director_context`
   updated. 0.5 day.
5. **Deep pass in the analysis job (D3).** `services.analysis.analyze_project` runs the
   deep pass as a second phase with its own progress words; `POST /analyze` does the same;
   the song map rebuilds when the deep file lands and the watcher's `project.changed`
   refreshes Track. The CLI keeps `--deep`. `docs/ARCHITECTURE.md` describes the song map
   and the two files it sits beside. 0.5 day.

**PR B2, cut on the grid and captions.**

6. **The grid in the planner.** `pacing.py` gains `grid_tiers(downbeats, beats, lead)`
   and `density_plan(sections, fps, beats_per_bar, tempo)`, pure functions returning the
   lead-adjusted frames and a target in cuts per 10 s per section (quiet about one bar per
   cut and holds allowed, middle one cut a bar, full two to three cuts a bar, clamped to the
   1.5 s minimum). `snap_joins` takes the five tiers in D4's order. `first_cut.suggest`
   uses them and writes `density_per_10s` into each `EditSection`, so the existing
   `density_target` check becomes live. Tests: a join one frame before a downbeat beats a
   beat two frames away; a line still beats a downbeat; no snap without a bar-length score.
   1.5 days.
7. **Split and merge with crop cuts (D5).** `pacing.split_points(start, end, bar_frames,
   target, min_frames)` returns bar-line frames inside one shot. In full sections,
   `suggest` adds `EditCrop` entries on those frames when a shot is longer than two bars:
   framings alternate between the whole still and a 1.25 detail at the shot's anchor, never
   above 1.4. In quiet sections it drops suggested crops and lets joins stretch toward
   `MAX_HOLD_SECONDS`. New report checks: `off_grid` (a cut in a full section more than three
   frames from any downbeat or beat when a grid exists) and `late_cut` (a cut one to three
   frames after a hit rather than before). `cutNotes.ts` gets plain sentences for both and
   for `density_target`. The Film change list counts crop cuts added and removed. 1.5 days.
8. **Captions (D6).** New `captions.py`: `caption_layers(root, indexes=None)` turns timed
   lines into `EditText` layers of style `lyric`, in at the line's frame, out at its end or
   two frames before the next line, between one and six seconds, clipped to the shot that
   holds its start and continued as a second layer when it crosses a join; ids `cap-<index>`.
   `edits.apply_captions(root, indexes, style)` replaces every `cap-` layer and saves through
   `save_edit`, so the cut's approval goes stale as for any cut change. `models.py:926`
   allows 24 text layers. Film panel: a *Captions* control (Off, All sung lines, Named
   sections only) with the count shown; Editor tool `set_captions`. `GET /captions.srt`
   and `GET /captions.vtt` from the timed lines; `render_final` writes both beside the
   final and lists them in the report. Report check `caption_overlap` when two text layers
   are on screen at once. 1.5 days.
9. **Acceptance, docs and the build.** See below. `docs/EDITING.md` gains the grid and
   captions, `docs/ARCHITECTURE.md` the song map, and the frontend build is committed.
   0.5 day.

Total about 10 days; B1 about 5, B2 about 5.

## Not changing

The bytes of `music.json`, `lyrics.json` and every approval hash; `analysis.py` and
`deep_analysis.py` measurements; `seed_edit`'s faithfulness; the owner-only tool gate;
the render request and the golden contract (text layers and crop cuts already exist in
it; nothing new is sent to the renderer); the legacy `music_map.py`; the Editor's model
and gateway. No paid call of any kind, no new provider, no model call in tests.

## Acceptance

- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, frontend
  `tsc`, tests and build, and `npm test --prefix renderers/remotion` pass; the app starts.
  New tests: the song map on fixtures with and without a deep file, the fallback, hash
  stability across every stage, the five tiers and their order, density targets written,
  crop cuts added only in full sections and never above 1.4, caption layers inside their
  shots and split at joins, SRT and VTT output, the three new report codes, the MCP name
  list, the snapshot for every Writer task. No model or paid call in any test.
- On a **scratch copy of Tree of Love** (38 shots, the Editor's cut), real films only
  read, $0 spent:
  - the deep pass and the song map run from the Track screen; both times are recorded;
  - `GET /song-map` names every section with a name, energy word, key, bars and a first
    line; the Track sections change only when no owner map is saved;
  - `work/approvals.json` and `stage_hash` for every stage are byte-identical before and
    after the song map exists;
  - the Writer snapshot for `concepts` holds the sung lines with times and the whole
    treatment; its character count is reported;
  - *Suggest a cut* with no model: at least four of five joins in full sections land
    exactly one frame before a downbeat or beat, crop cuts appear in full sections and not
    in quiet ones, every section has a density target, and the report has no hard
    findings;
  - *Captions: All sung lines* writes one layer per timed line, the Player and a local
    preview render show the same caption on one sampled frame, and the SRT and VTT files
    open in a player and in `ffmpeg -i`;
  - the real films' bytes, approvals and renders unchanged.
- Zero Bars (79 shots) gets the same suggestion run for the crop-cut count and timing.

## Risks

- **The deep pass costs time at intake.** `chroma_cqt` on a four-minute track may take
  tens of seconds; D3 keeps the quick pass first and measures before deciding where it runs.
- **Checkerboard boundaries can be wrong.** A 6 s separation can split a chorus or miss a
  quiet bridge. The fallback, the owner's layer and *Reset* keep this reversible, and the
  song map says which source each boundary came from.
- **A wrong downbeat phase would put every cut a beat early.** D4's score threshold and
  the beat tier limit the damage; the owner's eye on one suggested cut settles it.
- **More crop cuts, softer pictures.** The 1.4 limit holds until Phase C raises the
  still resolution.
- **Captions were never seen at scale.** The `lyric` style was tuned for a few Editor
  lines; a full song of 160-character lines needs a look on the Mac, and portrait safe
  areas wait for Phase C4.
- **A bigger snapshot costs tokens** on every turn. Task 4 measures it; a cap on lines
  (first 60, with a note) is the fallback.

## Out of scope

Per-word timing and caption typography (Phase C4), the delivery package beyond the two
sidecars (Phase F2), the Writer's craft layer and section-to-structure mapping (Phase E3),
any analysis of lyric meaning or emotional arc, paid transcription, merging storyboard
shots, the depth and motion work of Phase C, and the Critic.
