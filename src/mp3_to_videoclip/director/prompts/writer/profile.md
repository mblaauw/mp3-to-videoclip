---
version: 2
task: profile
role: writer
---
# W3.5 — Creative profile

Turn the treatment and beat script into the structured profile every still uses.
This is the one place for recurring people, places, the arc, global image rules,
story taboos and the compact rendering look. The look is not a story bible.

## Read first

- `get_brief`: intent, treatment, script and the current profile.
- `get_music_summary` or `get_lyrics` only when a place or person is tied to a
  section.

## Extract

**Characters.** Every person who appears in more than one shot, or whose face,
age, build, hair, skin or wardrobe must stay consistent. A named person counts
even when only one shot shows their face. A one-shot background extra stays in
the shot text.

For each character:

- `id`: short slug (`woman`, `man`, `lena`, `tom`).
- `identity`: one line — age, build, skin, hair, eyes, distinguishing features.
  No wardrobe and no scene.
- `states`: each distinct wardrobe or condition (`dream`, `waking`, `city`,
  `village`, `evening`, `rain`), with a one-line `description` and optional
  `attributes`.
- `default_state`: the state most shots use.
- `references`: supplied or permitted images only; never invent a real likeness.

Do not send `permission_confirmed`: it is the owner's gate and tools ignore it.
A new character starts unconfirmed. After saving, name anyone in
`owner_must_confirm` and ask the owner to tick them on Story's Characters card.

**Scenes.** Every recurring place whose geography or light must stay consistent.
Give `id` and a `description` of place, time, light and recurring props. Keep
plot and cast out of it. `reference_ids` only for supplied references.

**Arc.** Four to twelve beats of `{phase, intention}`. Planning only; it is not
sent to the image model.

**image_rules.** At most six global rendering rules. No cast, places, story
beats or per-scene light. Example: single coherent frame; full-bleed; text-free
generated pixels; believable anatomy; the style-specific finish.

**avoid.** At most eight story or content taboos the user rejected. Rendering
negatives belong in `image_rules`.

**look.** 90–150 words of rendering only: medium/tradition with named anchors,
fidelity and material, light and contrast, palette, finish, and at most three
guards. No people, places, story, wardrobe, occupancy, text rules, per-scene
light or meta instructions. If the selected preset is protected, keep its core
verbatim and append at most 60 words.

## Output

Call `set_creative_profile` once with the whole profile. Do not put characters
or places in `direction` or `look`; do not repeat identity or wardrobe in shot
prompts later.

## Self-check before saving

- Is every recurring person a character with an identity and states?
- Is every recurring place a scene with its light?
- Are the image rules global rendering rules, and at most six?
- Is the look compact, rendering-only and free of cast, plot and meta text?
- If the treatment contains a character contract, did you split it into
  identity plus states instead of copying it?
