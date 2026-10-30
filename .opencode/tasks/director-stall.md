# Director stall — record

**Objective:** a silent Writer turn is visible and bounded. A live turn sat with no
new step for about 9 minutes until it was stopped by hand; the same request retried
alone finished in 55 s. The cause of that stall was not established.

## What the code showed

- `AsyncOpenAI` kept its defaults: 600 s of read silence and 2 retries. Keep-alive
  bytes would reset even that without producing a chunk.
- The gateway had a 900 s limit on the whole turn and no idle limit, nothing bounded
  the wait for `server.connected`, and a closed event stream ended with no event.
- The Director ignored `done`, so gateway errors, including its old timeout, were
  never shown. It now shows them.
- OpenCode's `session.tool.input.started` and `.ended` carry nothing in between, so
  a long tool call is silent on the gateway path.

## Decisions

| Limit | Value | Why |
| --- | --- | --- |
| Direct and gateway silence | 180 s | About three whole 55 s turns, in case a provider holds a tool call back and sends it in one piece. |
| Gateway, tool arguments open | 300 s | The events say nothing until the arguments are complete. |
| Whole gateway turn | 900 s | Unchanged; now a plain error. |
| Director offers Stop | 60 s | Past a normal long step. Only an offer; the turn goes on. |

Retries stay at 1, inside the idle limit, so a quick 429 or 5xx still recovers but a
silent request is never sent twice.

## Acceptance

No paid or live model call was made. `tests/test_director_loop.py` and
`tests/test_director_opencode.py` prove the stalled turn ends with the error and
writes nothing, and that slow arguments which keep arriving are not a stall.

The UI was tried in the app against a fake model on a throwaway projects folder, with
the limit shortened to 75 s: the writing line and its count, the Stop offer at 1:00,
the plain error, an intact chat log, and Ask again answering. The gateway path has
fake-client tests only, not a run against a real OpenCode process, and the limits have
not yet met a live long turn.
