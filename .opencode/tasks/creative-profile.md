# Creative profile phase

## Objective

Make recurring people and places structural: a new production with a described
cast gets one validated creative profile, and the storyboard binds characters and
scenes by ID instead of repeating a contract in every image prompt.

## Base

`creative-profile` from merged `main` (`ca2771f`), which already contains the UX
handover and the two preserved local fixes.

## Decisions

- `CreativeProfile.profile_version` (integer, default 0) records that the profile
  was created through the new tool. Zero is omitted from serialization so legacy
  briefs and their hashes are unchanged.
- `production.set_creative_profile()` is the only writer for the cast, places,
  arc, global image rules, `avoid` and the look. It validates IDs, caps the
  writing budget (≤6 rules, ≤8 avoid, ≤12 arc beats, custom look ≤180 words, a
  protected preset's core verbatim plus ≤60 words) and versions the brief.
- The Writer gained a `profile` task between the script and revision, routed by
  `select_task` when `prompt_version == 2` and `profile_version < 1`, with
  `writer/profile.md` and a worked example.
- A v2 brief needs `treatment`, `creative.look` and `profile_version >= 1` for
  approval; `direction` and `style` are no longer required there. Legacy
  projects keep the old gate.
- Storyboard shots bind `character_ids` and `scene_id`; the compiler inserts
  identity and the resolved state, so shot text stays about the frame.
- Studio: a `ProfileCard` appears on Story for v2 films with a "Build cast &
  places" prompt; `CharactersCard` shows state chips; the next-step bar blocks a
  v2 story until the profile exists.

## Acceptance

- `uv run pytest -q` — 983 passed, 1 skipped (after adding the v2 profile gate,
  legacy-brief and unbound-cast tests).
- `uv run ruff check .` and `uv run ruff format --check .` — clean.
- `cd frontend && npm test` — 47 passed.
- `cd frontend && npx tsc -b` — clean.
- `cd frontend && npm run build` — clean.
- `projects/tree-of-love` (native v2, profile 0) and `projects/zero-bars`
  (legacy schema 3) still load unchanged.

## Open questions

- `tree-of-love` still repeats a 96-word contract in all 38 prompts and holds a
  597-word look. Repairing it is the acceptance exercise for this phase and
  would need three paid proof remakes (~$0.15) with the owner's authorization.
- The legacy FFmpeg/Pillow branches and the portable headless-shell decision
  remain from the rework.
