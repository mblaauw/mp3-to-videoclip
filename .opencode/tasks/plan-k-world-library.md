# Phase K: the world library and series — plan

**Proposed** 5 Nov 2026; base `main` at `78fbd26`. Follows
`docs/design/missing-features-2026-11-05.md`, item 3. Decisions taken as recommended.

**Objective:** stop every film starting from nothing. Characters with their reference
bytes and permission, places with their plates, narrators, looks and title packages can be
promoted from a film into a library above productions and adopted into a new film with one
click. A series carries a bible, an episode number and a cast that recurs; the Writer is
told what earlier episodes established. A still from another film can be brought in as an
upload shot with its provenance, so the by-hand copying the Cool Cat record names ends.

## What the code showed

- **A film's world is its brief.** `Brief.characters` (`models.py:251`) carry identity,
  references and `permission_confirmed`, which only the owner sets (`production/brief.py
  _keep_stored_permissions`); `CreativeProfile` carries `scenes`, `references` (kind
  `style|location|prop|sheet` with a path), `narrator`, `place`, `eras` and `look`.
  Reference bytes are immutable PNGs under `media/references/<sha>.png`, imported only by
  `references.import_reference` with a permission flag and a provenance note; the brief
  hash binds them through `image_specs.brief_references`.
- **Nothing lives above a production.** `parked.py` is the one app-level list, a JSON
  beside the settings. `config.NewFilms.brand` holds a brand kit. There is no series, no
  cross-film entry, no `derived_from`.
- **The Writer's snapshot is per film** (`director/context.py build_context`): brief,
  characters, song, shots, cut. Nothing says what another film settled.
- **Intake is one constructor** (`production/intake.py init_project`) with keyword
  options serialised only when set; `Project`'s serializer drops `None` fields so older
  hashes hold. `init_project` writes `brief.json` from the intent before any approval.
- **Still bytes are per film** under `assets/<shot>/v00N-*.jpg` with `input_hash` of the
  spec that made them. An `upload` shot kind (`shotkinds.py:24`) carries an `asset` path
  and is local, so a picture from elsewhere belongs there, not in a paid shot's versions.

## Decisions (taken as recommended)

- **D1 Where.** `library/` beside `projects/`, gitignored, never deleted or rewritten in
  place: `library/world.json` (entries, append-only; an entry is replaced only by a new
  version number), `library/references/<sha>.png`, `library/series/<id>.json`. The app
  takes `--library-dir`; tests use a temp folder.
- **D2 Entries.** `character`, `place` (a scene and its references), `narrator`, `look`
  (look text, image rules, style preset) and `titles` (package id, brand name, partner).
  An entry records `from` (slug, at), its payload as the film stored it, and `files` as
  sha to relative path. Promotion copies bytes, never moves them, and refuses an id that
  exists unless the payload is identical.
- **D3 Adopting is an owner write.** `library.adopt(root, entry_id)` imports the bytes
  through `import_reference` with the note "From the library: <id>, promoted from <slug>"
  and writes the brief through `update_brief(owner=True)` or the profile setter, so
  permission travels with the owner's click and the story asks to be approved again, as a
  reference binding does today. A narrator adopted sets `creative.narrator`; a look sets
  `creative.look`, `image_rules` and `project.style_preset`.
- **D4 Series.** `library/series/<id>.json`: `id`, `title`, `bible` (owner's text),
  `recurring` (entry ids), `episodes` (slug, number, title, logline). `Project.series =
  {"id", "episode"}` serialised only when set. Intake with a series adopts its recurring
  entries into the new brief at creation, before any approval, and appends the episode.
  The Writer's snapshot gets a `## Series` section: the bible clipped to 600 characters
  and each earlier episode's number, title and its treatment's first 240 characters, read
  from `projects/<slug>/brief.json` live, never copied.
- **D5 Bringing a still.** `library.bring_still(root, from_slug, shot_id, version)` copies
  the bytes to `media/uploads/<sha>.<ext>` with a `work/provenance.json` row (`from` slug,
  shot, version, sha) and returns the path for an `upload` shot's `asset`. Nothing is
  shared by reference across folders: the project folder stays the single source of truth.
- **D6 The screen.** A *Library* view at `#/library`: entries by kind with their source
  film and a thumbnail; a *Series* list with the bible editable. In a film: *Promote* on a
  character, place, narrator and the Look card; *From the library* on the Characters and
  World cards; *From another film* in the Storyboard inspector for an upload shot. New film
  gets a *Series* picker with an episode number.

## Tasks (one commit each)

1. **`library.py`.** Paths, entries, promote, adopt, series read and write, bring a still,
   provenance. Tests: bytes copied not moved, an id refused unless identical, adopting
   un-approves the story and keeps permission, a series episode appended once.
2. **Intake and snapshot.** `Project.series`, `init_project(series=, episode=)`, the
   Writer's `## Series` section, `ProjectSummary.series`. Golden unchanged; a film without
   a series keeps every hash (test on the four fixtures' payloads).
3. **Routes.** `GET /api/library`, `POST /api/library/promote`, `POST
   /api/projects/<slug>/library/adopt`, `GET/PUT /api/library/series/<id>`, `POST
   /api/projects/<slug>/library/bring-still`.
4. **The screen.** Library view, Series card, Promote and From-the-library controls,
   the series picker on New film, the still picker on an upload shot.

## Not changing

Approval hashes (a brief with no adopted entry is byte-identical), `import_reference`,
permission ownership, the never-delete rule (extended to `library/`).

## Acceptance

- Checks green. On a scratch copy of the Museum: promote the curator, the place and the
  narrator; create "002" in the series; the new brief carries them with permission, the
  Writer's snapshot names 001's logline; 001's folder is untouched.

## Risks

- A library entry can go stale against the film it came from; the entry records its
  source and date, and nothing is kept in sync by magic.
- `library/` is a new never-delete folder; `caches.py` does not list it.

## Done, 5 Nov 2026

Four commits on `film/phase-k-library`, stacked on the Sound phase: `library.py`; the series
field, intake and the Writer's `## Series` section; the routes and the `--library-dir` flag;
the screen. Decisions D1 to D6 as written, with one change: the `titles` entry kind was left
out, because a titles package lives in the graphics spec and the brand kit rather than in the
brief, and promoting it would have meant a third write path for no proven need.

**Proved:** 10 engine tests (bytes copied not moved, an id refused unless identical, a new
version for other content, adopting un-approves the story and keeps permission, an unpermitted
character travels without its pictures, a look sets the preset, a series keeps its episodes,
a still from another film is a copy with provenance, the series field moves no hash, the
snapshot names an earlier episode's treatment), 2 route tests including a new episode made
through `POST /api/projects` with the recurring cast from its first byte, 4 frontend tests.

**Not proven:** the screen was not driven in a browser test; the Museum's curator has not
been promoted for real (the owner's click); no second episode has been made.
