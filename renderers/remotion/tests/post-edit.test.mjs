import assert from 'node:assert/strict';
import test from 'node:test';
import {allocateSpans, visibleLayers, cameraAtFrame, keyframeCamera, layerRect,
  postEffectsStyle, transitionStyle, splitNames, validateAssetName} from '../src/timing.mjs';

test('transition handles preserve every allocated boundary and never expose black', () => {
  const {spans, totalFrames} = allocateSpans([
    {id:'a',image:'a.png',start_frame:0,duration_frames:8,dissolve_frames:4},
    {id:'b',image:'b.png',start_frame:8,duration_frames:8,dissolve_frames:4},
    {id:'c',image:'c.png',start_frame:16,duration_frames:8},
  ]);
  assert.equal(totalFrames,24);
  for(let frame=0;frame<totalFrames;frame++) {
    const layers=visibleLayers(spans,frame);
    assert.ok(layers.length>=1 && layers.length<=2);
    assert.ok(layers.some(layer=>layer.alpha===1));
  }
  assert.equal(visibleLayers(spans,8)[1].alpha,0);
  assert.equal(visibleLayers(spans,10)[1].alpha,0.5);
  assert.equal(visibleLayers(spans,12).length,1);
  assert.deepEqual(visibleLayers(spans,24),[]);
});

test('explicit keyframes hold, move and hold without new crops', () => {
  const span={duration_frames:24,handle:0,camera:'hold',camera_keyframes:[
    {frame:0,zoom:1,x:.5,y:.5},{frame:6,zoom:1,x:.5,y:.5},
    {frame:18,zoom:1.1,x:.6,y:.4},{frame:23,zoom:1.1,x:.6,y:.4},
  ]};
  assert.equal(cameraAtFrame(span,4).zoom,1);
  assert.equal(cameraAtFrame(span,12).zoom,1.05);
  assert.equal(cameraAtFrame(span,22).zoom,1.1);
  assert.throws(()=>keyframeCamera([{frame:1,zoom:1,x:.5,y:.5}],1),/zero/);
  assert.throws(()=>keyframeCamera([{frame:0,zoom:3,x:.5,y:.5}],0),/bounded/);
  assert.deepEqual(layerRect({width:100,height:50,zoom:1.2,x:1,y:0}),
                   {width:120,height:60,left:-20,top:-0});
});

test('paths interpolate with explicit easing and available overflow', () => {
  const span={duration_frames:5,handle:0,camera_path:{
    start:{zoom:1,x:0,y:0},end:{zoom:1.2,x:1,y:1},easing:'smoothstep'}};
  assert.equal(cameraAtFrame(span,1).x,0.15625);
  assert.equal(cameraAtFrame(span,4).x,1);
});

test('effects and transitions reject typos rather than silently ignoring them', () => {
  assert.throws(()=>postEffectsStyle({glitch:1}),/unsupported|unknown/);
  assert.throws(()=>postEffectsStyle({brightness:3}),/range|between|must/);
  assert.throws(()=>transitionStyle('spin',.5),/unsupported/);
  assert.equal(transitionStyle('wipe_left',.5).clipPath,'inset(0 50% 0 0)');
});

test('preferred identity names retain their factual wording', () => {
  assert.deepEqual(splitNames('MAHA KALA  ◆  VJDJ69').parts,['MAHA KALA','VJDJ69']);
  for(const name of ['https://example.org/a.png','../a.png','/a.png','.a.png']) {
    assert.throws(()=>validateAssetName(name));
  }
});
