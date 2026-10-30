import assert from "node:assert/strict";
import test from "node:test";
import { describeNote } from "../src/film/cutNotes.ts";

const context = {
  sections: [{ id: "section-3", name: "Section 3", start_frame: 1190 }],
  shots: [{ shot_id: "s009", start_frame: 1300 }],
};

test("report wording becomes a plain note anchored to where it happens", () => {
  const hold = describeNote(
    { code: "hold_ratio", section: "section-3", message: "section section-3 holds 3 of 3 shots; name a breathing-hold technique if that is the plan" },
    0,
    context,
  );
  assert.equal(hold.title, "Section 3: 3 of 3 shots hold still");
  assert.equal(hold.frame, 1190);
  assert.equal(hold.shotId, null);
  const framing = describeNote(
    { code: "framing_repetition", shot_id: "s009", message: "back-to-back close_up framings" },
    1,
    context,
  );
  assert.equal(framing.title, "s009: same framing as the shot before");
  assert.equal(framing.why, "Both are close up shots.");
  assert.equal(framing.frame, 1300);
  assert.equal(framing.shotId, "s009");
});

test("an unknown finding still says something and keeps no engine ids", () => {
  const note = describeNote(
    { code: "something_new", section: "section-3", message: "section section-3 needs a look" },
    2,
    context,
  );
  assert.equal(note.title, "Section 3: needs a look");
});
