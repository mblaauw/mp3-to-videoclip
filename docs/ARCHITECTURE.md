# Architecture

Two layers: a deterministic engine that owns timing, money and pixels, and a
presentation layer that is being replaced. The project folder is the single source
of truth; nothing in the app is a second state store.

## Engine (stable)

| Module | Responsibility |
| --- | --- |
| `models.py` | Pydantic contracts. All timing is integer output frames; dissolve handles cannot exceed either neighbour. |
| `timeline.py`, `pacing.py` | Frame/second lookup, shot-bound caption resolution, adaptive boundary planning with a validated tail. |
| `production.py` | Artifact IO, storyboard skeleton, reference binding, the prompt compiler and the legacy approval chain that the rework removes. |
| `analysis.py`, `deep_analysis.py` | Local measurement only. Every estimate is labelled; nothing invents meter, sections or lyrics. |
| `generation.py`, `providers.py` | Runware client with pre-submit journaling: reservation and task UUID are durable before the request; recovery is by UUID and never resubmits; changed bytes are quarantined. |
| `budget.py` | Cap, committed cost, unresolved reservations, admission. |
| `remotion.py`, `render.py`, `graphics.py` | Remotion render entry plus FFmpeg probe/mux/verify and the graphics spec. |
| `domain/archive.py` | Read-only view of frozen productions (title, duration, newest final render, selected stills). |

## Production folder

```text
projects/<slug>/
  project.json          slug, title, duration, fps, aspect, model settings, source hash
  media/song.mp3        immutable source audio
  brief.json            treatment, look, characters, scenes, references
  work/music.json       measured beats/energy/sections
  work/lyrics.json      supplied or transcribed lyrics (drafts until reviewed)
  work/storyboard.json  shots: stable ID, frames, purpose, prompt, camera
  work/assets.json      versions per shot: path, sha256, input_hash, selected
  work/tasks.json       paid-task journal (reservation before submit)
  renders/, previews/   versioned outputs plus a report JSON
  work/reviews/         graphics review material (not the verdict record)
```

`projects/`, `backups/` and `archive/` are never deleted and never rewritten in
place. Code rollback is the git tag `pre-gui-rework`; production rollback is the
metadata snapshot in `backups/` written by `scripts/snapshot_projects.py`.

## Money and evidence

The journal is the only thing that protects real money, so it stays strict: a
quote is scoped and hashed, authorization is user-owned, a submission is recorded
before it is sent, recovery is by UUID, and an unreported cost keeps its
reservation. Rendering, analysis and verification are local and free.

## Presentation (being replaced)

`serve.py` is a hand-written `ThreadingHTTPServer` that serves a review UI built
from Python string literals (`studio_ui*.py`, `human_*.py`), with content-hashed
approval stages and a terminal-enabled action capability. It is deliberately left
running until its replacement lands.

## Target

```text
app.py            FastAPI factory, static files, lifespan
launcher.py       `uv run studio`: free port, build frontend if stale, open browser
api/              projects, track, story, storyboard, images, film, director, jobs, media, settings
domain/           project store, schema 3 models, storyboard, prompts, staleness, budget
services/         analysis, generation, transcription, render, runware
director/         OpenAI-compatible adapter, tools, context, prompts, conversation
jobs/             asyncio runner, per-project serialisation, SSE events
frontend/         Vite + React + TypeScript, @remotion/player for the real composition
packages/composition/  shared Remotion compositions for renderer and browser
```

Staleness replaces approvals: a cheap fingerprint per artifact drives an "made
from an older version" badge and a "Regenerate affected" action, never a block.
One budget per production pauses a paid job as `needs_budget` when it runs out.
The phases, decisions (D1–D8) and acceptance criteria are in
`.opencode/tasks/gui-rework.md`; renderer notes stay in `docs/RENDERER.md`.
