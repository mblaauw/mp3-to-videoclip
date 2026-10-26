# 02 · Design direction, tokens and components

## The idea in one sentence

**The song is the spine.** A film made from a song lives on the song's timeline,
so the Studio keeps one timeline — waveform, named sections, a filmstrip of every
shot with its status, and a playhead — docked at the bottom of every stage. The
five stages above it are different ways of working on the same timeline.

Everything else is quiet so that the two things that matter stand out: the
pictures, and the one thing the user should do next.

## Principles

1. **One next step, always visible.** Every stage opens with a one-line status and
   one primary action ("Approve storyboard", "Make s033 · $0.04"). If something is
   blocked, the bar says by what and offers the way there ("Approve the story
   first" → Go to Story). Fixes A1, A2.
2. **Pictures at picture size.** Stills are shown as a contact sheet and a full-
   screen lightbox, never as 168 px thumbnails inside forms. Storyboard shows the
   picture of every shot (or a placeholder with its framing). Fixes C2–C4.
3. **Free movement, honest state.** Every stage is always open. Nothing is locked;
   things that changed upstream are marked *Changed* (violet) with the reason, and
   the user decides when to redo. Approvals are one click; a note is optional.
   Fixes B1–B4.
4. **The director is a colleague, not a column.** A collapsible drawer that shows
   which role answers (Writer / Editor), what it is doing right now, and every
   change it made as a card with *Show* and *Undo*. Fixes D2.
5. **Money is always one glance away.** The top bar shows what is left; every paid
   button carries its price; the budget popover explains spent / reserved / left
   and raises the budget in place. Fixes D4, D5.
6. **Speak filmmaker.** Shots, stills, sections, keep, redo, preview, final.
   Never artifact, hash, schema, base, stale, bytes. See the copy table in
   `03-screens.md`. Fixes E1–E2, B4.

## Colour

Images are judged on a **neutral** grey surround (video and photo tools use mid
to dark neutral grey so colour casts are not induced); the current navy tint is
replaced. One brand accent — the MAHA KALA gold from the logo's cut corner — means
"act here". Status colours mean status and nothing else.

| Token | Hex | Use |
| --- | --- | --- |
| `--surround` | #1B1C1F | App background, around every picture |
| `--panel` | #232428 | Drawer, spine, inspector, popovers |
| `--raised` | #2C2D32 | Inputs, buttons, hover |
| `--line` / `--line-soft` | #3A3B41 / #2F3035 | Region borders / dividers |
| `--well` | #141518 | Behind waveform, player, lightbox |
| `--ink` / `--ink-2` / `--muted` | #ECEAE5 / #B6B7BC / #9A9CA3 | Text levels |
| `--gold` | #D9B36C | Primary action, playhead, selection, **needs you** |
| `--sage` | #82C29A | Done, kept |
| `--violet` | #A996F0 | Changed upstream / made from an older prompt |
| `--red` | #EE6E66 | Error, redo |
| `--sec-1…5` | muted blue, violet, ochre, green, rose | Music sections on the waveform only |

Measured contrast (WCAG 2 formula): `--ink` on `--surround` 14.2:1; `--muted` on
`--surround` / `--panel` / `--raised` 6.2 / 5.7 / 5.0:1; `--on-gold` on `--gold`
8.6:1; `--violet`, `--red`, `--sage` on `--surround` 6.7 / 5.7 / 8.2:1. All pass AA
for small text. Status is never shown by colour alone: every dot has a word next to it.

## Type

One family: **Schibsted Grotesk** (variable, OFL), self-hosted with
`@fontsource-variable/schibsted-grotesk@5.3.0` — no network fetch at runtime. A
crisp newspaper grotesque that stays readable at 12–13 px in dense UI and has
enough character at 24–34 px for film titles.

| Token | Size | Use |
| --- | --- | --- |
| `--t-34` | 34 | Library title |
| `--t-24` | 24 | Stage title, dialog title |
| `--t-18` | 18 | Block titles ("Sections", "Ready to deliver") |
| `--t-15` | 15 | Body, inputs, chat |
| `--t-13` | 13 | Dense UI: buttons, chips, tables, captions |
| `--t-12` | 12 | Timecodes on the spine, step states |

Weights 420 / 540 / 680. Sentence case everywhere; no uppercase tracked labels.
Tabular figures **only** on numbers that line up (timecodes, durations, money,
counts) — this font spaces punctuation oddly if `tnum` is applied to prose.
Reading text (treatment, long prompts) uses `--lh-read` 1.6 and a 68 ch measure.

## Shape and space

- 4-pt spacing scale `--s-1…7` (4–48).
- Radius encodes kind: controls 4, pictures 6, surfaces 12. Not one radius on
  everything.
- Elevation only for things that float (popovers, dialogs, drawers on small
  screens): `--float`. Regions are separated by a 1 px line, not by cards.
- Motion: 160 ms ease for state changes caused by the user; one ambient motion in
  the whole app — the pulsing dot of a running job or a thinking director.
  `prefers-reduced-motion` sets durations to 0.

## Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ▣ Studio / Night Signal   1●Track  2●Story  3●Storyboard  4●Images  5●Film   $6.72 left ▬  ◷1  💬  ⚙ │  top bar 56
├───────────────────────────────────────────────────────────┬──────────────────┤
│ ● 34 shots cover all 2:53.  3 style-check shots chosen.  [Approve storyboard]│ Director  380   │
│───────────────────────────────────────────────────────────│ (or Inspector    │
│ Stage title  one-line explanation                         │  when a shot is  │
│ stage workspace (scrolls)                                 │  selected)       │
│                                                           │                  │
├───────────────────────────────────────────────────────────┴──────────────────┤
│ ▶  0:42 / 2:53 │ Opening        Verse   Chorus        Break   Final chorus     │  spine 132
│                │ ▁▂▃▅▆▇▆▅▃▂▁▂▃▅▇██▇▆▅▃▂▁▁▂▃▅▆▇█▇▆▅  (section-tinted waveform) │
│                │ [▦][▦][▦][▦][▦][▦][▦][▦][▦][▦][▦]…  filmstrip, status underline│
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Library** is its own full-width screen (no spine, no director): posters,
  progress, "needs you" line per film, a drop target for a new MP3, and a
  *Delivered* section for frozen films.
- Content is left-aligned on a 1320 px max width; the next-step bar is sticky.
- ≤ 1180 px: director and inspector become overlay drawers (closed by default),
  step state words hide.
- ≤ 700 px: top bar wraps to two rows with a scrollable stepper; spine shrinks to
  96 px (no section labels); grids go to two columns; lightbox is full screen.

## Components

Each maps to a file in `frontend/src/`. Props are the minimum; types come from the
generated API client (see `04-implementation-plan.md`).

| Component | File | Purpose | Key props / state |
| --- | --- | --- | --- |
| `AppShell` | `App.tsx` | Grid: top bar, main, side, spine; routes `#/` and `#/:slug/:stage` | `route`, `sideMode: "director" \| "inspector" \| null` |
| `TopBar` | `shell/TopBar.tsx` | Mark, breadcrumb, `Stepper`, `BudgetChip`, `JobsButton`, director toggle, settings | `project`, `stageStates` |
| `Stepper` | `shell/Stepper.tsx` | Five numbered stages with dot + state word | `states: Record<Stage, StageState>` |
| `NextStepBar` | `shell/NextStepBar.tsx` | Sticky one-line status + ≤ 2 actions | `tone: "done" \| "you" \| "changed" \| "error"`, `title`, `detail`, `actions[]` |
| `Spine` | `spine/Spine.tsx` | Transport, waveform, section labels, filmstrip, playhead; replaces `Timeline.tsx` and owns the shared playhead | `music`, `board`, `images`, `mode: "view" \| "edit-cuts"`, `selectedShot` |
| `Waveform` | `spine/Waveform.tsx` | SVG bars tinted by section; gold cut lines in edit mode; boundary drag + arrow keys (keep current `Timeline.tsx` logic) | `bars`, `sections`, `cuts`, `onRetime` |
| `Filmstrip` | `spine/Filmstrip.tsx` | One cell per shot, proportional width, thumbnail, 3 px status underline | `shots`, `onSelect` |
| `PlayerProvider` | `spine/player.ts` | One `<audio>` + current time store shared by Spine, Film player and Remotion Player | `time`, `playing`, `seek()`, `toggle()` |
| `Director` | `director/Director.tsx` | Drawer with role/model line, thread, activity line, composer with context chips, Stop | `slug`, `stage`, `selection` |
| `ToolCard` | `director/ToolCard.tsx` | One card per tool call: what changed, *Show*, *Undo*; money cards show reserve + progress | `event` from the chat stream |
| `BudgetChip` / `BudgetPopover` | `money/Budget.tsx` | "$6.72 left" + meter; popover with spent / reserved / left and *Add to budget* | `budget` |
| `JobsButton` / `JobsPopover` | `jobs/Jobs.tsx` | Count badge; list with progress, cost, cancel; fed by `/api/events` | `jobs` |
| `FilmCard` | `library/FilmCard.tsx` | 4-still poster, 5-segment progress, facts, next step | `summary` |
| `ShotCard` | `stages/storyboard/ShotCard.tsx` | Thumb or framing placeholder, star (style check), id, duration, job, tags | `shot`, `still`, `selected`, `isProof` |
| `ShotInspector` | `stages/storyboard/ShotInspector.tsx` | Side panel editor for one shot, prev/next, Ask the Writer, Remake still | `shot` |
| `StillTile` | `stages/images/StillTile.tsx` | Contact-sheet tile with status outline + pill + version count | `shot`, `status` |
| `Lightbox` | `stages/images/Lightbox.tsx` | Full-screen review: versions, Keep (K), Redo (R) with "what should change", ←/→ | `shots`, `index` |
| `Checklist` | `stages/film/Checklist.tsx` | "Ready to deliver" list with links back to the stage that owns each item | `gates` |
| `CreditsEditor` | `stages/film/CreditsEditor.tsx` | Role/name rows: add, remove, reorder | `spec` |
| `SettingsDialog` | `settings/SettingsDialog.tsx` | Keys, director models, defaults, this computer | `settings`, `setup` |
| `NewFilmDialog` | `library/NewFilmDialog.tsx` | Drop zone, title, kind, music, budget | — |
| `StatusDot`, `Pill`, `Seg`, `Chip`, `Button`, `IconButton` | `ui/*.tsx` | Primitives styled only from tokens | — |

### State vocabulary (one set, used everywhere)

| Engine state | Shown as | Dot |
| --- | --- | --- |
| approved | Done / Approved | sage |
| missing (no record) | Needs you | gold |
| stale | Changed — with the reason ("You moved the style-check shots") | violet |
| unavailable | Not ready — with the blocking stage ("Add lyrics first") | muted |
| job running | e.g. "Making 3 stills · 1 of 3" | pulsing gold |
| image accept / reject / uncertain / none | Kept / Redo / Not sure / Not reviewed | sage / red / gold / muted |
| image input hash ≠ current spec | Older prompt | violet |
| no version | Not made | hatched placeholder |
