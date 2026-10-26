# 01 · UX audit of the current Studio

Reviewed: `main` at `7b93068` (25 Oct 2026), `uv run studio` on Linux, Chromium at
1440×900, 1440×2600 and 390×844. Test data: a 2:53 vocal track ("Night Signal",
34 shots, 29 stills, 14 reviews), a 1:35 instrumental ("Glass Harbour", empty) and
one frozen archive film. Screenshots are in `screenshots/current/`.

> Re-checked at `42a33cf`: every finding below is still open; new findings G1–G8
> are in `05-update-42a33cf.md`.

**Verdict.** The engine underneath is solid and the Studio works end to end, but
it reads like an admin console for the engine rather than a place to make a film.
Every stage is a vertical stack of identical cards with uppercase headers; the most
important material — the song and the pictures — is small or absent; state,
next step and cost are scattered; and the language is the engine's (artifact,
schema-3, hash, stale, base) rather than a filmmaker's. Nothing is broken enough to
block work, but the user has to hold the whole workflow in their head.

Severity: **P1** blocks or misleads the user · **P2** slows every session · **P3** polish.

## A. Orientation: where am I, what's next, what is done

| # | Sev | Finding | Evidence |
| --- | --- | --- | --- |
| A1 | P1 | No "next step" anywhere. The tabs `track story storyboard images film` are lowercase words with no state; the user must open each stage and read its Approval card to learn what is done. | `full-02-track.png`, `App.tsx` `STAGES.map` |
| A2 | P1 | Invalidations surface in the wrong place. Saving proof shots in Storyboard silently makes the **brief** stale; the user only learns it in Images as a red line "brief needs current user approval" when pressing Estimate. | `full-07-estimate.png`; `Storyboard.tsx saveProof` sets a message only in Storyboard |
| A3 | P1 | Misleading blocker. On a vocal track without lyrics the brief shows "brief is not ready; its artifact has not been created" although `brief.json` exists. The real cause is missing lyrics (the brief's upstream). | `empty-03-story` capture; `api/approvals.py _approval` maps any `FileNotFoundError` to that text |
| A4 | P2 | Library rail shows `live · 173s`; no poster, no progress, no "needs you", no last edited. Three productions already need scanning by name. | `full-00-library.png` |
| A5 | P2 | Opening the app lands on an empty middle ("Select a production…") with an empty Director next to it. | `full-00-library.png` |
| A6 | P2 | The archive view prints an absolute file path and "0 stills preserved", with no player. | `full-01-archive.png` |

## B. Ceremony: approvals and reviews

| # | Sev | Finding | Evidence |
| --- | --- | --- | --- |
| B1 | P1 | Every approval requires typing a note ("what did you check?"); the Approve button stays disabled until something is typed. Owner asked for fewer, lighter approvals. | `ApprovalBar.tsx` disabled rule; backend `_body` requires 1–2000 chars |
| B2 | P1 | Reviewing one still takes four controls: verdict select, note field, "inspected the exact bytes" checkbox, Save. For 34 shots that is ~136 interactions. | `tall-05-images.png`, `Images.tsx saveReview` |
| B3 | P2 | Approval cards appear in different places per stage (top in Story/Storyboard/Images, bottom in Film) and list stages by engine id (`proof`, `stills`, `graphics`). | `tall-03-story.png`, `tall-06-film.png` |
| B4 | P2 | State words are engine words: `not ready`, `not approved`, `changed since approval`, `unavailable`, `stale`. | `ApprovalBar.tsx LABEL` |

## C. The material: song and pictures

| # | Sev | Finding | Evidence |
| --- | --- | --- | --- |
| C1 | P1 | Track has no player and no waveform. The analysis is a monospace list `0.0s unreviewed / 52.7s unreviewed…`. The user cannot listen to the song in the app outside the Film preview. | `full-02-track.png`; `/api/projects/{slug}/audio` exists but Track does not use it |
| C2 | P1 | Images is a 34-card vertical list, one shot per card, 168×94 px thumbnails. No grid, no full-size view, no compare, no keyboard review. | `tall-05-images.png` |
| C3 | P1 | Storyboard has no pictures at all: a 6-column table with truncated prompt textareas. The timeline's shot band labels collapse to `s0 s0 s0` at 34 shots. | `tall-04-storyboard.png` |
| C4 | P2 | Proof ("style check") shots are picked from a grid of 34 bare IDs (`s001`…`s034`), disconnected from what each shot is. | `tall-04-storyboard.png` |
| C5 | P2 | Film shows two players ("Live preview" and "Screen") with no explanation of the difference; the render buttons `preview / base / final` need a paragraph to explain. | `tall-06-film.png` |
| C6 | P2 | The waveform appears only in Storyboard; time is not shared between stages (scrub in Film, then switch stage → lost). | `Timeline.tsx` used only by `Storyboard.tsx` |

## D. Director, jobs, money

| # | Sev | Finding | Evidence |
| --- | --- | --- | --- |
| D1 | P1 | Errors from the director point to a Settings screen that does not exist ("no LLM key configured; open Settings"). There is no settings UI at all (keys, model, default budget, brand). | `full-08-director-error.png`; no settings component in `frontend/src` |
| D2 | P2 | The director panel is a fixed 360 px column on every screen, including the library and when empty. It shows only text: tool calls, changed shots and costs are invisible (`App.tsx` ignores `event.kind === "tool"`). | `App.tsx consume()` |
| D3 | P2 | Job tray: chips `analysis · succeeded` with no production, no progress, no time and no cancel; it polls every 3 s. | footer in every capture |
| D4 | P2 | Budget is a monospace line `cap 8.00 · committed 0.00 · remaining 8.00`, repeated in Images and Film, absent elsewhere. Raising the budget has no UI. | `tall-05-images.png` |
| D5 | P2 | Estimating needs a "reserve / shot $" number field and a "regenerate unchanged" checkbox before you can see a price. | `full-07-estimate.png` |
| D6 | P3 | Toasts and inline errors duplicate the same message. | `full-08-director-error.png` |

## E. Language and errors

| # | Sev | Finding | Evidence |
| --- | --- | --- | --- |
| E1 | P1 | Raw exceptions shown to the user, including absolute paths: `[Errno 2] No such file or directory: '/tmp/…/work/storyboard.json'`. | `empty-06-film.png` |
| E2 | P2 | Engine vocabulary in copy: "schema-3 film", "versioned artifact", "exact bytes", "Integer-frame timeline", "Render base". | `empty-01-new.png`, stage subtitles |
| E3 | P2 | New production still offers 9:16, against decision D6 (landscape for YouTube). | `empty-01-new.png` |
| E4 | P2 | Lyrics only accept LRC with timestamps; decision D7 says "paste if you have them" — most people have plain text. | `Track.tsx` placeholder |

## F. Visual design and layout

| # | Sev | Finding | Evidence |
| --- | --- | --- | --- |
| F1 | P2 | One pattern for everything: rounded card + uppercase tracked header, ~25 cards per page. No hierarchy between "the thing you came for" and supporting info. | all captures |
| F2 | P2 | Tinted navy surround (#0B0F14) shifts colour perception of the stills; image-judging tools use a neutral grey surround. | `styles.css :root` |
| F3 | P2 | Three fixed columns (240 / fluid / 360) leave ~600 px for the work at 1440 wide. | `styles.css .app` |
| F4 | P3 | Monospace for budget and analysis numbers; system font for everything else; no type scale. | `styles.css` |
| F5 | P2 | Phone: library, tabs, stage and a 50 vh director stack vertically; the job tray overlaps content. | `phone-04-storyboard.png` |

## What is good and must survive

- Live Remotion Player of the real composition — the best feature in the app.
- Waveform with draggable, keyboard-operable shot boundaries (`Timeline.tsx`).
- Honest money handling (estimate → budget check → queue) and the `needs_budget` path.
- Read-only archive, keyboard focus styles, toasts for errors that happen off screen.
