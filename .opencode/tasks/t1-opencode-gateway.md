# T1 — OpenCode gateway spike

**Objective:** prove the Studio can drive a locally spawned OpenCode v2 server
as the Writer/Editor gateway before committing to that design.

**Time-box:** one session. No paid or external model call: every model step went
to a local OpenAI-compatible mock on `127.0.0.1:40101`. The OpenCode server ran
isolated on `127.0.0.1:40999` with its own `XDG_*` directories. No production
folder was read for writing or modified.

## Verified contract (OpenCode 2.0.28)

### Server and auth

- `opencode serve --hostname 127.0.0.1 --port 40999` serves the v2 API and web
  UI. `GET /api/info` returns version, pid, URLs and capabilities.
- Basic auth is mandatory for `/api/*`. The generated password is printed once
  as `server password <43 chars>`; without it every request is `401`.
- Setting `OPENCODE_SERVER_PASSWORD` before launch fixes the password and
  suppresses the printed line. Verified: fixed password `200`, wrong password
  `401`, no header `401`.
- The Basic username is `opencode`; the header is
  `Authorization: Basic base64("opencode:<password>")`.
- The OpenAPI document at `/openapi.json` declares **no** security scheme, so
  generated clients will not add auth automatically.
- The CLI binary on this machine is 2.0.28, while the already-running shared
  service reported 2.1.4. The Studio must spawn and pin its own binary.

### Session, prompt and history

- `POST /api/session` with an optional `{title, model, location, permissions}`
  returns `{data: {id, projectID, location, time, ...}}`.
- `POST /api/session/{id}/prompt` with `{text, files?, agents?, skills?,
  metadata?, resume?}` durably admits one input and returns the inbox item; the
  model runs asynchronously. A later prompt on an idle session starts a new
  execution.
- `GET /api/session/{id}/message?limit&order&cursor` returns history newest-first
  by default, plus a cursor. Completion is recorded as a message with
  `type: "idle"` and `outcome: "succeeded"`, alongside the assistant message.
- `POST /api/session/{id}/model` with
  `{"model": {"id": "...", "providerID": "..."}}` returns `204`. A session moved
  from model `coder` to `alt`; the next `session.step.started` and assistant
  message both reported `alt`. Routing is per session, not per server.
- Prompt file attachments take a **`uri`**, not inline bytes:
  `{"uri": "data:image/png;base64,...", "name": "dot.png"}`. The server converts
  a data URI into an OpenAI `image_url` part. A 512 px JPEG data URI (the T0
  thumbnail size) was accepted and reached the provider as an `image_url`.
- The prompt response echoes the user's file as
  `payload.files[].data` containing the base64. The Studio must strip file data
  before persisting or logging that response.

### Events

`GET /api/event` is one global SSE stream for the server, not per session.
Envelope: `{id, created, type, data, location?, durable?}` plus `: heartbeat`
comments. Observed types:

| Type | Meaning |
| --- | --- |
| `server.connected` | Stream opened |
| `session.created` | Session exists |
| `session.inbox.enqueued` / `.delivered` | Prompt admitted / handed to the loop |
| `session.execution.started` / `.succeeded` / `.interrupted` | Execution lifecycle |
| `session.step.started` / `.streamed` / `.ended` / `.failed` | One model step |
| `session.text.started` / `.delta` / `.ended` | Streaming assistant text |
| `session.tool.input.started` / `.ended` | Tool arguments arriving |
| `session.tool.called` / `.progress` / `.success` | Tool execution |
| `permission.asked` / `permission.replied` | Callback approval |
| `session.usage.updated` | Cost/token totals |
| `session.instructions.updated` | System prompt changed |
| `skill.updated` | Skill catalog changed |

- `session.text.delta` carries `delta`; `session.text.ended` carries the full
  `text`, so a client can reconcile a dropped delta.
- Reconnect with `Last-Event-ID` was **ignored**: only `server.connected` and
  heartbeats arrived. The Studio must refetch `/api/session/{id}/message` after
  any reconnect and deduplicate by message ID.
- There is no per-session event filter; the Studio filters on
  `data.sessionID`.

### Stop

`POST /api/session/{id}/interrupt?resume=false` returned `{"interrupted":true}`.
The running step ended with `session.step.failed` followed by
`session.execution.interrupted`. The partial assistant text stayed in history
with `finish: "error"`, not a distinct "interrupted" finish. The Studio should
surface Stop as an interrupted state, not a failure.

### MCP callbacks

- Configure under `mcp.servers.<name>`; a local stdio server used
  `{"type": "local", "command": [...], "codemode": false}`.
  `codemode: false` exposes the tools directly; the default wraps them in Code
  Mode's `execute` tool.
- `GET /api/mcp` reports connection state. A server that used LSP-style
  `Content-Length` framing timed out; MCP stdio uses newline-delimited JSON.
- A tool call produced `session.tool.input.started/ended`,
  `session.tool.called`, `session.tool.success`, and a second model step with
  the tool result. The server received
  `_meta["ai.opencode/sessionID"]` with the invoking session ID, which is the
  correlation value the Studio needs.
- Permissions: an `ask` rule on `shell` emitted `permission.asked` with
  `{id, sessionID, action, resources, save, source}` and waited.
  `POST /api/session/{id}/permission/{requestID}/reply` with
  `{"decision": "once"}` returned `204`, followed by `permission.replied` and
  the tool result. Decisions are `once`, `always`, `reject`.
- MCP tools were allowed without a prompt by default; the Studio should still
  pin explicit allow rules for its own server and deny everything else.

### Prompt cost warning

The default `build` agent injected a **25,151-character** system prompt and 12
built-in tools (including shell, edit and subagent) into the mock provider
request, because the server ran in this repository and picked up `AGENTS.md`
and skills. A Studio gateway must run in a minimal dedicated workspace and use
a dedicated agent with Studio-only permissions and instructions.

## Proposed T2 decisions

1. **Transport:** spawn one `opencode serve` child per Studio app, on an
   allocated loopback port, with a random per-launch
   `OPENCODE_SERVER_PASSWORD` and isolated `XDG_*` directories. Do not reuse the
   user's shared service.
2. **Workspace:** run the server in a dedicated empty gateway directory, never
   in `projects/<slug>` and never in this repository. The Studio MCP server
   receives the production root explicitly.
3. **Tools:** expose the director tools through the Studio's own MCP server
   with `codemode: false`; disable or deny the built-in coding tools and shell.
4. **Images:** send T0 thumbnails as JPEG data URIs in `prompt.files`; strip
   base64 from every stored response.
5. **Streaming:** map text/tool/permission events to the existing Studio turn
   events; reconcile from session history after reconnect; Stop calls
   `interrupt`.
6. **Model routing:** select the model per session from
   `GET /api/model`; switch with the session model endpoint. Real provider
   credentials and prices remain unverified.

## Open questions

- Does a Studio-owned MCP tool result support image content, or must the director
  fetch thumbnails through a separate channel?
- Does the dedicated agent config cleanly remove all built-in tools without
  also removing MCP tools?
- How should OpenCode's own session store relate to `work/chat.jsonl`? Mirror
  text only, or treat OpenCode as the source and keep the Studio log as a cache?
- Which real provider/model and reasoning variant should the gateway use, and
  what is the accepted per-turn cost ceiling?
- Should the gateway be one server per app or one per open production, given
  location-scoped credentials and MCP servers?

## Evidence

- `GET /api/info` on the isolated server: `version: 2.0.28`.
- Auth matrix: fixed password `200`, wrong `401`, absent `401`.
- Plain prompt: text deltas, `session.execution.succeeded`, assistant finish
  `stop`.
- Model switch: `204`; next step and assistant message reported `alt`.
- Image: 512 px JPEG data URI accepted; provider request contained
  `image_url` with the data URI.
- Stop: `{"interrupted":true}`; `session.execution.interrupted`; partial text
  retained.
- MCP: `echo` tool result returned to a second model step; server log recorded
  `sessionID: ses_e8b925d86ffeXX6kmeWbxhOeIO`.
- Permission: `permission.asked`, `decision: once` -> `204`,
  `permission.replied`, `session.tool.success`.
- No external model call, no paid call, no production write.

## Status

Spike complete. The isolated server and mock provider were stopped; the scratch
fixtures remain under gitignored `.opencode/scratch/t1/` for the next phase.

## Implementation (slice 1, in progress)

- `director/opencode.py`: app-owned process manager, fixed password, 2.0.x
  health/version check, config writer, async client, SSE relay, session reuse,
  Stop on stream close, persisted text history.
- `director/mcp.py`: newline-delimited stdio MCP bridge over the safe director
  tools; paid jobs and renders excluded; slug confined to `projects/`;
  `get_images` becomes MCP image content.
- `config.py`: `gateway`, `opencode_bin`, `writer_model`, `editor_model` and
  `opencode_workspace`; the old direct fields stay for fallback.
- `api/director.py`: role-aware routing (`writer` for content stages, `editor`
  for Film), model availability check before the stream, gateway failure
  fallback only when a direct key exists, app-owned gateway cache.
- `app.py`: gateway shutdown in the app lifespan.
- `docs/ARCHITECTURE.md`: durable gateway contract and known limits.

Verified locally with the real 2.0.28 binary and the local mock provider: a
Writer session exposed only `clipstudio_*` tools and called
`clipstudio_get_project`, whose result fed a second model step. One manual
probe first created a session without setting its model; OpenCode fell back to
a free catalog model and returned a quota 429. No paid call was made. The
gateway now validates the configured model and sets it explicitly.

Remaining for T1: the settings UI, a live Writer/Editor probe on the
configured models (owner authorization required), and the PR/CI cycle.
