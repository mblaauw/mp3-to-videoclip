# 03 · Screens, behaviour and copy

Every screen below exists in the clickable prototype (`prototype/index.html`,
see README) and as a screenshot in `screenshots/proposed/` (`desk-`, `tablet-`,
`phone-` = 1440, 900, 390 px). API paths are the real routes at `7b93068`;
**[new]** marks a backend change listed in `04-implementation-plan.md`.

## Shell (all film screens)

**Top bar** — mark (→ library) · film title · stepper · budget chip · jobs · director · settings.

- Stepper item = number, status dot, stage name, state word (see state vocabulary in
  `02-design.md`). Stage states come from `GET /approvals?stages=…` plus image counts
  from `GET /images`. Clicking any stage always works.
- Budget chip = `remaining_usd` (already net of spent cost and unresolved
  reservations), with a meter of `committed / cap`.
- Click → **Budget popover**: spent on N stills, reserved for running jobs, left of
  cap **[new K12: `GET /budget` returns `spent_usd`, `reserved_usd`, `paid_stills`
  separately; today `committed_usd` merges them]**; one sentence ("The app spends inside this budget without asking.
  When it runs out, jobs pause and ask you."); amount + *Add to budget* →
  `POST /budget {amount, reason}`; history list below.
- Jobs button = count of running jobs. Click → **Jobs popover**: one row per job with
  dot, verb phrase ("Making 3 stills", "Measured the song", "Rendered preview 2"),
  film, progress bar, cost so far, *Cancel* (`POST /api/jobs/{id}/cancel`) or *Play*.
  Data from `/api/events` (SSE, already exists in `app.py`) — **stop polling**.

**Next-step bar** — sticky below the top bar. Exactly one primary button. Rules per
stage are in each section below. If a stage is blocked by another, the bar says
which and offers *Go to …*.

**Spine** — always visible on film screens (132 px; 96 px on phones).

- Play / pause (Space when focus is not in a field), timecode `0:42 / 2:53`.
- Section labels (from Track names), waveform from `music.fine_windows` tinted per
  section, filmstrip with one cell per shot (thumbnail of the selected version from
  `GET /images/{owner}/{version}`, hatched if none), 3 px underline for Kept / Redo /
  Older prompt.
- Click or drag on the waveform seeks; ←/→ seek 5 s when the spine has focus.
- Clicking a filmstrip cell selects that shot: opens the inspector in Storyboard,
  the lightbox in Images, and seeks the Film preview.
- In **Storyboard**, gold cut lines appear on the waveform and are draggable — move
  the existing `Timeline.tsx` boundary logic (pointer + keyboard, neighbour limits,
  `PATCH /storyboard/shots`) here.
- One shared time store drives the spine, the Film player and the Remotion Player,
  so time survives a stage switch (fixes C6).

**Director drawer** (380 px; overlay ≤ 1180 px; toggle in the top bar; closed on the
library).

- Header: "Director" and the answering role and model, e.g. "Writer · GPT-6.1 Sol"
  in Story/Storyboard/Images, "Editor · DeepSeek V4.1 Flash" in Track/Film (role
  routing from the writing & editing brief; until that lands, show the configured
  model).
- Thread: user bubbles right; assistant prose left; **tool events as cards** from the
  chat NDJSON stream (`kind: "tool"`): title ("Edited the storyboard"), what changed
  ("Chorus, s013–s021: timing and 3 new shots"), *Show* (jumps to the stage and
  selects the shots) and *Undo* **[new: history restore]**. Paid tools render as a
  gold money card with reserve and a progress bar bound to the job.
- Activity line while a turn runs: pulsing dot + what it is doing ("Writing prompts
  for s019–s021…") from the latest tool name.
- Composer: context chips sent with the message (stage, selected shot, playhead
  time) **[new: `POST /chat` accepts `context`]**; Enter sends, Shift+Enter newline;
  *Stop* aborts the request.
- Errors are inline cards with the fix: "The director has no model key. Open
  Settings to add it." with an *Open settings* button.

**Inspector** — replaces the director in the side column when a shot is selected in
Storyboard. Close returns to the director.

## Library `#/`

- Title "Your films", one-line summary ("Two in progress, one delivered."), *New film*.
- Film cards: 4-still poster (first selected kept stills; "No pictures yet" if
  none), 5-segment progress line coloured by stage state, title, facts (length,
  shot count or "Instrumental", money left), next step ("Approve the storyboard").
  Click opens the film at the stage that needs the user.
- Last tile: dashed drop target "Drop an MP3 to start a new film" (drop → New film
  dialog with the file filled in).
- *Delivered* section for archived films: poster, title, length, final version,
  delivered date. Opens a read-only player with the stills strip
  (`GET /film/renders/{name}`), never a file path (fixes A6).
- Data: `GET /api/projects` **[new: add `poster_stills`, `stage_states`,
  `next_step`, `remaining_usd`, `updated_at` to the summary]**.

## New film dialog

Fields: drop zone (shows name, size, length after probe), Title (prefilled from the
file name), Kind of film (Music video / Promo / Advert — Promo and Advert depend on
the writing brief's production kinds; ship disabled with "Coming soon" until then),
Music (Vocals / Instrumental), Budget for pictures (prefilled from settings). Fixed
note: "16:9, 1080p, 24 fps — made for YouTube." No 9:16 option (fixes E3).
*Create film* → `POST /api/projects?…` → open Track; toast "Created Night Signal.
Measuring the song…".

## 1 · Track

Purpose: listen, name the parts, add the lyrics.

- Facts row: length, "about 123 BPM, estimated", sections found, Vocals/Instrumental
  switch.
- **Sections**: one row per measured section — colour swatch, editable name (default
  "Section 1…"), time range, loud/medium/quiet from section energy. Names feed the
  spine, Storyboard groups and the director context **[new: section names stored in
  `work/music-notes.json`; never edit `music.json`]**. Hint: "Boundaries are
  estimates. Drag them on the timeline below to correct one." **[new: reviewed
  section boundaries]** — optional for v1; names alone are fine.
- **Lyrics**: if present, lines with times + *Edit lyrics*. If empty: a paste box that
  accepts **plain text or LRC** **[new: `PUT /lyrics` accepts `{text}`; untimed
  lines are stored without positions]**, and a quiet *Transcribe instead · $0.05*
  (only when empty, D7).
- Next-step bar: analysis running → "Measuring the song…" (no button); done → "Track
  is ready." + *Continue to Story*; vocal track without lyrics → "Add the lyrics
  before approving the story." (fixes A3).

## 2 · Story

- **Concepts**: 3 cards from `GET /treatments` (title + 2-line logline); the chosen one
  is gold. *Ask for three more* prefills the director composer. Empty state: "No
  concepts yet. Ask the Writer for three directions." with a button that sends that.
- **Treatment**: reading-width editor (68 ch, line height 1.6), autosaves 800 ms after
  typing stops via `PATCH /brief {treatment}` — no Save button. A small "Saved"
  appears for 2 s.
- **Look**: style preset card (sample still, name, one line), "Film-specific
  additions" text → `creative.look` suffix, rule chips from `creative.image_rules`.
- **Characters**: avatar (reference photo or "No photo"), name, one-line identity,
  *Add character*.
- Next-step bar: not approved → *Approve story*; changed since approval → violet
  "Changed since you approved it." + the reason + *See what changed* (diff vs the
  approved brief **[new: keep the approved brief snapshot]**) + *Approve story*.
- Approve = one click → `POST /approvals/brief {expected_hash, confirmed: true}`;
  note optional via *Add a note* **[new: note optional]**.

## 3 · Storyboard

- Tools: Pictures / Table switch, "★ 3 of 3 style-check shots", *Ask the Writer to
  revise…*.
- **Pictures view**: shots grouped by Track section (swatch, section name, time range,
  shot count). Each `ShotCard`: 16:9 thumb (selected still or hatched placeholder
  with the framing word), star toggle top-right (style-check shot; max 3; uses
  `POST /proof-shots`), id + duration, job (2 lines), framing / camera / transition
  tags. Click → inspector.
- **Table view**: the current table, plus a thumbnail column, sticky header.
- **Inspector**: still, time range + duration + section, "Job of this shot",
  "What changes from the shot before" **[new field `change` on Shot, optional]**,
  picture prompt, must show, framing, camera (hold, push in, pull back, pan left,
  pan right), into this shot (cut, dissolve, wipe), *Ask the Writer*, *Remake still ·
  $0.04*. Prev/next arrows. Fields autosave via `PATCH /storyboard/shots`. Hint:
  "Editing the prompt marks this still as made from an older prompt. Nothing is
  remade until you ask."
- Moving a star changes the brief: show a toast "Style-check shots changed. The
  story needs your approval again." and the Story step turns violet (fixes A2).
- Next-step bar: story not approved → "Approve the story first." + *Go to Story*;
  else "34 shots cover all 2:53. 3 style-check shots chosen." + *Approve storyboard*;
  placeholders left → "4 shots still need a job and a prompt." + *Show them*.

## 4 · Images

- **Style check** panel at the top (gold outline) while `proof` is not approved: the
  three starred shots with their state. Text: "Three hard shots first. When they
  look right, make the rest."
- Filter chips with counts: All, To review, Redo, Older prompt, Not made, Kept.
- Contact sheet: `StillTile` (232 px min) — still, status outline, id, job, pill, "2
  versions" badge. Click → lightbox.
- **Lightbox** (full screen, `--well` background): still as large as fits; header with
  id, time, duration, section, "4 of 34", close; footer with job + prompt, version
  thumbnails (click selects → `POST /images/select`), *Redo (R)* and *Keep (K)*.
  Keep → `POST /images/review {verdict: "accept", inspected: true}` **[new: note
  optional; today the route and `reviews.record_review` require 1–2000 chars]**, then
  advances to the next unreviewed still. Opening the still in the lightbox *is* the
  inspection, so `inspected: true` is sent by the client, not ticked by the user. Redo → inline field "What should change? The Writer
  rewrites the prompt." + *Remake · $0.04* (records `reject` with the text as note,
  sends it to the director, queues one image). ←/→ move, Esc closes.
- Generation lives in buttons with prices, not a form: next-step bar *Make s033 ·
  $0.04* / *Make all 8 missing · $0.32*, tool row *Remake 2 from older prompts ·
  $0.08*, inspector *Remake still*. Each calls `POST /images/estimate` then
  `POST /images/generate` in one go; if `needs_budget`, show the budget card ("This
  needs $0.36 more. Add $0.50 to the budget?") instead of an error. Reserve per shot
  comes from settings, not a field on screen (fixes D5).
- Next-step bar: style check incomplete → finish it; style check all kept and not
  approved → *Approve style check*; full set → "26 of 34 kept." + *Make 8 missing*;
  all kept → *Approve all stills*.

## 5 · Film

- **Screen**: the Remotion `LivePlayer` bound to the shared time store; segmented
  control *Live preview / Rendered files*; caption shows current shot id and job.
- **Ready to deliver** checklist, each line links to its owner stage: Story approved,
  Storyboard approved, Every still kept (26/34), Watched the preview with sound
  (checkbox = preview attestation), Titles checked on real frames (*Check* renders
  the base and shows 6 sample frames in a lightbox; approving them = graphics
  approval). *Render final* is primary and enabled only when all are done.
  Estimated time under it.
- **Titles and credits**: role/name rows with drag handle, remove, *Add role*;
  defaults from settings (D5) **[new: `PUT /graphics/credits`]**.
- **Rendered files**: previews and finals, newest first, *Play* (switches the
  screen) and *Download*; the final also offers the YouTube package (MP4 +
  thumbnail + description) when the writing brief's T4/T5 lands.
- Renderer missing → a setup card in place of the checklist: "The local renderer is
  not installed yet." + *Install renderer* + the missing tools list.

## Settings dialog (gear in the top bar)

Sections: Pictures (Runware key, masked, "Works" / "Rejected" after a test call
**[new: `POST /settings/test`]**), Director (Writer and Editor model selects;
OpenCode status), New films start with (budget, opening names, default credit
roles), This computer (renderer, FFmpeg, Node status from `GET /api/setup`).
Saves with `PUT /api/settings`. Fixes D1.

## Copy

Use these strings; keep verbs identical through a flow (button "Keep" → status
"Kept").

| Today | Replace with |
| --- | --- |
| track / story / storyboard / images / film | Track / Story / Storyboard / Images / Film |
| approved / not approved / changed since approval / not ready | Done or Approved / Needs you / Changed / Not ready |
| "what did you check?" (required) | *Add a note* (optional) |
| accept / reject / uncertain · "inspected the exact bytes" | Keep / Redo / Not sure (no checkbox) |
| proof shots | style-check shots |
| Render preview / Render base / Render final | Watch preview / Check titles / Render final |
| cap · committed · remaining | Budget · Spent · Reserved · Left |
| Estimate → Generate N stills | Make N stills · $X (one step) |
| regenerate unchanged | Remake |
| reserve / shot $ | (moves to Settings → Pictures → "Reserve per still") |
| One MP3 becomes a schema-3 film… | Start from a song. It stays on this computer; nothing is spent until you make pictures. |
| Integer-frame timeline, stable shot IDs… | Every shot has a job. Click one to edit it; drag the gold lines on the timeline to change when it cuts. |
| Ask the director to change the film. | Ask for a change… |

### Error mapping (never show raw exceptions or paths)

| Engine message / condition | Shown as |
| --- | --- |
| `FileNotFoundError …/storyboard.json` | "No storyboard yet. Make one in Storyboard." + *Go to Storyboard* |
| `brief is not ready; its artifact has not been created` caused by missing lyrics | "Add the lyrics first — the story is checked against them." + *Go to Track* |
| `brief needs current user approval` (anywhere) | "The story changed. Approve it again before making pictures." + *Go to Story* |
| `shot sNNN has no current selected still` | "sNNN has no picture yet." + *Make it · $0.04* |
| `503 no LLM key configured` | "The director has no model key." + *Open settings* |
| `needs_budget` | Budget card with the suggested top-up |
| Renderer missing | Setup card (above) |
| anything else | "Something went wrong while {verb}. Details are in the log." + *Copy details* (raw text only behind that button) |
