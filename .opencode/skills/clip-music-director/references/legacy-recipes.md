# Legacy and reusable recipes (labelled history)

Nothing here is the new-production default. The default is `default-style.md`
(current preset `photographic-painted-v2`). These recipes are retained because
they worked, they explain earlier productions, and a user may explicitly pick one.
**A recipe is not permission** — it is not an approved style, model, size or
spend, and no entry here is a golden reference for new films.

## Pinned upstream (Runware) recipes — unmodified

Installed by `uv run python scripts/bootstrap_production.py` from the pinned commit
in `.opencode/SOURCES.md`. Their bytes are preserved; do not edit them.

| Skill | Role for this project |
|---|---|
| `runware-models` | live model/capability/price discovery |
| `runware-run` | how to call a model correctly (schema-first) |
| `runware-prompting` | prompt phrasing, negation, cinematic grammar |
| `photoreal-stills` | photographic (camera-real) look technique |
| `character-consistency` | identity persistence across images |

Two further upstream recipes — `animate-image` and `cinematic-video` — are
**deselected** for this still-film project: they are not installed by default by
the bootstrap script and are denied by the project skill permission. They remain
available to a future, separately approved motion production.

Upstream defaults never override this project's approved model, format, prompt,
shot scope or spending rules. Where a recipe names a model or looks recipe, check
the live schema and price, then ask before choosing anything different or more
expensive.

## Heritage project recipes — original, superseded for new productions

| Reference | Status | Note |
|---|---|---|
| `painted-comic.md` | heritage | Painterly Alex Ross / Dell'Otto recipes, including a "not a photograph" hybrid. Superseded by `photographic-painted-v2`; keep for legacy productions. |
| `shot-review.md` | current | Fixed accept/reject/uncertain dispositions and review criteria; still the review rubric. |

## Retained reference example — rooftop / night / rain

Exact prompt and the user's reported result: `successful-manual-test.md`. Its
verbatim prompt is also the retained calibration fixture `ROOFTOP_CONTROL_PROMPT`
(`default-style.md`) — a control, not a new golden reference.

A manual test produced one successful still in a distinct reusable style:
photoreal **painted** night rooftop in rain, a lone figure, roughly **50 mm at
f/2**, wet reflective surfaces, one practical sodium/neon source, deep shadow.
It worked and is kept as a reference example and as the fingerprint control.

It is **one production's style choice**, not the project default. Its content
(rooftop), weather (rain), time (night), subject (hero) and optics (50 mm f/2)
must **not** be forced into every shot of an unrelated film. If you want this
look, name it explicitly per production and keep the rest of the brief free. The
style candidate a calibration shot produces is judged by the user, never adopted
automatically.
