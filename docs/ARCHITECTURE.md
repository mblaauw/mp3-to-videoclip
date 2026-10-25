# Architecture

Two layers: a deterministic engine that owns timing, money and pixels, and a
Studio that presents it. The project folder is the single source of truth; nothing
in the app is a second state store.

## Engine (stable)

| Module | Responsibility |
| --- | --- |
| `models.py` | Pydantic contracts. All timing is integer output frames; dissolve handles cannot exceed either neighbour. |
| `timeline.py`, `pacing.py` | Frame/second lookup, shot-bound caption resolution, adaptive boundary planning with a validated tail. |
| `production.py` | Artifact IO, storyboard skeleton, reference binding, the prompt compiler and the content-bound approval chain. |
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

## Presentation

`app.py` is the FastAPI factory; `api/` exposes the five stages, approvals,
library, jobs and settings; `frontend/` is the Vite/React Studio; `jobs/` runs
local work with per-project serialisation. `launcher.py` is `uv run studio`.

The old hand-written `ThreadingHTTPServer` and its Python-string UI were removed
in the Phase 4 cleanup. `cli.py` remains for engine tasks that do not have a GUI
yet: transcription, the listening pass, backups, signing and render maintenance.

## Director gateway

The Writer/Editor gateway is an app-owned OpenCode v2 process, not the user's
shared OpenCode service. `director/opencode.py` starts `opencode serve` on a
free loopback port with a per-launch `OPENCODE_SERVER_PASSWORD` (Basic user
`opencode`), checks `GET /api/info` and refuses anything outside 2.1.4–2.1.x.
The 2.0.x line fails GPT-6.1 Sol with an auto-compaction error. On macOS the
gateway prefers the desktop app's CLI when `opencode` on PATH is older. It runs
from a dedicated workspace, so this repository's `AGENTS.md` and skills never
enter the agent prompt.

The workspace config defines two primary agents, `writer` and `editor`, with
models from Settings. On 2.1.x a blanket `*` deny is a hard deny that overrides
later allows, so the built-in actions are denied one by one; `clipstudio_*` is
allowed last. A fresh session snapshots its tool catalog, so the gateway waits
for the MCP server and creates a discardable warm-up session before the real
one. Without that warm-up the first Writer can see no Studio tools.

The `clipstudio` MCP server is
`python -m mp3_to_videoclip.director.mcp --projects-dir <absolute projects>`,
using newline-delimited JSON with the legacy protocol. It exposes the safe
director tools and withholds paid jobs (`generate_images`, `transcribe_lyrics`)
and renders. `get_images` returns MCP image content, not base64 in text.

A Studio turn opens `/api/event` before prompting, filters the global stream by
`sessionID`, maps `session.text.delta` / tool events / `session.execution.*` to
the existing `TurnEvent` shape, and persists text-only history in
`work/chat.jsonl`. Stop is the HTTP stream closing: the turn interrupts the
OpenCode session and keeps the partial text. The session is reused per
production and role while its model fingerprint matches; a primary agent's
model is **not** applied at session creation, so the gateway sets the session
model explicitly.

Known v2.1.4 limits: the event stream ignores `Last-Event-ID`, so a reconnect
must refetch `/api/session/{id}/message`; interrupt ends the step as
`finish: "error"` plus `session.execution.interrupted`; and a model missing from
`GET /api/model` is rejected before a turn starts rather than falling back to a
free catalog model.

The live probe on 2026-10-25 passed on 2.1.4 with `openai/gpt-6.1-sol` and
`opencode-go/deepseek-v4.1-flash`. Each role called `clipstudio_get_project`,
`clipstudio_get_images` (two selected stills) and its write tool; no built-in
tool ran. The Writer used 2,932 input / 118 output tokens, the Editor 3,957 /
250 and reported $0.00078. The script still refuses to spend unless authorized:

```sh
PROBE_ALLOW_SPEND=1 uv run python scripts/probe_opencode.py \
  --project <writable-copy-of-a-production> --yes
```

It refuses production folders. Use `--opencode-bin` when the supported CLI is
not the one on PATH.

## Target

```text
app.py            FastAPI factory, static files, lifespan
launcher.py       `uv run studio`: free port, build frontend if stale, open browser
api/              projects, track, story, storyboard, images, film, director, jobs, budget, approvals, settings, setup
domain/           intake, models, migration, approvals, archive, budget, lyrics
services/         analysis, generation, graphics, transcription, render, preview input, runware
director/         direct adapter, OpenCode gateway, MCP bridge, tools, context, prompts, conversation
jobs/             asyncio runner, per-project serialisation, SSE events
frontend/         Vite + React + TypeScript, @remotion/player for the real composition
renderers/remotion/src/BaseFilm.jsx + timing.mjs
                  one composition and one frame model shared by MP4 and Player
```

Every artifact has a cheap fingerprint. A changed fingerprint makes its approval
stale, and the stage says so; the gate blocks until the current bytes are reviewed
and re-approved. One budget per production pauses a paid job as `needs_budget`
when it runs out.
The phase plan and acceptance criteria are in
`.opencode/tasks/gui-rework.md`; decisions D1–D8 are in the 25 Oct 2026 brief that
record references. Renderer notes stay in `docs/RENDERER.md`.
