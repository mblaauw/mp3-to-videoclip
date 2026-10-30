import assert from "node:assert/strict";
import test from "node:test";
import { QUIET_AFTER_SECONDS, quietLine, writingLine } from "../src/shell/directorActivity.ts";

test("a long tool call says what is being written, under either gateway's tool name", () => {
  assert.equal(
    writingLine("Writer", { tool: "create_storyboard", chars: 0 }),
    "The Writer is writing the storyboard…",
  );
  assert.equal(
    writingLine("Writer", { tool: "clipstudio_update_shots", chars: 12400 }),
    "The Writer is writing storyboard changes… · 12,400 characters",
  );
});

test("an unknown tool does not show its internal name", () => {
  assert.equal(writingLine("Editor", { tool: "new_tool", chars: 0 }), "The Editor is writing its next step…");
});

test("the Stop offer waits past a normal long tool call", () => {
  assert.ok(QUIET_AFTER_SECONDS >= 55);
  assert.equal(quietLine(0), null);
  assert.equal(quietLine(QUIET_AFTER_SECONDS - 1), null);
});

test("the Stop offer says how long it has been and that saved work is safe", () => {
  const line = quietLine(65);
  assert.match(line ?? "", /Nothing new for 1:05/);
  assert.match(line ?? "", /you can stop this/);
  assert.match(line ?? "", /already saved stays saved/);
});
