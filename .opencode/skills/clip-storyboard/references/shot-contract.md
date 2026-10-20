# Shot contract template (decisive stills)

Editable planning text for `work/storyboard.json`. Reuse the existing `Shot`
fields (`src/mp3_to_videoclip/models.py`); add no schema.

## Per-shot record

```jsonc
{
  "id": "s003",                         // stable identity, not position
  "purpose": "…",                        // the job this still does
  "start_frame": 0,                      // contiguous, exact
  "duration_frames": 192,                // hold length from the music (typ. 4–6 s)
  "dissolve_frames": 0,                  // clean cut unless motivated
  "image_prompt": "…",                   // subject/action/composition/must_show
  "motion_prompt": "",                   // deferred planning only, never animation
  "camera": "hold",                      // or zoom/pan; moves the crop only
  "camera_path": null,                   // optional start/end crop move
  "framing": "medium",                   // wide | medium | close_up | detail
  "must_show": ["…"],                    // load-bearing visible elements
  "character_ids": ["…"],                // identity refs bound per shot
  "character_states": {"…": "…"},        // resolved wardrobe/prop state
  "state_requirements": {"…": {"wardrobe": "…"}},
  "scene_id": "…",                       // neutral place text (no occupancy)
  "reference_ids": ["…"],                // only refs this shot needs
  "event_ids": ["…"],                    // reviewed musical position
  "asset_shot_id": null                  // alias: reuse an approved still's crop
}
```

## Writing the change

Before the fields, write one line per shot: *what is different from the previous
shot and what it advances*. If a shot changes nothing, cut or merge it. Vary the
jobs: establishing / medium / expression / hands-object / environment /
relationship. No deliberate repetition without a changed meaning.

## Timing (adaptive, deterministic)

- Timing follows the music's behaviour, not one universal range. For an energetic
  mix, typical holds are **4–6 s** with earned **1.5–3 s** inserts and only
  motivated long holds; calmer passages may hold longer.
- Snap first to **reviewed event boundaries**, then to measured musical
  opportunities/beats. Never infer a meter and never force a cut on every beat.
- The adaptive planner's range is a proposal, not a fixed panel count:

```sh
uv run clip skeleton PROJECT --timing adaptive --seconds 5 --min-seconds 1.5 --max-seconds 7
```

- Rebalance tails (do not leave a 1-frame orphan) and cover the **exact** source
  frame count. Shot intervals must be contiguous and ordered.
- An `asset_shot_id` alias reuses an already approved source image for a
  different editorial crop; it needs no new generation. **Editorial edits
  therefore outnumber new images** — never buy one image per edit.

## Proof selection

Exactly three risk IDs (or all if fewer). Include the hardest recurring
interaction/wardrobe requirement, not three attractive portraits. Record them in
the **brief's** `creative.proof_shot_ids` field — not on the storyboard.

## Preflight before approval

```sh
uv run clip preflight PROJECT --shots s001,s002,s003
uv run clip prompts   PROJECT --shots s001,s002,s003
```

Both must show the compiled prompt, refs/hashes, resolved states, purpose,
must_show, framing and frame intervals with no blocking conflict before the user
approves the board.
