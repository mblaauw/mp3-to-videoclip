"""One read policy for optional artifacts: a damaged file degrades, it does not crash."""

from mp3_to_videoclip.storage import read_json, read_optional


def test_missing_file_yields_the_default(tmp_path):
    assert read_optional(tmp_path / "absent.json") is None
    assert read_optional(tmp_path / "absent.json", {}) == {}


def test_readable_file_is_returned_unchanged(tmp_path):
    path = tmp_path / "ok.json"
    path.write_text('{"a": 1}')
    assert read_optional(path) == {"a": 1}


def test_corrupt_file_degrades_to_the_default(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    assert read_optional(path, []) == []
    # A writer still fails loudly: corruption must not be silently overwritten.
    try:
        read_json(path)
    except ValueError:
        pass
    else:  # pragma: no cover - guards the policy the docstring promises
        raise AssertionError("read_json must still raise on corrupt input")
