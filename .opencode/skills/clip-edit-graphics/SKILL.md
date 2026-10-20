---
name: clip-edit-graphics
description: Stage 8 of an MP3-to-videoclip production. Build the frame-exact timeline, edit stills to musical behaviour with deliberate holds, and composite local overlays verified by graphics preflight. Use for timing, camera paths, captions, intro/credits and animatic previews. Never cuts every beat or appends a silent tail.
---

# Stage 8 — Edit and graphics

**Output:** complete/partial/blocked; versioned edit, checks and playback coverage (not automatic approval).
**Position:** proof-only preview before full generation; available-set edit after stills review, before export. Links:
`../clip-music-director/SKILL.md`,
`../clip-music-director/references/production-gates.md`,
`../../../docs/PRODUCTION_WORKFLOW_V2.md`, `../../../docs/CREATIVE_WORKFLOW.md`.
Code: `timeline.py`, `preview.py`, `graphics.py`, `branding.py`, `render.py`.

## Inputs

- Approved stills with version-bound accept verdicts; approved music events.
- Before board lock: co-design rhythm/contrast/attention/text, not post-hoc zooms;
  follow `../clip-music-director/references/music-first-direction.md`.
- Required signature spec with confirmed credit roles for new films; any optional
  legacy `brand.json` is separate and does not replace the opening/closing package.

## Do — timing and edit

1. Use the contiguous frame-exact timeline from the approved board. Shot cadence
   (typical 4–6 s holds with earned 1.5–3 s inserts for an energetic mix; see
   `../clip-storyboard/SKILL.md`) belongs to storyboard development, not an
   automatic retiming of paid shots. To revise it now, review the explicit
   timeline change. **Never automatically cut on every beat**, and never infer a
   meter. Cover the exact source frame count and rebalance tails.
2. Use musical contrasts deliberately: held anticipation, a real reveal, short
   bursts, breathing space, selective offbeat/phrase cuts. A hold is a choice.
3. Match shapes, gaze, gesture, screen direction and light across cuts. Prefer
   clean cuts or motivated blends over a pile of unrelated transitions. Avoid
   default strobing, constant zooms and unearned speed.
4. Reuse an approved source image via `asset_shot_id` for a different editorial
   crop when its native detail allows. Each edit keeps a stable ID and exact
   allocated frames; no cycles/chains, and no new generation for a reused shot.
5. `camera_path` moves the crop/zoom only. `motion_prompt` does not animate rain,
   smoke, people, eyes or doors — do not rely on it for motion.

## Do — movement, transitions and grade

The post-editor designs, film-finisher executes; Remotion renders and FFmpeg encodes/muxes/probes
(`references/motion-and-grade.md`, `references/remotion-motion.md`).

1. **Choose movement per shot purpose** — keyframes, transition or effect only
   where the shot's job needs it. A deliberate hold stays valid; no automatic
   glitches, flashes or per-beat cuts, and no AI character animation.
2. **Attention per shot, not motion per shot**: hold/reveal/move/cut as justified; no identical-zoom recipe.
3. **Dissolves join** section boundaries, time/place shifts and emotional drops;
   `dissolve_frames` sits on the outgoing shot, must be shorter than **both**
   neighbours, and is consumed as handles — the film still covers every frame.
4. **Never retune a reviewed crop**; accepted `camera_path` bytes stay, or a
   sample-based review is invalidated.
5. **Motion on the beat means scale, not tempo**; never retime a cut or assert a
   meter, and judge motion on decoded frames, not prose.
6. **Grade is opt-in, local and versioned.** Never normalise or replace the audio.

## Do — graphics (local compositing)

1. Composite **every word locally** (intro, captions, SFX, credits) via
   `mp3_to_videoclip.graphics` / `branding`; generated panels stay text-free.
2. Keep the exported overlay track derived from the approved spec bytes.
3. Bind captions to shots, not brittle absolute seconds:

```json
{"id":"drop","shot_id":"s025","offset_frames":12,"duration_frames":72,
 "style":"sfx","text":"DROP","x":0.74,"y":0.25,"rotation":-6}
```

4. Verify long words fit their burst/box before export: the shape sizes to the
   measured text, and watch composited backgrounds, not raw alpha on grey.
5. Run graphics preflight on actual base footage and `clip locate` for exact
   shot/alias identity before the full composite.

For new films use `clip render PROJECT --base-only`, inspect the generated
`work/graphics-review.json` samples, then `clip approve PROJECT graphics
--inspected --note ...` and `clip render PROJECT` for the reviewed composite.
Normal final rendering will not silently deliver an unbranded base. The required
signature compositor currently supports 16:9; resolve portrait plans before spend.

```sh
uv run clip locate PROJECT --seconds 124
uv run python -m mp3_to_videoclip.graphics --root PROJECT --base BASE.mp4 \
  --preflight --output PROJECT/work/reviews/graphics-check --times 124,129
```

### Required signature for new films

Every new v2 film carries, inside the original music and through
`work/graphics-spec.json` plus the existing `graphics.py` visual family:

- a **25-second opening overlay** and a **final 40-second credit package**;
- the shared **MAHA KALA × VJDJ69** identity and the joint-production line
  `A JOINT MAHA KALA & VJDJ69 PRODUCTION`;
- the production's **actual** credit roles, supplied once at intake — never the
  randomized demo credits, never fabricated, and never omitted because the work
  was delegated;
- the collaboration identity from the project's `brand.json` (the `joint` emblem,
  one palette) so the opening, the credits and the render-time plate cannot drift
  into two half-identities. A design may adopt it with `design: "joint-v1"`; a
  production whose opening already renders the identity sets `plate: false` so the
  emblem is never drawn twice.

Reuse the existing `graphics.py` lockup/credit visual family; do not build a
second brand engine. All text is composited locally (the sole exception is the
authorized rooftop control test in
`../clip-music-director/references/default-style.md`). If the song is too short
to hold the 25 s / 40 s package inside the music, **stop and ask for an alternate
plan** — never add an intro tail, delay, stretch or appended credit tail.

## Boundaries and exit gate

- Never delay, truncate, stretch or normalise the original audio; never append a
  silent tail. Intro/closing overlays follow the approved spec and stay inside
  the continuing original song.
- Review phases at their intended times, not raw transparent PNGs. Never infer a
  shot ID by memory from a timestamp.
- **Exit gate:** the marked animatic/preview is judged on its actual continuous
  playback with audio, and the user approves pacing before the full export. Sampled
  frames and signal checks are measured evidence, **not** watching; a delegated
  proxy export needs explicit permission and is recorded **unwatched**, never a pass.
