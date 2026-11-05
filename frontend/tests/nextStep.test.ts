import assert from "node:assert/strict";
import test from "node:test";
import {
  nextStep,
  type ApprovalMap,
  type ImageFacts,
  type ProjectFacts,
  type StageState,
} from "../src/shell/nextStep.ts";

const states = (overrides: Partial<Record<string, StageState>> = {}) => ({
  track: "done" as StageState,
  story: "you" as StageState,
  storyboard: "not_ready" as StageState,
  images: "not_ready" as StageState,
  film: "not_ready" as StageState,
  ...overrides,
});

const project = (overrides: Partial<ProjectFacts> = {}): ProjectFacts => ({
  music_mode: "vocal",
  has_analysis: true,
  has_lyrics: true,
  stage_states: states(),
  ...overrides,
});

const approvals = (overrides: ApprovalMap = {}): ApprovalMap => ({
  brief: { state: "missing" },
  storyboard: { state: "missing" },
  proof: { state: "missing" },
  stills: { state: "missing" },
  preview: { state: "missing" },
  graphics: { state: "missing" },
  ...overrides,
});

const images = (overrides: Partial<ImageFacts> = {}): ImageFacts => ({
  total: 4,
  selected: 4,
  kept: 4,
  missing: 0,
  missing_ids: [],
  reserve_usd: "0.05",
  ...overrides,
});

const budget = { remaining_usd: "5.00", cap_usd: "8.00", committed_usd: "3.00" };

test("track asks for analysis when the song has not been measured", () => {
  const step = nextStep(
    "track",
    project({ has_analysis: false, stage_states: states({ track: "you" }) }),
    approvals(),
    images(),
    budget,
  );
  assert.equal(step.tone, "you");
  assert.match(step.title, /Measure the song/);
  assert.deepEqual(step.actions[0], {
    label: "Run analysis",
    target: "analysis",
    kind: "primary",
  });
});

test("track reports a running analysis without inventing progress", () => {
  const step = nextStep(
    "track",
    project({ stage_states: states({ track: "running" }) }),
    approvals(),
    images(),
    budget,
  );
  assert.match(step.title, /Measuring/);
  assert.equal(step.actions.length, 0);
});

test("track asks for lyrics on a measured vocal song without them", () => {
  const step = nextStep(
    "track",
    project({ has_analysis: true, has_lyrics: false, stage_states: states({ track: "you" }) }),
    approvals(),
    images(),
    budget,
  );
  assert.match(step.title, /Add the lyrics/);
  assert.deepEqual(step.actions[0], { label: "Add lyrics", target: "lyrics", kind: "primary" });
});

test("track still asks to measure when neither analysis nor lyrics exist", () => {
  const step = nextStep(
    "track",
    project({ has_analysis: false, has_lyrics: false, stage_states: states({ track: "you" }) }),
    approvals(),
    images(),
    budget,
  );
  assert.match(step.title, /Measure the song/);
});

test("a vocal advert does not demand lyrics", () => {
  const step = nextStep(
    "track",
    project({ kind: "advert", has_lyrics: false }),
    approvals(),
    images(),
    budget,
  );
  assert.equal(step.tone, "done");
  assert.equal(step.actions[0].to, "story");
});

test("track is ready once analysis and lyrics exist", () => {
  const step = nextStep("track", project(), approvals(), images(), budget);
  assert.equal(step.tone, "done");
  assert.equal(step.actions[0].to, "story");
});

test("story asks the writer to start when there is no brief", () => {
  const step = nextStep(
    "story",
    project({ stage_states: states({ story: "not_ready" }) }),
    {},
    images(),
    budget,
  );
  assert.match(step.title, /Write the story/);
  assert.equal(step.actions[0].target, "brief");
});

test("story names lyrics as the real blocker", () => {
  const step = nextStep(
    "story",
    project({ has_lyrics: false }),
    {
      brief: {
        state: "unavailable",
        blocking_stage: "lyrics",
        error: "lyrics is missing; its artifact has not been created",
      },
    },
    images(),
    budget,
  );
  assert.match(step.title, /lyrics first/);
  assert.equal(step.actions[0].to, "track");
});

test("story names analysis as the real blocker", () => {
  const step = nextStep(
    "story",
    project({ has_analysis: false }),
    {
      brief: {
        state: "unavailable",
        blocking_stage: "analysis",
        error: "analysis is missing; its artifact has not been created",
      },
    },
    images(),
    budget,
  );
  assert.match(step.title, /Measure the song first/);
  assert.equal(step.actions[0].to, "track");
});

test("story asks for approval when the brief is unapproved", () => {
  const step = nextStep("story", project(), approvals(), images(), budget);
  assert.match(step.title, /approve it/);
  assert.equal(step.actions[0].target, "approval");
  assert.equal(step.actions[0].approve, "brief");
});

test("story asks for lyrics before an unapproved brief even when the file is empty", () => {
  const step = nextStep(
    "story",
    project({ has_lyrics: false }),
    approvals({ brief: { state: "missing" } }),
    images(),
    budget,
  );
  assert.match(step.title, /lyrics first/);
  assert.equal(step.actions[0].to, "track");
});

test("story reports the real reason and the diff action when stale", () => {
  const step = nextStep(
    "story",
    project({ stage_states: states({ story: "changed" }) }),
    approvals({
      brief: {
        state: "stale",
        reason: "The style-check shots moved to s002, s018 and s033.",
      },
    }),
    images(),
    budget,
  );
  assert.equal(step.tone, "changed");
  assert.match(step.title, /changed/);
  assert.match(step.detail || "", /style-check shots moved/);
  assert.deepEqual(step.actions[0], { label: "See what changed", target: "changes" });
  assert.equal(step.actions[1].approve, "brief");
});

test("an advert asks for its message and call to action before the story", () => {
  const step = nextStep(
    "story",
    project({
      kind: "advert",
      has_message: false,
      has_cta: false,
      stage_states: states({ story: "you" }),
    }),
    approvals({ brief: { state: "missing" } }),
    images(),
    budget,
  );
  assert.match(step.title, /make people do/);
  assert.deepEqual(step.actions[0], {
    label: "Edit brief",
    target: "brief",
    kind: "primary",
  });
});

test("story continues to storyboard when approved", () => {
  const step = nextStep(
    "story",
    project({ stage_states: states({ story: "done" }) }),
    approvals({ brief: { state: "approved" } }),
    images(),
    budget,
  );
  assert.equal(step.tone, "done");
  assert.equal(step.actions[0].to, "storyboard");
});

test("a v2 story asks for the creative profile before approval", () => {
  const step = nextStep(
    "story",
    project({
      prompt_version: 2,
      profile_version: 0,
      stage_states: states({ story: "you" }),
    }),
    approvals({ brief: { state: "missing" } }),
    images(),
    budget,
  );
  assert.match(step.title, /build the cast and places/);
  assert.equal(step.actions[0].target, "director");
});

test("a v2 story with a profile offers the approval", () => {
  const step = nextStep(
    "story",
    project({
      prompt_version: 2,
      profile_version: 1,
      stage_states: states({ story: "you" }),
    }),
    approvals({ brief: { state: "missing", expected_hash: "abc" } }),
    images(),
    budget,
  );
  assert.equal(step.actions[0].approve, "brief");
  assert.match(step.title, /approve/);
});

test("storyboard is blocked by the story", () => {
  const step = nextStep(
    "storyboard",
    project({ stage_states: states({ story: "you" }) }),
    approvals(),
    images(),
    budget,
  );
  assert.match(step.title, /story needs approval/);
  assert.equal(step.actions[0].to, "story");
});

test("storyboard asks for a board when none exists", () => {
  const step = nextStep(
    "storyboard",
    project({ stage_states: states({ story: "done", storyboard: "not_ready" }) }),
    approvals({ brief: { state: "approved" } }),
    images(),
    budget,
  );
  assert.match(step.title, /No storyboard yet/);
  assert.equal(step.actions[0].target, "board");
});

test("storyboard asks for approval when the board is unapproved", () => {
  const step = nextStep(
    "storyboard",
    project({ stage_states: states({ story: "done", storyboard: "you" }) }),
    approvals({ brief: { state: "approved" } }),
    images(),
    budget,
  );
  assert.match(step.title, /approve it/);
  assert.equal(step.actions[0].target, "approval");
});

test("storyboard reports a changed board", () => {
  const step = nextStep(
    "storyboard",
    project({ stage_states: states({ story: "done", storyboard: "changed" }) }),
    approvals({ brief: { state: "approved" }, storyboard: { state: "stale" } }),
    images(),
    budget,
  );
  assert.equal(step.tone, "changed");
  assert.match(step.title, /changed/);
});

test("storyboard continues to images when approved", () => {
  const step = nextStep(
    "storyboard",
    project({ stage_states: states({ story: "done", storyboard: "done" }) }),
    approvals({ brief: { state: "approved" }, storyboard: { state: "approved" } }),
    images(),
    budget,
  );
  assert.equal(step.tone, "done");
  assert.equal(step.actions[0].to, "images");
});

test("images are blocked by the storyboard", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "you" }) }),
    approvals({ brief: { state: "approved" } }),
    images(),
    budget,
  );
  assert.match(step.title, /Approve the storyboard/);
  assert.equal(step.actions[0].to, "storyboard");
});

test("images ask for the style check", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({ brief: { state: "approved" }, storyboard: { state: "approved" } }),
    images(),
    budget,
  );
  assert.match(step.title, /style check/);
  assert.equal(step.actions[0].target, "pictures");
});

test("images report a changed style check", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "changed" }) }),
    approvals({
      brief: { state: "approved" },
      storyboard: { state: "approved" },
      proof: { state: "stale" },
    }),
    images(),
    budget,
  );
  assert.equal(step.tone, "changed");
  assert.match(step.title, /style check changed/i);
});

test("images ask for the missing pictures after the style check", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({
      brief: { state: "approved" },
      storyboard: { state: "approved" },
      proof: { state: "approved" },
    }),
    images({
      missing: 2,
      kept: 2,
      selected: 2,
      missing_ids: ["s003", "s004"],
      reserve_usd: "0.05",
    }),
    budget,
  );
  assert.match(step.title, /Make 2 missing pictures/);
  assert.match(step.detail || "", /5\.00/);
  assert.equal(step.actions[0].target, "make-missing");
  assert.equal(step.actions[0].label, "Make all 2 missing · $0.10");
  assert.deepEqual(step.actions[0].paid, { ids: ["s003", "s004"], scope: "stills" });
});

test("a single missing still is named with its price", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({
      brief: { state: "approved" },
      storyboard: { state: "approved" },
      proof: { state: "approved" },
    }),
    images({
      missing: 1,
      kept: 3,
      selected: 3,
      missing_ids: ["s033"],
      reserve_usd: "0.04",
    }),
    budget,
  );
  assert.equal(step.actions[0].target, "make-missing");
  assert.equal(step.actions[0].label, "Make s033 · $0.04");
});

test("images ask for review when every picture exists", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({
      brief: { state: "approved" },
      storyboard: { state: "approved" },
      proof: { state: "approved" },
    }),
    images({ missing: 0, kept: 3, selected: 4 }),
    budget,
  );
  assert.match(step.title, /Review the remaining 1 picture/);
  assert.equal(step.actions[0].target, "pictures");
});

test("images ask for the full stills approval when every picture is kept", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({
      brief: { state: "approved" },
      storyboard: { state: "approved" },
      proof: { state: "approved" },
    }),
    images({ missing: 0, kept: 4, selected: 4 }),
    budget,
  );
  assert.match(step.title, /Approve all stills/);
  assert.equal(step.actions[0].target, "approval");
});

test("images continue to film when the stills are approved", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "done" }) }),
    approvals({
      brief: { state: "approved" },
      storyboard: { state: "approved" },
      stills: { state: "approved" },
    }),
    images(),
    budget,
  );
  assert.equal(step.tone, "done");
  assert.equal(step.actions[0].to, "film");
});

test("film is blocked by unapproved stills", () => {
  const step = nextStep(
    "film",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals(),
    images(),
    budget,
  );
  assert.match(step.title, /Approve every picture/);
  assert.equal(step.actions[0].to, "images");
});

test("film asks for the preview", () => {
  const step = nextStep(
    "film",
    project({
      stage_states: states({ story: "done", storyboard: "done", images: "done", film: "you" }),
    }),
    approvals({ stills: { state: "approved" } }),
    images(),
    budget,
  );
  assert.match(step.title, /Watch the preview/);
  assert.equal(step.actions[0].target, "preview");
});

test("film reports a stale preview", () => {
  const step = nextStep(
    "film",
    project({
      stage_states: states({ story: "done", storyboard: "done", images: "done", film: "you" }),
    }),
    approvals({ stills: { state: "approved" }, preview: { state: "stale" } }),
    images(),
    budget,
  );
  assert.equal(step.tone, "changed");
  assert.match(step.title, /preview changed/i);
});

test("film asks for the titles after the preview", () => {
  const step = nextStep(
    "film",
    project({
      stage_states: states({ story: "done", storyboard: "done", images: "done", film: "you" }),
    }),
    approvals({ stills: { state: "approved" }, preview: { state: "approved" } }),
    images(),
    budget,
  );
  assert.match(step.title, /Check the titles/);
  assert.equal(step.actions[0].target, "render");
});

test("film is ready when every gate is approved", () => {
  const step = nextStep(
    "film",
    project({
      stage_states: states({ story: "done", storyboard: "done", images: "done", film: "you" }),
    }),
    approvals({
      stills: { state: "approved" },
      preview: { state: "approved" },
      graphics: { state: "approved" },
    }),
    images(),
    budget,
  );
  assert.equal(step.tone, "done");
  assert.match(step.title, /Ready to render final/);
  assert.equal(step.actions[0].target, "render");
});

test("film reports a verified final without sending you to Film again", () => {
  const step = nextStep(
    "film",
    project({
      stage_states: states({ story: "done", storyboard: "done", images: "done", film: "done" }),
    }),
    approvals(),
    images(),
    budget,
  );
  assert.equal(step.tone, "done");
  assert.match(step.title, /Final ready/);
  // The one way on is Publish, never Film itself.
  assert.deepEqual(step.actions.map((action) => action.to), ["publish"]);
});

test("publish waits for the final, then asks for the listening, and rests once released", () => {
  const before = nextStep("publish", project({ stage_states: states({ film: "you" }) }), approvals(), images(), budget);
  assert.match(before.title, /Render the final first/);
  assert.deepEqual(before.actions.map((action) => action.to), ["film"]);
  const ready = nextStep("publish", project({ stage_states: states({ film: "done" }) }), approvals(), images(), budget);
  assert.match(ready.title, /Hear it through/);
  const done = nextStep("publish", project({ stage_states: states({ film: "done" }), released: true }), approvals(), images(), budget);
  assert.equal(done.tone, "done");
  assert.match(done.title, /Released/);
});

test("film skips the preview and titles when this production has neither gate", () => {
  const step = nextStep(
    "film",
    project({
      signature_required: false,
      preview_required: false,
      stage_states: states({ story: "done", storyboard: "done", images: "done", film: "you" }),
    }),
    approvals({ stills: { state: "approved" } }),
    images(),
    budget,
  );
  assert.equal(step.tone, "done");
  assert.match(step.title, /Ready to render final/);
});

test("film keeps the preview gate when the production records one", () => {
  const step = nextStep(
    "film",
    project({
      signature_required: false,
      preview_required: true,
      stage_states: states({ story: "done", storyboard: "done", images: "done", film: "you" }),
    }),
    approvals({ stills: { state: "approved" } }),
    images(),
    budget,
  );
  assert.match(step.title, /Watch the preview/);
});

test("images offer to make the missing style-check stills at their price", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({ brief: { state: "approved" }, storyboard: { state: "approved" } }),
    images({ proof_total: 3, proof_kept: 0, proof_missing_ids: ["s1", "s4"], reserve_usd: "0.05" }),
    budget,
  );
  assert.equal(step.actions[0].target, "make-missing");
  assert.deepEqual(step.actions[0].paid, { ids: ["s1", "s4"], scope: "proof" });
  assert.match(step.actions[0].label, /\$0\.10/);
});

test("images offer to remake style-check stills made from an older look", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({ brief: { state: "approved" }, storyboard: { state: "approved" } }),
    images({
      proof_total: 3,
      proof_kept: 2,
      proof_missing_ids: [],
      proof_stale_ids: ["s006"],
      reserve_usd: "0.05",
    }),
    budget,
  );
  assert.equal(step.actions[0].target, "make-missing");
  assert.deepEqual(step.actions[0].paid, { ids: ["s006"], scope: "proof" });
  assert.match(step.actions[0].label, /Remake 1 style still/);
  assert.match(step.title, /Older style-check stills/);
});

test("images combine missing and stale style-check stills in one remake", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({ brief: { state: "approved" }, storyboard: { state: "approved" } }),
    images({
      proof_total: 3,
      proof_kept: 1,
      proof_missing_ids: ["s001"],
      proof_stale_ids: ["s006"],
      reserve_usd: "0.05",
    }),
    budget,
  );
  assert.deepEqual(step.actions[0].paid, { ids: ["s001", "s006"], scope: "proof" });
  assert.match(step.actions[0].label, /Remake 2 style stills/);
  assert.match(step.actions[0].label, /\$0\.10/);
});

test("images approve the style check from the bar once every proof still is kept", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({
      brief: { state: "approved" },
      storyboard: { state: "approved" },
      proof: { state: "missing", expected_hash: "abc" },
    }),
    images({ proof_total: 3, proof_kept: 3, proof_missing_ids: [] }),
    budget,
  );
  assert.equal(step.actions[0].approve, "proof");
  assert.match(step.title, /style-check stills kept/);
  assert.match(step.actions[0].label, /Approve style check/);
});

test("every approval in the bar names its stage, so it approves in place", () => {
  const board = nextStep(
    "storyboard",
    project({ stage_states: states({ story: "done", storyboard: "you" }) }),
    approvals({ brief: { state: "approved" } }),
    images(),
    budget,
  );
  assert.equal(board.actions[0].approve, "storyboard");
});

test("a running batch replaces the make button instead of offering a second batch", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({
      brief: { state: "approved" },
      storyboard: { state: "approved" },
      proof: { state: "approved" },
    }),
    images({ missing: 4, missing_ids: ["s2", "s3", "s4", "s5"], running: true, running_line: "2 of 4 images" }),
    budget,
  );
  assert.equal(step.actions.length, 0);
  assert.match(step.title, /Making stills/);
  assert.match(step.detail || "", /2 of 4 images/);
});

test("a new cut with every still kept is approved on Film, not sent back to Images", () => {
  const stale = { ...approvals(), stills: { state: "stale" as const, expected_hash: "h" } };
  const step = nextStep(
    "film",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "done", film: "you" }) }),
    stale,
    { ...images(), total: 3, selected: 3, kept: 3, stale: 0 },
    budget,
  );
  assert.match(step.title, /The cut changed/);
  assert.equal(step.actions[0].approve, "stills");
  const changedPicture = nextStep(
    "film",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "changed", film: "not_ready" }) }),
    stale,
    { ...images(), total: 3, selected: 3, kept: 3, stale: 1 },
    budget,
  );
  assert.match(changedPicture.title, /Approve every picture/);
});

test("a titles review waiting to be inspected is what the bar asks for", () => {
  const step = nextStep(
    "film",
    project({
      preview_required: false,
      titles_review_ready: true,
      stage_states: states({ story: "done", storyboard: "done", images: "done", film: "you" }),
    }),
    { ...approvals(), stills: { state: "approved" as const }, graphics: { state: "stale" as const } },
    images(),
    budget,
  );
  assert.match(step.title, /Review the titles/);
  assert.equal(step.actions[0].target, "render");
});


test("a film with no paid stills can still pass the style check", () => {
  const step = nextStep(
    "images",
    project({ stage_states: states({ story: "done", storyboard: "done", images: "you" }) }),
    approvals({
      brief: { state: "approved" },
      storyboard: { state: "approved" },
      proof: { state: "missing", expected_hash: "abc" },
    }),
    images({ proof_total: 0, proof_kept: 0, proof_missing_ids: [] }),
    budget,
  );
  assert.equal(step.actions[0].approve, "proof");
  assert.match(step.title, /No stills to buy/);
});

test("no step ever links to the stage it is shown on", () => {
  const stages = ["track", "story", "storyboard", "images", "film"] as const;
  const stageStates: StageState[] = ["done", "you", "changed", "not_ready", "running"];
  const decisions = ["approved", "stale", "missing", "unavailable"] as const;
  const errors = [null, "analysis is missing", "lyrics are missing", "permission to upload/depict hero is not confirmed.", "something else"];
  const facts: Partial<ProjectFacts>[] = [
    {},
    { has_analysis: false },
    { has_lyrics: false },
    { kind: "advert", has_message: false, has_cta: false },
    { prompt_version: 2, profile_version: 0, has_model_key: false },
    { prompt_version: 2, profile_version: 0, has_model_key: true },
    { has_storyboard: false },
    { placeholder_shot_ids: ["s001"] },
  ];
  let seen = 0;
  for (const stage of stages) {
    for (const state of stageStates) {
      for (const decision of decisions) {
        for (const error of errors) {
          for (const fact of facts) {
            const map = Object.fromEntries(
              ["brief", "storyboard", "proof", "stills", "preview", "graphics"].map((name) => [
                name,
                { state: decision, error },
              ]),
            ) as ApprovalMap;
            const step = nextStep(
              stage,
              project({ ...fact, stage_states: states({ [stage]: state }) }),
              map,
              images(),
              budget,
            );
            seen += 1;
            for (const action of step.actions) {
              assert.notEqual(action.to, stage, `${stage}: ${step.title} → ${action.label}`);
            }
          }
        }
      }
    }
  }
  assert.ok(seen > 1000);
});

test("an unconfirmed permission names who and goes to the card", () => {
  const step = nextStep(
    "story",
    project({ permission_pending: ["hero", "dj"] }),
    approvals({ brief: { state: "unavailable", error: "permission to upload/depict hero is not confirmed. Only the owner" } }),
    images(),
    budget,
  );
  assert.equal(step.title, "Confirm permission for hero, dj.");
  assert.deepEqual(step.actions[0], { label: "Go to World", target: "world", kind: "primary" });
});

test("a missing profile asks the Writer, or for the key the Writer needs", () => {
  const facts = { prompt_version: 2, profile_version: 0 };
  const withKey = nextStep("story", project({ ...facts, has_model_key: true }), approvals(), images(), budget);
  assert.equal(withKey.actions[0].target, "director");
  const noKey = nextStep("story", project({ ...facts, has_model_key: false }), approvals(), images(), budget);
  assert.match(noKey.title, /needs a model key/);
  assert.equal(noKey.actions[0].target, "settings");
});

test("unfinished shots are counted and shown, not approved", () => {
  const step = nextStep(
    "storyboard",
    project({
      placeholder_shot_ids: ["s001", "s002"],
      stage_states: states({ story: "done", storyboard: "you" }),
    }),
    approvals({ brief: { state: "approved" } }),
    images(),
    budget,
  );
  assert.equal(step.title, "2 shots still need a job and a prompt.");
  assert.equal(step.actions[0].target, "placeholders");
  assert.equal(step.actions[0].approve, undefined);
});

test("film without a storyboard sends to Storyboard before anything else", () => {
  const step = nextStep("film", project({ has_storyboard: false }), approvals(), images(), budget);
  assert.equal(step.title, "This film has no storyboard yet.");
  assert.equal(step.actions[0].to, "storyboard");
});
