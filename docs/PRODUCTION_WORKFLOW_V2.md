# Workflow 2: less rework, evidence-bound quality

Current new-film defaults and stage skills: [STILL_FILM_WORKFLOW.md](STILL_FILM_WORKFLOW.md).
Existing productions are not migrated to these new defaults.

The new `prompt_version: 2` / `photographic-painted-v2` candidate is style-first;
serialized older films retain their exact prompt order and hashes. Choose a film
title/folder independently of the MP3. New films also require confirmed factual
roles in the draft `work/graphics-spec.json` before brief approval. Required
signature: 25-second opening, final 40-second credits, shared joint-production
identity, all within the original song. The current signature compositor is
16:9-only: resolve portrait plans before spending, never silently omit graphics.
After stills approval, `clip render PROJECT --base-only` creates the base and
actual composited samples. Inspect them, record `clip approve PROJECT graphics
--inspected --note ...`, then `clip render PROJECT` produces the final composite.
The base is not delivery; the graphics approval binds spec, base inputs and sample
bytes. See README for title derivation and separate `clip style-test` commands.

New CLI productions default to `project.workflow_version: 2`. Existing projects
are **not migrated**. `clip init ... --workflow-version 1` explicitly retains the
old contracts for a new legacy-style project. Do not toggle an approved project
in place: references, prompts and approval bindings will change. The approved
implementation scope is [WORKFLOW_HARDENING.md](WORKFLOW_HARDENING.md).

## 1. Spending authority before any upload or inference

```sh
uv run clip budget PROJECT --cap 5.00 --max-corrections 1 \
  --note 'Actual user authorization: production scope and total allowance'
uv run clip budget PROJECT
uv run clip costs PROJECT
```

Setting this artifact records authority, not approval to invent it. Quotes still
need their individual `authorize` decisions. All image/audio/listening/transcript
tasks share the cumulative cap: actual reported costs plus every unknown-cost
reservation. An unpriced task without a reserve blocks admission. Ready uploads
whose prices are unknown retain their reservation. HTTP errors or taskNotFound
do not establish zero billing; `resolve-task` requires actual billing evidence.

Reservations are admitted **at submission**, not when authorizing unsent quotes.
Multiple quotes may be authorized, but their combined submissions cannot reserve
more than the allowance. Actual provider prices are not provider-enforced caps;
an unexpectedly expensive result stops further work and remains recorded.
Existing ambiguous tasks require recovery/reconciliation before new spending.

New budget records default to one original plus one correction per source shot.
Existing recorded limits are retained; `--max-corrections` is an explicit override. Simply
changing a prompt/hash does not reset this count. After diagnosing a failure:

```sh
uv run clip restage PROJECT --shots s024 \
  --note 'Diagnosis: interlocked hands fail; restage as separated hands with a gap'
```

This starts a new recorded correction cycle; it does not authorize spending,
approve art, change any image, or validate the artistic judgement. Model changes,
alternatives and masked edits still need their own reviewed scope/allowance.

## 2. Identity references are assets, not selected proof panels

```sh
uv run clip reference-import PROJECT --source /owned/neutral-person.png \
  --crop 20 10 420 610 --permission-confirmed \
  --note 'Actual authorized use; neutral face/body view, owned fictional design'
```

This local operation uploads nothing and never edits `brief.json`. It writes a
PNG named by its full SHA256 and a registry with source hash, pixel crop and
permission/provenance note. The brief must bind that returned path explicitly.
Never overwrite a reference or rerun a crop script that rewrites character text.
Importing a different crop creates a different asset. An older accepted source
version is valid identity evidence even if a newer production panel is selected.

Use neutral, clean views for the angles the film needs; more references is not
automatically better. New stored-model profiles permit up to fourteen references
per shot, normally only 2–4 useful ones; legacy profiles retain four. Each
reference is assigned a role in the compiled prompt. The selected
model's live schema remains authoritative; no SDK or model switch is automatic.

## 3. Separate identity and changeable state

Example `brief.characters` entry (replace the path with an imported asset):

```json
{
  "id": "juno",
  "identity": "Adult woman, short dark hair with one narrow bleached streak",
  "references": ["media/references/FULL_SHA256.png"],
  "permission_confirmed": true,
  "default_state": "arrival",
  "states": {
    "arrival": {
      "description": "Olive parka over a plain black dress",
      "attributes": {"wardrobe": "parka"}
    },
    "dancing": {
      "description": "Plain black dress, bare arms, no parka",
      "attributes": {"wardrobe": "dress"}
    }
  }
}
```

Each state may have its own `references` in addition to identity references.
State reference imports share the character's explicit depiction/upload
permission; only the resolved state's images are sent. Do not use incidental
wardrobe in an identity image as an unreviewed costume instruction.

In a shot:

```json
{
  "character_ids": ["juno"],
  "character_states": {"juno": "dancing"},
  "state_requirements": {"juno": {"wardrobe": "dress"}}
}
```

Only identity and the resolved state's description enter the prompt. Structured
requirements reject mismatches deterministically. Do not put "glasses stay on"
in identity if any shot removes them. Multi-character prose cannot reliably
assign a clothing prohibition to one person; use per-character requirements.

```sh
uv run clip preflight PROJECT --shots s019,s024,s025
uv run clip prompts PROJECT --shots s019,s024,s025
```

Preflight outputs exact prompt, references/hashes, state attributes, purpose,
must_show, framing and frame intervals. Known checks include clasp-vs-apart,
empty-vs-crowded scene, single-character clothing conflicts and ambiguous "five
fingers and a thumb". It is **not** arbitrary prose understanding. Both manual
compiled-prompt review and visual review remain necessary. Legacy projects can
inspect diagnostics without changed gates. For workflow 2, errors block
storyboard approval, quoting and generation before provider/schema calls.

## 4. Proof, a small rollout, then the full set

Choose exactly three risk proof IDs (or all if fewer), including the hardest
recurring interaction/wardrobe requirement—not three attractive portraits.
Compare models only inside a separately authorized experiment budget and use
the same actual reference-guided tasks. Evaluate first-pass fidelity and
continuity, not price/marketing or a shared seed.

After accepted proof and watched/approved proof-only preview, quote a diverse
6–8-shot subset using `--shots`. Inspect before releasing the remainder. This
small-rollout policy is directing guidance, not an automatically inferred gate.

Record every inspected selected version before proof/stills approval:

```sh
uv run clip select PROJECT --shot s024 --version 2
uv run clip review PROJECT --shot s024 --version 2 --verdict accept \
  --reviewer 'Actual reviewer / delegated agent session' --inspected \
  --note 'Examined this version; required gap and identity hold; distant paw simplified'
```

Use `reject` for obvious load-bearing anatomy/content/identity defects;
`uncertain` for details requiring a crop/comparison. Accept intentional stylised
or occluded small details with the exception in the note. Do not impose visible
pads/toe counts where the approved shot does not need them. Accept/reject/uncertain
history is bound to shot owner, version, actual bytes and generation inputs. New
selection or modified bytes cannot inherit acceptance. A later reject revokes
the gate even if an earlier stage approval exists. An acknowledgement records a
reviewer's claim; software cannot prove someone visually inspected the image.

`clip sheet PROJECT --scope stills` writes a versioned contact sheet with exact
frame interval, source owner, selected version and hash labels plus a JSON
sidecar. It is a review aid, not an approval, and does not overwrite prior sheets.

Use fresh bounded visual-review sessions with the relevant identity reference,
at most 15 image occurrences including detail crops. Return text-only coverage.
Calibrate severity on existing accepted/rejected examples before a paid film;
repeated sessions on one model are not independent confirmation. Failed/timed-
out reviewers are unavailable evidence, not PASS. No fake "all reviewed" claims.

## 5. Exact shot lookup and graphics preflight

```sh
uv run clip locate PROJECT --seconds 124
uv run clip locate PROJECT --frame 2976
uv run python -m mp3_to_videoclip.graphics --root PROJECT --base BASE.mp4 \
  --preflight --output PROJECT/work/reviews/graphics-check --times 124,129
```

Omit `--times` for representative intro phases and each overlay's midpoint (up
to 64 samples; truncation is reported). The local images show actual decoded
base frames with composited typography, plus a footer/JSON identifying exact
frame, shot/alias owner, recorded selected version/hash and overlay. Selection
metadata is not proof that an older base used those same bytes; verify its render
report before attributing a defect to the current selection. Unavailable metadata
is labelled, never guessed. Existing output directories are versioned.

Bind story-specific captions to shots instead of brittle absolute seconds:

```json
{"id":"drop","shot_id":"s025","offset_frames":12,"duration_frames":72,
 "style":"sfx","text":"DROP","x":0.74,"y":0.25,"rotation":-6}
```

The entire caption must fit inside its shot. Absolute `start`/`end` and shot-bound
forms cannot be mixed in one caption. Legacy absolute specs keep their existing
behaviour. Watch/read actual composited backgrounds, not raw alpha on grey.
Check a changed window before a full export. Intro/closing durations follow the
approved spec and remain inside the continuing original audio.

## 6. Less repeated local work, safe concurrency

- A non-proof generation-only prompt correction still needs storyboard review,
  but does not invalidate an unchanged proof-only movie. Timing, camera, purpose,
  framing, alias mapping or proof image/input changes invalidate the relevant
  proof/preview binding. No changed art is automatically reapproved.
- Overlay clips use per-element content keys; one caption edit reuses intro,
  credits and unrelated captions. The assembled alpha track keys include clip
  bytes and timing. Cache hits validate format/dimensions/frame counts; corruption
  raises an error instead of silently passing. Prior exports are never replaced.
- `clip generate PROJECT --quote ID --concurrency 2` allows 1–3 in flight (default
  1). The CLI holds the project lock. One coordinator reserves/journals before
  dispatch and writes every result; workers only submit. Stop new admission on
  errors/pending/overrun, drain existing workers, retain ambiguous UUIDs, recover
  without resubmission. Direct Python callers must hold `project_lock(root)`;
  don't launch multiple generators against the same project.

## 7. Brand identity, motion and the deeper local map

Three capabilities added after the first delivered film. All three are local and
free; none of them spends.

```sh
# A deeper music map, beside the approved analysis rather than over it.
uv run clip analyze PROJECT --deep      # writes work/music-deep.json (v3)
```

`work/music-deep.json` holds a refined pulse with its half/double ambiguity, a
candidate downbeat phase with bar-length scores, a key candidate reported next to
its runner-up, candidate section boundaries and bass-/vocal-band onsets. It is
**unreviewed measurement**: it approves nothing and never retimes an approved
edit. Because it is a separate artifact, running it can never rewrite the approved
`work/music.json`.

**One identity source.** The collaboration identity lives in the project's
`brand.json` (`mark: "filmstrip"` for the selected identity, one palette and wordmark). A graphics
spec adopts it with `design: "joint-v1"` instead of restating a palette and a
mark; a production whose opening already renders the identity sets
`plate: false` so the renderer does not also composite the plate and draw the
emblem twice. A spec with no `design` key renders exactly as before.

**Motion is part of the edit.** `dissolve_frames` (declared on the outgoing shot,
shorter than both neighbours, consumed as handles so the frame count is exact) and
`camera_path` start/end zoom with smoothing are the built-in tools. Remotion also
supports explicit `camera_keyframes`, bounded `post_effects` and `transition`
(`fade`, `wipe_left`, `wipe_right`). Deliberate holds remain valid; effects must
serve the shot rather than satisfy a motion quota. `post-editor` designs the movement and
`film-finisher` executes it; `clip-edit-graphics` and its
`references/motion-and-grade.md` carry the scales and the evidence method. Judge
motion by comparing decoded frames, and never retune a reviewed crop.

**Renderer and reviews.** New CLI productions default to Remotion; existing
project JSON without `renderer_backend` remains on FFmpeg. Opt-in migration sets
`project.renderer_backend: "remotion"` and `graphics-spec.renderer: "remotion"`,
then renews the existing content-bound gates. Install locally using
`npm ci --prefix renderers/remotion --ignore-scripts --no-audit --no-fund`; provide
local Node/Chrome, never an implicit browser download. See
[RENDERER.md](RENDERER.md) for source-of-truth, cache and compatibility contracts.

Before brief/storyboard approval, use the bounded story/board critique lanes in
`LOOP.md`: narrative + reviewed-music binding for story; visual story/continuity +
render feasibility for board. One author revision normally. Pixel acceptance
still requires actual rendered images; text critique cannot stand in for it.

## Evaluation, not a speed/quality promise

`clip costs` includes reported/reserved costs, counts by kind/model/shot and task
latencies with timestamp coverage. Report successful calls/final source panel,
first-pass accepted rate, corrected shots, correction dollars, full-export count
and elapsed time separately. Provider waits are not all wall-clock gaps; reasoning
usage is not the Runware bill. These code tests prove safeguards only, not better
images. A future small paid evaluation needs new explicit scope and allowance.

Keep the current project-scoped Runware MCP for discovery and the durable CLI
for paid operations. No new MCP server, SDK migration or global agent rerouting
is required. Original project policy overrides upstream recipes: never import
photorealistic defaults into a painted brief, assume model-choice promises, or
bypass ledger/approval/budget checks with an interactive MCP paid call.
