---
name: clip-music-director
description: Route an MP3-to-videoclip production through nine bounded stages — music analysis, story, storyboard, art direction, image prompts, image production, visual review, edit/graphics and delivery. Use for direction, approvals, spending gates, defaults and stage references. Load the matching stage skill for detail.
---

# Music-video direction: stage router

Read `../../../LOOP.md`, `../../../AGENTS.md`, `references/music-first-direction.md`
and `../../../docs/MUSIC_LED.md`. CLI artifacts and content-bound approvals are
authoritative. This skill is original project guidance; upstream Runware recipes
neither override approved scope nor authorize spending. Workflow 2 examples:
`../../../docs/PRODUCTION_WORKFLOW_V2.md`; defaults:
`../../../docs/STILL_FILM_WORKFLOW.md`. Do not modify pinned upstream recipes or
global MCP/agent settings to fix one production.

## Crew roles

`LOOP.md` defines the crew — `film-director` plus six specialists — and these nine
stage skills are their capabilities. Reuse them; add no skills, committees or
per-agent files; this router stays the single stage map.

## Authority and scope gates (apply to every stage)

- **Spending:** a cumulative `clip budget` cap plus a per-quote `authorize`
  decision exist before any upload or inference. A loaded skill, an upstream
  recipe or "tooling" is never permission; when in doubt, stop and ask.
- **Approvals are content-bound and user-owned.** Never approve on the user's
  behalf. Changed brief/storyboard/image/timing bytes require renewed review.
  A delegated production keeps the exact delegation; label it
  **agent-reviewed under delegation**, never as the user's inspection.
- **Evidence honesty:** report separately what was measured, what a provider
  model reported, what was visually inspected, what was technically verified,
  what remains uncertain and what awaits the user. Never claim a mocked test,
  contact sheet or prompt text proves image quality or likeness.
- **Change and scope:** edit only the requested project/shot. Stable shot IDs
  are identity, not position. Never mutate an approved production to adopt a new
  default; new defaults apply to new productions unless explicitly overridden.
- **Defaults are replaceable.** The new-production preset, model, settings and
  sizes live in one canonical place — see `references/default-style.md` — and any
  explicit user override replaces them for that production. Do not restate model
  or settings constants in stage skills or in ten places.
- **Text:** every word on screen (title, captions, SFX, credits) is composited
  locally unless the user explicitly overrides. Generated panels carry no text.
- **Image review budget:** one quick actual inspection of every generated image,
  bounded fresh sessions, text-only returns. See `references/production-gates.md`.
- **Motion:** stills plus deliberate local movement — Remotion movement, keyframes,
  transitions and effects chosen per purpose, where a deliberate hold stays valid.
  No AI character animation, glitches, flashes or per-beat cuts.
- **Feedback lanes:** story and board drafts each pass one bounded independent
  review before the user gates; the draft's owner revises once (`references/crew-feedback-loop.md`).

## Stage sequence

These are stage capabilities, not nine extra sequential approval gates. Develop
story and art direction together **before brief approval**, then storyboard and
compiled prompts **before storyboard approval**. Never silently change an earlier
approved artifact. The execution sequence is:

1. Reviewed music → story + art direction → approved brief.
2. Storyboard + prompt inspection → approved storyboard.
3. Proof generation ↔ visual review → approved proof.
4. Edit skill: watched proof-only preview → preview approval **before** stills quote.
5. Small rollout ↔ review, then remaining generation ↔ review → stills approval.
6. Available-set edit/graphics preflight → export, verification and delivery.

New films are delivered with the required in-music signature: a **25-second
opening overlay and a final 40-second credit package**, both inside the original
song, carrying the shared MAHA KALA × VJDJ69 identity and the joint-production
line. Supply the film title, slug and this production's **actual** credit roles at
intake, once; never copy randomized demo credits or omit them because the work was
delegated. See `../../../docs/MUSIC_LED.md` and `clip-edit-graphics`; all text is
local except the authorized rooftop control test (`references/default-style.md`).

| # | Stage skill | Owner artifact | Exit gate |
|---|---|---|---|
| 1 | `clip-music-analysis` | `work/music.json`, `work/music-map.md/json` | User reviews map; events approved |
| 2 | `clip-story` | `brief.json` (`treatment`, `creative.arc`) | User approves brief |
| 3 | `clip-storyboard` | `work/storyboard.json` + preflight | User approves storyboard |
| 4 | `clip-art-direction` | `brief.creative.look` / `image_rules` | Included in brief review, before storyboard |
| 5 | `clip-image-prompts` | `clip prompts` output | Compiled prompt inspected |
| 6 | `clip-image-production` | journaled images + `clip costs` | Quote authorized; results tracked |
| 7 | `clip-visual-review` | `clip review` verdicts | Every selected version inspected |
| 8 | `clip-edit-graphics` | timeline + `graphics --preflight` | Preview watched, timing approved |
| 9 | `clip-delivery` | versioned MP4 + report | Approvals, hashes, audio intact |

## Stage routing summary

1. **Music analysis** — local measurement and reviewed interpretation of the
   actual recording. No invented genre/meter/emotion; instrumentals skip lyrics.
2. **Story** — concept/sequence directions inside the existing brief approval;
   narrative is optional, with a causal spine only when chosen. A narrative film's treatment
   carries an actual 250–400-word visual short story (goal, conflict, visible
   actions, a choice with a cost, escalation, an earned ending), not a premise
   followed by a shot list. Symbolic/abstract and process directions are valid.
3. **Storyboard** — decisive stills, not animation. Job/change/must-show/framing/
   state/music binding/frame interval/transition per shot, from music, not meter.
4. **Art direction** — one coherent world; medium/palette/light/texture only in
   `creative.look`; scene text states place, never occupancy. Developed *with* the
   story, before brief approval; per-shot optics/materials stay in the shot prompt.
5. **Image prompts** — subject/action/composition/must_show first, occupancy and
   no-text in the shot; only relevant refs bound.
6. **Image production** — quote → authorize → tracked generate; worse-case
   reservations, no silent model swaps, concurrency limits respected.
7. **Visual review** — one real inspection per image, severity calibrated,
   containment before whole-frame rolls.
8. **Edit/graphics** — musical behaviour, deliberate holds, local overlays and the
   required in-music opening/credit signature; timing follows the reviewed events.
9. **Delivery** — version-bound approvals, a hashed base and final composite,
   ffprobe verification, intact audio, provenance and a plain report of what is
   proven versus assumed.

## References

- `references/default-style.md` — canonical new-production preset (`photographic-painted-v2`),
  model, settings, sizes, style/compile rules and reference policy (single source
  of truth), plus the retained `ROOFTOP_CONTROL_PROMPT` calibration fixture.
- `references/production-gates.md` — authority, budget, review budget, repair
  ladder, delegation and reporting gates in one place.
- `references/crew-feedback-loop.md` — the two lanes, owners, one-revision rule and report shape.
- `references/legacy-recipes.md` — labelled **history**: pinned upstream recipes,
  the painterly `painted-comic.md` recipes, `shot-review.md` and the retained
  rooftop/night/rain test style. Reusable, never forced onto every shot, and never
  the new golden reference.
