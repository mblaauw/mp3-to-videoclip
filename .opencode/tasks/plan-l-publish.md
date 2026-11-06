# Phase L: the Publish stage and the watched-with-sound gate — plan

**Proposed** 5 Nov 2026; base `main` at `78fbd26`. Follows
`docs/design/missing-features-2026-11-05.md`, items 2 and 4. Decisions taken as recommended.

**Objective:** the film does not stop on disk. A Publish stage after Film takes the verified
final through what the upload form asks for: platform presets over the versions that exist,
three thumbnail candidates set in the film's own type, title and description written under
the truth rules, chapters and captions in platform format, and a release checklist whose
first line is measured: the owner has heard the whole final with the sound on.

## What the code showed

- **Delivery is one checklist and one package.** `domain/delivery.py build` asks the
  engine the same gates `render final` applies; `delivery.make_package` writes poster,
  contact sheet, chapters (text and ffmetadata), SRT and VTT beside a verified final and
  never replaces a file; `services/render.render_variant` makes 9:16 and 1:1 from the
  current final; `api/film.py` lists exports and serves package files by a strict name
  pattern.
- **"Watched" is a checkbox.** The preview approval requires `preview_watched: true`
  (`domain/approvals.py:66`, `production/approvals.py:422`) and the Studio sets it from a
  checkbox. Nothing measures playback. The Player keeps one `<audio>` element with
  `volume`, `muted` and a 60 Hz time store (`spine/player.tsx`); rendered files play in
  their own element.
- **Text is drawn locally already.** `localplate.py` draws cards with the three embedded
  faces (`renderers/remotion/fonts/`), a palette from the film's grade and the brand logo;
  `delivery.poster_frame` picks a frame by brightness.
- **The Writer writes under rules.** Tasks are chosen per stage (`director/prompts.py
  STAGE_ROLE`, `select_task`); a write tool needs a reason and is logged; the truth rules
  forbid invented facts; `Intent` carries objective, audience, message, CTA and mandatories.
- **Rights are recorded.** `brief.unconfirmed_permissions` lists characters and the
  narrator without confirmed permission; `budget.unresolved_tasks` lists paid tasks still
  out.

## Decisions (taken as recommended)

- **D1 Measured listening.** The frontend keeps, per media identity, the set of whole
  seconds that played while the element was not muted and volume was above 0.05, from
  `timeupdate` and `ended`; it posts them in batches to `POST
  /api/projects/<slug>/watched` as `{media, sha256?, seconds: [...]}` and the engine unions
  them into `work/watched.json`, append-only. `watched.coverage(root, media, total)` is
  heard seconds over total. A final counts as watched with sound at 98% of its seconds,
  because the last bucket of a file rarely fires. The media identity of a rendered file is
  its name and sha; of the live Player, `live:<audio key>`.
- **D2 Where the gate sits.** On the release checklist, as the first required line, bound
  to the current final's sha, so a new final needs a new listen. The preview approval's
  checkbox stays as it is, so no existing flow or test changes; it gains the measured
  number beside it as information.
- **D3 The copy.** A Writer task `publish` with the tool `write_publish_copy` writes
  `work/publish.json`: three titles, a description, tags and the chapter list it may edit,
  with a reason. `publish.check_copy` refuses a URL other than the CTA's, a price or a
  percentage not in the brief's mandatories or the script's claims, and a name not in
  the cast, so the truth rules are enforced in code as the eval checks do.
- **D4 Thumbnails.** `publish.thumbnails(root, film)` writes three 1280×720 JPEG
  candidates beside the final, `<final>.thumb-f<frame>-<n>.jpg`: the package's poster
  frame, the frame at the film's loudest second and the one at its brightest contrast,
  each with the chosen title set in the film's display face over a gradient band and the
  brand name small, under 2 MB. The owner picks one; the choice is recorded in
  `work/publish.json`.
- **D5 Presets.** `youtube` (the 16:9 final, chapters, SRT, loudness option), `shorts`
  and `reels` (the 9:16 version), `square` (1:1). `publish.plan(root)` lists per chosen
  preset what exists and what to make, naming the route; nothing is copied, a manifest
  `renders/<final>.publish.json` names files by sha.
- **D6 The checklist.** Required: a current verified final; heard with sound; copy
  written and checked; a thumbnail chosen; every character and the narrator permitted;
  no paid task unresolved. Optional: captions reviewed (when the film has words), the
  9:16 version rendered when shorts or reels is chosen. *Mark as released* records
  `{at, presets, final sha}` in `work/publish.json`; the Library card then says
  "Released". Uploading stays outside the app.
- **D7 Stage and scope.** A `publish` stage after Film for every kind, shown once a final
  exists; the engine refuses copy before a final so nothing is written for a film that
  does not exist yet.

## Tasks (one commit each)

1. **`watched.py` and the Player.** Coverage union, route, the frontend tracker on the
   shared Player and the rendered-file player, the number on the preview line. Tests:
   union is append-only, muted seconds never count, 98% rule, a new sha starts at zero.
2. **`publish.py`.** Copy model and checks, thumbnails, presets and plan, checklist,
   release record. Tests with a real final from the existing render fixtures: three
   candidates under 2 MB, a URL not in the CTA refused, a release refused unheard.
3. **Routes and the Writer.** `GET /publish`, `PUT /publish/copy`, `POST
   /publish/thumbnails`, `POST /publish/choose`, `POST /publish/release`; the `publish`
   task, example and tool inside the pin.
4. **The Publish stage.** Stage, next step, the page: checklist, presets, thumbnails,
   copy card with the Writer's button, files per preset. Frontend tests for the checklist
   words; an e2e that reads "heard 0%" on a film with a final fixture.

## Not changing

Approval hashes, the preview checkbox flow, `delivery.make_package`, render routes.

## Acceptance

- Checks green. On a scratch copy of the Museum: the final plays in the Studio with sound
  to the end and the line turns to done; muted playback leaves it at 0%; thumbnails drawn;
  copy written by hand (no live turn) passes the check; release recorded. The Writer's
  live turn is listed as not done.

## Risks

- Playback coverage is reported by the browser, not proved by a microphone: it is evidence
  the owner cannot reach by accident, not a proof. The record says so.
- Thumbnail type over a busy frame can be hard to read; the band is darkened to a fixed
  contrast and the owner chooses among three.

## Done, 5 Nov 2026

Four commits on `film/phase-l-publish`, stacked on the library phase: `watched.py`;
`publish.py`; the routes and the W7 task; the stage. Decisions D1 to D7 as written.

**Proved:** 2 listening tests (seconds unioned and never forgotten, other bytes start over,
98% rule, the live mix as its own media), 5 publish tests on a real small final (a link that
is not the call to action's and a figure the brief never gave are refused, the last copy is
kept in a history, three thumbnails at 1280×720 under 2 MB never rewritten, presets name what
is missing and stop once the package exists, the release waits for the ear, the copy and the
thumbnail and then writes a manifest, a paid task still out blocks it), 2 route and tool
tests, 6 frontend tests, one browser test that draws the thumbnails and picks one.

**Not proven:** playback coverage is what a browser reports; nobody checked a speaker. The
Writer's copy has met no real model. The thumbnail's type is Inter, because the renderer's
Fraunces and Bebas Neue are WOFF2, which Pillow cannot open; a TTF of either would let the
thumbnail use the film's own face. No film has been marked released.
