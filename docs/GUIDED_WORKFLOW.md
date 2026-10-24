# Guided Studio workflow

The guided flow is the simpler creation path for **new** productions. It keeps
every content-bound gate, but presents five human steps instead of eight stage
tabs and four administrative menus:

1. **Track** — the agent analyses the recording locally. Measurements remain
   estimates; the user is not asked to certify tempo, beats or sections. Lyrics
   are shown as drafts when relevant.
2. **Story** — the user and agent agree the concept, film style and storyboard.
   The style prompt is visible and editable. A revision request records the
   requested style and notes for the agent; it does not spend.
3. **Style check** — a small selection of representative stills (the existing
   proof IDs) is generated. Each image can be approved or sent back with
   feedback. Approval records a byte-bound verdict.
4. **Images** — every selected still is reviewed. Approve each image or request
   a change. The full set can only be approved when every selected image has an
   accepted verdict for its current bytes.
5. **Finish** — factual credits are prefilled from the last production template,
   edited for this film and confirmed. Composited title/credit samples are
   inspected before the graphics gate. The final render is a separate local
   action; the GUI never starts a paid provider call.

The five steps are presentation; the canonical artifacts, hashes and CLI gates
remain authoritative.

## Guided vs recorded v2

`work/guided-flow.json` marks a guided production. The file is deliberately **not**
part of `project.json` or any artifact hash, so adding the policy cannot silently
change an existing approval. The marker carries the production's source hash and
slug; a marker copied from another production is ignored, and `flow.mark` refuses
a production that already has recorded decisions. Converting a recorded v2 film
is an explicit migration, never a side effect of a stray file.

| Behaviour | Guided (`work/guided-flow.json`) | Recorded v2 (no file) |
| --- | --- | --- |
| Music review | Agent-owned analysis/events; not a user step | Same gates, exposed per stage |
| Preview before full stills | Optional local check | Mandatory watched preview gate |
| Full-still parent | `proof` | `preview` |
| Credits | Late-bound: edited at Finish without invalidating image gates | Digest is inside the brief hash; editing requires a brief revision |
| Studio steps | Five | Five grouped presentation; underlying gates unchanged |

Existing productions are **not migrated**. Their approvals, hashes, preview
binding and credit coupling remain exactly as recorded.

For guided productions, approving the brief does not require prior user approval
of analysis, lyrics, events or the brand package. Those artifacts are still bound
into the brief hash (analysis/lyrics as the upstream hash; events, brand and
listening when present), so changing them makes the brief stale. Recorded v2
productions keep the full upstream approval chain.

## Story approval

The Story screen approves the brief and storyboard as **one human decision** on
guided productions; recorded v2 productions keep their separate per-stage
decisions. The kernel still validates both gates:

- `GET /api/project/<slug>/story-review` returns both current hashes, both readable
  artifacts and a combined hash. It is a lock-free read and creates no files.
- `POST /api/project/<slug>/approve-story` requires the human action capability,
  the combined hash, a decision note and explicit confirmation. It re-derives both
  hashes under the project lock, validates and approves the brief, then the
  storyboard. If the second gate fails, the approvals file is restored byte-for-byte;
  a single click cannot leave a half-approved story.

## Per-image review and feedback

- `POST /api/project/<slug>/review` records an `accept`, `reject` or `uncertain`
  verdict through `reviews.record_review`. The client supplies the shot, version
  and SHA256 it inspected; the server refuses changed bytes. It never generates.
- `POST /api/project/<slug>/feedback` records a durable revision request under
  `work/feedback.json`. Feedback is a human instruction for the agent, not an
  approval and not a generation trigger. It can target the whole film or one
  shot and may carry a replacement style prompt.
- `clip feedback PROJECT --list [--stage story] [--status open]` reads requests.
  `clip feedback PROJECT --resolve ID --reply 'what changed'` closes one after
  the agent has applied and inspected the revision.

Paid regeneration remains a separate scope: the agent prepares a quote, the user
authorizes it in the human Studio session, and a later executor run spends only
within the cumulative cap. The GUI cannot enlarge the quote or start generation.

## Credits

Guided productions can edit `work/graphics-spec.json` at Finish:

- `POST /api/project/<slug>/credits` requires the human action capability, the
  current specification hash, the project title, role/name pairs, a confirmation
  note and an explicit factual-role confirmation. At least one role/name pair is
  required; an empty credit block cannot be confirmed.
- The title and shared production identity remain fixed. Only the factual cards
  and `credit_roles_confirmed` change.
- The brief hash no longer includes the signature for guided productions, so this
  late correction does not invalidate storyboard, proof or image approvals.
- A saved set can be written to `work/credits-template.json`; new guided
  productions prefill from the newest sibling template. Without an explicit
  template, the newest sibling `work/graphics-spec.json` cards are used as a
  read-only fallback, so the current productions can prefill the next film too.
  The new film still requires its own confirmation.
- Film style is prefilled from the newest sibling brief that has a recorded
  brief approval (falling back to the newest brief). An inherited custom style is
  recorded as a custom preset so it remains approvable; a default-compatible
  style keeps the approved default preset. The Story step can still edit it.

Recorded v2 productions refuse this route. Their credits are part of the approved
brief and must be revised through the signature/brief path—no silent rewrite.

## API and security summary

Read-only (session token, no capability, no writes):

```text
GET /api/project/<slug>/workflow
GET /api/project/<slug>/story-review
GET /api/project/<slug>/feedback
```

Human write routes (same-origin JSON, project lock, `X-Studio-Action` capability):

```text
POST /api/project/<slug>/feedback
POST /api/project/<slug>/review
POST /api/project/<slug>/approve-story
POST /api/project/<slug>/credits
POST /api/project/<slug>/approve/<stage>
POST /api/project/<slug>/authorize/<quote>
```

Feedback/review/credits are not spending authority. None of these routes calls a
provider, uploads data or runs an executor. The existing approval/authorization
routes retain their exact-content hash checks.

## CLI

```sh
uv run clip feedback PROJECT --list --status open
uv run clip feedback PROJECT --stage story --message 'Make the middle quieter'
uv run clip feedback PROJECT --resolve fb-... --reply 'Revised s015 and rebounded the board'
```

`feedback` is classified as an `edit` command: it writes only
`work/feedback.json`, never approvals or provider state.

## Archive

The active `projects/` directory contains only the two productions the user chose
to keep:

- `forward-ever`
- `stof-en-stilte`

The other six were moved, not deleted, to
`archive/projects-2026-10-24/` and are ignored by git and by Studio. To bring one
back, move its directory into `projects/` and refresh—no manifest edit is needed.
