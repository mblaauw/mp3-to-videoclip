import test from "node:test";
import assert from "node:assert/strict";
import {COMPACT_FIELDS, compactIntroPhases, compactPanels, validateCompactLayout} from "../src/compact.mjs";
import {introPhasesAt} from "../src/timing.mjs";
import {validateRequest} from "../src/request.mjs";
import path from "node:path";

test("compact layout is explicit and rejects unknown/partial/invalid controls", () => {
  assert.equal(validateCompactLayout(undefined), null);
  for (const layout of [null, {}, [], {kind:"other"}, {kind:"compact-v1",x:.4},
    {kind:"compact-v1",identity_switch_frame:59},
    {kind:"compact-v1",identity_switch_frame:59,handoff_frames:0},
    {kind:"compact-v1",identity_switch_frame:2,handoff_frames:8}]) {
    assert.throws(() => validateCompactLayout(layout));
  }
  assert.throws(() => validateCompactLayout({kind:"compact-v1",identity_switch_frame:59,handoff_frames:8}, {kind:"identity",frames:60}));
});

test("identity changes fixed fields without travelling across subjects", () => {
  const layout = {kind:"compact-v1",identity_switch_frame:59,handoff_frames:8};
  const part = {kind:"identity",frames:144};
  const before = compactPanels(layout,part,40,24);
  assert.equal(before[0].alpha,1); assert.equal(before[1].alpha,0);
  const middle = compactPanels(layout,part,59,24);
  assert.equal(middle[0].alpha,0); assert.equal(middle[1].alpha,0);
  const after = compactPanels(layout,part,80,24);
  assert.equal(after[0].alpha,0); assert.equal(after[1].alpha,1);
  assert.deepEqual(before.map(p=>p.field),after.map(p=>p.field));
  for (let frame=0;frame<144;frame++) {
    const panels=compactPanels(layout,part,frame,24);
    assert.ok(panels.every(p=>p.alpha>=0 && p.alpha<=1));
    assert.ok(panels[0].alpha*panels[1].alpha === 0);
  }
});

test("compact opening retains all original phase timing including factual mini roles", () => {
  for (const t of [0,3,8.5,10,17.9,20.5,23.5,24.9]) {
    const frame = Math.round(t*24);
    assert.deepEqual(compactIntroPhases(frame,24,25),introPhasesAt(frame/24,25));
  }
  assert.ok(compactIntroPhases(18*24,24,25).mini_credits_1>.5);
  assert.ok(compactIntroPhases(21*24,24,25).mini_credits_2>.5);
});

test("fields remain inside the canvas and overlays retain their own durations", () => {
  for (const [a,b,c,d] of Object.values(COMPACT_FIELDS)) assert.ok(0<=a && a<c && c<=1 && 0<=b && b<d && d<=1);
  const part={kind:"card",frames:360};
  assert.equal(compactPanels({kind:"compact-v1"},part,120,24)[0].alpha,1);
  assert.equal(part.frames,360);
});

test("real request boundary rejects unsupported layout before bundling", () => {
  const request={kind:"graphics",output:path.resolve("compact-fixture.mov"),assetRoot:process.cwd(),
    width:1920,height:1080,fps:24,frames:144,input:{part:{kind:"identity",frames:144},
      spec:{layout:{kind:"compact-v1",identity_switch_frame:59,handoff_frames:8}},
      logo:"data:image/svg+xml;base64,"+Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"></svg>').toString("base64")}};
  assert.equal(validateRequest(request).part.frames,144);
  request.input.spec.layout.kind="ignored-typo";
  assert.throws(()=>validateRequest(request),/compact-v1/);
});
