---
version: 4
task: profile
role: writer
---
# W3.5 — Creative profile

Global image rules, the look and a place go into the prompt of every shot they touch,
so once stills exist, changing them makes those stills out of date, and each costs
money to remake. A change for one shot belongs in that shot's prompt.

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
- `references`: the owner sets these in Studio. Leave them out; yours are ignored and
  theirs are kept.

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

## Craft digest

Choose the motif now, and make sure the arc plants it in the first section,
transforms it in the middle and pays it off in the last chorus. Write the arc as a
colour script as well: one palette and one light per section, a change of colour
spent only where the song changes. When the song map is measured, record those
palettes in `sections`, one entry per section with its start and end in seconds,
`palette`, `light` and `lens`; a film with one look throughout leaves it out. Give
every recurring place enough description that shots of it can vary in scale. The
look holds the whole film, so per-section colour belongs in `sections`, not there.

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
