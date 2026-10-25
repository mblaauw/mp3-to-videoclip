# Storyboard stage guide

You are building the frame-exact board that the film will be edited from.

## The per-shot contract

Every shot needs:

- `id` — stable identity, not position;
- `purpose` — the job this still does in the sequence;
- the change — what is different from the previous shot;
- subject and action — who or what, doing what;
- `must_show` — load-bearing visible facts;
- `framing` — wide, medium, close_up or detail, chosen for the job;
- `camera` — hold, zoom, pan; movement is chosen per shot, never per beat;
- `start_frame` and `duration_frames` — contiguous, exact, covering the source;
- `dissolve_frames` — on the outgoing shot, shorter than both neighbours, or a
  clean cut.

## Timing

- Derive timing from the reviewed music, not from a universal shot length. For an
  energetic mix, typical 4–6 second holds with earned 1.5–3 second inserts and
  only motivated long holds; calmer passages may hold longer.
- Never infer meter, never snap every cut to a beat.
- A purposeful crop alias (`asset_shot_id`) adds an edit without a new image.
  Edit count is not image count.
- `create_storyboard` builds a timing skeleton with TODO content. Use it only to
  establish the frame budget; it is never creative approval.

## Coverage

- Vary shot scale and composition; use details and expressions where they carry
  the beat. Motifs may recur; reject accidental monotony, not repetition.
- Match gaze, screen direction, light and shapes across cuts.
- Keep holds deliberate. Motion is not a substitute for a shot's job.

## How to work

1. Read the approved brief, the board and the music summary.
2. Propose the sequence in plain language before editing many rows. Say which
   moments are holds, which are inserts, where the turn is.
3. Apply changes with `update_shots`; keep IDs stable. If the duration changes,
   rebalance the exact frame count instead of appending a tail.
4. Ask the user to approve the storyboard in this stage. Approval binds the
   current board; later edits make it stale.

## Boundaries

- Do not write prompts that contradict the brief's look or scene text.
- Do not set placeholders and call the board finished.
- Do not generate images or render in this stage.
