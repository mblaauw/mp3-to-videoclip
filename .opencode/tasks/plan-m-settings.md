# Plan M: the Director on every stage, and a settings pane that knows the new work

## Objective

Two things the owner found after phases J, K and L landed. The Writer could not
write the release copy on the Publish stage. And the settings pane was written
before cues, the library and the release existed, so it says nothing about them
and some of its words are no longer true.

## What the code showed

- `api/director.py _context` accepts only `track, story, storyboard, images,
  film` as a context stage. The shell sends the current stage in every turn's
  context, so on Sound and Publish every turn, typed or from a button, fails
  with "context stage is invalid" before any model is asked. The Script stage
  had the same hole.
- `useDirector.ts` opens the drawer on the Editor unless the stage is story,
  storyboard or images. On Sound and Publish the Writer's own buttons went to the
  Editor with the Editor's prompt.
- The pane has tabs for roles, voices, pictures, keys, new films, this computer
  and costs. Nothing chooses the music or effects model; the price words know no
  "run" or "clip"; the Roles hints stop at images; the Pictures note says the
  video model and upscaler are stored for later, which `clips.py` and
  `upscale.py` disprove; nothing says where the library or the productions are.
- `publish.read` starts every film on YouTube with no way to start elsewhere.

## Decisions

- D1. The allowed context stages are the stages the prompt suite knows
  (`STAGE_ROLE`), one list, not two.
- D2. The drawer's default role follows the same map, kept in `chat.ts` beside
  the suggestions, with a test.
- D3. A Sounds tab: the music model, the effects model, each with its price, a
  reset to the catalogue's recommendation, and the reserve per cue.
- D4. Words are made honest, not features added: the Roles hints name every
  stage each role answers; the Pictures note says what is used today.
- D5. This computer gains "Where things are": the productions folder and the
  world library with their counts, read-only, with how to point elsewhere.
- D6. New films gains "Where it goes": the presets a new film starts with.
  `publish.read` reads them for a film that has not chosen; a film that chose
  keeps its choice. Unknown presets are dropped, never raised.
- D7. The settings file's path is shown in the pane, so the owner knows what a
  save writes.

## Tasks

- M1. The Director answers on every stage: `_context`, the drawer's default role,
  tests for both.
- M2. The pane: Sounds tab, price units, honest notes, where things are, where
  it goes, the file path; the settings and publish engine changes under them.
- M3. The acceptance record.

## Not changing

The settings file schema version. The keys tab. The Writer's publish prompt,
which was never reached. Thinking stays stored and unused, and the note says so.

## Acceptance

Posting a chat context with stage "publish" or "sound" is accepted. The drawer
on Publish opens on the Writer. The Sounds tab shows the two models with their
prices and saves a choice. "$0.0009 per run" and "$0.15 per clip" read as such.
A fresh film starts on the presets the settings name. Every suite green.

## Done, 6 Nov 2026

### Proved

- `tests/test_api_director_context.py`: every stage in `STAGE_ROLE` passes the
  chat route's context check; sound, publish and script reach the Writer; an
  unknown stage is still refused.
- `frontend/tests/chat.test.ts`: the drawer opens on the Writer on sound,
  publish and script, on the Editor on track and film, and every stage with
  suggestions has a role.
- The Sounds tab shows ACE-Step at "$0.0009 per run" and Mirelo at "$0.00025
  per second", saves a choice, shows "$0.15 per clip" for MiniMax, and resets to
  the catalogue's recommendation (browser test).
- New films shows the presets a film starts with; the last one cannot be taken
  away (browser test). `publish.read` starts an unchosen film on them, drops a
  preset the app does not know, falls back to YouTube, and leaves a film that
  chose alone (`tests/test_publish.py`).
- This computer shows the productions folder with its film count, the world
  library with its entry and series counts, and the settings file (browser and
  route tests). The catalogue route reports the folders.
- The Roles hints name every stage each role answers; the Pictures note says the
  video model and upscaler are used. Looked at in the real Studio on port 18990
  with the owner's own settings: 7 films, 0 library entries.
- Every suite green; the committed frontend build is current.

### Not proven

- A live Writer turn on the Publish stage. The route no longer refuses it; the
  model's answer is the owner's to read. No paid call was made.

## After the owner's look, 6 Nov 2026

- M4. What confused: ten "Stills for …" rows that all said the look's own model
  at the same price, because the catalogue lists one still model and nothing
  reads the per-look choice; a Narrator model under Roles that nothing reads
  either, since a voice carries its model; "Stored for when clips arrive" under
  a reserve that clips already use; an upscaler "None yet" that really means
  Real-ESRGAN. Now: Pictures names the one still model once (the per-look grid
  returns only when the catalogue lists a second), the Narrator left Roles and
  Voices says which model speaks the chosen voice at what price, the blank
  upscaler is named as the recommendation, and the clip reserve says what it is.
  `pictures.image_model_by_look` and `roles.narrator` stay in the file, unread.
- The library said "Final ready" where Publish said there was no current final:
  the library compared clocks and Publish compared hashes, and the renderer's
  revision had moved. `_final_state` now asks `exports.render_currency`, the
  same check Publish uses minus the movie's bytes, so the two cannot disagree.
  Every finished film today reads "Render the final again" for that reason.
- `library/` is ignored like `projects/`.
