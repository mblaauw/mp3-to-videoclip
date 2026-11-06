# What the app should have and does not, 5 November 2026

A helicopter view over `main` at `78fbd26`. It starts from the app's purpose and asks
what a tool with that purpose must do, then checks each answer against the code.
Every "does not exist" below was checked by reading the routes, the models, the
tools and the prompts; where a partial exists it is named.

## The purpose, stated plainly

One person, on their own computer, turns a song or a script into a **finished short
film for release**: a music video, a promo, an advert, or a narrated episode. The
owner's taste is the gate at every stage, the money is journaled before it is spent,
and nothing is invented. The real films so far say what "release" means: YouTube
episodes (The Museum of Tomorrow 001), a venue promo and its advert (Cool Cat After
Dark), and the owner's own songs (Suno MP3s with their lyrics in the file).

So the chain the app must own is:

**intent → words → sound → pictures → motion → cut → finished film → audience → next film**

The app is strong from intent to cut. It is thin on sound, it stops at "finished film
on disk", and it starts every film from nothing. Those three are where the missing
features cluster.

## Missing, in order of how much the purpose needs it

### 1. Sound is half the film and has no stage

Today: narration takes through the journal, one bed file, ambience spans the owner
supplies, measured ducking, loudness to -14 LUFS, a source MP3 that is never changed.
There is no way to make a sound, only to mix sounds the owner brings. The Museum film
is 140 s of narration over silence; the record says so. The Critic cannot hear.

Should have:

- **A Sound stage** beside Images, with the same shape: a cue list derived from the
  script and the song map (score per section, ambience per place, a sting on the
  reveal, a signature at the end), each cue bought through the journal from a music or
  effects model, or brought as a file, with Keep and Redo like a still.
- **A score for story films** that follows the structure's beats, with the same
  "re-record a line and only later shots move" discipline the soundtrack already has.
- **An ear for the Critic.** The narration is already matched to the script by text;
  the Critic should also be told the mix (speech over music per line, silence longer
  than N seconds, a cue that cuts mid-word) so its notes cover what a viewer hears.

Why first: a viewer forgives a soft still before a silent minute, and the story film
is the kind the owner is making episodes of.

### 2. The film stops on disk; the audience is the point

Today: a final MP4, a delivery package (poster frame, contact sheet, chapters, SRT and
VTT), vertical and square versions. Nothing knows what platform the film is for.

Should have:

- **A Publish stage** that takes the brief's intent (audience, CTA, window) and
  produces what the upload form asks for: title variants, a description written only
  from the brief and script under the truth rules, chapter list in the platform's
  format, tags from the brand kit, a thumbnail with the title set in the film's own
  faces and grade, three candidates to choose from.
- **Platform presets** behind the versions that already exist: YouTube 1080p and 4K,
  Shorts and Reels at 9:16 with their safe areas and a loudness target each, a
  15 s and 6 s cut-down for adverts.
- **A release checklist** as a gate like the others: watched with sound, captions
  checked, thumbnail chosen, rights of every reference confirmed, budget settled.
- Upload itself can stay outside the app; a checklist and a folder per platform is
  enough for one person.

### 3. Every film starts from nothing; the owner makes series

Today: a creative profile, references, sheets, a narrator and a look live inside one
production. The record says stills for the advert were copied by hand from the
promo, scene references were imported with a direct call, and "reuse across a series"
is listed as not done. The Museum is "001".

Should have:

- **A world library** above productions: characters with their sheets and permission
  record, places with their plates, a narrator with its locked voice, looks, title
  packages and structures. A new film picks from it; a film can promote what it made
  into it. Hashes stay content-bound: the library holds bytes, the film binds them.
- **A series** as a first-class thing: a bible, an episode number, an opening and an
  end card that recur, a cast that carries, and the Writer's snapshot naming what
  earlier episodes established so it does not contradict them.
- **Derivatives from one production:** an advert cut from a promo, a lyric video
  from a music video, a teaser from an episode, sharing stills, takes and clips by
  reference rather than by file copy, and keeping the parent's approvals where the
  bytes are the same.

### 4. The owner cannot leave a note on the film

Today: thumbs with a note per artifact, a Critic that writes notes on Film, a decisions
log, a history with restore. The owner's review of a render is a flag
(`preview_watched`) and a hash.

Should have:

- **Timestamped notes on the Player**: press a key at 0:42, type "the door is wrong",
  and it lands on the shot, in the Editor's and Critic's snapshot, with Done and
  Dismiss. This is how every film review tool works and it is the natural input for
  the next Editor turn.
- **Compare two finals** side by side or by toggle at the same frame, with the cut
  differences listed; the record shows v004 against v006 was judged by memory.
- **A watch-through gate** that is more than a flag: the Player records that every
  second was played with sound at least once before a final can be approved. The
  Museum record's "nobody has heard it" should be impossible to reach by accident.

### 5. The owner's taste never reaches the next film

Today: thumbs are bound to the artifact hash and prompt revision; Keep and Redo are
recorded on every still; the eval harness checks format, never quality, and no live
run is stored. The Writer reads a per-film creative profile and the same examples
every time.

Should have:

- **A maker profile** that the app writes from evidence: which looks the owner keeps,
  which it redoes and why, how many shots it cuts per minute, which transitions it
  removes, what the notes say most. It is appended to the Writer's and Editor's
  prompts as "what this owner keeps", never as rules the model invents.
- **Quality evals from verdicts:** the harness already stores a prompt hash with
  every rating. Report, per prompt version, the keep rate of stills and the fraction
  of Editor cuts the owner changed. That turns thumbs into the measurement the policy
  document says is missing.

### 6. The owner's own pictures and footage

Today: `upload` is a shot kind for a still; a product may carry an uploaded asset; a
character may have an uploaded reference; the owner's own recording is a take. There
is no way to put the owner's own video into a shot, and no way to bring a folder of
photographs in as candidates.

Should have:

- **Own clips as shots**: a dropped MP4 or MOV becomes a clip version of a shot,
  probed, trimmed in the cut, held after its end like a bought clip; with the owner's
  footage the music video can at last contain the artist.
- **A photo set as a round**: drop twenty photographs on a storyboard section and
  pick from them in the lightbox as though they were a generated round, at $0.
- **A performer in the film.** The honest-medium rule says no acting and no lip-sync,
  which is right for generated stills. It is a ceiling the owner should choose, not
  inherit: a lip-synced clip of a cast character on a sung line, bought through the
  journal, is the one feature that makes a music video read as one.

### 7. A film's cost before it starts

Today: a cap per film, a price on every batch before it is bought, a first draft under
a ceiling. Model turns are counted, not priced. Nothing says what the whole film will
cost before the first still.

Should have:

- **An estimate at intake**: from kind, length and the catalogue, the expected cost
  of stills with one redo round, takes, clips if chosen, upscales and about N
  Director turns, as a range, before the cap is set. Update it as the storyboard
  takes shape.
- **The Director under the journal**: a verified price per default text model, an
  estimated reservation per turn admitted against the same cap, and tokens shown
  beside every answer meanwhile.

### 8. A way out to a real editor

Today: the cut is `work/edit.json`, the renderer is the only consumer. A promo or an
advert made for a client sometimes needs a finishing pass in Resolve or Premiere, or
a sound designer's session.

Should have:

- **An OpenTimelineIO or FCPXML export** of the cut with every still, clip, take,
  bed and title as media, so a human can finish or re-grade without rebuilding; and
  **stems** (narration, bed, ambience, source) as separate WAVs beside the final.
- A corresponding import is not needed; the app is the author.

### 9. The fast path should reach every kind

Today: one-click first draft from concept to preview under a budget ceiling, music
video, promo and advert only; it refuses a story film. Every stage otherwise needs a
click, by design.

Should have: the same draft for a story film (script, casting with the $0 read-rate
estimate, a board, a preview with estimated timing), since the episode is the kind
most likely to be made in numbers.

### 10. Smaller things a release tool is expected to have

- **Captions in a second language**, translated under the truth rules and reviewed,
  since one of the films on disk is Dutch and the audience is not only Dutch.
- **A sample production on first run** with no keys, so a new user sees a film
  before buying anything; the screenshot fixtures already exist.
- **Project export and import** as one archive, so a production can move to another
  machine or be handed over; the metadata snapshot is a backup, not a transfer.
- **An audio-only release** of the mixed narration (a podcast cut of an episode) from
  the same soundtrack, at no cost.

## What the app should keep refusing

Some gaps are deliberate and should stay so: no polling, no second state store, no
auto-resolution of an unknown cost, no invented fact, no paid call without a shown
price, no approval that survives changed bytes, no cloud dependency for rendering.
Every feature above fits inside those rules.

## If only three

1. A Sound stage with a score for story films.
2. A world library and series, with derivatives by reference.
3. A Publish stage with thumbnails, metadata and a watched-with-sound gate.
