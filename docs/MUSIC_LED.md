# Music-led films, DJ mixes and integrated identity

Use the original project skill `clip-music-director` alongside the existing
Runware execution/model/prompt recipes. It does not grant upload/spending or
creative approval. The pinned upstream recipes are not modified.

## Music is evidence, not a lyric checklist

```sh
uv run clip init projects/example --slug example --mp3 /path/to/mix.mp3 --music-mode music-led
uv run clip analyze projects/example
uv run clip quote-music projects/example --reserve 0.05
# Only with the user's exact upload/model/spending authority:
uv run clip authorize projects/example --quote QUOTE_ID --cap APPROVED_USD --note 'User decision'
uv run clip listen projects/example --quote QUOTE_ID
# If pending, recover the returned task; never repeat a submission blindly:
uv run clip recover projects/example --task TASK_UUID
uv run clip music-map projects/example
```

Local analysis preserves the old beat/energy/section outputs and adds half-second
level, bass-share, brightness/centroid and onset-density measurements; 8 s summaries,
24 s pulse candidates with half/double ambiguity, and unreviewed change candidates.
Relative loudness is not emotional energy or tension. Do not infer genre, meter,
key, instrument identity or exact downbeats from these values.

The structured Runware listening pass is audio-blind (no supplied style/lyric
block in its prompt). It describes approximate passages, groove, texture, bass,
transitions, subjective energy/tension, uncertainty and intelligible hook drafts.
Actual cost/raw/usage are journaled before parsing. The model's confidence is not
a calibration guarantee; it is still an unreviewed interpretation. Invalid results
stay billed/evidenced and never trigger an automatic second request.

music-map.json/md combine measurements with those interpretations, retaining
their separate provenance. Nearby measured changes are suggestions, not automatic
replacements for the model's times. The embedded draft_event_map is **estimated**,
not automatically promoted to work/events.json or approved. Keep the user's
original style/lyrics separately as intended context; reconcile disagreements by
listening rather than rewriting the evidence to match the prompt.

`music-led` briefs depend on reviewed analysis/events and, when present, the
reviewed listening artifact—not mandatory lyric transcription. Sparse hooks can
be optional accents. Before treatment/storyboard lock, review the map with the
user, correct timings/interpretation, then record actual analysis/listening/events
decisions. Do not relabel approximate boundaries as manual without checking them.

## Brand inside the music

**New films:** the mandatory 25-second opening / final 40-second credit package
uses `work/graphics-spec.json` and the shared joint-production identity. See
[STILL_FILM_WORKFLOW.md](STILL_FILM_WORKFLOW.md). The optional `brand.json` below
is a separate legacy overlay, not permission to omit that signature or stack two
unreviewed identities. Required signature compositing currently supports 16:9;
portrait plans must be resolved before brief approval or spending.

The optional project-root brand.json is a versioned local BrandPackage (see
`clip schema brand`): open-frame, cutline or monogram; optional approved name,
track title, colours and 5–10 s duration. Blank name means **no approved artist
name**, not permission to infer one. Character/brand images are separate scopes.

```json
{"id":"my-approved-identity","version":1,"mark":"open-frame","name":"",
 "title":"Working Film Title","monogram":"","duration_seconds":8,
 "foreground":"#F4F1E8","accent":"#D8FF3E","safe_margin":0.08}
```

Drawn from local vector-like shapes/typesetting, never embedded as AI lettering.
It fades over the **first song seconds** after the camera transforms, scaled to
landscape or portrait safe zones. It neither adds pre-roll nor delays/trims the
source audio. Package/version/renderer hash enters brief and preview review;
changing it requires re-review, not image regeneration. A present package needs
the user's `brand` approval before brief approval. It appears in the actual timed
preview and final render. Absent package preserves existing brandless projects.

Brand drafts are not finished/approved identities. Review mark, type, colours,
legibility, artist wording and integration in the real opening before reuse.
Do not claim a static plate/fade implements an elaborate cinematic ident; its
surrounding shot sequence still needs to be directed and reviewed.

## Professional still-based editing

Use a coherent protagonist and physical world, with purposeful establishing,
medium, expression, detail and relationship frames. Time rhythm changes to the
actual map, not every beat and not the provided scene list. A dramatic musical
change can motivate a sustained image as well as a cut. Do not default to strobe,
random wipes or a zoom on every shot.

A shot may reuse another source shot's selected image with `asset_shot_id`:

```json
{"id":"detail-reprise","asset_shot_id":"s001","start_frame":720,
 "duration_frames":24,"purpose":"Return to the same image as an accent",
 "image_prompt":"Reuse s001; no new image generation","camera":"hold",
 "camera_path":{"start":{"zoom":1.4,"x":0.8,"y":0.4},
                "end":{"zoom":1.4,"x":0.8,"y":0.4},"easing":"linear"}}
```

The owner must be another existing, non-reused shot. No self-reference, missing
targets, chains or cycles. Reused shots retain their own stable edit IDs, music
allocation, crop and transitions. Their image-level instructions do not generate
a different picture: inspect the source's compiled prompt/selected bytes.
Quotes generate only source shots; explicit proof IDs select source images.
Use native detail conservatively; digital crops do not invent resolution.

The existing full-frame timeline, original-audio, immutable-version and proof /
preview / full-still gates remain. The editor is still a photographic cut-and-crop
system: no person, smoke, curtain, liquid or light inside an image is animated.
Real generated motion, image alternatives and upscales need separate scope and
allowance; an audio-analysis budget never authorizes them.

## Deliberate refinement and model limits

`quote-music PROJECT --refine` creates a **new quote**, not a retry. It is allowed
only for an existing unreviewed draft, binds that draft's exact hash, reuses the
completed upload, and archives the old draft before a valid replacement. A missing,
edited or approved target blocks submission/replacement. It requests at most 20 s
passages using measured changes as listening checkpoints, not verified sections.
Each pass needs its own exact authorization inside the user's remaining total
scope; no automatic loop or silent paid/model upgrade is implemented.

The live selected schema controls thinking levels and output mode. JSON-capable
models receive a schema; TEXT-only models receive an explicit JSON contract and
are validated locally, with no provider-side guarantee. One enclosing Markdown
fence may be removed as a transparent format normalization, with raw evidence
unchanged. This never fixes invented labels, overlapping/gapped intervals or
passages that exceed the quoted granularity.

The first DJ-track runs demonstrated the limitation: both Flash Lite and a
separately approved Pro pass produced passages too broad for detailed editing.
Confident language is not reliable musical direction. Retain rejected priced
results, show review flags and the measured sound chart, and obtain actual
listening/timing corrections before locking a storyboard. Do not keep spending
until a model produces the desired narrative.

## Maha Kala / VjDj69 identity and the required film signature

The user identified the collaboration as Maha Kala productions with VjDj69 as
artistic director and co-producer, while explicitly noting that music, images and
art direction may be by either collaborator on different productions. Ask for
this production's exact role assignments every time; do not infer them from the
MP3 name or the usual collaboration pattern.

Every **new film** carries, inside the original music:

- a **25-second opening overlay** and a **final 40-second credit package**;
- the shared **MAHA KALA × VJDJ69** identity and the joint-production line
  `A JOINT MAHA KALA & VJDJ69 PRODUCTION`, with the film title kept separate;
- this production's **actual** credit roles (music, visual/image creation, art
  direction, artistic direction, producer/co-producer), supplied once at intake,
  combined, shared or omitted only as the user states.

Never copy the randomized demo credits, never fabricate a contribution, and never
omit them because the work was delegated. Supply the film title and slug once,
early, at intake; a film's title/mark is film-specific, not always the cat/signal
mark. Reuse the existing `graphics.py` lockup/credit visual family — do not build
a second brand engine. All text is locally composited and generated panels carry
no lettering; the only exception is the explicitly authorized rooftop style
control in
`../.opencode/skills/clip-music-director/references/default-style.md`.

If the track is too short to hold the 25 s intro and 40 s credit package inside
the music, **stop and ask for an alternate plan**. No added audio/pre-roll, music
delay, stretch or appended credit tail is ever authorized.

History: an earlier proposal asked for a closing sequence of at most 20 seconds;
that is superseded by the mandatory 40-second package. The working title "The
Signal" (and the isolated 'The Singal' typo) belongs to that earlier production;
each new film supplies its own title.
