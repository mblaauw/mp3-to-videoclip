---
name: clip-image-production
description: Stage 6 of an MP3-to-videoclip production. Quote, get authorized, and generate stills through the tracked executor with durable cost/journal records. Use for spending requests, image generation batches, concurrency and recovery. Never calls paid Runware tools without an authorized quote.
---

# Stage 6 — Image production

**Job:** produce the approved stills with tracked spending and no silent model
drift. **Position:** after prompt inspection, before review. Links:
`../clip-music-director/SKILL.md`,
`../clip-music-director/references/default-style.md`,
`../clip-music-director/references/production-gates.md`. Code:
`generation.py` (`DEFAULT_MODEL`, `quote`, `authorize`, `generate`, `recover`,
`resolve-task`), `budget.py`, `cli.py`.

## Inputs

- Inspected compiled prompts for the approved scope.
- A cumulative `clip budget` cap and explicit per-quote authority from the user.
- Immutable, role-labelled reference assets (`clip reference-import`).

## Do

The same bounded stage runs twice: proof first, then rollout/full stills. Proof
images must be visually reviewed and approved; invoke edit/graphics for a watched
proof-only preview and its approval **before** quoting stills. Then generate a
6–8-shot diverse rollout, review it, and expand only after it holds. These remain
the existing CLI gates, not additional automatic purchasing stages.

1. `clip quote` for the exact scope (shots, model, size, settings). Check the
   live schema/price; the model must be `live` and accept the declared
   `project.native_size`.
2. Show the quote; obtain the user's `clip authorize`. Authorizing does not
   generate or upload.
3. `clip generate PROJECT --quote ID --concurrency N` (1–3 in flight, default 1).
   The CLI holds the project lock; one coordinator reserves/journals before
   dispatch and writes every result. Stop new admission on errors/pending/
   overrun; drain workers; retain ambiguous UUIDs and `recover` — never resubmit.
4. `clip costs` — report actual/reserved dollars, counts by kind/model/shot and
   task latencies separately from elapsed time.

## Style calibration (single image, not a batch)

A fingerprint calibration is not a production batch: use the tracked single-image
path `uv run clip style-test PROJECT quote|run|recover` (root-argument form; check
`clip style-test --help`), which reuses the existing quote/authorize/journal/
recover helpers and records the prompt, settings, schema, request, cost and hash.
One control image (Nano Banana 2.1, control fixture, no references, no automatic
retry). Its result is a **candidate** the user judges — it never becomes the
golden reference automatically, and an older film's reference set is history.

## Defaults (link, do not restate)

- Resolve the stored production choices and `profiles.py`; use
  `../clip-music-director/references/default-style.md` for the canonical policy.
  Overrides must be explicit and recorded; never inherit Google-specific
  controls into an unrelated model override.
- A `seed` may be set for reproducibility but is **not** an identity lock.
- Normally bind **2–4** useful immutable references; the live schema sets the
  hard cap (up to ~14) and is the only hard limit — never hard-cap at 4. Bind
  identity/load-bearing refs only; a populated scene anchor is for geography
  continuity, not for pinning poses. More references is not better.
- Default correction policy: **one original plus one correction**
  (`DEFAULT_MAX_CORRECTIONS`) — see stage 7 before spending on a correction.

## Boundaries

- **No paid model comparisons by default.** The user chose the default model;
  compare alternatives only inside a separately authorized experiment allowance,
  on the same reference-guided tasks, judged on first-pass acceptance and
  continuity — not price or a shared seed.
- MCP/public schema is for discovery. Paid calls go through the tracked CLI
  executor; an interactive MCP paid call is not budget-enforced. Do not install
  the optional Runware CLI or replace the executor in this change.
- Unknown billing keeps its reserve; HTTP 400 / taskNotFound is not proof of
  zero billing. Never print keys or put them in artifacts.
- **Exit gate:** every requested image has a durable journaled record (or an
  explicit ambiguous/recovered state) and `clip costs` reconciles.
