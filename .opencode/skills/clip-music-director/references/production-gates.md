# Production gates (shared)

## Path notation

Sibling `../clip-...` and `references/...` links are relative to the skill or
reference that contains them. Bare Python filenames in Code lists denote modules
under the workspace's `src/mp3_to_videoclip/` directory, not new files next to
the skill. `work/...`, `brief.json` and media/assets paths denote artifacts inside
the selected production directory. Shell commands are examples, not file links.

One place for the gates every stage shares. Stage skills add their own detail;
they do not restate these.

## 1. Authority and spending

- A cumulative cap (`clip budget PROJECT --cap ... --max-corrections ...`) plus a
  per-quote `authorize` decision exist **before** any upload or inference. The
  budget artifact records authority; it is not authority to invent a cap.
- All image/audio/listening/transcription tasks share the cap: actual reported
  cost plus every unknown-cost reservation. An unpriced task without a reserve
  is not admitted. HTTP errors and `taskNotFound` do not prove zero billing.
- Reservations are admitted at submission. Authorizing several quotes does not
  permit their combined submissions to exceed the allowance.
- MCP/public schema is for **discovery**, the tracked CLI executor for **paid**
  work. An interactive MCP paid call is not budget-enforced. If using MCP for a
  paid generation, equivalent durable request/result/cost tracking must exist
  first; otherwise do not call it.
- No free/billed repair assumptions: alternatives, upscales, masked edits and
  reference uploads each need their own authorized quote. Never borrow an audio
  allowance for images (or the reverse).

## 2. Approvals are content-bound

- Approve brief → storyboard → proof → full still set, in order, on the user's
  decision. Never self-approve. A changed artifact (bytes, timing, camera,
  framing, purpose, proof image, alias mapping) invalidates the approval it
  changes and requires renewed review.
- `clip review` accept/reject/uncertain is bound to shot owner, version, actual
  bytes and generation inputs, with an inspection acknowledgement, reviewer and
  note. A later reject revokes the gate even if an earlier stage passed.
- A user may delegate remaining creative decisions for one production. Preserve
  the exact scope; label results **agent-reviewed under delegation**; obtain the
  actual cap; do not extend it to new models, new productions or real-person refs.

## 3. Review budget and honesty

- **One quick actual inspection of every generated image is mandatory.** No
  sampling, no "looks fine from the prompt", no reporting an unseen file as
  reviewed.
- Spend detailed/deep review only where there is an obvious or load-bearing
  issue (identity, required content, anatomy that the shot depends on).
- Fresh bounded sessions: **at most 15 image occurrences per session, including
  reference and detail crops** — practically **6–8** per pack, with headroom kept
  below the ceiling. Inventory and deduplicate first, keep coverage complete, and
  add no mandatory re-reads or per-frame review divisions. Return text-only
  coverage; never forward images into the coordinating session.
- A failed/timed-out reviewer is unavailable evidence, not a PASS. Repeated
  sessions on one model are not independent confirmation; stop re-confirming
  with a single model. Calibrate severity on existing accepted/rejected examples.
- Severity calibration: accept intentional stylisation and simplified or
  occluded distant detail (for example stylised distant digits or paw pads)
  unless the approved shot genuinely depends on it. Do not impose toe counts,
  visible pads or readable distant fingers.

## 4. Repair ladder

1. Keep the original plus **one** correction by default (`DEFAULT_MAX_CORRECTIONS
   = 1`, see `default-style.md`).
2. After that, do not silently roll again. **Diagnose** the failure and record an
   explicit **restage** (`clip restage`) with the changed approach before another
   cycle.
3. Prefer containment over a whole-frame reroll: a crop/composite for a small
   isolated defect, a reprise of an accepted panel for a repeated composition, a
   restaged framing for a wrong composition. Two failures at the same requirement
   means the inputs or approach are wrong, not that another roll will fix it.
4. Repairs land **before** a whole-frame batch roll or export; never re-render an
   entire set to fix one detail unless the user authorizes the scope.

## 5. Delegation and reporting

Finish any stage by reporting, separately:

- what local tooling **measured**;
- what a provider model **reported** (billed/evidenced, unreviewed);
- what a human or bounded session **actually inspected** (coverage listed);
- what was **technically verified** (ffprobe, preflight, hashes);
- what remains **uncertain**;
- what **awaits the user's decision**.

Never claim you personally heard audio if only features/a model were used. Never
claim mocked tests prove real provider output, likeness or artistic quality.
