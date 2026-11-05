# Phase J: the Sound stage — plan

**Proposed** 5 Nov 2026; base `main` at `78fbd26`. Follows
`docs/design/missing-features-2026-11-05.md`, item 1. The owner asked for research, a
plan, validation and an implementation in one run, so the decisions below are taken as
recommended and said so; every one is easy to reverse before the first paid cue.

**Objective:** give every film a sound layer the app can make, not only mix. A film gets a
list of cues: a music bed, ambience under a place, an effect on a moment, a sting on a
reveal. Each cue is bought through the money journal from a music or effects model, or
brought as the owner's own file, kept immutable under its own version, and mixed under the
speech with the ducking the app already measures. The Player and every render hear the
same mix. The Critic reads the mix as words. Nothing here changes a clock, a hash or an
approval.

## What the code showed

- **Mixing already exists twice, for speech.** `production/soundtrack.py` mixes a story
  film's takes with one bed and ambience spans tied to lines, measured to −16 LUFS, into
  the WAV that is the film's clock; its key covers every input and the voice approval binds
  `voice_content` (spec, takes, key). `voice.py:378-471` mixes a song film's placed voice
  lines over the excerpt into `work/audio/mix-<key>.wav`. `production.film_audio`
  (`project.py:109`) is the one function the Player (`api/voice.py:75`) and every render
  (`services/render.py:80,177,238,333,370`) call. A layer added there is heard everywhere.
- **The journal takes any kind.** `generation.begin_task` already admits `narration`,
  `upscale`, `sheet` and `clip` with a per-kind `check_before_spend`; `clips.py` is the
  model for an asynchronous purchase with polling that stops at the first task still out.
  `RunwareClient.submit_speech`/`recover_speech` accept any `audioInference` task and look
  only for `audioURL` and `cost`, so a music or effects task goes through them unchanged.
- **The provider has the models.** Read on 5 Nov from Runware's model pages: MiniMax Music
  2.6 (`minimax:music@2.6`, $0.15 a clip, `settings.instrumental`, prompt, no duration
  field, about 2 min 20 s a request, so async); ACE-Step v1.5 XL Turbo
  (`runware:ace-step@v1.5-xl-turbo`, from $0.0009 a run by compute time, `duration` 30 to
  300 s, `settings.bpm`, `settings.keyScale`, about 4 s a request); Mirelo SFX 1.5
  (`mirelo:1@1`, $0.00025 a second, `duration` 1 to 10 s, about 5 s). All answer
  `audioURL` and `cost`; none reports a length, so the file is measured after download.
  The audio API reference itself returned 404, so the live schema each quote reads
  (`client.schema(slug)`) is the contract, as it is for clips.
- **A soundtrack's key is the clock.** `soundtrack.key` binds takes, pauses, bed and
  ambience; a changed key makes the voice approval stale, and the storyboard's parent is
  `voice` on a story film. A cue must therefore stay out of that key, or adding rain would
  un-approve the storyboard.
- **The owner's own sound is one function.** `soundtrack.add_sound` copies a file under its
  hash into `media/`; the route is `POST /soundtrack/sound` and refuses non-story films.
- **The Critic reads frames only** (`critique.py`); the snapshot (`director/context.py`)
  has `_narration` but no sound section.

## Decisions (taken as recommended)

- **D1 Where cues live.** `work/sound.json`: `{"version": 1, "cues": [...]}`, one entry
  per cue with `id`, `kind` (`music`, `ambience`, `effect`), `prompt`, `start` and `end`
  anchors, `gain_db`, `duck_db`, `loop`, `versions` and `selected`. Bought files go under
  `work/sound/<cue>/v00N-<task>.wav`; owner files under `media/sound-<hash>.<ext>` through
  the existing `add_sound`. A cue with no selected version is silent and the report says so.
- **D2 Anchors.** An anchor is `{"line": "<id>"}` on a story film (from the first word of
  that line to the end of the other line's pause, so a re-recorded take moves the sound
  with it) or `{"frame": n}` on any film. A song film has no lines in its script, so it
  uses frames; `{"frame": -1}` means the film's end.
- **D3 Out of every hash.** Cues are not in `soundtrack.key`, `voice_content` or any stage
  hash. They are a layer on `film_audio`: `sound.with_cues(root, base, spans)` writes
  `work/audio/sound-<key>.wav` keyed by the base's hash and every selected cue's bytes and
  settings, and `voice.film_audio` takes that as its base. A film without cues keeps the
  file it has today, byte for byte. What proves the owner heard the sound is Phase L's
  watched-with-sound gate on the final.
- **D4 Ducking.** The same measured duck as speech: spans from the story film's layout or
  the song film's placed voice lines, `duck_db` per cue, 0.2 s attack and 0.35 s release
  from `voice._duck`. A music cue defaults to −14 dB under the film, an ambience to −24,
  an effect to −6, and every gain is one linear number so no line moves.
- **D5 Purchase.** `sound.py` with `quote_cues`, `generate_cues`, `recover_cue`, journal
  kind `sound`. A quote reads the model's public schema, builds
  `{taskType: audioInference, positivePrompt, outputType: URL, outputFormat: WAV,
  deliveryMethod, numberResults: 1, includeCost: true}` plus `duration` clamped to the
  schema's range when it has one and `settings.instrumental: true` when it offers one, and
  validates against the schema; a model whose schema refuses that shape is refused by
  name. The reserve is the catalogue's price (per clip, per second times the clamped
  duration, or per run) with a $0.01 floor, doubled for a per-run price because compute
  time is not known in advance. `deliveryMethod` is `async` and polled like a clip when
  the catalogue says the model is slow, else `sync`.
- **D6 Models in the catalogue.** Three new rows with price, source and date; Settings
  gains `sounds.music_model` and `sounds.effects_model` with ACE-Step and Mirelo
  recommended, since a bed at a cent and an effect at a tenth of a cent make a $0 film
  nearly free. MiniMax Music is listed, not recommended, for a sung piece.
- **D7 Who writes the cue list.** `sound.suggest(root)` with no model: a story film gets
  one music bed over the whole film and one ambience per structure beat named from the
  place and era, a song film gets nothing (the song is the music) until the owner adds a
  cue. A Writer task `sound` with a tool `write_sound_cues` (reason required, logged in
  `decisions.jsonl`) can propose a richer list under the truth rules: a cue's prompt may
  name only what the brief, script or storyboard names. Only the owner buys.
- **D8 The Critic's ear.** `sound.report(root)` measures the current mix: silence longer
  than 8 s, a cue with no sound, a cue that runs past the end, speech-to-bed margin under
  6 dB on any line, and the mix loudness. The report is a section of every Director
  snapshot and a card on the Sound stage.
- **D9 The screen.** A `sound` stage after Images for every kind: the cue list over the
  spine with each cue as a band, a play button per version, Keep like a take, *Make this
  sound · $x* one per cue or for all unmade, *Bring your own* per cue, the report, and the
  Writer's *Suggest cues*.

## Tasks (one commit each)

1. **`sound.py` and the mix.** Cue model and validation, `read`/`write`, anchors resolved
   against the layout or frames, `with_cues` layered into `film_audio`, `suggest`, `report`.
   Tests with real WAVs: a film without cues keeps its mix bytes; a cue follows its line
   when a take gets longer; ducking under speech; a cue past the end is cut and reported.
2. **Purchase through the journal.** `quote_cues`, `generate_cues`, `recover_cue`,
   `check_before_spend`, `begin_task` admission for kind `sound`, catalogue rows and
   `sounds` settings. Tests with fake clients: reservation before the request, no resubmit,
   a stuck task holds spending, recovery by id, a schema without `duration` and a schema
   with it, an owner file as a version.
3. **Routes and the Writer.** `GET/PUT /sound`, `POST /sound/suggest`, `/sound/estimate`,
   `/sound/generate`, `/sound/select`, `/sound/upload`, `GET /sound/<cue>/<version>`,
   `/sound/report`; the `sound` task file, example and `write_sound_cues` tool inside the
   7,000-token pin; the snapshot section. Tests over the routes and the tool.
4. **The Sound stage.** Stage in both lists, next-step facts, the page, the panel on
   Film's delivery list ("Sound: n cues, m silent"). Frontend tests for cue bands and
   the report notes; an e2e that opens the stage on a film with no key and reads the
   refusal.

## Not changing

Takes, the soundtrack's clock and key, `voice_content`, every stage hash, the journal's
contract, the renderer, `voice._duck`.

## Acceptance

- `pytest`, `ruff`, frontend tests, lint and build, renderer tests green; dist current.
- On scratch copies of the Museum and the Cool Cat promo: `film_audio` is byte-identical
  before and after with no cues; with one owner-supplied ambience the Player and a preview
  render play it under the narration, measured ducking at the first line.
- No paid call. The first live cue (one ACE-Step bed and one Mirelo effect, under $0.05)
  needs the owner's authorisation and is listed here as not done.

## Risks

- The audio API reference was unreachable; the three model pages agree on the shared
  fields, and the live schema decides. A model whose schema wants something else is
  refused by name rather than guessed at.
- A long async music task behaves like a stuck clip: the journal holds the film's
  spending until it resolves. The batch stops at the first task still out.
