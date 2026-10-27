"""The pre-migration metadata snapshot must be complete and strictly read-only.

``projects/`` is gitignored, so this zip is the rollback for real productions.
The test builds a throwaway production containing metadata beside media, stills
and renders, then proves the archive holds every metadata file, no binary, a
per-file sha256 manifest, and that the source tree is byte-identical afterwards.
"""

from __future__ import annotations

import errno
import hashlib
import importlib.util
import json
import os
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "snapshot_projects.py"


def _load():
    spec = importlib.util.spec_from_file_location("snapshot_projects", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode() if isinstance(content, str) else content)


def _fixture(root: Path) -> None:
    project = root / "projects" / "demo"
    _write(project / "project.json", '{"schema_version": 1}\n')
    _write(project / "work" / "storyboard.json", '{"shots": []}\n')
    _write(project / "work" / "tasks.json", '{"tasks": []}\n')
    _write(project / "DELIVERY.md", "# delivered\n")
    _write(project / "media" / "song.mp3", b"not really audio")
    _write(project / "assets" / "s001" / "v001.jpg", b"\xff\xd8\xff")
    _write(project / "assets" / "s001" / "notes.json", '{"ignored": true}\n')
    _write(project / "renders" / "final-v001.mp4", b"\x00\x00\x00")
    _write(project / "previews" / "preview.mp4", b"\x00\x00\x00")
    _write(root / "projects" / "README.txt", "outside a production\n")


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_snapshot_captures_metadata_only_and_leaves_projects_untouched(tmp_path):
    snapshot = _load()
    _fixture(tmp_path)
    before = _tree_hashes(tmp_path / "projects")

    result = snapshot.snapshot(tmp_path / "projects", tmp_path / "backups")
    assert result["projects"] == 1
    assert result["files"] == 4
    archive_path = Path(result["zip"])
    assert archive_path.is_file()

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        assert names == {
            "manifest.json",
            "demo/DELIVERY.md",
            "demo/project.json",
            "demo/work/storyboard.json",
            "demo/work/tasks.json",
        }
        manifest = json.loads(archive.read("manifest.json"))
        payload = archive.read("demo/work/tasks.json")

    assert manifest["projects"]["demo"]["work/tasks.json"] == hashlib.sha256(payload).hexdigest()
    assert _tree_hashes(tmp_path / "projects") == before


def test_each_snapshot_is_a_new_archive_and_nothing_is_overwritten(tmp_path):
    snapshot = _load()
    _fixture(tmp_path)
    before = _tree_hashes(tmp_path / "projects")
    first = snapshot.snapshot(tmp_path / "projects", tmp_path / "backups")
    second = snapshot.snapshot(tmp_path / "projects", tmp_path / "backups")
    assert first["zip"] != second["zip"]
    # Both survive even when two runs land in the same second.
    for result in (first, second):
        with zipfile.ZipFile(result["zip"]) as archive:
            assert "demo/work/storyboard.json" in archive.namelist()
    assert _tree_hashes(tmp_path / "projects") == before


def test_dry_run_writes_nothing(tmp_path, capsys):
    snapshot = _load()
    _fixture(tmp_path)
    code = snapshot.main(
        [
            "--projects",
            str(tmp_path / "projects"),
            "--out",
            str(tmp_path / "backups"),
            "--dry-run",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["files"] == 4
    assert not (tmp_path / "backups").exists()


def test_restore_preserves_logs_reviews_approvals_and_hashes(tmp_path):
    snapshot = _load()
    _fixture(tmp_path)
    project = tmp_path / "projects" / "demo"
    metadata = {
        "work/chat.jsonl": '{"role":"user","content":"keep this"}\n',
        "work/prompt-artifacts.jsonl": '{"hash":"revision-1"}\n',
        "work/ratings.jsonl": '{"rating":"up"}\n',
        "work/tasks.json": '{"tasks":[{"status":"unknown","reserved_usd":1}]}\n',
        "work/reviews/stills.json": '{"accepted":["s001"]}\n',
        "work/approvals.json": '{"storyboard":"sha256:approved"}\n',
    }
    for relative, content in metadata.items():
        _write(project / relative, content)
    before = _tree_hashes(tmp_path / "projects")
    result = snapshot.snapshot(tmp_path / "projects", tmp_path / "backups")
    restored = tmp_path / "restored"
    with zipfile.ZipFile(result["zip"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert snapshot.collect(project) == manifest["projects"]["demo"]
        for relative, sha in manifest["projects"]["demo"].items():
            assert hashlib.sha256(archive.read(f"demo/{relative}")).hexdigest() == sha
        archive.extractall(restored)
    for relative, content in metadata.items():
        assert (restored / "demo" / relative).read_bytes() == content.encode()
    assert _tree_hashes(tmp_path / "projects") == before


@pytest.mark.parametrize(
    "relative",
    [
        ".env",
        ".env.json",
        ".secrets/provider.json",
        "secrets/provider.json",
        "work/secrets.toml",
        "work/secrets.yaml",
        "work/credentials.json",
        "work/.credentials.json",
        "work/credentials/provider.toml",
        "media/notes.jsonl",
        "assets/notes.json",
        "renders/report.json",
        "work/audio.wav",
    ],
)
def test_secrets_and_binaries_are_not_read_or_archived(tmp_path, monkeypatch, relative):
    snapshot = _load()
    _fixture(tmp_path)
    _write(tmp_path / "projects" / "demo" / relative, "private")
    read = snapshot._read_file
    reads = []

    def tracked(root, name, expected):
        reads.append(name)
        return read(root, name, expected)

    monkeypatch.setattr(snapshot, "_read_file", tracked)
    result = snapshot.snapshot(tmp_path / "projects", tmp_path / "backups")
    with zipfile.ZipFile(result["zip"]) as archive:
        assert f"demo/{relative}" not in archive.namelist()
    assert f"demo/{relative}" not in reads
    assert all(Path(name).suffix in snapshot.METADATA_SUFFIXES for name in reads)


@pytest.mark.parametrize("name", [".secrets", ".env", "credentials", "secrets", ".credentials"])
def test_secret_root_directories_are_not_read_or_archived(tmp_path, monkeypatch, name):
    snapshot = _load()
    _fixture(tmp_path)
    projects = tmp_path / "projects"
    _write(projects / name / "provider.json", '{"api_key":"private"}')
    read = snapshot._read_file

    def checked_read(root, relative, expected):
        assert not relative.startswith(f"{name}/")
        return read(root, relative, expected)

    monkeypatch.setattr(snapshot, "_read_file", checked_read)
    result = snapshot.snapshot(projects, tmp_path / "backups")
    assert result["projects"] == 1
    with zipfile.ZipFile(result["zip"]) as archive:
        assert not any(relative.startswith(f"{name}/") for relative in archive.namelist())
        assert name not in json.loads(archive.read("manifest.json"))["projects"]


@pytest.mark.parametrize(
    "mutation", ["write", "append", "add", "mkdir", "remove", "rmdir", "replace", "binary"]
)
def test_concurrent_mutation_fails_without_output(tmp_path, monkeypatch, mutation):
    snapshot = _load()
    _fixture(tmp_path)
    project = tmp_path / "projects" / "demo"
    (project / "empty").mkdir()
    read = snapshot._read_file
    mutated = False

    def racing_read(root, relative, expected):
        nonlocal mutated
        payload = read(root, relative, expected)
        if not mutated:
            mutated = True
            if mutation == "write":
                # Same length, and restore mtime: ctime still exposes the write.
                path = root / relative
                info = path.stat()
                path.write_bytes(b"x" * len(payload))
                os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
            elif mutation == "append":
                with (root / relative).open("ab") as handle:
                    handle.write(b"\n")
            elif mutation == "add":
                _write(project / "work" / "new.jsonl", "{}\n")
            elif mutation == "mkdir":
                (project / "new-directory").mkdir()
            elif mutation == "remove":
                (root / relative).unlink()
            elif mutation == "rmdir":
                (project / "empty").rmdir()
            elif mutation == "replace":
                replacement = tmp_path / "replacement"
                replacement.write_bytes(payload)
                replacement.replace(root / relative)
            else:
                (project / "media" / "song.mp3").write_bytes(b"changed binary")
        return payload

    monkeypatch.setattr(snapshot, "_read_file", racing_read)
    with pytest.raises(RuntimeError, match="changed"):
        snapshot.snapshot(tmp_path / "projects", tmp_path / "backups")
    assert mutated
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("kind", ["file", "directory", "binary-directory", "production"])
def test_symlinks_are_rejected_even_in_excluded_directories(tmp_path, kind):
    snapshot = _load()
    _fixture(tmp_path)
    outside = tmp_path / "outside"
    _write(outside / "secret.json", "secret")
    project = tmp_path / "projects" / "demo"
    link = {
        "file": project / "escape.json",
        "directory": project / "escape",
        "binary-directory": project / "media" / "escape",
        "production": tmp_path / "projects" / "linked-project",
    }[kind]
    link.symlink_to(outside / "secret.json" if kind == "file" else outside)
    with pytest.raises(ValueError, match="symlinks"):
        snapshot.snapshot(tmp_path / "projects", tmp_path / "backups")
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize("via_link", [False, True])
def test_output_cannot_be_inside_productions(tmp_path, via_link):
    snapshot = _load()
    _fixture(tmp_path)
    projects = tmp_path / "projects"
    before = _tree_hashes(projects)
    out = projects / "demo" / "backups"
    if via_link:
        out = tmp_path / "linked-out"
        out.symlink_to(projects / "demo", target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        snapshot.snapshot(projects, out)
    assert _tree_hashes(projects) == before
    assert not (projects / "demo" / "backups").exists()


def test_output_symlink_retarget_during_capture_never_writes_inside_production(
    tmp_path, monkeypatch
):
    snapshot = _load()
    _fixture(tmp_path)
    projects = tmp_path / "projects"
    backups = tmp_path / "backups"
    backups.mkdir()
    alias = tmp_path / "out-link"
    alias.symlink_to(backups, target_is_directory=True)
    before = _tree_hashes(projects)
    before_names = sorted(path.relative_to(projects) for path in projects.rglob("*"))
    capture = snapshot._capture

    def retarget(root, **kwargs):
        alias.unlink()
        alias.symlink_to(projects / "demo", target_is_directory=True)
        return capture(root, **kwargs)

    monkeypatch.setattr(snapshot, "_capture", retarget)
    result = snapshot.snapshot(projects, alias)
    assert Path(result["zip"]).parent == backups
    with zipfile.ZipFile(result["zip"]) as archive:
        assert archive.testzip() is None
    assert _tree_hashes(projects) == before
    assert sorted(path.relative_to(projects) for path in projects.rglob("*")) == before_names
    assert not list(backups.glob(".snapshot-*"))


def test_publication_is_complete_exclusive_and_retries_collision(tmp_path, monkeypatch):
    snapshot = _load()
    _fixture(tmp_path)
    out = tmp_path / "backups"
    out.mkdir()
    stamp = datetime(2026, 10, 27, tzinfo=UTC)
    existing = out / "projects-metadata-20261027T000000Z.zip"
    existing.write_bytes(b"existing backup")
    link = snapshot.os.link
    calls = []

    def racing_link(source, target, **kwargs):
        target_path = out / target
        calls.append(target_path)
        # No final ZIP is visible before its complete archive has been closed.
        with zipfile.ZipFile(out / source) as archive:
            assert archive.testzip() is None
            assert "manifest.json" in archive.namelist()
        if len(calls) == 2:
            target_path.write_bytes(b"concurrent backup")
        return link(source, target, **kwargs)

    monkeypatch.setattr(snapshot.os, "link", racing_link)
    result = snapshot.snapshot(tmp_path / "projects", out, now=stamp)
    assert Path(result["zip"]).name.endswith("-02.zip")
    assert existing.read_bytes() == b"existing backup"
    assert calls[1].read_bytes() == b"concurrent backup"
    assert not list(out.glob(".snapshot-*"))
    assert Path(result["zip"]).stat().st_mode & 0o777 == 0o600


def test_publication_collision_rechecks_source_before_retry(tmp_path, monkeypatch):
    snapshot = _load()
    _fixture(tmp_path)
    out = tmp_path / "backups"
    link = snapshot.os.link

    def racing_link(source, target, **kwargs):
        (out / target).write_bytes(b"concurrent backup")
        _write(tmp_path / "projects" / "demo" / "new.jsonl", "{}\n")
        return link(source, target, **kwargs)

    monkeypatch.setattr(snapshot.os, "link", racing_link)
    with pytest.raises(RuntimeError, match="changed"):
        snapshot.snapshot(tmp_path / "projects", out)
    assert len(list(out.iterdir())) == 1
    assert next(out.iterdir()).read_bytes() == b"concurrent backup"


@pytest.mark.parametrize("failure", ["zip", "publish", "late-mutation"])
def test_failed_archive_cleanup_exposes_no_partial_zip(tmp_path, monkeypatch, failure):
    snapshot = _load()
    _fixture(tmp_path)
    out = tmp_path / "backups"

    def fail(*args, **kwargs):
        raise OSError("simulated failure")

    if failure == "zip":
        monkeypatch.setattr(snapshot.zipfile.ZipFile, "writestr", fail)
    elif failure == "publish":
        monkeypatch.setattr(snapshot.os, "link", fail)
    else:
        write = snapshot.zipfile.ZipFile.writestr

        def late_write(self, *args, **kwargs):
            result = write(self, *args, **kwargs)
            _write(tmp_path / "projects" / "demo" / "late.jsonl", "{}\n")
            return result

        monkeypatch.setattr(snapshot.zipfile.ZipFile, "writestr", late_write)
    with pytest.raises((OSError, RuntimeError)):
        snapshot.snapshot(tmp_path / "projects", out)
    assert not list(out.iterdir())


@pytest.mark.parametrize("unsupported", [False, True])
def test_publication_fsyncs_output_directory_when_supported(tmp_path, monkeypatch, unsupported):
    snapshot = _load()
    _fixture(tmp_path)
    out = tmp_path / "backups"
    fsync = snapshot.os.fsync
    synced_directories = []

    def checked_fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            synced_directories.append(fd)
            assert not list(out.glob(".snapshot-*"))
            archives = list(out.glob("*.zip"))
            assert len(archives) == 1
            with zipfile.ZipFile(archives[0]) as archive:
                assert archive.testzip() is None
            if unsupported:
                raise OSError(errno.EINVAL, "directory fsync unsupported")
        return fsync(fd)

    monkeypatch.setattr(snapshot.os, "fsync", checked_fsync)
    snapshot.snapshot(tmp_path / "projects", out)
    assert len(synced_directories) == 1


def test_directory_fsync_does_not_hide_real_io_errors(tmp_path, monkeypatch):
    snapshot = _load()

    def fail(fd):
        raise OSError(errno.EIO, "storage failure")

    monkeypatch.setattr(snapshot.os, "fsync", fail)
    with pytest.raises(OSError) as caught:
        snapshot._fsync_directory(123)
    assert caught.value.errno == errno.EIO
