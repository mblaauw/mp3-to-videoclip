import assert from "node:assert/strict";
import test from "node:test";
import { ApiError, errorAction, errorCopy } from "../src/api/errors.ts";

test("an error prints as its sentence, not its class", () => {
  const error = new ApiError(404, "storyboard_missing", "The storyboard has not been made yet.");
  assert.equal(String(error), "The storyboard has not been made yet.");
});

test("a code with no copy falls back to what the server said", () => {
  assert.equal(new ApiError(400, "bad_request", "select at least one shot").message, "select at least one shot");
});

test("provider tokens never reach the owner bare", () => {
  for (const code of ["network_error", "invalidApiKey", "insufficientCredits", "provider_error"]) {
    assert.doesNotMatch(new ApiError(502, code, `${code} (http status 500)`).message, /_|http status|[a-z][A-Z]/, code);
  }
});

test("a missing key offers Settings", () => {
  for (const code of ["no_llm_key", "no_runware_key", "invalidApiKey"]) {
    assert.deepEqual(errorAction(code), { label: "Open settings", settings: true }, code);
  }
});

test("a missing artifact offers the stage that makes it", () => {
  assert.deepEqual(errorAction("storyboard_missing"), { label: "Go to Storyboard", stage: "storyboard" });
  assert.deepEqual(errorAction("brief_missing"), { label: "Go to Story", stage: "story" });
  assert.deepEqual(errorAction("analysis_missing"), { label: "Go to Track", stage: "track" });
  assert.equal(errorAction("bad_request"), undefined);
  assert.equal(errorAction(undefined), undefined);
});

test("copy is available for job failures by code", () => {
  assert.match(errorCopy("no_runware_key") ?? "", /Runware key/);
  assert.equal(errorCopy("nonsense"), undefined);
  assert.equal(errorCopy(null), undefined);
});
