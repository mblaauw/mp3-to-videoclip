# 05 · Update for `main` at `42a33cf`

The audit and design were made at `7b93068`. Since then 13 commits (PRs #18–#23)
landed the T0–T5 work from the writing & editing brief: safe director writes, the
OpenCode gateway, production kinds with Story intake, writer/editor prompt suites,
shot kinds, the edit list and ratings. This file is the delta. **Where it disagrees
with 01–04, this file wins.**

**Verdict:** the redesign still holds. None of the new work touches the shell,
library, approvals ceremony, budget display, image review or director drawer, so
every finding in `01-ux-audit.md` is still open and Phases 1–2 can start as
written. Phases 3–5 need the additions below, because the new features arrived in
the old visual language (long forms, raw tables, a JSON editor).

Screenshots of the new features as they are today: `screenshots/current-42a33cf/`.

## 1 · A bug to fix first (blocks every vocal promo and advert)

A promo or advert made from a song with vocals can never get its story approved.

- `production.effective_upstream(root, "brief")` returns `"lyrics"` unless
  `music_mode` is instrumental or music-led — it ignores `kind`.
- `PUT /lyrics` refuses non-music-video kinds (`"lyrics are a music-video intake"`),
  so `work/lyrics.json` can never exist for them.
- `stage_hash` then raises `FileNotFoundError`, and Story shows
  *"brief is not ready; its artifact has not been created"* with no way forward.

Reproduced on a fresh advert (vocal mp3, 30 s, CTA "Pre-save now"): treatments and
brief written, approval impossible.

**Fix (K13):** in `effective_upstream`, return `"analysis"` for `brief` when
`load_project(root).kind not in (None, "music_video")`. Add a test that creates a
vocal advert, writes a brief and approves it. This is a correctness fix, not
presentation; do it in its own PR before Phase 1.

## 2 · New audit findings (G1–G8)

| # | P | Finding | Evidence |
| --- | --- | --- | --- |
| G1 | P1 | Vocal promo/advert story cannot be approved (see §1). | `production.effective_upstream`, `api/track.update_lyrics` |
| G2 | P1 | Story for promo/advert opens with a 13-field intake form stacked above everything else; nothing says which fields matter or that it autosaves only on *Save*. | `IntakeCard.tsx`, `ad-story.png` |
| G3 | P2 | The Film *Cut* section shows the edit report as raw keys and offers *Edit JSON* — a textarea over `work/edit.json`. Easy to break, no undo, unreadable for a single user who isn't a developer. | `Film.tsx`, `ns-film-cut.png` |
| G4 | P2 | When `edit.json` owns timing, the storyboard timeline turns read-only with no explanation of where timing now lives. | `Timeline.tsx` `readOnly`, `Film.tsx` "Move timing into an edit" |
| G5 | P2 | Storyboard table gained Kind / Message / Text columns; at 1440 px it scrolls sideways, at 390 px it is unusable. Card and logo shots show the same empty picture cell as an unmade still. | `Storyboard.tsx`, `ns-storyboard.png` |
| G6 | P2 | Rating blocks (`ArtifactRating`) are full-width panels — Good / Needs work, an always-open note box, *Save rating*, and developer text ("prompt … · 2 ratings") — placed four times: Story (brief and treatments), Storyboard, Film. They compete with the next step. | `ArtifactRating.tsx` usages |
| G7 | P3 | The director has Writer and Editor roles now (routing by stage, `role` accepted in the payload), but the drawer never shows which one is answering and cannot switch. | `api/director.py`, `App.tsx` Director |
| G8 | P3 | New production still offers 9:16; the target is YouTube landscape (E3 stands). Promo/advert length is a free number field next to preset lengths. | `NewProduction.tsx`, `api/projects.create_project` |

## 3 · Screen additions (extend `03-screens.md`)

### New film dialog

Kind of film is a real choice now (the prototype is updated). Show only what the
kind needs at creation; everything else moves to Story.

| Kind | Fields in the dialog |
| --- | --- |
| Music video | Title, Music (Vocals / Instrumental), Budget |
| Promo | Title, One message, Length (30 / 60 / 90 s), Budget |
| Advert | Title, One message, Length (6 / 15 / 30 / 60 s), Call to action, Budget |

Look preset defaults from the kind (`kinds[].default_style` from `/settings`) and
is changed on Story, not here. Drop 9:16 from the UI (frontend only); the backend keeps accepting it so old productions still open.
The API already accepts all of this in `POST /api/projects`.

### Story — intake and excerpt (promo/advert only)

Replace the wall of fields with a **Brief card** at the top of Story that reads
like a sentence and expands to edit:

> **Advert · 30 s** — *Night Signal is out Friday* — for late-night listeners —
> ends on **Pre-save now** → example.com · Look: Clean photographic  `Edit`

- Expanded: three groups — **The point** (objective, message, up to 3 reasons),
  **Who and how** (audience, tone chips ≤ 3, must-haves, avoid), **Ending** (CTA
  text + link). Autosave on blur via `PUT /intake`, show "Saved".
- **Song excerpt** lives on the spine, not in the form: in Story the waveform shows
  the `audio_window` as a gold band with drag handles for start and end and small
  fade ramps; the length readout snaps to the chosen preset length and warns in
  plain words when it doesn't match ("31.4 s — 1.4 s longer than the advert").
  Play plays the excerpt with fades (`/audio-excerpt`).
- Next-step rule: until message and CTA (advert) are filled, the bar says
  "Say what the advert should make people do" with *Edit brief*; then the usual
  concepts → treatment → approve flow.

### Storyboard — shot kinds

- `ShotCard` gets a small kind label top-left for anything that isn't `scene`
  (Product, Upload, Card, Bridge, Split, Reprise, Logo, End card), with the shot's
  `message` as the caption and on-screen `text` lines shown as type over a neutral
  plate — so a card shot looks like a card, not like a missing still.
- Paid vs free is visible: only paid shots (`is_paid`: scene, generated bridge,
  product without an asset) show the price dot; local kinds say "Made here, free".
- Inspector: a Kind picker (from `GET /settings` `shot_kinds`), then only the
  fields that kind validates (message ≤ 400, up to 8 text lines, product ref, bridge
  mode, 2–3 panes). This replaces K10: the existing `message` field is the "what
  this shot says" line, so K10 is dropped.
- Table view keeps one *Kind* column with the label; Message and Text move into the
  inspector. No horizontal scroll at 1440.

### Images — local plates

Local shots appear in the contact sheet using `plate` (`/plates/{shot_id}`) with a
"Made here" tag, no K/R verdict and no version picker. The filter chips get a
*Made here* chip. The style-check and paid counts ignore them, so "Keep 12 of 12"
counts only paid stills.

### Film — the Cut

Film gets a two-tab header: **Cut** and **Rendered files**. Cut replaces the raw
report and the JSON editor.

- No edit yet → card: "Let the Editor cut it" (*Make a first cut* → `POST
  /edit/seed` with `{}`), plus "or keep the storyboard timing".
- With an edit: a readable cut list grouped by the Track section names — per shot:
  thumbnail, duration, how it arrives (*Cut*, *Fade 12 f*, *Whip pan*…), motion,
  accents, and the `reason` in muted text. `techniques` show as chips at the top
  ("Match cut", "Cut on the downbeat"…).
- Changes go through the director (*Ask the Editor*: "Make the chorus cuts
  faster") or small inline controls (transition type, frames). Raw JSON stays only
  behind *Settings → Advanced → Show edit file*, read-only.
- **Spine:** when the edit owns timing, boundary drags in the waveform edit the
  edit list (`PUT /edit`), and a one-line note in the spine header says "Timing
  comes from the cut". The storyboard's own boundaries are shown greyed.

### Ratings

Ratings are for evaluation, not a step. Replace the panels with a small inline
thumbs pair (icon buttons labelled "Good" and "Needs work") beside the artifact
title. Clicking saves at once (`POST /ratings` with `rating: "up"|"down"` — the API
already takes exactly this); *Needs work* then opens a one-line optional note. The
prompt revision goes into a tooltip, not the visible text. One rating spot per
stage: Story (treatment), Storyboard, Film (cut).

### Director — roles

The drawer header shows who is answering: **Writer · GPT-6.1 Sol** on Story,
Storyboard and Images; **Editor · DeepSeek V4.1 Flash** on Track and Film (from
`STAGE_ROLE` and the model names in settings). A small *Ask the Writer / Ask the
Editor* switch sends `role` in the payload for one conversation. If the gateway is
`direct` (fallback), show "Direct API" in muted text so it's clear OpenCode isn't
in use.

### Settings

The fields now exist in `config.Settings`; the dialog in the prototype maps 1:1:
gateway (OpenCode / Direct), Writer model, Editor model, OpenCode path and
workspace, brand name and partner (opening names), default budget, default credit
roles. There is still no Settings screen in the frontend, so this remains Phase 5.

## 4 · Backend list — status at `42a33cf`

| # | Status | Note |
| --- | --- | --- |
| K1 | Open | Notes still required in `domain/approvals._body` and `api/images.review_image` (+ `inspected`). |
| K2 | Open | `_approval` unchanged; becomes urgent with G1. |
| K3 | Partial | `ProjectSummary` has `kind`; the other fields are still missing. |
| K4 | Open | `PUT /lyrics` takes `{lrc}` or the Lyrics model; no plain text. |
| K5 | Open | No section names file. The Cut view needs them too. |
| K6 | Open | |
| K7 | Open | Chat takes `role` now, not `context`. |
| K8 | Partial | Snapshots written to `work/brief-history/`, treatments and lyrics history; no restore route. Add `POST /history/{artifact}/restore` and cover `edit.json` and `storyboard.json`. |
| K9 | Open | Also test the OpenCode gateway (binary found, signed in) without a model call. |
| K10 | **Dropped** | Use the existing `Shot.message`. |
| K11 | Open | |
| K12 | Open | |
| **K13** | **New, first** | `effective_upstream`: brief depends on analysis for non-music-video kinds (§1). |
| **K14** | New | `GET /api/projects/{slug}/edit/summary` — the edit report with section names, human labels for transitions/motions/accents and per-shot reasons, so the UI doesn't decode raw keys. |

## 5 · Plan changes (apply to `04-implementation-plan.md`)

- **Phase 0 (new, ½ day):** K13 + test, plus K2, so promo/advert are usable before the
  visual work starts.
- **Ground rules:** add `work/edit.json` to the "do not change" list for timing
  logic: the UI writes it only through `PUT /edit`/`/edit/seed`, never by computing
  frames itself.
- **Phase 1:** `openapi-typescript` will now also type the intake, edit and ratings
  routes; keep `shotKinds.ts` but source labels from `/settings`.
- **Phase 3:** add the New film kinds, the Brief card and the excerpt band on the
  spine. Done when: a vocal advert goes from new → approved story with no error,
  and dragging the excerpt end shows the length warning.
- **Phase 4:** add shot kinds on cards and inspector, local plates in Images.
  Done when: a storyboard with a card and a logo shot shows them as designed plates
  and the paid count excludes them.
- **Phase 5:** add the Cut tab (K14), spine editing of the edit, director role line
  and switch, inline ratings. Done when: *Edit JSON* is gone from the default UI and
  a change asked of the Editor appears in the cut list with its reason.
- **Out of scope** is now smaller: production kinds, roles and the edit list
  exist; only the YouTube package (title, description, chapters, thumbnail) is
  still to come.
