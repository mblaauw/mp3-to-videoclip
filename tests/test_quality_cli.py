"""CLI integration, preview review gates and private local backups."""

import math
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest
from test_creative_production import make_root

from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.ffmpeg import probe
from mp3_to_videoclip.storage import file_hash, read_json, write_json


def real_audio(root):
    source = root / "media/song.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=2", str(source)],
        check=True,
    )
    config = read_json(root / "project.json")
    config.update(
        duration=float(probe(source)["format"]["duration"]), source_sha256=file_hash(source)
    )
    write_json(root / "project.json", config)
    total = math.ceil(config["duration"] * config["fps"])
    events = read_json(root / "work/events.json")
    events.update(total_frames=total, source_sha256=config["source_sha256"])
    write_json(root / "work/events.json", events)
    board = read_json(root / "work/storyboard.json")
    board["total_frames"] = total
    board["shots"][-1]["duration_frames"] = total - board["shots"][-1]["start_frame"]
    write_json(root / "work/storyboard.json", board)
    music = read_json(root / "work/music.json")
    music["duration"] = config["duration"]
    write_json(root / "work/music.json", music)


def test_cli_private_backup_is_complete_and_excludes_caches_and_secrets(tmp_path):
    root = make_root(tmp_path)
    (root / "work/plates").mkdir()
    (root / "work/plates/cache.mp4").write_bytes(b"rebuildable")
    (root / ".env").write_text("mock-secret-configuration")
    (root / ".secrets").mkdir()
    (root / ".secrets/token").write_text("mock-nested-secret")
    (root / ".env.d").mkdir()
    (root / ".env.d/provider").write_text("mock-nested-provider")
    source_before = file_hash(root / "media/song.mp3")
    result = execute(
        parser().parse_args(["backup", str(root), "--directory", str(tmp_path / "backups")])
    )
    backup = Path(result["backup"])
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    with tarfile.open(backup) as archive:
        names = archive.getnames()
        assert f"{root.name}/media/song.mp3" in names
        assert f"{root.name}/work/tasks.json" in names
        assert not any(
            "cache.mp4" in n or n.endswith("/.env") or n.endswith("/.lock") for n in names
        )
        assert not any("/.secrets/" in n or "/.env.d/" in n for n in names)
    assert file_hash(root / "media/song.mp3") == source_before
    assert result["sha256"] == file_hash(backup)
    with pytest.raises(ValueError, match="outside"):
        execute(parser().parse_args(["backup", str(root), "--directory", str(root / "bad-backup")]))


def test_cli_init_instrumental_and_event_schema(tmp_path):
    source = tmp_path / "source.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=0.5", str(source)], check=True
    )
    root = tmp_path / "instrumental"
    result = P.init_project(root, source, "instrumental", music_mode="instrumental").model_dump()
    assert result["music_mode"] == "instrumental"
    assert not (root / "work/lyrics.json").exists()
    assert read_json(root / "brief.json")["creative"] is not None
    assert read_json(root / "work/events.json")["events"] == []
    assert execute(parser().parse_args(["schema", "events"]))["type"] == "object"


def test_restage_normalises_padding_and_rejects_phantom_ids(tmp_path):
    """Whitespace is normalised; unknown, duplicate or empty IDs never record a cycle."""
    from test_creative_production import make_root

    from mp3_to_videoclip import budget as B

    root = make_root(tmp_path)
    for shots in ("s001,s99", "s001,s001", "", "s001,,s002"):
        with pytest.raises(ValueError, match="restage needs unique, known"):
            execute(
                parser().parse_args(["restage", str(root), "--shots", shots, "--note", "diagnosis"])
            )
    assert not (root / "work/restaging.json").exists()
    execute(
        parser().parse_args(["restage", str(root), "--shots", "s001, s002", "--note", "diagnosis"])
    )
    assert set(read_json(root / "work/restaging.json")["shots"]) == {"s001", "s002"}
    # The budget layer refuses a padded key even if a caller bypasses the CLI.
    with pytest.raises(ValueError, match="exact, unpadded"):
        B.authorize_restaging(root, ["s003 "], "diagnosis")


def test_costs_lists_unpriced_tasks_instead_of_crashing(tmp_path):
    from test_creative_production import make_root

    root = make_root(tmp_path)
    write_json(
        root / "work/tasks.json",
        {"x": {"uuid": "x", "kind": "images", "status": "submitted", "quote_id": "q"}},
    )
    report = G.costs(root)
    assert report["unpriced_tasks"] == ["x"]
    assert report["unresolved_reservations_usd"] == "0"
    assert "reconcile" in report["unpriced_note"]
    assert report["budget"]["unpriced_tasks"] == ["x"]
