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
