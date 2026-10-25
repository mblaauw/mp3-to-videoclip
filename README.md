# mp3-to-videoclip

One local web app that turns an MP3 into a finished videoclip: import the track,
talk to a built-in director, review the storyboard and the stills, and render the
film. Money, source audio and generated stills stay on this machine.

**Current state (25 Oct 2026): mid-rework.** The engine, the paid-task journal and
the renderer are mature. The GUI is still the interim Studio reached through
`clip`, and the in-app director is being built. The phase plan, decisions and
acceptance criteria live in `.opencode/tasks/gui-rework.md`.

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
- Remotion for both stills-film previews and the final cut; FFmpeg for probe,
  mux and verification (`remotion.py`, `render.py`).
- Read-only archive view of frozen productions (`domain/archive.py`).

## Setup

```sh
uv sync
npm ci --prefix renderers/remotion --ignore-scripts
```

Also required on `PATH`: `ffmpeg`, `ffprobe`, `node` (the Remotion renderer is
pinned in `renderers/remotion/package.json`).

The Runware key is read from `PROJECT_VEIL_RUNWARE_API`. It is only needed for
paid image work; analysis and rendering are local. Never commit it or write it
into a production folder.

## Using the interim Studio

```sh
uv run clip init PROJECT --source song.mp3 --title "…"   # new production
uv run clip serve --projects-dir projects               # review-only over loopback
uv run clip serve --projects-dir projects --actions     # add human decisions (TTY)
uv run clip status PROJECT
```

Ordinary stages remain review-and-decide in the browser. Paid work is quoted,
authorized and then executed exactly once:

```sh
uv run clip quote PROJECT --shots s001,s002
uv run clip authorize PROJECT --quote Q0001       # redirects to the Studio
uv run clip generate PROJECT --quote Q0001
```

Approvals, reviews and spending are content-bound: bytes, prompt inputs and
quote scopes are hashed, so changing an artifact invalidates its approval instead
of silently inheriting it.

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
src/mp3_to_videoclip/    engine: models, timing, generation, renderer, interim Studio
renderers/remotion/      pinned Remotion renderer (render.mjs)
projects/                productions (gitignored, never deleted, never rewritten in place)
backups/                 metadata snapshots and private archives (gitignored)
docs/ARCHITECTURE.md     how the pieces fit and where the rework is going
.opencode/skills/        craft notes kept until they are distilled into director prompts
```

## Where the rework is going

One FastAPI process, one job runner, one event stream and a Vite/React frontend;
the in-app director owns the LLM turn, the paid batch and the render, and the user
moves freely between Track, Story, Storyboard, Images and Film. The interim
Studio, the CLI surface and the approval machinery are deleted once their
replacements land. See `docs/ARCHITECTURE.md` and the task record.
