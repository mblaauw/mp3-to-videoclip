# 04 · Implementation plan

> **Updated:** `main` is now at `42a33cf`. Read `05-update-42a33cf.md` first — it
> adds Phase 0 (K13), K14, drops K10 and extends Phases 3–5.

For a code agent working in `mblaauw/mp3-to-videoclip` on top of `main` at
`7b93068`. Six phases, one PR each, every phase ends with `uv run pytest`,
`uv run ruff check .`, `npm run build --prefix frontend` green, the browser tests
green and the app starting with `uv run studio`.

## Ground rules

- **Do not change money, timing or pixels.** `generation.py`, `budget.py`,
  `timeline.py`, `pacing.py`, `remotion.py`, `render.py` and the approval hashing
  stay as they are. This rework is presentation plus the small backend changes
  listed below.
- **Reference, not source.** `prototype/` is vanilla JS with mock data. Rebuild it as
  typed React components under `frontend/src/`; copy `tokens/tokens.css` verbatim
  and the CSS rules you need from `prototype/studio.css`, renamed per component.
- New frontend dependencies, exactly: `@fontsource-variable/schibsted-grotesk@5.3.0`
  (runtime), `openapi-typescript` (dev, latest 7.x). Nothing else.
- Commit `frontend/dist` as today (fresh clones serve it without Node).
- Never show raw exception text or file paths (see error mapping in `03-screens.md`).
- Keep keyboard and screen-reader support at least as good as today: focus visible,
  every icon button labelled, status words next to colour, lightbox focus-trapped.

## Phase 1 — Foundations (½–1 day)

1. Add `frontend/src/styles/tokens.css` (from `tokens/tokens.css`) and the font
   import in `main.tsx`; replace `styles.css` root variables; set `color-scheme: dark`.
2. Generate `frontend/src/api/schema.d.ts` with `openapi-typescript` from
   `GET /openapi.json`; add `npm run api:types`; type `api.ts` against it.
3. `ui/` primitives: `Button` (primary / default / quiet / small), `IconButton`,
   `StatusDot`, `Pill`, `Seg`, `Chip`, `Field`.
4. `useEvents()` hook on `/api/events` (EventSource, reconnect with backoff) that
   feeds a jobs store; remove the 3 s `JobTray` polling.

**Done when:** the existing screens render with the new tokens and font, the jobs
tray updates from SSE with polling removed, and type-checking covers `api.ts`.

## Phase 2 — Shell, library, spine (2 days)

1. `AppShell` with routes `#/` (library) and `#/:slug/:stage`; remove the left rail.
2. `TopBar` + `Stepper` + `BudgetChip`/`BudgetPopover` + `JobsButton`/`JobsPopover` +
   settings entry.
3. `NextStepBar` with per-stage rules from `03-screens.md`; one function
   `nextStep(stage, project, approvals, images, budget)` in `shell/nextStep.ts`
   with unit tests for every rule.
4. `Library` with `FilmCard`, drop target, *Delivered* section and read-only
   archive player. Backend: extend `ProjectSummary` (below).
5. `PlayerProvider` (one `<audio src="/api/projects/:slug/audio">`, time store) and
   `Spine` = `Waveform` + `Filmstrip` + playhead; move boundary dragging from
   `Timeline.tsx` into `Waveform` edit mode, then delete `Timeline.tsx`.
6. Director drawer restyled; overlay ≤ 1180 px.

**Done when:** at 1440, 900 and 390 px the library and every stage show the top
bar, next-step bar and spine like `screenshots/proposed/*-01…06`; playing the song
in Track and switching to Film keeps the time; no route produces a console error
or a request ≥ 400 (extend the browser test that already checks this).

## Phase 3 — Track and Story (1½ days)

1. Track: facts row, editable section names, lyrics view, plain-text/LRC paste,
   *Transcribe instead* only when empty.
2. Story: concepts from `/treatments`, autosaving treatment, look card, characters.
3. One-click approvals with optional note on Story (and reuse in later phases).
4. Changed-state banner with the reason and *See what changed*.

**Done when:** a vocal production without lyrics shows "Add the lyrics first…" in
the Story bar instead of "artifact has not been created"; approving the story is
one click; editing the treatment shows "Saved" with no button; moving a style-check
star in Storyboard turns the Story step violet with its reason.

## Phase 4 — Storyboard and Images (2½ days)

1. Storyboard pictures view (`ShotCard`, section groups, star toggle), table view
   with thumbnails, `ShotInspector` with autosave and prev/next.
2. Images: style-check panel, filter chips, contact sheet (`StillTile`), `Lightbox`
   with K / R / ← / → / Esc, version picking, Redo with "what should change".
3. Priced action buttons that estimate and generate in one call; `needs_budget` →
   budget card with *Add $X*; reserve per still read from settings.

**Done when:** reviewing 20 stills with the keyboard takes 20 key presses plus
the arrow keys (no note, no checkbox); every paid button shows its price before
the click; a batch that exceeds the budget shows the top-up card and resumes after
*Add to budget*.

## Phase 5 — Film, director cards, settings (2 days)

1. Film: Remotion `LivePlayer` bound to the shared time store, *Live preview /
   Rendered files*, `Checklist` with deep links, *Check titles* (base render +
   sample lightbox = graphics approval), `CreditsEditor`, rendered files list.
2. Director: `ToolCard` for every `kind: "tool"` event, money cards bound to jobs,
   activity line, context chips, inline error cards with fixes, *Undo* wired to
   history restore.
3. `SettingsDialog` (keys with test, models, defaults, this computer).

**Done when:** the delivery checklist reflects real gate state and *Render final*
enables exactly when the backend would accept it; every director tool call appears
as a card; the "no LLM key" error offers *Open settings* and the dialog saves the key.

## Phase 6 — Polish and checks (1 day)

1. Empty, loading and error states for every screen (copy in `03-screens.md`).
2. Responsive pass at 390 / 900 / 1280 / 1440 against `screenshots/proposed/`.
3. Accessibility pass: keyboard-only path through all five stages; lightbox focus
   trap; `aria-live` on next-step bar and jobs; reduced motion.
4. Update `README.md` screenshots.

**Done when:** browser tests cover: library → open film → each stage → lightbox
keep → approve story → render preview, at 1440 and 390 px, with zero console
errors.

## Backend changes (small, each with a test)

| # | Change | Why | Where |
| --- | --- | --- | --- |
| K1 | Approval and image-review **note optional** (store `null`, never fabricated text) | B1, B2 | `domain/approvals._body`, `api/images.review_image`, `reviews.record_review` |
| K2 | `_approval` reports the real blocking stage ("lyrics is missing") instead of "{stage} is not ready; its artifact has not been created" | A3 | `api/approvals._approval`: catch the upstream `FileNotFoundError` and name the file's stage |
| K3 | `GET /api/projects` summary adds `poster_stills[≤4]`, `stage_states`, `next_step`, `remaining_usd`, `updated_at` | Library | `api/projects.py` (cheap: reuse cached fingerprints, never full gate checks per card) |
| K4 | `PUT /lyrics` accepts `{text}` (plain lines, no positions) as well as `{lrc}` | E4, D7 | `api/track.py`, `domain/lyrics.py` |
| K5 | Section names: `GET/PUT /music-notes` → `work/music-notes.json` `{sections: [{start, name}]}`; never write `music.json` | Track | new route in `api/track.py` |
| K6 | `PUT /graphics/credits` `{cards: [[role, name], …]}` | Credits editor | `api/film.py`, reuse the old `save_credits` rules |
| K7 | `POST /chat` accepts `context: {stage, selected_shots, time}` and adds it to the system context | Director chips | `api/director.py`, `director/context.py` |
| K8 | History snapshot + `POST /history/{artifact}/restore` for brief and storyboard writes | *Undo*, *See what changed* | `domain/`, `director/tools.py` |
| K9 | `POST /settings/test` checks the Runware key with a free call (model list), never a paid one | Settings | `api/settings.py` |
| ~~K10~~ | Dropped at `42a33cf`: use the existing `Shot.message` | — | — |
| K11 | Every 4xx/5xx returns `{detail, code}` with a stable `code` the UI maps to copy | Error mapping | `app.py` exception handler |
| K12 | `GET /budget` adds `spent_usd`, `reserved_usd`, `paid_stills` (split of `committed_usd`) | Budget popover | `api/budget.py`, `domain/budget.py` (read-only sums over `work/tasks.json`) |

K1 changes what an approval record contains, so record it in the task file and keep
the existing content-hash binding exactly as is.

## Out of scope here

The Writer/Editor routing, production kinds, new transitions and the YouTube
package are specified in the writing & editing brief; the UI leaves room for them
(role line in the director header, Kind of film control, Rendered files list).
