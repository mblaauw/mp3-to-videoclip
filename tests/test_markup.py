"""The single escaping and script-embedding policy shared by every page."""

import json

from mp3_to_videoclip.markup import esc, script_json


def test_escaping_covers_markup_and_attributes():
    assert esc(None) == ""
    assert esc("<b>") == "&lt;b&gt;"
    assert esc('a "quote" & ampersand') == "a &quot;quote&quot; &amp; ampersand"
    assert esc(7) == "7"


def test_script_json_is_compact_and_cannot_close_its_script_tag():
    payload = {"id": "s001", "label": "</script><script>alert(1)</script>"}
    text = script_json(payload)
    assert "</script" not in text
    assert "<\\/script" in text
    assert json.loads(text.replace("<\\/", "</")) == payload
    assert ", " not in text, "compact separators keep the embedded payload small"
