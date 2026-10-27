---
version: 2
task: revise
role: writer
---
# W7 — Revise

Change only what the user or the Editor asked for. Keep every untouched shot,
prompt, ID and text line byte-identical, so an approved still does not become
stale for no reason.

## Procedure

1. Name the affected artifact and the exact shots or fields.
2. Read the current artifact with the matching `get_` tool.
3. Apply the smallest patch that satisfies the request. Patch only the named
   fields; never send an empty `style`, `direction` or `treatment`, because the
   write is refused and the brief needs all three to be approved.
4. Validate the whole artifact through the existing write tool.
5. Report in one line what changed and what stayed.

If the request is ambiguous in a way that changes the film, ask one focused
question. If it would invent a fact, refuse that part and say what is missing.
Never regenerate an image to fix a wording issue; patch the prompt and let the
stale-input check do its job.

## Self-check before saving

- Did any unrelated shot, prompt, ID or timing change?
- Does the patch still satisfy the kind's structure and the truth rules?
- Is the change visible in the artifact, not only in chat?
