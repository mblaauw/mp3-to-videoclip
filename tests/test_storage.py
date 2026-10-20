"""One read policy for optional artifacts: a damaged file degrades, it does not crash."""

from mp3_to_videoclip.storage import read_json, read_optional, write_versioned_page


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


def test_generated_pages_are_versioned_and_never_overwritten(tmp_path):
    first = write_versioned_page(tmp_path, "studio", None, "<html>a</html>", "studio")
    second = write_versioned_page(tmp_path, "studio", None, "<html>b</html>", "studio")
    assert first.name == "studio-v001.html" and second.name == "studio-v002.html"
    assert first.read_text() == "<html>a</html>"

    named = write_versioned_page(tmp_path, "studio", "custom.html", "<html>c</html>", "studio")
    assert named.name == "custom.html"
    for bad in ("../escape.html", "Upper.html", "no-extension"):
        try:
            write_versioned_page(tmp_path, "studio", bad, "x", "studio")
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"{bad} must be refused")
    try:
        write_versioned_page(tmp_path, "studio", "custom.html", "x", "studio")
    except ValueError as error:
        assert "never overwritten" in str(error)
    else:  # pragma: no cover
        raise AssertionError("an existing page must be refused")
