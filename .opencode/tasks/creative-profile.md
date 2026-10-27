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

- `uv run pytest -q` — 984 passed, 1 skipped (after adding the v2 profile gate,
  legacy-brief, unbound-cast and legacy-routing tests).
- `uv run ruff check .` and `uv run ruff format --check .` — clean.
- `cd frontend && npm test` — 47 passed.
- `cd frontend && npx tsc -b` — clean.
- `cd frontend && npm run build` — clean.
- `projects/tree-of-love` (native v2, profile 0) and `projects/zero-bars`
  (legacy schema 3) still load unchanged.

## tree-of-love acceptance (2026-10-27)

The production was repaired through the new writers only; no provider call was
made and no still was touched.

- Snapshot first: `backups/tree-of-love-metadata-20261027T183829Z.zip`
  (`project.json`, `brief.json`, `brand.json`, `work/`; media and assets left
  out). Roll back by unpacking it over `projects/tree-of-love`.
- Profile: `woman` (`dream`, `waking`, `waking-loose`) and `man` (`dream`,
  `waking`); five scenes (`dream-garden`, `her-room`, `his-room`, `grounds`,
  `courtyard`); eight arc beats; five global image rules; six `avoid` entries; a
  174-word rendering look.
- `direction` lost its 96-word character contract and now holds only the waking
  world, the no-lip-sync/lens rule and the credits note (121 words).
- 25 of 38 shots bind cast; 13 stay deliberately unbound (empty establishing
  shots, hand, eye and root macros). Every shot binds a scene.
- Compiled prompt text fell from 32,863 to 16,175 words across the board
  (`s003` 879 → 462, `s001` 901 → 441, `s006` 865 → 386).
- The brief and storyboard are now `stale` and need the owner's re-approval. The
  three proof versions (`s003` v2, `s006` v1, `s038` v1) remain on disk and are
  stale against the new prompts.

## Open questions

- The three proof remakes (~$0.15) and the owner's re-approval are the only
  remaining steps for `tree-of-love`; the spend needs explicit authorization.
- The legacy FFmpeg/Pillow branches and the portable headless-shell decision
  remain from the rework.
