# T2 — Production kinds, intake and brief

Status: complete
Revision: merged as ff7be5b (PR #20), from branch commit 0d531a1
Authorized: 2026-10-25, owner said "continue and do the whole of T2".

## Objective

Make the Studio capable of three production kinds (music video, promo, advert)
with a kind-appropriate intake, a creative `brief.intent`, an excerpt audio
window with fades, and style presets that are selectable rather than a mandatory
photographic-painted core.

## Accepted defaults

- Q1–Q6 from the Writer/Editor brief stand unless the owner overrides them.
- Music video keeps the 25 s opening + 40 s credits signature. Promo and advert
  do not require it.
- Advert lengths offered: 6, 15, 20, 30, 60 s; any positive length is accepted
  by the API. Promo offers 30–120 s plus the full track.
- Default styles: music video `photographic-painted-v2`, promo and advert
  `clean-photographic-v1`.
- The full source MP3 is immutable. An excerpt is a derived WAV under `work/`.

## Acceptance

1. Creating an advert asks for objective, message, CTA and length.
2. An advert's `brief.json` intent matches the brief example: kind, objective,
   audience, message, reasons, tone, mandatories, avoid, cta, length_seconds and
   audio_window.
3. A 30 s excerpt renders with a 1.5 s fade-out, and every render path muxes the
   excerpt instead of the full source.
4. Style presets are files under `director/prompts/styles/`, exposed as a list,
   and the photographic-painted core is enforced only when that preset is
   selected.
5. `pytest`, `ruff check`, `ruff format --check` and the frontend build pass.

## Constraints

- Never write `projects/`, `backups/` or `archive/`.
- Source audio and stills are immutable.
- No paid provider call in tests or during implementation.
- Legacy `Project` and `Brief` serialization must stay byte-stable when the new
  optional fields are unset; `stage_hash` includes both payloads.

## Decisions

- One canonical excerpt window lives on `Project` (`audio_window`, `duration`
  and `source_duration`). `Brief.intent.audio_window` mirrors it for the Writer.
- The Story intake save applies intent, style preset and window together and
  deletes stale measurement; the user re-runs local analysis.
- Kind files and the style files carry a small JSON-valued front matter block so
  no YAML dependency is added.
- The kind table is code (`kinds.py`) and the prose is `prompts/kinds/*.md`; the
  code table is authoritative for lengths, defaults and signature.

## Open questions

None blocking. Reference-image upload in the intake is not part of T2; the card
accepts reference links and the existing reference flow stays the image path.

## Implementation

- `models.py` / `domain/models.py`: optional `Project.kind`,
  `source_duration`, `audio_window`; `Brief.intent` with CTA, audience, reasons,
  tone, mandatories, avoid, window, notes, MV about/performance, links and
  assets. None/empty fields are dropped so legacy payload hashes are unchanged.
- `kinds.py` and `director/prompts/kinds/*.md`: one table and three prose blocks
  for purpose, lengths, structures, shot mix, text density, pacing,
  opening/closing, signature and style choices.
- `production.py`: kind-aware init, excerpt window validation, kind-based
  signature package (music video only), Story intake apply, style preset apply
  and legacy-safe project/brief writes.
- `styles.py` and `director/prompts/styles/*.md`: four preset files, a settings
  list, and the protected photographic-painted core. Only that preset is forced
  to keep the verbatim core.
- `audio.py`: derived PCM excerpt keyed by source hash/window, fades, full-track
  waveform peaks and a cache.
- `api/story.py`, `api/track.py`, `api/projects.py`, `api/settings.py`: intake
  GET/PUT, excerpt audio route, kind/window/style/intent fields, preset list.
- `services/analysis.py`, `services/render.py`, `services/preview.py`,
  `preview.py`, `cli.py`: every analysis/render/Player path uses the excerpt.
- `api/director.py` / `director/context.py`: kind block, W1 brief task and the
  intent/window in the Writer snapshot.
- Studio: kind/style/advert fields in New Production; Story intake card with
  kind-dependent fields and a draggable excerpt waveform; Track hides lyrics for
  promo/advert; library shows kind.

## Evidence

- `uv run pytest -q`: 859 passed, 1 skipped.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: clean.
- `cd frontend && npm run build`: clean.
- Real 120 s source, advert window 62–92 s, fade-out 1.5 s:
  `Project.duration=30.0`, `source_duration=120.0`, source hash unchanged;
  brief intent matched the example exactly; excerpt measured 30.0 s; middle RMS
  0.084, last 0.25 s RMS 0.0106.
- `tests/test_audio_excerpt.py` also muxes that excerpt through Remotion's real
  FFmpeg path with a fake silent base and measures the same fade in the output.
- `tests/test_api_intake.py` proves the upload asks for and persists advert
  objective/message/CTA/length, skips the signature, and the intake update
  applies style and window.

## Acceptance mapping

1. New Production shows Advert, objective, key message, CTA, URL and length;
   the API rejects an advert without objective, message, CTA or length.
2. Direct advert intake and the Story intake produce the example intent,
   including reasons, tone, mandatories, avoid, CTA and window.
3. The excerpt is a derived WAV; analysis, Player URL, preview, base and final
   receive it; the 30 s/1.5 s mux is measured, not inferred.
4. Four preset files are exposed by settings; only `photographic-painted-v2`
   enforces the verbatim core.
5. Full checks are green.

## Limitations

- Reference-image upload is not in T2: the intake card takes reference links and
  product/brand asset notes, while image references remain the existing
  permission-gated import flow. No invented asset is accepted.
- `Intent.length_seconds` is whole seconds; a fractional window is preserved in
  `audio_window` and the film duration, while the intent rounds to the nearest
  second. The UI offers whole-second choices.

## Merge

PR #20 squash-merged as `ff7be5b`; the branch commit `0d531a1` and the
merge tree are identical. CI check passed (4m35s) after the first runner was
cancelled for a stuck `apt-get install ffmpeg`.
