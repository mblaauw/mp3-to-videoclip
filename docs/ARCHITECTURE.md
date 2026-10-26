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
  brief.json            intent, treatment, look, characters, scenes, references
  work/audio/           derived excerpt WAV for promo/advert (source stays untouched)
  work/music.json       measured beats/energy/sections
  work/lyrics.json      supplied or transcribed lyrics (drafts until reviewed)
  work/storyboard.json  shots: stable ID, frames, kind, purpose, message, text, prompt, camera
  work/assets.json      generated versions per shot: path, sha256, input_hash, selected
  work/local-plates/    deterministic cards, splits, bridges, logos and end cards
  work/tasks.json       paid-task journal (reservation before submit)
  work/prompt-current.json / prompt-artifacts.jsonl
                        assembled prompt hash and file versions per turn/write
  renders/, previews/   versioned outputs plus a report JSON
  work/reviews/         graphics review material (not the verdict record)
```

`projects/`, `backups/` and `archive/` are never deleted and never rewritten in
place. Code rollback is the git tag `pre-gui-rework`; production rollback is the
metadata snapshot in `backups/` written by `scripts/snapshot_projects.py`.

## Production kinds and intake

Every new production carries `project.kind` (`music_video`, `promo` or
`advert`). The code table in `kinds.py` is authoritative for lengths, default
style, text density, pacing, opening/closing and whether the 25/40 graphics
signature is required; the prose block the Writer reads is
`director/prompts/kinds/<kind>.md`. Music videos keep the 25 s opening and 40 s
credits. Promo and advert are created with `signature_required=false`, no
`brand.json` and no `graphics-spec.json`; their final render is the film itself,
without a credits composite.

The Story intake is one card over `GET/PUT /api/projects/<slug>/intake`. It
writes `brief.intent` (objective, audience, message, reasons, tone,
mandatories, avoid, CTA, length, window), selects a style preset and, for
promo/advert, the excerpt window. The optionals are serialized only when set, so
legacy brief and project payloads keep their approval hashes.

`project.duration` is the film duration. `project.source_duration` is the full
recording and `project.audio_window` is the absolute source window with fades.
`audio.py` writes a derived PCM WAV under `work/audio/`, keyed by source hash and
window; the source MP3 is only read. Analysis, the live Player, preview, base and
final all render the excerpt. A window change is refused once a storyboard,
non-empty event map or lyrics exist, and it deletes stale measurement.

Style presets are Markdown files in `director/prompts/styles/` with a small
JSON-valued header (look, image rules, model settings, protected flag). The
settings API exposes the list. `photographic-painted-v2` keeps its approved core
verbatim and is the only protected preset; choosing it or inheriting it still
requires the core at the start of `creative.look`. Custom looks and the other
presets are not prefixed with that core.

## Writer/Editor prompts

Every prompt file starts with a `version:` front-matter block. The app assembles
one task at a time: `writer|editor/system.md`, `shared/truth.md`,
`kinds/<kind>.md`, `styles/<preset>.md` (Writer only), the task file and its
worked example. `director/prompts.py` chooses the task deterministically from
the stage and the artifacts already written: Story moves from brief to concepts
to script to revise; Storyboard loads the board task; Images loads prompts or
review; Track and Film route to the Editor. The assembled text is under 2,000
words per Writer task, excluding the project snapshot appended by the API.

`work/prompt-current.json` carries the assembled hash and every file version for
the current turn; `work/prompt-artifacts.jsonl` appends the same metadata when a
tool writes the brief, treatments, proof shots or storyboard. Chat history keeps
the metadata on the user turn. A bad output can therefore be traced to the exact
prompt revision without changing any artifact schema or approval hash.

## Shot kinds and local plates

`shotkinds.py` owns the only paid/local decision. `scene`, generated `product`
and `bridge.mode=generated` compile an image spec and may enter a quote. `card`,
`upload`, `split`, `reprise`, `logo`, `end_card`, designed `bridge` and a
`product` with an uploaded `asset` are local: Pillow renders a deterministic
full-frame PNG under `work/local-plates/`, keyed by the shot definition, project
size, source panes and `LOCAL_PLATE_VERSION`. The renderer and the Player receive
ordinary image files, so no Remotion primitive is added.

`Shot.kind`, `message`, `text`, `bridge`, `product_ref`, `panes` and `asset` are
dropped from serialization while they hold defaults. Legacy shots, briefs and
approval hashes therefore stay byte-stable. `proof_ids`, `quote_images`,
`reviews.require_accepted` and preflight operate on paid kinds only; the proof
stage hash also binds local plate bytes where they can render (or the shot
definition for a split whose panes do not exist yet), and the stills stage binds
every local plate. `GET /api/projects/<slug>/plates/<shot_id>` serves the local
file; the Player points local shots at that URL and keeps paid shots on the
existing image route.

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
from a dedicated workspace, so this repository's `AGENTS.md` and prompt files
never enter the agent prompt.

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
