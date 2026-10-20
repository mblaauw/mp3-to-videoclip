---
name: clip-music-analysis
description: Stage 1 of an MP3-to-videoclip production. Measure the actual recording, build the music map, and get reviewed musical events approved. Use before any story/brief work, for local analysis, the optional paid listening pass, event maps and timing evidence. Does not write a treatment or spend without authority.
---

# Stage 1 — Music analysis

**Job:** understand the *actual* recording from measured evidence plus one
reviewed interpretation, and freeze a musical event map the story can bind to.
**Position:** first stage. Its output is the timing evidence for storyboard and
edit. Links: `../clip-music-director/SKILL.md` (router),
`../clip-music-director/references/production-gates.md` (authority),
`../../../docs/MUSIC_LED.md`, `../../../docs/PRODUCTION_WORKFLOW_V2.md`.
Code: `src/mp3_to_videoclip/music_analysis.py`, `music_map.py`, `timeline.py`.

## Inputs

- Source MP3 imported by `clip init` (never re-encode or trim it).
- Optional supplied style/lyric blocks — kept as **intended context**, separate
  from audio evidence. Never force their order or meaning onto the MP3.
- Spending authority (`clip budget`) and, only if chosen, a per-quote
  `authorize` for the paid listening pass. Without it, do local analysis only.

## Do

1. `clip analyze` — local beat/energy/rough-section analysis plus half-second
   level, bass-share, brightness/centroid and onset-density measurements, 8 s
   summaries, 24 s pulse candidates with half/double ambiguity, and **unreviewed**
   change candidates.
2. Optionally `clip quote-music` → user `authorize` → `clip listen` for the
   audio-blind listening pass (approximate passages, groove, texture, subjective
   energy/tension, uncertainty, hook drafts). Raw/cost/usage are journaled before
   parsing; an invalid result stays billed and never auto-retries.
3. If a listening draft exists, `clip music-map` combines it with measurements,
   keeping provenance separate. Without paid listening, review `work/music.json`
   and `work/events.json` directly; do not call music-map or invent a draft to
   satisfy a gate. An empty reviewed event map is valid.
4. In vocal mode, import supplied lyrics or use the authorized transcription
   flow, then review/correct and approve the lyric draft. Music-led chants can
   remain contextual; instrumental mode has no lyric stage.
5. Review the available evidence with the user and correct events.

## Outputs and exit gate

- `work/music.json`, `work/music-map.md/json`, and — when the user accepts the
  reviewed events — `work/events.json` with `timing_basis` recorded honestly.
- **Exit gate:** the user has reviewed the map; timings/interpretation are
  corrected; approved events are explicitly approved (an empty map can be
  approved deliberately).

## Boundaries

- Measurements are **not** instruments, genre, key, meter, emotional meaning or
  verified sections. Loudness is not tension or excitement. Never invent a genre,
  meter, language, time signature or drop that the audio does not evidence.
- A model's confident wording is not proof of granularity. If it misses required
  detail, keep its billed raw result and flag the limitation; no silent model
  upgrades, no endless paid retries. Each refinement needs an exact quote.
- **Instrumentals: no transcription, no invented words and no lyric timestamps.**
  The structural musical timing needed for editing is still built locally.
- A supplied "drop"/"chorus" label is not evidence the recording drops or has a
  chorus. Sparse vocal chants are optional accents, never a compulsory
  lyric-to-image story.
- Paid listening is optional and only after the user reviews the local map and
  authorizes the upload/model/budget.
- Reviewed events are **edit opportunities**, not compulsory cuts. The actual
  cadence (typical 4–6 s holds with 1.5–3 s inserts on an energetic mix) is
  decided in `clip-storyboard`, not here. A fingerprint calibration
  (`clip style-test`) is a paid single-image style job, not music analysis.
