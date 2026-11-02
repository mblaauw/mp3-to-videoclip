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

**D · fast** (two PRs, about 9 days). D-1 renderer: packet counts from the join's
own listing instead of decoding the film twice, the failed-final store cleaned and
resumable by its key, a frame scan that skips suspects inside planned dip, flash
and crop windows with one reused browser for confirmation, K parallel render
workers (cores ÷ 2, at most 4, a memory guard, the machine lock taken once),
previews at 960×540 with placeholder plates passed through, a renderer-owned
loopback asset server so the bundle key is code-only and a new still never
rebundles, GPU raster behind a flag that stays off until measured. D-2 backend: a
source hash cached by path, size, mtime and inode, views that never verify the
source, every GET under a read snapshot in the thread pool, and
`work/stage-state.json` written by approve so the library reads exact state and
the one-second slack goes. A benchmark protocol on a scratch copy of Tree of Love
sets targets: a full base under three minutes at K=4, a half-size preview under
ninety seconds, one changed shot under twenty seconds, a new still with no
rebundle under a second, the library under 300 ms with zero source bytes read.
Decisions: worker count and memory guard; a failed final resumes only from its own
store; GPU raster gated on 1.3× and SSIM 0.999; previews at 960×540 only; the
loopback asset server; where the stage-state file lives and who writes it.

**F · open it up** (three PRs, about 2.5 weeks). F-1 titles as packages:
`signature.PACKAGES` with `joint-v1` byte-identical when no package is set,
`title-v1` with a 0 to 5 s title and a 0 to 10 s end card, and `none`; the planner
allows zero intro and zero cards; new films record the brand from Settings so the
two name literals become legacy-only; title and end-card parts with portrait
layouts; New film offers the three title choices and 9:16 again. F-2 delivery:
`delivery.py` sidecars (poster, contact sheet, chapters from edit sections, SRT and
VTT) that never rewrite a final; a 2 s GOP through the existing FFmpeg hook; 48 kHz
and two-pass loudness with measured values for promo and advert only; a q90 final
capture as a named choice with PNG the default; vertical and square variants from
the same cut with an anchor-based reframe and a Player toggle. F-3 portability: CPU
lyric timing tried in a two-day box with a documented refusal as the fallback, a
doctor line on the Library, a 50 MB streamed upload. Decisions: what the short
opening shows; end card and none allowed; the owner's default stays joint 25/40
through the brand kit; loudness −14 LUFS opt-in for promo and advert; PNG finals
with a q90 option; do not pin the headless shell; the boxed CPU lyric path; 50 MB.

## Final order

A, H, B, D, C-1, C-2, E-1, E-2, F-1, I-1, I-2, C-3, E-3, I-3, C-4, I-4, F-2, F-3,
with G-3's resource store before I-1 and the rest of G behind everything. The two
numbers that matter: about 16 weeks of work in total, and the first narrative film
plays in the Player about nine weeks in.

## Corrections after PR #66, 1 Nov 2026

The plans were written on `c1414a3`, before the Cool Cat After Dark run merged. Where they disagree, this section wins until the plan is next touched.

- **The Critic exists** (`critique.py`, `critic_model`, `director/prompts/critic/`). There are 14 flat settings, not 13. Phase H shows the Critic as a working role, not a greyed row. Phase E's "the Critic as a third role" is no longer out of scope.
- **Retiring the gateway includes the Critic.** Its frame review, tool allow-list and fresh sessions run through OpenCode today; the direct adapter must carry them before E-1 retires anything.
- **Evaluation has a live runner** (`tests/evals/live.py`) and a baseline in `docs/EVALUATION.md`.
- **Voice exists** (`voice.py`, `EditVoice`, `api/voice.py`, a Film panel). Phase I builds on it or says how `narration.py` relates to it.
- **Cache clearing:** `scripts/clean_caches.py` covers `work/graphics/cache`, which Phase H's list leaves out. There is one allowlist.
- **Text styles** `logotype`, `tagline`, `cta` and the `fade_in` animation exist; Phases C and F start from them.
- **Effort:** the phase summaries add up to about 120 working days, not 16 weeks. The table above is older than the summaries; the summaries are nearer.

Phase A changes: `needs_new_round` stays a 200 like `needs_budget`, since both are decisions, and `api/voice.py` follows the same contract. `cutNotes.ts` needs six missing codes, adding `text_not_drawn` and `reprise_uncropped`. The browser tests run as their own CI job and stay out of the plain `pytest` run.

## Where the roadmap stands, 1 Nov 2026

Merged: A (#69), H (#73, #74), B and D (#75), C-1 and C-2 with debt from those phases (#76),
E-1 (#77), E-2 and F-1 (#78), G-3's resource store, I-1 and I-2 (#79), C-3 and E-3 (#80). I-3 and C-4 are
in the PR after #80. Next in the final order: I-4.

Differences from the plans, where the plan was wrong or could not hold:

- **H:** `llm_model` keeps its own setting. Runware's refresh re-reads public schemas, because
  model search is not documented as free. A voice sample plays only a free preview.
- **B:** a film whose owner named its sections keeps them. A full section targets one cut a bar,
  not 2.5, because cuts land on bar lines.
- **D:** library state lives beside the settings and the listing takes no read snapshot, so
  opening the library writes nothing into a film. The 0.999 parity number cannot be met:
  full-size renders do not repeat exactly even with one browser.
- **C:** the type face lives in `grade.typeface`. Upscaling uses Real-ESRGAN at a published
  $0.0006. No paid batch has happened; it needs the owner. Real depth ran on a scratch copy and
  the owner chose 0.6 as a new film's start, where the tools are set up. Existing films stay off.

- **E-1:** the plan mapped `gateway: "opencode"` to the OpenCode Go provider. That would send
  `gpt-6.1-sol` to a provider that may not offer it, so a role keeps its own provider and is
  refused by name if it has no key. `continue` and the model record replace the plan's `/costs`
  route with `/model-usage`. No text model has a verified price yet, so costs read "no price known".

Still open by decision: the OpenAI major version; E-1 still uses that SDK's streaming, and no live
call has proven the adapter.
The narrator voice in Settings is not used until Phase I; `voice.py` keeps its own default.
`_final_state` keeps its mtime check. C-4 was the last part of C.

- **E-2:** a per-shot seed is reduced to 31 bits, because the image models' schemas stop there.
  Today's models have no separate edit input, so an edit sends the rejected still as the first
  reference image; a model without reference images says so and makes the still again. Section
  looks are refused on a version 2 film, so a look that its prompt never shows cannot mark stills
  out of date. The colour script sits on the World tab's profile, not on the Spine. Sheets, plates
  and edits are proved with fake clients only: the $0.50 live acceptance needs its own authorisation.
  So do the eval reference runs, whose pages all change with the new prompt hashes.
- **F-1:** the new parts are `ShortTitlePart` and `EndCardPart`, since `TitlePart` already names the
  dispatcher. A joint package on a song too short for it is refused when the Studio creates the
  film, and otherwise at the story's approval as before. Only an SVG logo can be drawn. On a scratch
  copy of Tree of Love all 38 image specs, the brief and stage hashes match main; the titles hash
  moves only with the renderer revision, as it does for any renderer change. `title-v1` was rendered
  at 16:9 and 9:16 and looked at.

- **After I-2, the owner's word:** an OpenAI model with no OpenAI key goes through OpenCode Go, under
  the same bare id. That reverses E-1's refusal. No real call has proved OpenCode Go accepts that id.
- **G-3 store:** subscribers and `useResource` landed, and the Script stage and Spine read through
  them. `request` already shared fetches through `resources.read`, so `FilmShell`, `Images`,
  `useFilmData` and `useStoryData` still make their own `Promise.allSettled` over that shared store;
  moving them stays with the rest of G-3.
- **I-1, I-2:** speech already had a journaled path in `voice.py` and a real schema: requests use
  `speech: {text, voice}`, WAV and sync, not the plan's `positivePrompt`, MP3 and async. That schema has no
  speed, pitch or emotion, so a direction steers the words and a redo, and `settings_from_direction` was not
  written. **The plan's default voice `English_Magnetic_Male_2` is not among the 332 voices on the schema saved
  on disk**, so a quote using it is refused by name until the owner picks another voice or the live schema
  offers it. Tabs run Story then Script rather than Script in Track's place, because the brief comes first (D3).
  The voice is locked in `work/narration.json`, not `intent.voice`, because locking it in the approved brief
  would un-approve everything; takes bind it through their input hash. The measured reading rate is kept beside
  the takes for the same reason, not written into the script. A line's first take goes straight into the mix, and
  later ones wait for Keep. The owner's own recording works on every line, which the plan did not ask for and
  which makes a whole film possible for $0. Ducking reuses `voice.py`'s measured spans and one linear gain reaches
  the loudness target, in place of a `sidechaincompress` and `loudnorm` graph, so no line moves by a sample;
  ambience waits for I-3. The plan's `STUDIO_PROJECTS` does not exist: the flag is `--projects-dir`. Takes, casting
  and the Writer's turn have only met fakes: the $3.00 batch and one live turn need the owner's authorisation.

- **C-3:** a ramp lies in the frame range strictly inside its shot. Look options were measured as 20 stills
  rather than a 10 s film; none costs a measurable amount. A caption becomes `kinetic_words` only when its whole
  line was heard and fits one shot.
- **E-3:** the tools are about 6,800 tokens, not 6,000, because this file's phases added nine tools; the test pins
  7,000. A required reason is enforced on real turns only, so engine callers and tests can still write. A write
  result is cut down only past 2,000 characters. `describe_images` is not in the Critic's tools, and neither is
  `compare_versions`: the rule that the Critic only reads is pinned by name. The model allowance also stops at
  400,000 tokens, because no text model has a verified price. A first draft refuses a story film. Nothing about a
  first draft, a caption or a judge has met a real model: each needs the owner's authorisation.

- **I-3:** the plan's Images tab for takes was not built: the Script stage already reviews takes with Keep, so a second
  place would only disagree. The era anchor stays a reference on the World tab; a place with no reference image still
  compiles from its words, so bind one before buying. The mix keeps I-2's one gain and measured ducking, not
  `sidechaincompress` and `loudnorm`, and ambience runs from one line to another rather than by seconds, so it follows the
  takes. `docs/primitives/` was not regenerated: `caption` is a text style and the sample set is per animation. Narrator,
  place and eras cost the prompt budget, so their words live in `kinds/narrative.md`, not `profile.md`. A narrator's
  permission asks again when the persona changes. No era or document still has been bought, and word timing in spoken
  captions has only met constructed words.
- **C-4:** a clip does not join `versions`, because every reader of that list assumes a picture: it has its own `clips` list
  and `clip` field, sharing the version numbers. It belongs to its still by `still_root`, so a sharper copy keeps it and a
  different picture turns it off. A reprise re-crops the still and never plays the clip. The request shape came from the
  published schemas of Kling 2.5 Turbo and Veo 3.1 Lite: `videoInference`, async, `inputs.frameImages`, a duration from the
  model's own list. Kling Turbo Standard is in the catalogue at a published $0.042 a second; no model is chosen by default.
  The renderer's remote-asset guard refused the compositor's own download, which only a real render showed: it now
  allows exactly the files the request names, on this computer. Rendered through Remotion with a local test clip: frames
  follow it, hold after its end to within 0.02 and cut cleanly; the Player loaded it with Range requests and showed it.
  The Player's hold past a clip's end was not looked at. `propose_motion` was not added: the tools are at their budget, and
  `propose_alternatives` can say the same. No clip has been bought: the capped batch needs the owner's authorisation, and
  the frame scan on real motion is unmeasured.
