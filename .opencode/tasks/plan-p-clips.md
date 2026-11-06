# Phase P: a clip from the model you choose, at the price it publishes

## Objective

Clicking a still offers one model, Kling 2.5 Turbo Standard, at a price that is
Settings' reserve rather than the model's. The owner wants the models people use,
each priced plainly, each asked in the shape its schema demands.

## What the code and the provider showed, 6 Nov 2026

- `clips.quote_clips` reads the model's public schema, takes the `duration` nearest
  five seconds, sends the film's width and height only when the schema accepts them
  with a first frame, validates, and reserves `pictures.reserve_usd_per_clip_second`
  times the duration: $0.50 for five seconds of any model. The purchase sends
  `inputs.frameImages` as one data URI and polls an async task.
- The catalogue lists one video model. `MakeClip.tsx` shows "Make a clip", then "Make a
  clip · up to $0.50 for 5 s", with no model, length, size or sound to choose.
- Runware, read from each model's schema today: thirteen image-to-video models across
  Kling, MiniMax, Google, ByteDance, Alibaba, Vidu, PixVerse and Lightricks. Each
  schema's `info["x-pricing"].rates` carries the price per second, by resolution and
  with or without the model's own audio where that costs more, or per clip (Vidu). The
  request shapes differ: `duration` is an enum (5/10, 4/6/8, 5/8), a range (1 to 8, 1.2
  to 12) or "auto"; size is a `width`/`height` pair from a list, a `resolution` word
  (720p, 1080p, 4K) when a frame is given, or forbidden with a frame; the model's own
  sound is `providerSettings.klingai.sound`, `.google.generateAudio`,
  `.bytedance.audio`, `.alibaba.audio` or top-level `settings.audio`; `negativePrompt`
  and `seed` exist on some; `frameImages` takes one or two frames. Every schema says
  `additionalProperties: false`. Seedance 1.5 Pro deactivates on 11 Nov 2026.

## Decisions

- D1. The catalogue lists the models in use: Kling 2.5 Turbo Standard and Pro, Kling
  2.6 Pro, MiniMax Hailuo 02, Google Veo 3.1 and 3.1 Fast, ByteDance Seedance 1.0 Pro,
  Alibaba Wan 2.5 Preview, PixVerse V5, Vidu Q2 Pro and Lightricks LTX-2.5 Pro, each
  with its lowest published rate as the catalogue price, the tiers in its note, the
  source and the read date. Seedance 1.5 Pro is not added.
- D2. The price is the model's, read when the quote is made. A quote matches the chosen
  resolution and sound against the schema's published rates: a rate per second times
  the duration, or a rate per clip once, floored at a cent. The quote records the rate
  it used, and the button says "$0.21 for 5 s at 720p, the published price". When no
  rate matches, the reserve is Settings' rate per second and the quote says so.
- D3. The request follows the schema, never a table of models. `duration` is the enum
  value or range bound nearest the wish, or "auto" is left to the model; size is sent
  as `resolution` when the schema offers it with a frame, as the film's width and
  height when it accepts them, else not at all; the model's own sound is sent only when
  the owner asked and the schema has a key for it, found by name under
  `providerSettings` or `settings`; `negativePrompt` and `seed` are sent only when the
  schema has them. What was sent is validated against the schema before any money
  moves, as today.
- D4. The owner chooses on the still. The panel offers the catalogue's live video
  models with their catalogue price, the lengths the chosen model's schema allows, its
  resolutions, and its own sound when it has one, with Settings' video model first.
  The Writer's motion suggestion stays; the motion prompt is shown and can be edited
  before a quote, since the words are what the model animates.
- D5. Two steps stay: the price, then the purchase. The second button carries the
  published rate and what was chosen, so nothing is bought that was not read.
- D6. The grid tells a clip from a still. The owner asked, on Cool Cat's s019: back on
  the Images grid a shot that plays its clip is recognisable as one, and plays there.

## Tasks

- P1. The catalogue rows; `clips.quote_clips` takes `seconds`, `resolution`, `audio`,
  prices from the schema's rates, shapes the request from the schema, and records the
  rate; the route and service pass the choices; tests with schemas of each shape.
- P2. The clip panel: model, length, resolution, sound, the motion prompt, the price
  with its basis, the purchase; a browser test.
- P3. The Images grid says which shots are clips: a shot whose clip is in use wears a
  clip mark with its length on its tile, and the tile plays the clip in place on hover
  or a click, so the owner sees the motion without opening the still. The record.

## Not changing

The journal and recovery. The reserve floor. The Player and the renderer's use of a
clip. Settings' video model stays the default.

## Acceptance

On a still, the owner picks Veo 3.1 Fast, 8 s, 1080p, no sound, reads "$0.80 for 8 s
at 1080p, the published price", and buys exactly that; a Vidu quote prices per clip; a
Kling 2.5 Standard quote sends no size; a Veo quote sends `resolution` and omits width
and height; an unmatched rate falls back to Settings' reserve and says so. Every suite
green. No live call in tests.

## Done, 6 Nov 2026

Commits on `film/phase-p-clips`, stacked on Phase O: P1 the engine, P2 and P3 the screen.

### Proved

- P1. Eleven video models in the catalogue with their lowest published rate, the tiers
  in the note, source and read date. `quote_clips` takes seconds, model, resolution, own
  sound and a prompt of the owner's own; follows the schema for the length (enum, range,
  "auto"), sends `resolution` when the schema names sizes with a frame and the film's own
  size when it takes one, says the own-sound switch wherever the schema has one, and
  prices from the published rates that fit (per second times the length, per clip once,
  a cent at least), falling back to Settings' reserve and saying so when none fits
  (`tests/test_clips.py`, schemas of each shape). `options_for` reads a model's choices
  from its schema; the routes offer the models and the options and take the choices.
- P2. On a still, the panel offers the catalogue's video models with their price,
  Settings' choice first; the chosen model's lengths, sizes and own-sound switch from
  its schema; the motion prompt, editable; "Price a clip", then "Make it · $0.80 for 8 s
  at 1080p, the published rate" or "up to $…, Settings' reserve". Looked at on Cool Cat's
  s019: Kling offers 5 s or 10 s and no size; Veo 3.1 Fast, read live, offers 4, 6, 7 and
  8 s, 720p, 1080p and 4K, and its own sound. No quote was made on the owner's film.
- P3. On the Images grid a shot that plays its clip wears a gold edge and "▶ Clip ·
  5.0 s", and the tile plays the clip in place on hover. Looked at on Cool Cat's s019.
- Every suite green; the committed frontend build is current.

### Not proven

- No clip was bought in this phase. The first clip from a model other than Kling 2.5
  Turbo Standard proves the request shape against the live provider: a Veo or Vidu
  request validated here against its public schema has not been answered by Runware.
  A grid tile's hover play was seen in the preview, not measured.

## After the owner's look, 6 Nov 2026

- P4. The panel read as a loose stack of controls, and a clip being made looked like
  nothing. Now it is a card: a header with what it does and the model's lowest rate
  as a pill, the model as a full-width menu with its note, length and size as
  segmented choices, sound as a switch with a sentence, the motion prompt, and a
  footer with the price and how long the provider's own example runs took (the
  median of `x-pricing.examples`, as `typical_seconds` on the options and the quote).
  The clip purchase runs as a job of its own kind, `clip`; the panel remembers which
  job makes which shot in this tab, shows a ring that fills over the usual time and
  stops short of full, says the minutes so far against the usual, says when it runs
  long and that a slow clip is collected from the journal, and the grid tile says
  "Making a clip…". Looked at on Cool Cat's s002. The ring itself has not been
  watched over a live purchase.
