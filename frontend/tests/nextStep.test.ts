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

test("track asks for lyrics on a vocal song without them", () => {
  const step = nextStep(
    "track",
    project({ has_lyrics: false }),
    approvals(),
    images(),
    budget,
  );
  assert.match(step.title, /Add the lyrics/);
  assert.equal(step.actions[0].to, "track");
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
  assert.equal(step.actions[0].to, "story");
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
});

test("story reports a stale approval", () => {
  const step = nextStep(
    "story",
    project({ stage_states: states({ story: "changed" }) }),
    approvals({ brief: { state: "stale" } }),
    images(),
    budget,
  );
  assert.equal(step.tone, "changed");
  assert.match(step.title, /changed/);
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
  assert.equal(step.actions[0].to, "storyboard");
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
    images({ missing: 2, kept: 2, selected: 2 }),
    budget,
  );
  assert.match(step.title, /Make 2 missing pictures/);
  assert.match(step.detail || "", /5\.00/);
  assert.equal(step.actions[0].target, "pictures");
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
  assert.match(step.title, /Ready to deliver/);
  assert.equal(step.actions[0].target, "render");
});

test("film reports a delivered final", () => {
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
  assert.match(step.title, /Delivered/);
});
