---
name: clip-art-direction
description: Stage 4 of an MP3-to-videoclip production. Set one coherent painted world: medium, palette, light and texture in creative.look, and non-contradictory image_rules that keep text out of generated pixels. Use for look, wardrobe/scene consistency and style overrides. Never restates model or settings constants.
---

# Stage 4 — Art direction

**Job:** one coherent physical world and a neutral, honest medium description.
**Position:** develop alongside story, before brief approval and shot prompts. Links:
`../clip-music-director/SKILL.md`,
`../clip-music-director/references/default-style.md` (canonical look/model),
`../clip-music-director/references/production-gates.md`. Code:
`models.py` (`CreativeProfile.look`, `image_rules`), `preflight.py`.

## Inputs

- Draft brief + selected treatment/arc; the user's selected/rejected style intent.
- Any explicit style override (artist-inspired, franchise-inspired, photographic).
- The user-approved style benchmark in `default-style.md`, used for rendering
  comparison only, not its rooftop/character/weather/lettering/cover layout.

## Do

1. Put **only** neutral medium/palette/light/texture in `creative.look` and
   verifiable rules in `image_rules`. Do not describe people, action or occupancy
   here — scene text says *what a place is*, never what is happening in it (the
   Signal v2 "dense crowd" leak followed every later shot).
2. Keep `image_rules` free of contradictions: no leftover "AI comic lettering is
   welcome"-type text fighting the current no-text rule. Every word on screen is
   composited locally; generated panels carry no text, lettering, speech bubbles,
   numbers or symbols.
3. Name the medium honestly. The default `photographic-painted-v2` is a
   **photographic-painted** hybrid: a fully painted illustration driven toward
   photographic craft, roughly 70/30 Alex Ross / Gabriele Dell'Otto (monumental
   clean anatomy and believable light; deep blacks, hard highlights and gritty
   paint). Keep the artist names explicit and the style language prominent; state
   the blend textually and do not parametrise it. It is not a flat comic or
   cel-shaded look. `photoreal-painted-v1` is legacy for recorded productions.
4. Separate **universal** from **per-shot**: keep medium/palette/light/texture in
   `creative.look`; put focal length, depth of field, lens character, materials,
   weather and time of day in each shot's `image_prompt` (no separate lens
    schema).
   For the default preset, preserve `profiles.DEFAULT_STYLE` verbatim first in
   `creative.look`; append film-specific palette/light after a blank line. Do not
   summarize, weaken or replace it to accommodate a new story or references.
5. Record any override and its authority before quoting. An override replaces
   the default **for that production** only.

## Outputs and exit gate

- Updated `brief.creative.look` / `image_rules` (and scenes written as neutral
  architecture), reviewed against the approved story.
- **Exit gate:** no contradictory rules; the look is neutral; the world is one
  coherent place with varied rooms/scale/light rather than a new city per change.

## Boundaries

- Do **not** duplicate the model, AIR, native sizes, settings or correction count
  in this stage. They live in `default-style.md` / `profiles.py`; link, don't copy.
- One successful manual style (e.g. the retained rooftop/night/rain/50 mm example
  in `../clip-music-director/references/legacy-recipes.md`) is that production's
  choice and must not be forced onto an unrelated film.
- No paid work happens in this stage. Loading a recipe is not permission to spend
  or to change an approved model.
