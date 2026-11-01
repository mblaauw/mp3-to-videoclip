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

Filled in from each plan as it lands; the plan files are authoritative.
