# A settings panel that chooses everything — plan

**Proposed** 1 Nov 2026 for owner approval; base `main` at `c1414a3`.

**Objective:** make Settings the one place where every model, voice, picture model, price,
key and new-film default is chosen, and where the app says plainly what is missing to make
a film. Phase H of the 31 Oct 2026 assessment (Part 2, H1 to H3): a provider and model
catalogue in the engine with on-demand refresh, a settings file with a schema version and
sections by role, an API that reports what each entry needs, and a tabbed panel in the
Studio. Phase H stores and shows per-role models, voices and video models even where the
code that consumes them arrives with Phase E (per-role models on the direct path, token
accounting) and Phase I (narration, clips). No money, timing, hash or approval rule changes.

## What the code showed

- **Thirteen flat keys.** `config.py:23-36` `Settings`: `runware_api_key`, `gateway`,
  `opencode_bin`, `writer_model`, `editor_model`, `opencode_workspace`, `llm_base_url`,
  `llm_api_key`, `llm_model`, `brand_name`, `brand_partner`, `default_budget_usd`,
  `image_reserve_usd`. The file is `~/.config/mp3-to-videoclip/settings.toml` under one
  `[settings]` table (`39-52`); the writer only emits flat scalars and lists (`58-68`) and
  writes the file private, 0600, then swaps it in (`69-75`). There is no schema version;
  unknown keys are ignored by pydantic, so an old file loads, but a renamed key silently
  falls back to its default. Environment fallbacks are only `PROJECT_VEIL_RUNWARE_API` and
  `OPENAI_API_KEY` (`78-91`), and the file wins when both exist.
- **The API masks keys and tests two things.** `api/settings.py:16-28` `_public` blanks the
  two secrets and adds `has_llm_api_key` and `has_runware_api_key`, plus style presets, kinds
  and shot kinds. `POST /api/settings/test` (`97-104`) knows `runware` (a free `recover` of a
  random UUID, `43-47`) and `opencode` (`--version` and `auth list`, `64-94`). `PUT` (`107-123`)
  keeps a stored key when the field is empty and closes the gateways. Tests:
  `tests/test_api_routes.py:85` (masking and empty-secret preservation) and `131` (tests are
  free). `tests/test_api_errors.py` builds a `Settings()` for the no-key path.
- **The dialog is five stacked sections.** `shell/SettingsDialog.tsx` (408 lines):
  Director (`215`: gateway select at `218`, free-text Writer and Editor model ids at `229`
  and `236`, OpenCode path and workspace), Pictures (`288`: key, reserve at `303`), New films
  start with (`326`: budget, and "Opening names" as two unlabeled inputs at `338`), This
  computer (`357`: the setup booleans), Advanced (`372`). `llm_model` and `llm_base_url` are
  not in the dialog at all, although `api.ts:374-375` types them. `settings.css` is 178
  lines. The gear is `GearIcon` (`shell/TopBar.tsx:391-392`, `ui/icons.tsx:70`).
- **One model for both roles on the direct path.** `api/director.py:260-265`: with
  `gateway == "direct"` the `DirectorLLM` is built from `settings.llm_base_url`,
  `llm_api_key` and `llm_model` for every role; `writer_model` and `editor_model`
  (`director/opencode.py:37-38, 145-146, 179, 186`) only reach the OpenCode gateway. The
  Director header shows `writer_model` or `editor_model` from settings
  (`shell/Director.tsx:384-393, 744-747`) whichever gateway runs, so on the direct path it
  names a model that is not the one answering.
- **The model is not recorded per turn.** `promptlog.remember(root, bundle.meta)`
  (`api/director.py:200`) stores the prompt hash, versions, role and task
  (`director/prompts.py:225` onward) into `work/prompt-current.json`
  (`promptlog.py:17, 25-26`); no field holds the model or provider. The assessment's H3
  assumed it did. Phase H adds it, since "a model change never changes an approval" is only
  honest if the model used is written down.
- **OpenCode can list models already.** `OpenCodeClient.models()` calls `GET /api/model`
  (`director/opencode.py:265-268`). Runware has no model-search call in `providers.py` and
  there is no ElevenLabs code anywhere in `src/`.
- **The brand is bound at intake.** `production/intake.py:258-259` reads `load_settings()`
  and `film_brand(settings.brand_name, settings.brand_partner)` when a music video is made;
  `signature.py:18-20` keeps the three literals and `signature.py:41-44` returns `None` (the
  joint package) when the name is empty or equals the literal. Existing films carry their
  brand in their own spec, so a changed kit affects only new films; moving the literals out
  of `signature.py` is Phase F1.
- **Defaults that new films read today.** `api/projects.py:398` takes the budget cap from
  `default_budget_usd`; `api/images.py:157` defaults the reserve to `"0.05"` from the
  request, which the Studio fills from `image_reserve_usd`; kind, aspect and style preset
  are request fields of `create_project` (`api/projects.py:354-360`); fps and length have
  no setting. `kinds.public_kinds()` (`kinds.py:126`) and `styles.public_presets()`
  (`styles.py:120`) already give the panel its lists.
- **Costs live in each film's journal.** Paid tasks are `work/tasks.json` per production
  (`generation.py:169, 386, 443`), and `budget.split_commitment` (`budget.py:172`) already
  splits committed from spent. Nothing sums across films or by kind.
- **Caches are never cleaned.** `docs/RENDER_PERFORMANCE.md:17-18`: chunks live in
  `work/remotion-chunks/` with a receipt each "and nothing is cleaned up"; `119-120` and
  `131-133`: receipts and bundle entries "fail closed without repair" when missing or
  malformed, so a removed cache is rebuilt, never trusted. Locations: `work/remotion-chunks`
  (`remotion.py:751`), `work/remotion-assets` (`remotion.py:551, 847`,
  `services/preview.py:155`), the renderer's bundle store `renderers/remotion/.cache/<sha>`
  (`render.mjs:9`, lock at `remotion.py:252-253`), and the lyric tools under
  `~/.cache/mp3-to-videoclip/lyric-tools` (`lyric_tools.py:49`). The first two are inside a
  production folder, which `AGENTS.md` says is never deleted (D3).
- **This computer.** `setup.status()` (`setup.py:38-48`) reports node, npm, chrome, ffmpeg,
  ffprobe, renderer and frontend as booleans; `lyric_tools.status()` (`lyric_tools.py:60-74`)
  reports support, readiness and the download size with a reason. No voice tool exists and
  the owner decided there will be no local voice.
- **Owner's answers already taken (not re-asked here).** Runware is the only voice
  provider for now; the narrator is MiniMax speech through Runware with
  `English_Magnetic_Male_2` as the default; ElevenLabs is scaffolded and listed only when
  `elevenlabs_api_key` is in the file or `ELEVENLABS_API_KEY` in the environment; catalogue
  refresh is on demand and never silent; one TOML file with a schema version.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | How is nested TOML written? | Add `tomli-w` (small, MIT) as a runtime dependency rather than growing the hand-written emitter at `config.py:58-68`, which cannot write tables. Reading stays on `tomllib`. |
| D2 | What does *Play sample* cost? | Free when the catalogue entry carries a provider preview (ElevenLabs voices do); otherwise a five-word sample bought once per voice at the shown price, on an explicit click, journaled in `~/.config/mp3-to-videoclip/samples.json` with the same pre-submit UUID pattern as `generation.py`, and cached under `~/.cache/mp3-to-videoclip/samples/`. The sample button is never pressed in tests or acceptance. |
| D3 | May *Clear* delete `work/remotion-chunks` and `work/remotion-assets` inside a production? | Yes, for exactly those two names and the renderer's `.cache`, through one engine function with an allowlist that refuses any other path and skips archived films. They are derived caches with receipts that fail closed, so clearing is safe; the panel says so and shows what will be rebuilt. `AGENTS.md` gets one sentence naming this exception. |
| D4 | What do the brand kit defaults say on a fresh install? | Keep "MAHA KALA" and "VJDJ69" as today, migrated into `new_films.brand`. Emptying them would change a fresh clone's titles through `signature.py:41-44`, which is Phase F1's change, not this one. |
| D5 | Is the Critic shown? | Yes, as a greyed row "Arrives with Phase E" with its provider and model stored, so the owner can choose it once and nothing has to move later. |
| D6 | Where do the published prices in `catalog.toml` come from? | Each entry carries `price_source` (URL) and `price_checked` (date), filled from the providers' public price pages when the file is written; an entry without a verified price has no price and the panel says "price unknown". No price is invented. |

## Tasks (one commit each, two PRs)

### PR H-1: the catalogue, the settings schema and the API

1. **`catalog.toml` and `catalog.py`.** (1 d) Pydantic `Provider` (`id`, `label`, `kind`
   among `openai-compatible`, `anthropic`, `gemini`, `opencode-go`, `runware`, `elevenlabs`,
   `key_setting`, `env_var`, `lists_models`), `Model` (`id`, `provider`, `label`,
   `capabilities` from `text`, `vision`, `image`, `video`, `speech`, `music`, `upscale`,
   `price` as `{amount, unit}` with units `1k_tokens_in`, `1k_tokens_out`, `image`, `second`,
   `1k_chars`, `context`, `max_output`, `recommended`, `source` static or listed,
   `price_source`, `price_checked`) and `Voice` (`id`, `provider`, `model`, `label`,
   `language`, `preview_url`, `recommended`). `load()` merges the static file with the cache
   under `~/.cache/mp3-to-videoclip/catalog/<provider>.json` (with `fetched_at`), overridable
   by `MP3_TO_VIDEOCLIP_CATALOG_CACHE` for tests. `refresh(provider, client)` uses
   `OpenCodeClient.models()` (`opencode.py:265-268`), a new free `RunwareClient.search_models`
   for the Runware model search, and a minimal `ElevenLabsClient.voices` that exists only
   behind a key; listed entries never overwrite a static price. The recommended set: the
   current defaults (`gpt-6.1-sol` for the Writer, `deepseek-v4.1-flash` for the Editor,
   `google-nano-banana-2-1` for pictures, `English_Magnetic_Male_2` for the narrator). Tests
   with recorded responses, no network.
2. **Settings schema 2.** (1 d) `config.py`: `schema_version: int = 2` and nested models
   `roles` (`writer`, `editor`, `critic`, `narrator`: `provider`, `model`, `thinking` in
   `off`, `low`, `medium`, `high`, `max_tokens_per_turn`), `voices` (`provider`,
   `default_voice`, `favourites`), `pictures` (`image_model_by_look`, `video_model`,
   `upscaler`, `reserve_usd_per_still`, `reserve_usd_per_clip_second`), `keys` (`runware`,
   `openai_compatible` with `base_url`, `anthropic`, `gemini`, `opencode_go`, `elevenlabs`),
   `new_films` (`kind`, `length_s`, `aspect`, `fps`, `look`, `budget_usd`,
   `signature_package`, `credit_roles`, `brand` with `name`, `partner`, `logo`, `palette`,
   `font`), `prices` (overrides keyed by model id), and `computer` (`opencode_bin`,
   `opencode_workspace`, `gateway`). The thirteen flat names stay as read-only properties
   computed from the nested ones so `providers.py:187`, `intake.py:258-259`,
   `api/projects.py:398`, `api/director.py:260-265`, `opencode.py:145-146` and the frontend
   types keep working unchanged. `load_settings` migrates a file without `schema_version`
   (the thirteen keys into their new homes, everything else defaulted) and writes a
   `settings.toml.v1.bak` once before the first schema-2 save. `save_settings` writes
   nested tables per D1 and keeps the 0600 swap. `EnvSettings` (`78-81`) gains
   `ELEVENLABS_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` and `OPENCODE_API_KEY`; the
   file still wins. Golden test: a v1 fixture loads to the same effective values before and
   after, and a round trip is byte-stable.
3. **The settings API.** (1 d) `GET /api/settings` returns the nested shape with every key
   blanked and `has_<provider>_key` per provider; `PUT` accepts a partial nested patch and
   merges it, keeping stored keys when a field is empty (`api/settings.py:111-114` rule kept).
   `GET /api/settings/catalog` returns providers, models and voices with a `ready` object per
   entry: `key` (present or not), `reachable` (null until tested, then the last test result
   and time from the cache), `tool` (from `setup.status`), and `unlocks` per provider
   ("pictures", "clips", "voices", "writer", "editor"). `POST /api/settings/catalog/refresh
   {provider}` runs task 1's refresh and reports what changed. `POST /api/settings/test`
   grows `kind: "provider"` with `provider` and optional `model` (free calls only: Runware's
   `recover` as today, OpenAI-compatible and OpenCode Go `GET /models`, Anthropic and Gemini
   model listing, ElevenLabs `GET /v1/user`) and `kind: "voice"` per D2. `GET
   /api/settings/costs` sums every production's `work/tasks.json` by film and by kind using
   `budget.split_commitment`, read-only, in the thread pool. `GET /api/settings/caches` lists
   the four locations with sizes; `POST /api/settings/caches/clear {name}` per D3, through a
   new `caches.py` with the allowlist and a test proving nothing else under a project is
   touched (the `tests/test_archive.py` pattern). Extend `tests/test_api_routes.py` and
   `test_api_errors.py`.
4. **Record the model that answered.** (0.5 d) `promptlog.remember` (`promptlog.py:25-26`)
   is called with `provider` and `model` from the gateway that will run
   (`api/director.py:200`), and the chat row's `prompt` meta (`director/loop.py:69-70`)
   carries them, so the Director header and the prompt history can show the model actually
   used. Approval hashes do not read this file, so nothing goes stale. The per-turn token
   budget and thinking level are stored and shown but not enforced until Phase E2; the
   direct path keeps `roles.writer` for both roles until Phase E1, and the API says so in a
   `notes` field the panel displays.

### PR H-2: the panel

5. **The panel shell.** (1.5 d) `shell/settings/SettingsPanel.tsx` replaces
   `SettingsDialog.tsx` and `settings.css`: a left tab rail, a search box that filters fields
   across tabs, a "What is missing to make a film" checklist at the top computed from the
   catalogue's `ready` states (a Writer key, a Runware key, the renderer, FFmpeg) with each
   line linking to its field, per-field *Saved* through `ui/SaveState.tsx` on blur, *Reset to
   recommended* per section from the catalogue's `recommended` flags, and a `ModelSelect`
   with an "Other…" row that turns into a text field so a new id never blocks the owner.
   The gear (`ui/icons.tsx:70`) is redrawn so it reads as a gear. Escape and the focus trap
   as today.
6. **Roles, Voices, Pictures, Keys.** (1 d) Roles: Writer, Editor, Critic (D5), Narrator,
   each with provider then model dropdowns filtered by capability (`text` and `vision` for
   roles, `speech` for the Narrator), thinking level, per-turn token budget, and the honesty
   note from task 4. Voices: Runware MiniMax voices with the default
   `English_Magnetic_Male_2`, favourites, *Play sample · $price* per D2, and ElevenLabs
   voices only when its key is present. Pictures: image model per look preset, video model,
   upscaler, reserve per still, reserve per clip-second, each with the catalogue price
   beside it and "price unknown" where none is verified. Keys: one row per provider with a
   masked field, *Test*, the status word and "unlocks: …".
7. **New films, This computer, Costs.** (1 d) New films start with: kind, length, aspect,
   fps, look, budget, signature package on or off, credit roles, and the brand kit (name,
   partner, logo file, palette, font) replacing the two unlabeled inputs; `NewProduction.tsx`
   reads these defaults. This computer: tool status dots from `setup.status` and
   `lyric_tools.status` with the existing install buttons (`api.installRenderer`,
   `api.setupLyricTools`), and the four caches with sizes and *Clear*, each saying what is
   rebuilt and that receipts fail closed. Costs: totals by film and by kind from
   `/api/settings/costs`, and the editable price table that writes `prices` overrides, with
   the line "a price here is a reservation input, not a bill; the journal keeps the
   provider's reported cost".
8. **Honesty, docs and the build.** (0.75 d) The Director header (`Director.tsx:744-747`)
   shows the model from the last turn's recorded meta, with the gateway word, and the Roles
   tab repeats the Phase E note; changing a role's model changes no approval (proved by a
   test that approvals are unchanged across a settings save); the narrator voice id and its
   settings hash are stored under `voices` so Phase I can bind takes to them. README
   (`78-80`, `131-133`), `docs/ARCHITECTURE.md:391` and `AGENTS.md` (D3) are updated;
   `frontend/dist` is rebuilt.

About 3.5 days for H-1 and 4.25 days for H-2. The assessment's "three to four days" did not
count the catalogue refresh clients, the costs and cache routes or the migration.

## Not changing

Approval hashes and what they bind (the brand of an existing film stays in its own spec),
the paid-task journal and its truth about cost, timing, the golden contract, the prompts,
the three literals in `signature.py:18-20` and the joint package fallback (Phase F1), the
direct path's single-model behaviour (Phase E1), token accounting (Phase E2), and
production folders beyond the two cache directories allowed by D3. No paid call is made
by any test, any *Test* button or any acceptance step; the only priced button is *Play
sample* and it is not pressed.

## Acceptance

- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, frontend `tsc`,
  `npm test` and `npm run build`, renderer tests pass. New tests: the catalogue loads with
  no cache and no network; a refresh from recorded responses adds listed models without
  touching static prices; a v1 `settings.toml` loads to the same effective values and the
  thirteen flat properties still answer; a schema-2 round trip is byte-stable and the file
  stays 0600; no response from `/api/settings` or `/api/settings/catalog` contains a key
  value; costs sum a two-film fixture correctly by kind; `caches.clear` refuses any path
  outside the allowlist and an archived film; a settings save leaves every approval record
  unchanged.
- On a **throwaway projects folder** in the browser, no key and $0 spent: the panel opens
  from the gear; the checklist names the missing Writer key, Runware key and renderer, and
  each line focuses its field; a model chosen through "Other…" saves and shows *Saved*;
  *Reset to recommended* restores the recommended set; the Narrator shows
  `English_Magnetic_Male_2` and the ElevenLabs section is absent, then present after a
  fake key is saved; *Test* on an empty Runware row says "Add a Runware key first"; This
  computer shows the renderer missing with its install button; Costs shows the fixture
  totals; *Clear* on `work/remotion-chunks` removes only that folder and the next preview
  rebuilds it. On the owner's real settings file: a `.v1.bak` appears once, every existing
  value is still shown, and the Director still answers with the same model as before.
- At 390×844 the tab rail becomes a top strip and no field is cut off.

## Risks

- **The settings file is shared by every film and the launcher.** A bad migration would
  lock the owner out of the Director and pictures at once. The `.v1.bak` copy, the golden
  migration test and the flat properties are the three guards.
- **Catalogue drift.** Model ids and prices change monthly; the static file will be stale
  the day it ships. The `price_checked` date is shown, "Other…" always works, and refresh is
  one click. No automatic refresh, by the owner's rule.
- **A free *Test* may not be free everywhere.** Each provider's test is a listing or
  account call; the plan names them, and a provider that offers no free call gets "cannot be
  tested without a charge" instead of a hidden charge.
- **Per-role models shown but not yet used on the direct path.** Until Phase E1 the Roles
  tab could mislead; task 4's recorded model and the visible note are the mitigation.
- **The panel grows large.** Seven tabs in one file would repeat the 408-line dialog's
  problem; `shell/settings/` is one file per tab from the start.

## Out of scope

Wiring per-role providers on the direct path and retiring `opencode serve` (Phase E1),
tokens and model cost in the journal (Phase E2), narration, takes and voice casting (Phase
I), clips and upscaling purchases (Phases C and I), moving the signature literals and the
preset (Phase F1), a local voice (declined by the owner), and any change to how a
production's budget cap is enforced.
