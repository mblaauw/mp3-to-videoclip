import assert from "node:assert/strict";
import { test } from "node:test";
import {
  anchorKind,
  anchorOf,
  anchorSeconds,
  bandFor,
  chosen,
  clockTenths,
  dbWords,
  describeAnchor,
  dollars,
  fitWords,
  freshId,
  heardSpan,
  isMoment,
  packRows,
  placesWords,
  playsMode,
  rulerTicks,
  soundState,
  withPlays,
} from "../src/sound/cueBands.ts";

test("a band is a slice of the ruler and never leaves it", () => {
  assert.deepEqual(bandFor({ start_seconds: 30, end_seconds: 60 }, 120), { left: 25, width: 25 });
  assert.deepEqual(bandFor({ start_seconds: 100, end_seconds: 500 }, 120), {
    left: (100 / 120) * 100,
    width: (20 / 120) * 100,
  });
  assert.equal(bandFor({ start_seconds: null, end_seconds: 5 }, 120), null);
  assert.equal(bandFor({ start_seconds: 5, end_seconds: 5 }, 120)?.width, 0.5);
});

test("the stage's word follows the cues that sound", () => {
  assert.equal(soundState(0, 0), "not_ready");
  assert.equal(soundState(3, 1), "you");
  assert.equal(soundState(3, 3), "done");
});

test("ids are plain words and never collide", () => {
  assert.equal(freshId("music", []), "bed");
  assert.equal(freshId("music", ["bed"]), "bed-2");
  assert.equal(freshId("effect", ["hit", "hit-2"]), "hit-3");
});

test("the chosen version is the one that plays", () => {
  const versions = [
    { version: 1, path: "a", sha256: "x", source: "upload" as const, seconds: 2 },
    { version: 2, path: "b", sha256: "y", source: "generated" as const, seconds: 3 },
  ];
  assert.equal(chosen({ versions, selected: 2 })?.path, "b");
  assert.equal(chosen({ versions, selected: null }), null);
});

test("anchors read as a line, a time or the end", () => {
  assert.equal(describeAnchor({ line: "l003" }, 24), "l003");
  assert.equal(describeAnchor({ frame: 48 }, 24), "2.0 s");
  assert.equal(describeAnchor({ frame: -1 }, 24), "end");
  assert.equal(describeAnchor({ shot: "s004" }, 24), "cut of s004");
  assert.equal(describeAnchor({ beat: "hook" }, 24), "beat hook");
  assert.equal(anchorKind({ shot: "s1" }), "shot");
  assert.equal(anchorKind({ frame: 3 }), "frame");
});

test("places read as once, a gap or a count, and anchors are made from a kind and a value", () => {
  assert.equal(placesWords(null, null), "once");
  assert.equal(placesWords({ every: 2 }, 12), "every 2 s, 12 times");
  assert.equal(placesWords({ every: 1.5, jitter: 0.2 }, undefined), "every 1.5 s ± 0.2 s");
  assert.equal(placesWords({ at: [{ shot: "a" }, { shot: "b" }] }, null), "at 2 places");
  assert.equal(placesWords({ at: [{ shot: "a" }] }, 1), "at 1 place");
  assert.deepEqual(anchorOf("shot", "s2", 24, false), { shot: "s2" });
  assert.deepEqual(anchorOf("frame", "2.5", 24, false), { frame: 60 });
  assert.deepEqual(anchorOf("frame", "", 24, true), { frame: -1 });
  assert.deepEqual(anchorOf("frame", "oops", 24, false), { frame: 0 });
  assert.deepEqual(anchorOf("beat", "hook", 24, true), { beat: "hook" });
});

test("a moment is one anchor twice, and is heard as long as its sound", () => {
  assert.equal(isMoment({ start: { frame: 24 }, end: { frame: 24 } }), true);
  assert.equal(isMoment({ start: { shot: "s1" }, end: { shot: "s1" } }), true);
  assert.equal(isMoment({ start: { frame: 0 }, end: { frame: -1 } }), false);
  const versions = [{ version: 1, path: "a", sha256: "x", source: "generated" as const, seconds: 1.5 }];
  const moment = { start_seconds: 13, end_seconds: 13, versions, selected: 1, loop: false, places: null };
  assert.deepEqual(heardSpan(moment, 70), { start: 13, end: 14.5 });
  assert.deepEqual(heardSpan({ ...moment, selected: null }, 70), { start: 13, end: 13 });
  const once = { ...moment, end_seconds: 20 };
  assert.deepEqual(heardSpan(once, 70), { start: 13, end: 14.5 });
  assert.deepEqual(heardSpan({ ...once, loop: true }, 70), { start: 13, end: 20 });
  assert.deepEqual(heardSpan({ ...once, places: { every: 2 } }, 70), { start: 13, end: 20 });
  assert.equal(heardSpan({ ...moment, start_seconds: null }, 70), null);
});

test("plays is one choice that sets the loop and the places together", () => {
  assert.equal(playsMode({ loop: true, places: null }), "loop");
  assert.equal(playsMode({ loop: false, places: undefined }), "once");
  assert.equal(playsMode({ loop: true, places: { every: 2 } }), "every");
  assert.equal(playsMode({ loop: false, places: { at: [] } }), "at");
  assert.deepEqual(withPlays("loop", []), { loop: true, places: null });
  assert.deepEqual(withPlays("at", ["s1", "s2"]), { loop: false, places: { at: [{ shot: "s1" }, { shot: "s2" }] } });
  assert.deepEqual(withPlays("at", []), { loop: false, places: { at: [{ frame: 0 }] } });
  assert.deepEqual(withPlays("every", ["s1"]), { loop: false, places: { every: 2, jitter: 0 } });
});

test("a lane packs overlapping cues into rows and the ruler steps round", () => {
  assert.deepEqual(
    packRows([
      { id: "b", start: 2, end: 6 },
      { id: "a", start: 0, end: 3 },
      { id: "c", start: 3, end: 4 },
      { id: "d", start: 6, end: 9 },
    ]),
    { a: 0, b: 1, c: 0, d: 0 },
  );
  assert.deepEqual(rulerTicks(70), [0, 10, 20, 30, 40, 50, 60, 70]);
  assert.deepEqual(rulerTicks(12), [0, 5, 10]);
  assert.equal(rulerTicks(600)[1], 60);
  assert.equal(clockTenths(13.04), "0:13.0");
  assert.equal(clockTenths(67.25), "1:07.3");
  assert.equal(clockTenths(5), "0:05.0");
  assert.equal(dbWords(-8), "−8 dB");
  assert.equal(dbWords(3), "+3 dB");
  assert.equal(dbWords(0), "0 dB");
});

test("the inspector says how the sound fills its cue", () => {
  const versions = [{ version: 1, path: "a", sha256: "x", source: "generated" as const, seconds: 10 }];
  const base = { start: { frame: 0 }, end: { frame: 528 }, loop: true, places: null, versions, selected: 1, start_seconds: 0, end_seconds: 22, places_seconds: null };
  assert.equal(fitWords(base), "Loops its 10.0 s sound 2.2 times to fill 22.0 s.");
  assert.equal(fitWords({ ...base, loop: false }), "Plays its 10.0 s sound once; 12.0 s of the stretch stays quiet.");
  assert.equal(fitWords({ ...base, end: { frame: 0 }, end_seconds: 0 }), "Plays its 10.0 s sound whole from 0:00.0.");
  assert.equal(fitWords({ ...base, places: { every: 2 }, places_seconds: [0, 2, 4] }), "Plays its 10.0 s sound 3 times, whole each time.");
  assert.equal(fitWords({ ...base, selected: null }), null);
  const where = { fps: 24, duration: 70, shots: [{ id: "s2", start: 4 }], lines: [], beats: [{ id: "b", start: 1, end: 9 }] };
  assert.equal(anchorSeconds({ frame: 48 }, where, false), 2);
  assert.equal(anchorSeconds({ frame: -1 }, where, true), 70);
  assert.equal(anchorSeconds({ shot: "s2" }, where, false), 4);
  assert.equal(anchorSeconds({ beat: "b" }, where, true), 9);
  assert.equal(anchorSeconds({ line: "x" }, where, false), null);
});

test("money reads to the cent unless it is less than one", () => {
  assert.equal(dollars("0.1"), "$0.10");
  assert.equal(dollars("0.0025"), "$0.0025");
  assert.equal(dollars(0), "$0.00");
  assert.equal(dollars("1.5"), "$1.50");
});
