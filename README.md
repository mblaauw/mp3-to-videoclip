# mp3-to-videoclip

One local web app that turns an MP3 into a finished videoclip: import the track,
talk to a built-in director, review the storyboard and the stills, and render the
film. Money records, the library, source audio and generated stills are kept
locally. Only an explicitly authorized paid transcription, listening pass or
image batch sends the required bytes to the provider.

**Current state (25 Oct 2026): the new Studio is live.** `uv run studio` opens the
library, creates a schema-3 production from an MP3, measures it locally, and takes
it through Track, Story, Storyboard, Images and Film with content-bound approvals
and a job tray. The waveform timeline, the Remotion Player preview, the error tray,
image reviews, the preview and graphics attestations and the stills approval are
live. The old interim server and its Python UI are gone; `clip` remains only for
engine tasks that have no GUI yet (transcription, listening, backups, signing,
maintenance). The phase plan and acceptance criteria live in
`.opencode/tasks/gui-rework.md`; the decisions came from the 25 Oct 2026 brief it
references.

## What works today

- Integer-frame storyboard over the real recording, stable shot IDs, validated
  dissolve handles (`models.py`, `timeline.py`, `pacing.py`).
- Local music measurement: tempo, beats, energy, rough sections, deep pass
  (`analysis.py`, `deep_analysis.py`). No upload, no invented meter or lyrics.
- Versioned stills with an input hash per version, so the app can tell which
  images came from an older prompt (`production.py`, `generation.py`).
- Paid image batches with a pre-submit journal: task UUID and reservation are
  written **before** the request, recovery happens by UUID and never resubmits,
  and an unknown cost keeps its reservation until the provider reports it.
- Remotion for stills-film previews, the final cut and the live Studio Player;
  FFmpeg for probe, mux and verification (`remotion.py`, `render.py`). The Player
  runs the renderer's own `BaseFilm` and `timing.mjs`, so the live picture uses
  the same spans, camera, grade and transitions as the MP4.
- A measured waveform under the storyboard; drag a boundary (or use the arrow
  keys) and both adjacent shots resize without moving later cuts.
- Read-only archive view of frozen productions (`domain/archive.py`).
- Image reviews bound to exact versions and bytes, plus content-bound brief,
  storyboard, proof, preview, stills and graphics approvals in the Studio.

## Setup

```sh
uv sync
uv run studio
```

That is the whole install. The Studio serves the committed frontend build; the
first launch installs the pinned renderer packages if they are missing (no browser
download, no paid call) and never invokes `tsc` without frontend dependencies.
The Film screen shows a setup card when the local renderer is missing; the card
lists any missing system tool as well.

Also required on `PATH`: `ffmpeg`, `ffprobe`, `node` (the Remotion renderer is
pinned in `renderers/remotion/package.json`). Frontend development is the only
reason to run `npm ci --prefix frontend`; the renderer install is
`npm ci --prefix renderers/remotion --ignore-scripts` when diagnosing a failed
first run.

The Runware key can be saved in the Studio settings file or supplied as
`PROJECT_VEIL_RUNWARE_API`; a saved key wins. It is only needed for paid image,
transcription or listening work; analysis and rendering are local. Never commit it
or write it into a production folder.

## Using the Studio

```sh
uv run studio                  # free loopback port, opens the browser
uv run studio --port 8799
```

**New production:** press *+ New production*, drop an MP3 (25 MB limit) and choose
a title, starting budget and 16:9 or 9:16. The app probes and copies the source,
writes a schema-3 production, and queues the local analysis job. Paste LRC
timestamps in Track when the track has vocals; no lyric position is invented.
In Storyboard, drag the gold boundaries over the waveform (or focus one and use
the arrow keys) to retime the cut; later cuts stay put. Film shows a live Player
preview from the selected stills and the source audio before you render. It runs
the renderer's own composition and timing module, not a second approximation.

**Director:** add `llm_api_key` (and optionally `llm_base_url` / `llm_model`) under
`[settings]` in `~/.config/mp3-to-videoclip/settings.toml`, or set
`OPENAI_API_KEY`. The Runware key can also live there instead of the environment.

Approvals, reviews and spending are content-bound: bytes, prompt inputs and
quote scopes are hashed, so changing an artifact invalidates its approval instead
of silently inheriting it. Renderer approvals bind the renderer source, locked
dependencies, font and output bytes; a Chrome security update changes no approval. Archived films open read-only; every stage endpoint
refuses to write to them.

## Checks

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

`tests/test_contract_golden.py` pins the compiled prompt, the frame timing and the
Remotion request; regenerate it only for an intended change and say why in the
commit. No test makes a paid call.

## Repository

```text
src/mp3_to_videoclip/    engine: models, timing, generation, renderer, CLI
renderers/remotion/      pinned Remotion renderer (render.mjs)
projects/                productions (gitignored, never deleted, never rewritten in place)
backups/                 metadata snapshots and private archives (gitignored)
docs/ARCHITECTURE.md     how the pieces fit together
.opencode/skills/        craft notes kept until they are distilled into director prompts
```

## How it fits together

One FastAPI process, one job runner, one event stream and a Vite/React frontend;
the in-app director owns the LLM turn, the paid batch and the render, and the user
moves freely between Track, Story, Storyboard, Images and Film. The old server
and its UI are deleted; `cli.py` stays only for engine tasks without a GUI yet.
See `docs/ARCHITECTURE.md` and the task record.
