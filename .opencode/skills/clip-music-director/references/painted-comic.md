# Painted comic realism — reusable style recipes

> **Heritage, superseded for new productions (2026-10-17).** The current default
> is `photographic-painted-v2` in `default-style.md` — a photographic **painted**
> hybrid roughly 70/30 Alex Ross / Gabriele Dell'Otto; the earlier
> `photoreal-painted-v1` is legacy for recorded productions. Recipe C and the other
> "not a photograph / not CG" phrasings here are kept for legacy productions and
> explicit user choice; they do not describe the default. See
> `legacy-recipes.md`.

Original project guidance for artist-inspired demo productions in the painted
comic tradition of Alex Ross and Gabriele Dell'Otto. These are style traits, not
imitation of a living artist's signature works; say "in the spirit of" in the
brief and note the production is an unaffiliated homage. Copy the chosen recipe
into `brief.creative.look` and keep `image_rules` free of contradictory text.

## What the style is

- Fully painted illustration: figures read as **painted**, never as a photograph
  and never as 3D CGI. Photoreal *modelling* with visible brush handling.
- Sculptural anatomy: believable weight, joints, muscle flow and drapery.
- Theatrical lighting: strong key/rim separation, deep shadow shapes, glow used
  as an event rather than as a filter.
- Deliberate composition: monumental staging, strong silhouette, one clear
  focal hierarchy; faces and hands carry the emotion.
- Print texture: subtle halftone/paper grain, ink-like contours that thin and
  break rather than uniform hard outlines.

## Recipe A — Ross-leaning (monumental, clean anatomy)

`look`: "Fully painted comic realism in the spirit of classic painted superhero
comics: photoreal painted figures with heroic, anatomically correct anatomy,
sculptural modelling, theatrical chiaroscuro with strong rim light, deep
saturated jewel tones against near-black shadow, subtle halftone print texture,
monumental splash-page staging; a hand-painted comic illustration, not a
photograph."

## Recipe B — Dell'Otto-leaning (chiaroscuro, expressive paint)

`look`: "Expressive painted comic illustration in the spirit of dark painted
European comic art: heavy chiaroscuro, deep blacks with selective lost edges,
bold painterly brushwork and textured strokes, restrained saturated highlights
against desaturated shadow, dramatic low-key lighting, figures emerging from
darkness, cinematic graphic-novel staging; painted illustration, not a
photograph and not 3D CGI."

## Recipe C — Hybrid (recommended default for character-led films)

`look`: "Painted comic realism blending monumental structural anatomy with
expressive brushwork: believable realised fur, fabric and metal; dramatic
painted lighting with clear key and rim separation; deep near-black shadows and
a restrained three-colour palette with one saturated accent; faint halftone
print grain; graphic-novel framing with strong silhouettes; clearly a
hand-painted illustration, not a photograph and not CG."

Pair any recipe with:

`image_rules`: ["No text, lettering, speech bubbles or symbols inside generated
panels; all screen text is composited locally by the production", "Single
coherent frame: no collage, split screen, border or panel gutter", "No
watermarks, signatures, UI chrome or camera metadata", "Hands, paws, feet and
 limbs anatomically correct with separated digits"].

## Keep the look neutral, put occupancy in the shot

`creative.look` and scene descriptions must describe **what a place is**, never
what is happening in it. The Signal v2 shipped a "floor" scene containing
"dense crowd ... DJ booth ringed by the crowd"; every prompt that needed an
empty hall inherited the crowd and the model obeyed the scene, not the shot.
Write scenes as empty architecture ("raw concrete, steel columns and trusses,
laser rigs, drifting smoke") and state occupancy, people and action in the shot
prompt. Inspect `clip prompts PROJECT --shots ...` before spending.

## Character canon for nonhuman protagonists

Write the roster once, freeze it, and reuse the exact sentence everywhere:

- Species, build and silhouette: "bipedal anthropomorphic cat, lean athletic
  build, walks upright on two legs, one tail with a pale tip".
- Face: muzzle shape, ear shape, fur pattern with its exact asymmetry.
- Signature accessory and wardrobe, named and colour-locked.
- Personality as visible behaviour: posture, gaze, what the character does with
  its hands/paws when not acting.
- Forbidden drifts: "do not add extra tails, do not turn the character into a
  mascot/cartoon animal, keep the same sunglasses shape".

Generate a small anchor pack first (full-body, three-quarter portrait, close-up,
back view), review it, and bind those bytes as the character's references on
**every** shot the character appears in. A design that changes mid-batch
invalidates the whole set.

## Model routing

- Prefer a model with strong multi-reference identity and instruction
  adherence for character-led sets; verify `status: live`, the reference limit
  and the **supported native sizes** against the live schema before quoting.
- Declare `project.native_size` to a pair that model accepts (for example
  1376×768 or 2752×1536); a hardcoded 1536×864 quietly excludes several of the
  best current models.
- Price the whole scope before the batch and re-check after a comparison run;
  model choice is quote-bound and must not drift mid-production.

## Failure modes seen in production

| Failure | Fix |
|---|---|
| Fake brand lettering on gear, numbers on meters, glyphs on walls | No-text rule in `creative.look`; blank/abstract surface clause in the shot; local compositing for every word |
| "Empty" locations filled with a crowd | Neutral scene text + explicit "not a single person in the frame" in the shot |
| Generic male figure standing in for the lead | Bind the identity reference on every shot where the lead appears |
| Repeated booth/wide compositions | Plan a coverage matrix (establishing/medium/close-up/detail/pairs) and reject duplicates at review |
| Floating boots, fused hands, extra limbs | Hand/foot hygiene clause + reject at review; after two failures restage or reuse an accepted crop |
| SFX burst text clipped by its own star outline | Size the shape from measured text bounds; verify a rendered frame before export |
| Retry loops | Two failures at the same requirement = change shot, staging or model |
