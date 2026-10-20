# Default new-production style and model preset

Single canonical statement of the **new-production still-film default**. Code is
authoritative: `src/mp3_to_videoclip/profiles.py` defines the executable
constants; this file explains them. Change the preset in code and here together,
never in a stage skill. Pinned upstream recipes may quote stale model parameters
or capabilities — the **live provider schema plus `profiles.py`** decide what is
actually sent, never a recipe.

## Canonical constants (import; do not re-declare)

```python
from mp3_to_videoclip.profiles import (
    DEFAULT_MODEL,             # "google-nano-banana-2-1"
    STYLE_PRESET_ID,           # "photographic-painted-v2" — current default
    LEGACY_STYLE_PRESET_ID,    # "photoreal-painted-v1" — recorded productions only
    DEFAULT_MAX_CORRECTIONS,   # 1: one original plus one correction
    DEFAULT_STYLE,             # canonical style string (see below)
    ROOFTOP_CONTROL_PROMPT,    # exact retained calibration fixture (see below)
    STYLE_BENCHMARK,           # user-approved original, hashes and decision
)
```

Skills, docs and tests import or link these names. Do not copy the model string,
style prose, native sizes or correction count into a second place: a duplicated
default drifts and the compiled prompt silently changes.

## Model and settings (verified against the public schema)

- **Model AIR:** `google:nano-banana@2.1` (recorded slug `google-nano-banana-2-1`).
  Confirm `status: live` and the current reference limit against the public
  schema before quoting; never assume from this file.
- **Settings (defaults copied into new productions, explicitly overridable):**
  - `settings.thinkingLevel = "minimal"` — the user's economical baseline, not
    a guarantee of quality or measured speed compared with other levels.
  - `settings.imageSearch = false` and `settings.webSearch = false` — the film's
    look and content come from the approved brief, not from live web retrieval.
- These live under `settings`, **not** `providerSettings`. Unsupported or guessed
  diffusion controls must not be sent.
- A `seed` may be set when the user asks for a reproducible request, but it is
  **not an identity lock**. Likeness comes from immutable, role-labelled
  references and review, never from a shared seed.
- **Native sizes:** `1376x768` landscape or `768x1376` portrait. Declare
  `project.native_size` to one of these (or transpose) or the quote fails
  validation. Do not hardcode a size the model rejects.
- Deliverable format is JPG for the synchronous one-result path; the result
  record includes cost, which the tracked executor journals.

## Style preset `photographic-painted-v2`

Use `profiles.DEFAULT_STYLE` verbatim as the protected prefix of `creative.look`;
`clip init` copies it and `DEFAULT_IMAGE_RULES` into the brief. Append film-specific
palette/light notes after a blank line, never paraphrase or shorten the core.
Default-preset brief approval and prompt compilation reject a missing/altered core.
An intentional different style needs a recorded explicit override, not a quiet edit.
It restores the **original
successful photographic-painted fingerprint**: a fully painted illustration
driven hard toward photographic craft, naming **Alex Ross** and **Gabriele
Dell'Otto** exactly and prominently, roughly 70% Ross for photographic anatomy,
material and believable light, 30% Dell'Otto for deep blacks, hard highlights and
gritty painted texture. Painted by brush, not photographic capture; measured,
monumental and cinematic — **not** a flat comic, cel-shaded or outlined look. The
70/30 ratio is prose, not an API control.

- **Compile order is style-first for v2 only.** In a v2 production the style
  fingerprint leads the compiled prompt. `photoreal-painted-v1` productions keep
  their recorded prompt text and **exact prompt hashes**: never migrate,
  recompile or regenerate them to adopt v2.
- Inspect the actual preset text without buying an image:

```sh
uv run python -c 'from mp3_to_videoclip.profiles import DEFAULT_STYLE; print(DEFAULT_STYLE)'
```

### Universal style versus per-shot optics and materials

`creative.look` carries only the **universal** medium/rendering/texture/lighting
language. Anything that belongs to one picture — focal length, depth of field,
lens character, camera height, materials, weather, time of day, place — is written
in that shot's `image_prompt`. There is **no separate lens/optics schema** and
none is needed; do not add one.

### Retained rooftop control fixture

**Approved benchmark:** the user inspected the generated control and said
“the style is perfect.” `profiles.STYLE_BENCHMARK` records the exact original's
private path, image/task/prompt/settings hashes and approval wording. The durable
decision is `work/style-approval.json` in that calibration workspace. Verify the
original hash before comparison; if unavailable, restore the private original,
not an invented/re-generated substitute. Do not regenerate the approved control
for every new story. Proofs test transfer to new subjects and shot scales.

The approval covers **rendering style**, not the depicted man, coat, rooftop,
rain/night, sodium/searchlight arrangement, 50mm f/2, title, caption, cream border
or cover composition. Production frames stay full-bleed and text-free. Different
stories may be daylight, interiors, landscapes or different casts without losing
photographic anatomy/materials, brush fidelity, deep blacks and hard highlights.
The original is a **local review benchmark**: no automatic reference binding or
provider upload is authorized. If later explicitly authorized as a style input,
label it style-only and reject leakage of its content, layout or lettering.

`ROOFTOP_CONTROL_PROMPT` is the exact supplied full manual-test prompt retained
verbatim — including its own request for the test headline `THE LAST LIGHT` and
its caption box — as a style **control**, not the film default. Full text:
`successful-manual-test.md`. Calibrating the fingerprint is the one deliberate
exception to the local-text rule.

- Calibration is a **separate tracked single-image job**: Nano Banana 2.1,
  supplied control prompt as-is, at most **USD 0.10**, no references, no automatic
  retry. It is not a remake of any earlier film and must not reuse another
  production's remaining allowance. The runtime's tracked calibration entry point
  and its flags are its own — inspect `clip --help` / the relevant `--help` rather
  than assume an invented flag.
- **A new calibration shot starts as a candidate**, not automatically a golden
  reference. The first image produced never becomes golden automatically; only
  the user's own inspection may promote a style candidate. Prior film/Takeover
  reference sets are labelled history, not new golden. Until the user decides,
  report the candidate at most **agent-reviewed under delegation**. The current
  rooftop benchmark has now passed that explicit user-decision gate; this does
  not auto-accept other outputs or authorize more calibration spending.

## Reference policy

- The live schema sets the hard cap (it can reach ~14). **Normally bind only 2–4
  useful, immutable, role-labelled images**; more refs are not better and can
  dilute identity. Never hard-cap references at 4 in code or policy — the schema
  is the cap.
- Bind **identity or other load-bearing** references. A populated full-scene
  anchor is for geography/scale continuity only; do not bind it in a way that
  pins people, poses or wardrobe across unrelated shots.
- The model decides how each reference is used; label each reference's job in the
  prompt and review the result.

## Separation of concerns (the Signal v2 lessons)

- `creative.look` describes medium/rendering; scene text describes a place;
  occupancy, people and action belong in the shot. An "empty" shot in a scene
  written with a crowd inherits the crowd.
- One coherent world with varied rooms, scale and light beats a new city/style at
  every musical change.
- Content, lens, weather and time of day observed in one successful test (for
  example the retained rooftop/night/rain example, `legacy-recipes.md`) are that
  production's choices. They are **not** the default style and must not be forced
  into every shot.
- The older `painted-comic.md` "not a photograph / not CG" heritage recipes are
  superseded for new productions; legacy productions keep their recorded look.

## Overrides

An explicit user choice — different model, size, settings, style prose or
correction count — replaces the default for that production. Record the override
and its authority before quoting. Nothing here authorizes spending.
