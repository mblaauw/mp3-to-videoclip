# Studio redesign — handover

A redesign of the mp3-to-videoclip Studio GUI, ready to implement locally by you
or a code agent. Based on a hands-on audit of `main` at `7b93068` (25 Oct 2026),
re-checked against `42a33cf` (26 Oct 2026, after T0–T5 landed) — see `05-update-42a33cf.md`.

**The change in one line:** the song becomes the spine of the app — one timeline
with waveform, named sections and a filmstrip of every shot stays docked under all
five stages — while each stage shows one clear next step, pictures at picture
size, one-click approvals and a director drawer that shows what it changed.

## What is in this folder

| Path | What it is | Read it when |
| --- | --- | --- |
| `01-ux-audit.md` | 31 findings (P1–P3) with screenshot and code evidence | You want to know *why* |
| `02-design.md` | Principles, colour, type, layout, component list, state vocabulary | You build or review the look |
| `03-screens.md` | Every screen: layout, behaviour, API calls, copy table, error mapping | You build a screen |
| `04-implementation-plan.md` | 6 phases with "done when", 12 small backend changes (K1–K12), rules | You plan or hand off the work |
| `05-update-42a33cf.md` | Delta for the newer `main`: one blocking bug (K13), findings G1–G8, screen additions for kinds, intake, shot kinds, the Cut, ratings, roles; K-list status; plan changes. **Wins over 01–04 where they differ** | Before anything else |
| `tokens/tokens.css` | Design tokens, drop-in for `frontend/src/styles/tokens.css` | Phase 1 |
| `prototype/` | Clickable prototype with real test data, stills and audio | You want to feel it |
| `screenshots/current/` | The Studio at `7b93068` | Comparing |
| `screenshots/current-42a33cf/` | The new features at `42a33cf` (advert intake, shot kinds table, cut report) | Comparing |
| `screenshots/proposed/` | The prototype at 1440 (`desk-`), 900 (`tablet-`), 390 px (`phone-`) | Visual target per phase |

## Open the prototype

It loads local files, so serve the folder rather than double-clicking:

```sh
cd studio-redesign
python3 -m http.server 8811
# open http://127.0.0.1:8811/prototype/index.html
```

Try: open *Night Signal* → Storyboard (click a shot, star a shot) → Images (open
a still, press K and R, use ← →) → Film (press Play; the titles show for the first
25 s) → the budget chip, the jobs clock and the gear. Space plays/pauses; click the
waveform to seek. Data is mock: approvals and verdicts reset on reload.

## Handing it to a code agent

Copy this folder into the repo (for example `docs/design/studio-redesign/`) and
give the agent this instruction:

> Implement the Studio redesign in `docs/design/studio-redesign/`. Read
> `05-update-42a33cf.md` first; it overrides 01–04 where they differ. Start with
> its Phase 0 (K13, K2), then follow `04-implementation-plan.md` phase by phase,
> one PR per phase, with the backend changes K1–K14 where a phase needs them. Use `02-design.md` and `03-screens.md`
> as the spec and `screenshots/proposed/` as the visual target; the prototype is a
> reference, not code to copy. Do not change money, timing or rendering logic.

## Decisions baked in (change them before Phase 1 if you disagree)

1. **No left rail.** The library is its own screen; inside a film you get the full
   width plus the director drawer.
2. **Approvals stay, ceremony goes.** Content-bound approvals remain; the required
   note and "inspected the exact bytes" checkbox go (backend change K1).
3. **Neutral grey surround** instead of navy, so stills are judged without a colour
   cast; MAHA KALA gold is the only accent.
4. **Schibsted Grotesk**, self-hosted (OFL licence included in `prototype/fonts/`).
5. **Kind of film** (Music video / Promo / Advert) is a live choice in the New film
   dialog; it asks only what the kind needs and the rest moves to a Brief card on
   Story (`05-update-42a33cf.md` §3).
6. **The cut is readable, not JSON.** Film shows the Editor's cut as a list with
   reasons and is changed by asking the Editor or small controls; the raw edit file
   is read-only under Settings → Advanced.

Test data note: the stills are procedural placeholders and the song is a
synthesized test track; no real production or paid call was used.
