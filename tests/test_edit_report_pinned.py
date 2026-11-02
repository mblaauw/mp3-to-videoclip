"""The report's exact bytes on three cuts, so changing how it is built cannot change what it says."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from test_edits import _energetic_edit, _energetic_root

from mp3_to_videoclip import edits
from mp3_to_videoclip.models import EditAccent, EditMotion, EditText, EditTransition

GOLDEN = Path(__file__).parent / "golden"


def _flash(edit):
    first = edit.shots[0]
    edit.shots[0] = first.model_copy(
        update={
            "accents": [EditAccent(frame=frame, type="flash") for frame in (0, 6, 12, 18)],
            "transition_in": EditTransition(type="whip_pan", frames=0),
        }
    )
    return edit


def _messy(edit):
    """Every shot the same move, a joining habit, and text too quick to read."""
    shots = []
    for index, shot in enumerate(edit.shots):
        update = {
            "motion": EditMotion(type="hold"),
            "accents": [],
            "crops": [],
            "text": [],
        }
        if index:
            update["transition_in"] = EditTransition(
                type="dip_to_black", frames=4, reason="a habit"
            )
        if index == 1:
            update["text"] = [
                EditText(
                    id="fast",
                    style="super",
                    text="far too many words to read in this little time at all",
                    in_frame=shot.start_frame,
                    out_frame=shot.start_frame + 4,
                )
            ]
        shots.append(shot.model_copy(update=update))
    edit.shots = shots
    return edit


CASES = {"energetic": lambda edit: edit, "flash": _flash, "messy": _messy}


@pytest.mark.parametrize("name", CASES)
def test_the_report_says_exactly_what_it_said(tmp_path, name):
    root = _energetic_root(tmp_path)
    edit = CASES[name](_energetic_edit())
    edits.save_edit(root, edit)
    value = json.dumps(edits.report(root), indent=1, sort_keys=False) + "\n"
    path = GOLDEN / f"report-{name}.json"
    if os.environ.get("UPDATE_REPORT"):
        path.write_text(value)
    assert value == path.read_text()
