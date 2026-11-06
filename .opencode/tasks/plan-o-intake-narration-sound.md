# Phase O: fewer decisions at intake, the voice where the words are, sound on the cut

A design assessment of three screens, read against the code on 6 Nov 2026, with the
phase that would follow. Nothing here is built; the decisions are proposals for the
owner to take or change.

## What the code showed

### The New film pane (`NewProduction.tsx`, `newFilm/model.ts`, `formats.py`)

- A format is a row that fills the form: kind, length, shape, titles, destinations,
  look and, for a story film, the structure. The film keeps the answers, never the
  format's id. That is the right contract: a format is a starting point, not a type.
- The pane then shows every one of those answers again as a control under "Details",
  with "As One place across time" or "Adjusted from" beside the heading. Counted on the
  story film in the screenshot: a format grid, a music bed drop zone, a title, a
  narrator, an invented-world switch, six length chips, two shapes, a structure, a
  titles menu, a look menu with swatch, destination chips, a budget, and a series menu
  when one exists. Fourteen controls, of which the format already answered seven.
- The right column is a second rendering of the same facts (structure, look, where it
  goes, budget, the beats as bands) plus the one thing the form still needs ("Still
  needed: a title"). It is the better of the two: it reads as the film.
- The Structure menu on a story film offers the four story templates, which are exactly
  the four format cards above it. On the other kinds it offers the Writer's structures
  ("Let the Writer propose three") that Story's Concept room already offers as concepts.
- The Look menu changes `style_preset` and the look's own model at creation. Story's
  World part has a Look card that changes the preset later; a film keeps the image model
  it was made with, which today is the same for every look.
- The Narrator menu lists the catalogue's voices with "(Settings' choice)" and says to
  hear it on Script. No voice can be heard here. The provider and model are not shown.
- The music bed drop zone comes before the title. Since Phase J a bed is also a cue the
  Sound stage can make or take as a file.

### Narration on Story and Script

- The narrator's persona is part of the Writer's creative profile (Cast & places). The
  voice is chosen at intake, or on Script in a bare menu of voice ids with no provider,
  model or price, beside "Hear the first line" (a paid take of line 1 through the
  journal), "Record the lines" and "Hear a draft".
- A film locks its voice id (`narration.lock_voice`). It does not lock the provider or
  the model: a MiniMax voice carries its model, and an ElevenLabs voice takes
  `voices.elevenlabs_model` from Settings at quote time. A later Settings change would
  record the next line with another model.
- A free sample exists only where the provider publishes one: ElevenLabs voices have
  `preview_url`; the two MiniMax voices in the static catalogue have none, so "Play
  sample" in Settings says so. A paid sample of a short line costs under a cent on
  either provider.
- The story outline on Story (the passages) shows where narration falls, and the Script
  stage shows each line with its estimate or take. Neither says what the whole script
  would cost to record, though the quote can: characters times the rate.

### The Sound stage (`stages/Sound.tsx`, `sound.py`)

- A cue is a kind (music, ambience, effect), a prompt, a start and an end anchored to a
  line on a story film or to a frame, a gain, a duck under speech, a loop flag, and its
  versions. A ruler shows the lines as marks and the cues as bands; a cue's row always
  shows its six fields; the Writer can suggest a list; the Critic's report measures the
  mix.
- An effect "on a moment" has no moment to point at except a line or a typed second.
  The storyboard's cuts, the structure's beats and the song's beats are not anchors. A
  sound that recurs (a clock, steps, a breath every few seconds) has no way to be said
  except as many cues, each bought.
- The model comes from Settings per kind. The catalogue lists one effects model
  (Mirelo, priced per second) and two music models (ACE-Step per run, MiniMax Music per
  clip). A chooser for effects would offer one thing.
- The ruler is not the spine: it has no shots, no playhead, and does not play.
- No cue has ever been bought; the live request shape is unproven.

## Decisions (proposed)

- **D1 The pane asks only what the format cannot know.** The left column keeps the
  format grid and what is the film's own: the file, the title (first, since it is the
  one thing always still needed), the budget, and for a story film the invented-world
  switch. Everything a format answers moves to the right column as a fact a click can
  change: length, shape, titles, look, where it goes, structure. Length and shape stay
  one click away because they are the facts an owner most often changes; the rest open
  in place. "Adjusted from" stays beside the preview's title.
- **D2 Structure is the format on a story film.** The Structure control leaves the
  pane. A story film's structure is the card; the preview shows its beats as it does
  now. Another kind's structure is a seed for Story's first concept: the preview says
  "First concept: Mood film" and the Concept room, which already offers three, is where
  that is chosen.
- **D3 The look is shown, not asked.** The format's look stays as a swatch and a
  sentence in the preview, with "Change on Story" beside it. Story's Look card is where
  the look is chosen, next to the cast and places it must suit. The intake still writes
  the format's look, so a film starts as its format says.
- **D4 The narrator leaves the pane.** A story film starts on Settings' voice, and the
  preview says so. The voice is chosen on Story, where the words are (D5). The music
  bed drop zone moves below the title as one line, "Add a music bed, optional", since
  the Sound stage can also make or take one.
- **D5 A Narration card on Story.** On the World part, above Cast & places: the
  narrator's persona from the profile; the provider, the voice and the model it speaks
  with, grouped by provider in one menu, each with its price per 1,000 characters; the
  script's cost to record at that rate (characters times rate, the same arithmetic the
  quote makes); where the narration falls, per beat, as the outline already shows it;
  and "Hear it": the provider's free preview where one exists, otherwise "Hear line 1 ·
  $0.01", the existing paid first take through the journal with its price on the
  button. The Script stage's voice menu becomes a link to this card.
- **D6 A film keeps its voice, provider and model.** `lock_voice` records the provider
  and the model beside the voice id; a quote uses the film's model, not Settings', and a
  take says which model made it. Changing the voice on the card re-locks all three.
  This is the same rule as the image model and the presets: a film keeps what it was
  made with.
- **D7 Sound anchors at the cut, the beat and the second.** A cue's start or end may
  name `{"shot": id}` (the first frame of that shot in the current cut) or `{"beat":
  id}` on a story film, beside the line and the frame it has today. The resolver is
  `timeline.py`'s, never arithmetic in the stage. An effect added "on this shot"
  defaults to the model's shortest length, not the film's end.
- **D8 One sound, many places.** A cue may carry `places`: a list of anchors, or `every`
  seconds with an optional `jitter`, between its start and end. One bought file is
  placed at each; the mix layer repeats it. The report counts placements, and a cue's
  price is still one purchase.
- **D9 The ruler becomes the spine.** The stage's ruler shows the shots as tiles, the
  lines, the beats and the cue bands over one timeline with the Player's playhead, and
  plays the current mix. A click on the spine adds an effect at that second or on that
  shot. A cue's row is a summary line (kind, when, gain, what plays) that opens to its
  fields.
- **D10 A chooser only where there is a choice.** The Make button names the model as it
  does. A music cue offers a menu only because the catalogue lists two music models; an
  effect offers none while Mirelo is the one effects model. The menu writes the cue's
  `model`, and the quote reads it before Settings.

## Tasks

- O1. The pane: the facts column with in-place changes, the structure and look as
  facts, the narrator and the bed demoted, the title first. Formats unchanged.
- O2. The Narration card: the locked voice, provider and model (`narration.json`,
  `lock_voice`, the quote), the price per voice, the script's cost, the free preview or
  the priced first line, the Script menu as a link.
- O3. Sound anchors and places: the model and `timeline.py` resolution, the mix layer's
  repeats, the report's placements, tests with real WAVs.
- O4. The Sound spine: tiles, playhead, click to add, collapsed cue rows, the music
  model menu.
- O5. The record, and the first live cue and first live take as the proving step, each
  under five cents and each on the owner's authorization.

## Not changing

The formats and what a film keeps. The journal and its reserves. The Writer's cue
suggestions and the Critic's report. The settings schema version.

## Acceptance

A new story film takes a format, a file, a title and a budget and starts; every other
fact is visible and changeable in the preview before Create. The Narration card names
the provider, the voice and the model with their price, says what the script costs to
record, plays a free preview or prices the first line, and a film records every line
with the model it locked. A cue can sit on a shot's cut or a beat, repeat every few
seconds from one purchase, and be heard in place on the spine; an effect offers no model
menu while the catalogue lists one. Every suite green.

## Done, 6 Nov 2026

Four commits on `film/phase-o-intake-narration-sound`, O1 to O4 as planned; O5's live
proving step is not part of this branch.

### Proved

- O1. The New film pane: a story film takes a title and a budget, the song or an optional
  bed, and starts; length, shape, titles, look and where it goes are facts in the preview
  with their controls, the structure is the card's and the narrator is Settings' voice.
  "Adjusted from" stays by the preview's name. Browser tests: the New film suite and the
  story film's creation; looked at on both a music video and a story film.
- O2. `lock_voice` keeps the provider and the model beside the voice; a quote records with
  what the film locked, however Settings change (`tests/test_narration.py`). The Narration
  card names the voice, its model and the price, prices the script at the catalogue rate,
  lists where the lines fall per beat, plays the provider's free preview or prices the
  first line through the journal, and changes the voice; the Script stage links to it
  (browser test on a pasted script; looked at on the Museum film: 23 lines, about $0.12).
- O3. A cue on a shot's cut follows the cut; one on a beat spans its lines; one sound is
  placed every so many seconds with a fixed jitter, or at anchors, bought once and heard
  at each place with nothing between; the receipt counts the placements; a placed cue
  that lands nowhere is reported; a cue's own model is checked against the catalogue and
  cues of different models are quoted apart; a placed sound is quoted as long as its gap
  (`tests/test_sound.py`, real WAVs). The Writer's tool says the new anchors.
- O4. The Sound stage's spine shows the shots with their stills, the beats, the lines, the
  cue bands and each placement, with the Player's playhead; a click seeks, a shot click
  picks its cut and offers an effect there; a cue row folds to one line and opens to its
  fields, with Time, Shot's cut, Line and Beat anchors, places, and a music model menu
  only while the catalogue lists more than one. Browser tests: a silent cue's price still
  needs a key; a placed cue shows its places and a click offers an effect. Looked at on
  the Museum film.
- Every suite green; the committed frontend build is current.

### Not proven

- No cue has been bought and no ElevenLabs take has been made: the first of each, under
  five cents, needs the owner's authorization in the Studio. Whether a placed effect reads
  as one at the cut is the owner's ear to judge on a real film.

## Found on the owner's film, 6 Nov 2026

- Every effect the Writer placed on Cool Cat had its end on its start, a moment, and
  a moment spanned nothing, so the five bought effects were silent and the owner heard
  no cue at all under the song. A cue whose end is on its start now plays its sound
  whole from there, and the report names a muted moment instead of calling it empty.
- "Approve this cut" on Film failed, because the full set signs off on top of the
  style check and this film's style check had gone stale on 31 October. The Film step
  now sends the owner to Images to approve the style check first instead of offering
  a button that can only be refused.
- Images and Film sent the owner to each other: the shell counted Images as done when
  every picture was kept and only the cut had moved, without looking at the style
  check, which a used clip had retired, while Film refused the cut's sign-off until the
  style check was current. A stale style check no longer counts as the cut moving, so
  Images offers "Approve style check" and Film follows. On Cool Cat the style check and
  the full set were then approved on the owner's instruction, and the final rendered.
