# Roadmap, November 2026 — index

**Proposed** 1 Nov 2026 for owner approval; base `main` at `c1414a3`. The
assessment behind it is `docs/design/studio-assessment-2026-10-31.md`; the owner
answered its twelve decisions on 1 Nov 2026 and asked for plans for all of it.

Every phase has its own plan in this folder, in the house format: objective, what
the code showed, decisions, tasks one commit each, not changing, acceptance, risks.
This file is the order, the dependencies and the rules that apply to all of them.

## Order and size

| # | Phase | Plan | PRs | Effort | Depends on |
| --- | --- | --- | --- | --- | --- |
| 1 | A · blocked states | `plan-a-blocked-states.md` | 1 | 1 to 2 days | nothing |
| 2 | H · settings panel and catalogue | `plan-h-settings.md` | 1 to 2 | 3 to 4 days | nothing; E wires the per-role models it stores |
| 3 | B · make it musical | `plan-b-musical.md` | 1 to 2 | 1 week | nothing |
| 4 | D · make it fast | `plan-d-fast.md` | 2 | 1 week | nothing |
| 5 | C · make it move | `plan-c-move.md` | 2 to 3 | 2 to 3 weeks | B (downbeats for motion), H (catalogue for the video model) |
| 6 | E · the Director | `plan-e-director.md` | 3 | 2 weeks | H (catalogue, per-role models), B (song map in context) |
| 7 | I · narrative films | `plan-i-narrative.md` | 4 to 5 | 5 to 7 weeks | H (voice catalogue), E5 (consistency engine for eras), C2 (depth for painted scenes), C5 (clip asset model), F1 (titles optional) |
| 8 | F · open it up | `plan-f-open.md` | 2 | 1 week | C (portrait layouts and fonts), H (brand kit) |
| 9 | G · pay down the debt | `plan-g-debt.md` | 3 | ongoing | runs behind everything; some tasks move earlier where a phase touches the same file |

F1 (titles as a preset) is needed by I before I6, so it is pulled forward and
lands as its own small PR between E and I. The G task that adds a shell-level
resource cache lands before I7, because the narrative screens build on it.

## Rules for every phase

- One commit per numbered task, one PR per phase or per listed sub-phase. Each
  phase ends with `uv run pytest`, `uv run ruff check .`, `uv run ruff format
  --check .`, the frontend `tsc`, tests and build, the renderer `npm test`, and an
  app that starts from a fresh clone.
- Approval hashes, the money journal, integer-frame timing and the golden contract
  do not change unless a plan says so, with the reason in the commit. New fields
  are serialised only when set, so existing films keep their hashes.
- No paid call in tests. A live test that spends money is listed in the plan's
  acceptance as its own line with a maximum spend and needs the owner's explicit
  authorisation each time.
- `projects/`, `backups/` and `archive/` are never deleted or rewritten in place.
- Providers: Runware is the only paid media provider for now (stills, upscales,
  clips, speech). The narrator default is MiniMax speech through Runware, voice
  `English_Magnetic_Male_2`. ElevenLabs exists as a scaffolded adapter that the
  catalogue lists only when a key is present. No local voice.
- Model providers for the Director: one multi-provider direct adapter (Phase E);
  OpenCode Go stays as a provider URL; the local OpenCode server is retired.

## Owner decisions already taken (1 Nov 2026)

1. The 25 s / 40 s signature becomes a preset, default for the owner's films.
2. Depth parallax: go, optional per film, off for existing films.
3. Generated clips per shot: opt-in, journaled like a still, after depth ships.
4. The OpenCode gateway is retired; OpenCode Go stays as a provider URL.
5. One-click first draft under a budget ceiling, with draft approvals distinct
   from the owner's.
6. The Director never authorises spend itself; every paid batch asks, with the price.
7. Phase order as above.
8. One `narrative` kind with structure templates.
9. Shots bind to narration lines; frames are re-derived from kept takes.
10. Runware MiniMax speech first; ElevenLabs scaffolded behind a key; no local voice;
    the $0 draft is a read-rate estimate.
11. Clips after depth parallax.
12. Invented facts only when the brief declares the world fictional, each listed.

## Phase summaries

The plan files are authoritative; this is the one-paragraph view, with the
decisions each plan still asks of the owner.

**A · blocked states** (one PR, about 4.5 days). One `engine_error()` installed as
app exception handlers: `ValueError` 400, provider errors 502 with their code, a
`no_runware_key` 409, missing artifacts 404 with a per-artifact code and never a
path; the twelve HTTP-200 error bodies become 400s. The frontend copy map covers
every code and carries an action (Open settings, Go to stage). `nextStep.ts` gets
the facts it lacks (model key, storyboard present, placeholder shots, permission
pending) and a guard that no step links to its own stage. Compact bars show the
detail. Film without a storyboard shows one card; the missing renderer card is
fixed. Placeholders read as "Needs a job"; the Storyboard header, rating refresh,
cut and titles notes, the phone tab row and transport, and error toasts as alerts.
Four Playwright smoke tests over the blocked states. Decisions: adopt Playwright
through pytest-playwright (yes); 404 with per-artifact codes; a
`placeholder_shot_ids` field on the storyboard; placeholders shown empty with the
engine marker written back on an empty save; `role=alert` for error toasts only.

**H · settings and catalogue** (two PRs, about 3.5 + 4.25 days). A `catalog.toml`
and `catalog.py` of providers, models and voices with capabilities, unit prices
carrying a source and a date, a recommended flag, and on-demand refresh from
OpenCode, Runware model search and ElevenLabs voices behind a key. Settings schema
2 by role, voices, pictures, keys, new-film defaults with a brand kit, prices and
computer, with the thirteen flat names kept as computed properties so no caller
changes, and a v1 migration. Routes for the catalogue, tests per provider and per
voice, costs from every journal, and cache listing and clearing through an
allowlist. The panel: tab rail, search, "what is missing" checklist, per-field
Saved, reset to recommended, "Other…" on every dropdown, the MiniMax default voice,
ElevenLabs only with a key, the Critic greyed. Decisions: `tomli-w` for nested
TOML; a voice sample is free from the provider's preview else bought once on an
explicit click; clearing `work/remotion-chunks` and `work/remotion-assets` inside
productions as a written exception to the never-delete rule; keep the owner's two
names as defaults until F1; prices only with a source and a date.

**B · musical** (two PRs, about a week). A `song_map.py` merging the quick and deep
measurements with the owner's section layer into one cached `work/song-map.json`,
served, injected into every Writer task and given to both roles as a tool; sections
from the checkerboard novelty peaks live in the song map only so `music.json` and
every hash hold; the deep pass becomes the second phase of the standard analysis
job; lyrics with times and the whole treatment reach concepts, script and import;
`pacing.py` gains grid tiers (section start, sung line, downbeat, change snapped to
a downbeat, beat, each led by a frame or two) and split points on bar lines using
crop cuts, with quiet sections stretching toward holds; captions from
`lyric-timing.json` as text layers plus SRT and VTT. Decisions as recommended in
the plan, including the join order and what "merge when quiet" means.

**C · move** (four PRs, about four weeks). C-1 sharper and typed: a journaled 2×
upscale as a derived still version, a 1024 px rotated grain tile, three OFL display
faces embedded per look. C-2 depth: a local `depth.py` job (Depth Anything V2
Small, cached by still hash) and parallax layers in the composition as pure frame
functions, `grade.look.depth` per film with a per-shot off switch, off for existing
films. C-3 motion and look: easing curves, ramps and impulses on downbeats from the
song map, bloom, halation, flare, dust and haze as look options, text decorations
and safe areas, per-word lyric timing. C-4 clips: one image-to-video model from the
catalogue, 5 s clips as journaled asset versions with a clip layer in both outputs.
Decisions: upscale rather than a larger native size; factor 2; depth per film and
per shot; the tile over per-pixel noise; Inter, Fraunces and Bebas Neue; two capped
paid batches for acceptance (up to 10 upscales, up to 3 clips of 5 s).

**E · the Director** (three PRs, about two weeks). E-1: provider plugins behind the
one adapter (OpenAI-compatible, Anthropic, Gemini), per-role provider and model,
the gateway retired with `director/mcp.py` kept for outside agents, usage priced
from the catalogue into `work/model-usage.jsonl` and shown under each answer and in
the budget popover, the loop keeping its own reasoning across compaction. E-2: a
`shared/craft.md` under 380 words, three new example idioms, a context that hears
the song map and sees the owner's references, `creative.sections[]` for the
evolving look, compiler version 3 for new films (subject before look, negative
prompt, per-shot seeds) so existing films keep their hashes, character sheets and
scene plates bought and bound from the World tab, edit-mode redos. E-3: typed tool
schemas, a required reason on every write persisted to `work/decisions.jsonl` with
diffs in the tool row, five new tools, the one-click first draft as a job under a
$1.00 default ceiling with draft approvals that unlock only brief, storyboard and
the proof batch, and the creative evaluation with a judge from another provider
where two keys exist. Decisions as recommended in the plan.

**I · narrative films** (four PRs, about 33 days). Step 1: `Project.spine =
"soundtrack"`, `audio.build_soundtrack` as the clock with a read-rate estimate,
`work/script.json`, beats from structure templates, the `script` and `voice`
approvals, the Script stage and a 2:00 film playing silently in the Player from a
script. Step 2: `narration.py` on the journal's pattern with Runware MiniMax takes
and an ElevenLabs scaffold, takes reviewed like stills, the Writer's script and
narration tasks with the five-beat, place-across-time, essay and fable templates.
Step 3: `plate`, `era`, `document`, `date_card` and `title_card` kinds, the
painted-documentary, archival and illustrated looks, the narrator and place with
eras in the profile, the mixer with ducking and loudness in the soundtrack build,
captions and sidecars. Step 4: clips after C-4. Decisions: mixer in the soundtrack
build; duration leaves the project hash only for soundtrack films; brief, script,
voice, storyboard in that order; a stale take stays audible but blocks the voice
approval; one capped first batch ("The Last House Key", at most 25 lines, cap
$3.00); word timing through the lyric tools where set up; captions not burned in
by default; short clips hold their last frame.

**G · debt** (three PRs, about 20 days). G-1: FFmpeg helpers out of the renderer,
the zoompan path and the animatic deleted, schema 3 only with the version fields
kept inert so hashes hold, the golden regenerated on a schema-3 fixture, the
compositor and its caches behind the CLI as `legacy/` with slow tests. G-2: a CLI
dispatch table with 14 commands and 20 deleted, `edits.report` as finding
families, approve and dispatch as tables, reservation from published pricing,
a streamed upload, pixel goldens as a separate Chrome-gated script in CI. G-3: one
shell-level resource store, the OpenAPI generator deleted, the three large
components split, stylesheets into the token system, ESLint. Decisions: the pilot
production becomes an archive; delete rather than move the FFmpeg renderer; refuse
a final whose titles review came from the old compositor; inert version fields.

**D · fast** and **F · open it up**: plans in progress; summaries follow when they
land.
