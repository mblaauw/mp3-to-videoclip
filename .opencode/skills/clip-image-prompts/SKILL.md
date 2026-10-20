---
name: clip-image-prompts
description: Stage 5 of an MP3-to-videoclip production. Write each shot's prompt — subject, action, composition, framing and must_show — with occupancy and the no-text rule in the shot, then inspect the compiled prompt. Use before quoting or generating. Never bakes text into generated pixels or restates model settings.
---

# Stage 5 — Image prompts

**Job:** turn each approved shot into a prompt that gives the model exactly what
to draw. **Position:** during storyboard development; inspect before storyboard
approval and before the quote. Links:
`../clip-music-director/SKILL.md`,
`../clip-music-director/references/default-style.md`,
`../clip-music-director/references/production-gates.md`. Code:
`preflight.py` (`clip prompts`), `production.py`, `generation.py`.

## Inputs

- Draft storyboard with per-shot purpose/change/must_show/framing/state/refs.
- Neutral `creative.look` from stage 4 (never repeat it shot by shot).

## Do — write in this order

1. **Subject** and **action** — who/what and what they are doing, in the shot.
2. **Composition / framing** — where the subject sits, the focal hierarchy, the
   framing named in the board (`wide`/`medium`/`close_up`/`detail`). Add the
   **per-shot optics** (focal length, depth of field), materials, weather and time
   of day here; the universal style comes from `creative.look` and is never
   restated shot by shot. No separate lens schema exists.
3. **`must_show`** — required load-bearing elements, phrased as visible facts.
4. **Occupancy** — state it explicitly in the shot ("not a single person in the
   frame", or the exact crowd), never in the scene. A scene written with a crowd
   will leak into every shot that needs it empty.
5. **No-text clause** — "no text, lettering, speech bubbles, numbers or symbols
   in the image" per shot. All lettering is composited later.
6. Bind only the references this shot needs (the identity + the resolved state),
   not the whole pack.

## Inspect the compiled prompt (mandatory)

```sh
uv run clip prompts PROJECT --shots s001,s002,s003
uv run clip preflight PROJECT --shots s001,s002,s003
```

Read what the model actually receives, not your intention. A scene description
that contradicts a shot-level instruction cancels it. Preflight is not arbitrary
prose understanding; confirm the known checks (clasp-vs-apart, empty-vs-crowded,
single-character clothing, ambiguous finger counts) pass.

For the default preset, confirm the exact protected `DEFAULT_STYLE` leads every
compiled source prompt, once, regardless of the scene or character. The approved
rooftop is a rendering benchmark, not a scene template: no copied man, rain,
lettering, border or composition. Do not contradict the core with flat/cel-shaded
or outline instructions. Proofs must include varied content and shot scales so
style transfer is inspected before a batch; a matching prefix alone is not proof.

## Boundaries

- Do not restate the model, AIR, native size, settings or seed policy here. Link
  to `default-style.md` / `profiles.py`; keep one canonical place.
- Do not force one shot's successful content, weather, time, lens or subject
  (e.g. rooftop/night/rain/50 mm f/2) into every shot.
- `image_prompt` and `motion_prompt` are different fields: a still is one
  decisive instant; motion_prompt is deferred planning, not animation.
- **Exit gate:** the compiled prompt was inspected and contains subject/action/
  composition/must_show, explicit occupancy and the no-text clause. No paid call
  happens in this stage.
