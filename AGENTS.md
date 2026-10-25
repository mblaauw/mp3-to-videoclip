# MP3 to videoclip

This is an agent-operated staged production tool, not an autonomous one-click
generator. Read README.md and PLAN.md. Use `uv run clip --help`.

## Production crew

`LOOP.md` is loaded as project instructions (`instructions` in `opencode.json`)
and is the production loop: read the validated artifacts → name the next missing
requirement or blocker → dispatch one bounded owner → inspect the result
creatively and technically → commit through the existing `clip` gates or stop.
The project defaults to the `film-director` agent, the single canonical state and
the only paid coordinator, with six specialists that never spend and never
nest: `music-editor`, `short-film-writer`, `visual-director`, `visual-critic`
(read-only, in story/board/pixels modes), `post-editor` (movement, keyframes,
transitions, effects and grade; drafts only) and `film-finisher`. Two bounded,
independent lanes run before the user gates — a story draft checked for narrative
and music binding, and a storyboard draft checked for visual story/continuity and
render feasibility, each followed by one bounded revision — and the director
alone dispatches, approves and spends. Remotion is the primary visual renderer
for new productions; FFmpeg remains the encode/mux/probe and legacy path, and
older projects migrate only by explicit opt-in. Agent rules live inline in `opencode.json`; do
not add `agent/*.md` overrides. Those permission and shell rules are workflow
discipline, not a security sandbox, and `runware_run` prompts are not budget
enforcement — the quote/authorization/reservation record is. `default_agent`
applies to fresh, unselected sessions only. Engineering work on the tooling
itself uses the ordinary build workflow with tests, not the film crew.

New productions use the guided Studio flow: **Track → Story → Style check →
Images → Finish** (`work/guided-flow.json`). Music analysis is agent-owned, the
watched preview is optional, full stills gate on the style check, and factual
credits are confirmed at Finish. Story approval is one human decision that still
validates brief and storyboard as two gates. `work/feedback.json` / `clip feedback`
carries durable revision notes, not approval or spend. Recorded productions without
the policy file keep their exact v2 gates. See docs/GUIDED_WORKFLOW.md.

Validate or refresh the local bundle with `uv run python
scripts/bootstrap_production.py --check` (read-only: no clone, install, archive
or network) or without `--check` to install the five pinned recipes and archive
the deselected motion recipes.

## Delegation bounds

Run at most two concurrent review lanes and at most three subagents per turn.
Batch frames, stills and files into one contact sheet or one bounded review
batch; never spawn one subagent per frame, still or file. Reuse a reviewer for a
second pass on the same bytes instead of opening a new child, and do not
re-review unchanged bytes. Reuse is only free for bytes that reviewer already
has: reaching the image budget is a per-session, cumulative limit (global
`AGENTS.md`, "Image review budget"), so a reviewer near its ceiling gets no new
images and new bytes go to a fresh bounded session. The director remains the
only dispatcher; specialists never dispatch helpers.

## Approval authority

Ordinary stage approvals and quote authorizations are human Studio actions:
the user starts `uv run clip serve --actions` in their own interactive terminal,
opens its human action link and confirms the reviewed content. Public
`clip approve` / `clip authorize` commands redirect to Studio. The director
prepares artifacts/quotes and reads the resulting records; it must not mint an
action capability, automate confirmation or call internal decision APIs on the
user's behalf. Older command examples are not an alternative authority path.
Individual image verdicts and style-test decisions retain their existing flow.
These rules are workflow discipline, not same-OS process isolation.

- Review music analysis and uncertain lyrics with the user before treatment.
- Propose 2–3 treatments, then record their selected direction/style in brief.json.
- Approve brief, then storyboard, then a three-shot proof, then the full still set.
- Never approve artifacts on the user's behalf without their explicit decision.
- Never upload source audio/person references or invoke chargeable tools without
  an approved scope and spending allowance. `go` authorized implementation and
  local analysis only, not transcription or generation spending.
- Upstream Runware skills are recipes, not permission. They MUST NOT override
  our approved model, format, prompt, shot scope or spending rules. Load the
  foundational execution/model/prompt skills as appropriate, check live schema
  and price, and ask before selecting a different or more expensive model.
- `runware_run` requires a permission prompt. MCP prompts alone are not budget
  enforcement. Prefer our quote/authorize/generate executor for batches. If using
  MCP for paid generation, equivalent durable request/result/cost tracking is
  required first. An interactive MCP importer is not implemented yet: use MCP
  for discovery and the CLI for tracked paid calls; never lose tracking.
- Never print keys, put them in artifacts, or commit source media/reference photos.
- All sung lyrics are drafts until reviewed, even when confidence scores look good.
  Never invent words, genre, language, time signature, verse/chorus labels or
  subjective musical meaning from a filename or automated measurements.

## Editing and verification

For new productions use docs/PRODUCTION_WORKFLOW_V2.md. Set an actually authorized
cumulative `clip budget`, import immutable neutral identity refs without rewriting
canon, bind wardrobe/accessory states explicitly, inspect compiled preflight,
and record `clip review` against every selected version before approval. Prove
hard interactions, release a small reviewed rollout before the full set, and
use `clip locate`/graphics `--preflight` before full exports. Warnings about small
stylised details are not automatic regeneration orders. No new paid calls or
global MCP/agent changes are authorized by a tooling implementation request.

Edit only the requested project/shot. Stable shot IDs are identity, not position.
JSON approvals are content-bound; changed artifacts require renewed review.
No paid downstream work happens automatically. Keep prior image/render versions.
Use the local renderer — Remotion for new productions, FFmpeg for encode/mux/probe
and legacy — not a required Resolve session. Future video assets replace stills on
the same frame-exact timeline; do not silently stretch clips. Continuous playback
with audio is its own checkpoint: sampled frames and signal checks are measured
evidence, not watching, and a delegated proxy preview is allowed only with the
user's explicit permission, declared unwatched, never a pass.

Run `uv run pytest` and `uv run ruff check .`. Verify exports with ffprobe and
inspect contact sheets and sample frames. Never claim mocked tests prove real
provider generation or character likeness. No live paid calls in tests.

## Creative quality workflow

Every crew member reads
`.opencode/skills/clip-music-director/references/music-first-direction.md` before
creative work. `film-director` is the single music-video lead: narrative optional,
recording-to-sequence relationship first. Music-editor and post-editor contribute
before board lock/generation; store the sequence treatment in the existing brief.
Review neighboring shots and actual-song contrast, not just attractive stills.
No invented music grid, compulsory beat cuts/motion, automatic grade/parallax or
paid candidate sets. Early intent-based concepts stay provisional until music review.

For new still films load `clip-music-director`, then the relevant focused stage
skill. Defaults are copied from `src/mp3_to_videoclip/profiles.py`: the approved
photoreal-painted Alex Ross / Gabriele Dell'Otto hybrid and Nano Banana 2.1, with
explicit per-production overrides. See docs/STILL_FILM_WORKFLOW.md. Develop
story/art direction before brief approval and storyboard/prompts before board
approval. Instrumentals skip transcription/lyric timestamps, not music structure.
`clip analyze PROJECT --deep` adds a deeper **local** music map to
`work/music-deep.json` (downbeat phase, key with its runner-up, candidate
sections, bass- and vocal-band onsets). It is a separate artifact on purpose so
it can never silently rewrite an approved analysis; it stays unreviewed
measurement, is not an approval, and never retimes an approved edit on its own.
One economical inspection per source image and one correction by default; no
pedantic distant-anatomy retries. Movement is local and deliberate: Remotion is
the primary renderer for new productions and renders movement, keyframes,
transitions and effects chosen per shot purpose — a deliberate hold stays valid —
with no AI character animation, no automatic glitches, flashes or per-beat cuts,
and no paid call.

Read docs/CREATIVE_WORKFLOW.md for new productions (`brief.creative`). Keep the
approved legacy pilot unchanged unless the user explicitly requests its revision.
Use the original `clip-music-director` skill and docs/MUSIC_LED.md for DJ/mixed
tracks, branded openings and protagonist-led music direction. Keep supplied Suno
style/lyric intent separate from measured and model-listened evidence.

- Treat each track independently: narrative, symbolic or abstract; no genre,
  meter or emotional meaning invented from a filename or tempo estimate.
- Use reviewed music events/phrases as edit opportunities, not mandatory cuts.
  Instrumental mode skips lyrics; never fabricate lyrics to pass a gate.
- Put medium/palette/light/texture in creative.look/image_rules. Put locations
  in bound scenes and the subject/action/composition in each shot. Never repeat
  the whole story or every location into each image prompt.
- Plan a visual arc (scale, intimacy, light, recurring motifs). Choose three
  proof IDs for creative risk/coverage, not automatic first/middle/last sampling.
- Judge every still against purpose, framing and must_show; review the sequence
  for accidental repetition, anatomy/prop errors, distracting text and continuity.
  A coherent colour palette is not proof of shot fidelity or narrative progress.
- Approve the proof, render the marked local preview, review pacing on the actual
  music, then ask for explicit preview approval before quoting the full batch.
  Placeholder shots are not generated/approved stills. Available-set previews
  are for later editing checks; proof-only previews bind the new batch gate.
- Keep holds deliberate. camera_path controls crop/zoom only; motion_prompt is
  deferred planning and does not make people, curtains, rain or lights animate.
- Scene/prop/style references need upload permission and a quoted byte hash just
  like faces. No paid A/B testing, upscale or alternatives without new scope.
