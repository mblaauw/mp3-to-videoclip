"""The world library: what a film settled, kept above productions for the next one.

A character with its reference bytes and permission, a place with its plates, a narrator and a
look can be promoted out of a film into ``library/`` beside ``projects/``, and adopted into
another film with one owner's click. A series carries a bible, its episodes and the entries that
recur. Bytes are copied, never moved, and nothing here is deleted or rewritten in place: an
entry promoted again with other content is a new version. Adopting writes the brief as the
owner, through the same functions the Studio's own cards use, so the story asks to be approved
again, as any reference binding does. The project folder stays the single source of truth: a
still brought from another film is a copy with its provenance written down.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .models import Brief, Character, Scene, VisualReference
from .storage import digest, file_hash, inside, read_optional, write_json

ENV = "MP3_TO_VIDEOCLIP_LIBRARY"
DIRNAME = "library"
WORLD = "world.json"
REFERENCES = "references"
SERIES = "series"
KINDS = ("character", "place", "narrator", "look")
MAX_BIBLE = 6000
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def library_dir(projects_dir: Path | None = None) -> Path:
    """``library/`` beside ``projects/``, unless the environment names another folder."""
    named = os.environ.get(ENV)
    if named:
        return Path(named)
    base = Path(projects_dir or "projects").resolve()
    return base.parent / DIRNAME


def _now() -> str:
    from .production.project import now

    return now()


# ------------------------------------------------------------------ entries


def read_world(lib: Path) -> dict:
    value = read_optional(Path(lib) / WORLD)
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
        return {"version": 1, "entries": []}
    return value


def entries(lib: Path, kind: str | None = None) -> list[dict]:
    """The newest version of every entry, optionally of one kind."""
    newest: dict[str, dict] = {}
    for entry in read_world(lib)["entries"]:
        if kind is not None and entry.get("kind") != kind:
            continue
        key = entry["key"]
        if key not in newest or entry["version"] > newest[key]["version"]:
            newest[key] = entry
    return sorted(newest.values(), key=lambda item: (item["kind"], item["id"]))


def latest(lib: Path, key: str) -> dict:
    found = next((entry for entry in entries(lib) if entry["key"] == key), None)
    if found is None:
        raise ValueError(f"the library has no entry {key}")
    return found


def _copy_bytes(root: Path, lib: Path, relative: str) -> str:
    """The file's bytes under its hash in the library; never moved, never overwritten."""
    source = inside(root, relative)
    sha = file_hash(source)
    target = Path(lib) / REFERENCES / f"{sha}{source.suffix.lower()}"
    if target.exists():
        if file_hash(target) != sha:
            raise ValueError("a library file's bytes changed; restore it, do not overwrite")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".partial")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    return target.name


def _payload(root: Path, brief: Brief, kind: str, entry_id: str) -> tuple[dict, dict]:
    """What an entry holds, and the film files it carries, as relative path to library name."""
    creative = brief.creative
    if kind == "character":
        character = next((item for item in brief.characters if item.id == entry_id), None)
        if character is None:
            raise ValueError(f"this film has no character {entry_id}")
        paths = list(character.references)
        for state in character.states.values():
            paths += state.references
        return character.model_dump(), {path: None for path in paths}
    if kind == "place":
        scene = next((item for item in (creative.scenes if creative else []) if item.id == entry_id), None)  # fmt: skip
        if scene is None:
            raise ValueError(f"this film has no place {entry_id}")
        refs = [item for item in creative.references if item.id in scene.reference_ids]
        return {"scene": scene.model_dump(), "references": [r.model_dump() for r in refs]}, {
            item.path: None for item in refs
        }
    if kind == "narrator":
        if creative is None or creative.narrator is None:
            raise ValueError("this film has no narrator")
        return creative.narrator.model_dump(), {}
    if kind == "look":
        if creative is None or not creative.look.strip():
            raise ValueError("this film has no look yet")
        from .production import load_project

        return {
            "look": creative.look,
            "image_rules": list(creative.image_rules),
            "avoid": list(brief.avoid),
            "style_preset": load_project(root, verify_source=False).style_preset,
        }, {}
    raise ValueError(f"the library keeps {', '.join(KINDS)}, not {kind}")


def promote(root: Path, lib: Path, kind: str, entry_id: str, *, label: str = "") -> dict:
    """Copy one thing a film settled into the library. The film is only read."""
    from .production import load_brief, load_project

    root, lib = Path(root), Path(lib)
    if kind not in KINDS:
        raise ValueError(f"the library keeps {', '.join(KINDS)}, not {kind}")
    if not isinstance(entry_id, str) or not _ID.match(entry_id):
        raise ValueError("an entry needs a short lowercase id")
    brief = load_brief(root)
    project = load_project(root, verify_source=False)
    payload, files = _payload(root, brief, kind, entry_id)
    carried = {relative: _copy_bytes(root, lib, relative) for relative in files}
    key = f"{kind}:{entry_id}"
    world = read_world(lib)
    same = [entry for entry in world["entries"] if entry["key"] == key]
    content = digest({"payload": payload, "files": sorted(carried.values())})
    for entry in same:
        if entry.get("content") == content:
            return entry
    entry = {
        "key": key,
        "kind": kind,
        "id": entry_id,
        "version": max([e["version"] for e in same] + [0]) + 1,
        "label": (label or "").strip()[:120] or entry_id.replace("-", " ").replace("_", " "),
        "from": {"slug": root.name, "title": project.title, "at": _now()},
        "payload": payload,
        "files": carried,
        "content": content,
    }
    world["entries"].append(entry)
    lib.mkdir(parents=True, exist_ok=True)
    write_json(lib / WORLD, world)
    return entry


# ------------------------------------------------------------------ adopting


def _import(root: Path, lib: Path, entry: dict, original: str, *, permitted: bool) -> str:
    from .references import import_reference

    source = Path(lib) / REFERENCES / entry["files"][original]
    note = f"From the library: {entry['key']} v{entry['version']}, promoted from {entry['from']['slug']}"  # fmt: skip
    return import_reference(root, source, note=note, permission_confirmed=permitted)["path"]


def adopt(root: Path, lib: Path, key: str) -> dict:
    """Write a library entry into this film's brief as the owner. The story will need approving again."""
    from .production import load_brief, load_project, update_brief

    root, lib = Path(root), Path(lib)
    entry = latest(lib, key)
    brief = load_brief(root)
    kind, payload = entry["kind"], entry["payload"]
    skipped: list[str] = []
    if kind == "character":
        character = Character.model_validate(payload)
        permitted = bool(character.permission_confirmed)
        paths: dict[str, str] = {}
        for original in entry["files"]:
            if not permitted:
                skipped.append(original)
                continue
            paths[original] = _import(root, lib, entry, original, permitted=True)
        value = character.model_dump()
        value["references"] = [paths[p] for p in character.references if p in paths]
        for state_id, state in value.get("states", {}).items():
            state["references"] = [paths[p] for p in character.states[state_id].references if p in paths]  # fmt: skip
        others = [c.model_dump() for c in brief.characters if c.id != character.id]
        update_brief(root, {"characters": [*others, value]}, owner=True)
        changed = ["characters"]
    elif kind == "place":
        scene = Scene.model_validate(payload["scene"])
        refs = [VisualReference.model_validate(item) for item in payload["references"]]
        creative = brief.creative.model_dump() if brief.creative else {}
        kept = [r for r in creative.get("references", []) if r["id"] not in {x.id for x in refs}]
        for reference in refs:
            if not reference.permission_confirmed:
                skipped.append(reference.path)
                continue
            value = reference.model_dump()
            value["path"] = _import(root, lib, entry, reference.path, permitted=True)
            kept.append(value)
        known = {r["id"] for r in kept}
        scene_value = scene.model_dump()
        scene_value["reference_ids"] = [r for r in scene.reference_ids if r in known]
        scenes = [s for s in creative.get("scenes", []) if s["id"] != scene.id] + [scene_value]
        update_brief(root, {"creative": {**creative, "scenes": scenes, "references": kept}}, owner=True)  # fmt: skip
        changed = ["creative.scenes", "creative.references"]
    elif kind == "narrator":
        creative = brief.creative.model_dump() if brief.creative else {}
        update_brief(root, {"creative": {**creative, "narrator": payload}}, owner=True)
        changed = ["creative.narrator"]
    elif kind == "look":
        creative = brief.creative.model_dump() if brief.creative else {}
        update_brief(
            root,
            {
                "creative": {**creative, "look": payload["look"], "image_rules": payload["image_rules"]},  # fmt: skip
                "avoid": payload.get("avoid", brief.avoid),
            },
            owner=True,
        )
        changed = ["creative.look", "creative.image_rules", "avoid"]
        preset = payload.get("style_preset")
        project = load_project(root, verify_source=False)
        if preset and project.style_preset != preset:
            write_json(root / "project.json", project.model_copy(update={"style_preset": preset}).model_dump())  # fmt: skip
            changed.append("project.style_preset")
    else:
        raise ValueError(f"the library keeps {', '.join(KINDS)}, not {kind}")
    return {
        "adopted": key,
        "version": entry["version"],
        "changed": changed,
        "skipped_files": skipped,
        "note": "The story needs approving again.",
    }


# ------------------------------------------------------------------ series


def _series_path(lib: Path, series_id: str) -> Path:
    if not isinstance(series_id, str) or not _ID.match(series_id):
        raise ValueError("a series needs a short lowercase id")
    return Path(lib) / SERIES / f"{series_id}.json"


def list_series(lib: Path) -> list[dict]:
    folder = Path(lib) / SERIES
    rows = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        value = read_optional(path)
        if isinstance(value, dict) and value.get("id"):
            rows.append(value)
    return rows


def read_series(lib: Path, series_id: str) -> dict:
    value = read_optional(_series_path(lib, series_id))
    if not isinstance(value, dict):
        raise ValueError(f"there is no series {series_id}")
    return value


def write_series(lib: Path, value: dict) -> dict:
    """Create or change a series. Episodes already listed are kept."""
    if not isinstance(value, dict):
        raise ValueError("a series is an object")
    series_id = value.get("id")
    path = _series_path(lib, series_id)
    previous = read_optional(path)
    previous = previous if isinstance(previous, dict) else {}
    title = str(value.get("title", previous.get("title", "")) or "").strip()
    if not title:
        raise ValueError("a series needs a title")
    bible = str(value.get("bible", previous.get("bible", "")) or "")
    if len(bible) > MAX_BIBLE:
        raise ValueError(f"a bible is at most {MAX_BIBLE} characters")
    recurring = value.get("recurring", previous.get("recurring", []))
    if not isinstance(recurring, list) or not all(isinstance(k, str) for k in recurring):
        raise ValueError("recurring is a list of entry keys")
    known = {entry["key"] for entry in entries(lib)}
    unknown = [key for key in recurring if key not in known]
    if unknown:
        raise ValueError(f"the library has no entry {', '.join(unknown)}")
    saved = {
        "id": series_id,
        "title": title[:120],
        "bible": bible,
        "recurring": list(dict.fromkeys(recurring)),
        "episodes": previous.get("episodes", []),
        "created_at": previous.get("created_at") or _now(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, saved)
    return saved


def add_episode(lib: Path, series_id: str, slug: str, number: int, title: str) -> dict:
    """List a film as an episode, once; a number already taken is refused."""
    series = read_series(lib, series_id)
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError("an episode number is a whole number from 1")
    if any(ep["slug"] == slug for ep in series["episodes"]):
        return series
    if any(ep["number"] == number for ep in series["episodes"]):
        raise ValueError(f"episode {number} of {series_id} already exists")
    series["episodes"].append({"slug": slug, "number": number, "title": title, "at": _now()})
    series["episodes"].sort(key=lambda ep: ep["number"])
    write_json(_series_path(lib, series_id), series)
    return series


def join_series(root: Path, lib: Path, series_id: str, number: int) -> dict:
    """A new film takes the series' recurring entries and is listed as an episode."""
    from .production import load_project

    project = load_project(root, verify_source=False)
    series = read_series(lib, series_id)
    adopted = [adopt(root, lib, key)["adopted"] for key in series["recurring"]]
    add_episode(lib, series_id, root.name, number, project.title)
    return {"series": series_id, "episode": number, "adopted": adopted}


def series_context(lib: Path, projects_dir: Path, series_id: str, current_slug: str) -> list[str]:
    """What the Writer is told: the bible and what earlier episodes established, read live."""
    try:
        series = read_series(lib, series_id)
    except ValueError:
        return [f"- Series {series_id}: not in the library."]
    lines = [f"- Series: {series['title']} ({series_id})."]
    bible = " ".join(series.get("bible", "").split())
    if bible:
        lines.append(f"- Bible: {bible[:600]}")
    if series.get("recurring"):
        lines.append("- Recurring: " + ", ".join(series["recurring"]))
    for episode in series.get("episodes", []):
        if episode["slug"] == current_slug:
            continue
        brief = read_optional(Path(projects_dir) / episode["slug"] / "brief.json")
        treatment = " ".join(str((brief or {}).get("treatment", "")).split()) if isinstance(brief, dict) else ""  # fmt: skip
        lines.append(
            f"- Episode {episode['number']}, {episode['title']}: "
            + (treatment[:240] if treatment else "no treatment on file")
        )
    return lines


# ------------------------------------------------------------------ a still from another film


def bring_still(root: Path, projects_dir: Path, from_slug: str, shot_id: str, version: int) -> dict:
    """Copy a still another film made into this one, as a file an upload shot can use."""
    root = Path(root)
    if not isinstance(from_slug, str) or not _ID.match(from_slug):
        raise ValueError("name the film the still comes from")
    other = Path(projects_dir) / from_slug
    if not (other / "project.json").is_file():
        raise ValueError(f"there is no film {from_slug}")
    assets = read_optional(other / "work/assets.json")
    entry = (assets or {}).get(shot_id) if isinstance(assets, dict) else None
    still = next((v for v in (entry or {}).get("versions", []) if v["version"] == version), None)
    if still is None:
        raise ValueError(f"{from_slug} has no still {shot_id} v{version}")
    source = inside(other, still["path"])
    sha = file_hash(source)
    if sha != still["sha256"]:
        raise ValueError("that still's bytes changed on disk; recover it there first")
    relative = f"media/uploads/{sha}{source.suffix.lower()}"
    target = inside(root, relative)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".partial")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    rows = read_optional(root / "work/provenance.json")
    rows = rows if isinstance(rows, list) else []
    row = {"path": relative, "sha256": sha, "from": {"slug": from_slug, "shot_id": shot_id, "version": version}, "at": _now()}  # fmt: skip
    if not any(r.get("path") == relative for r in rows):
        rows.append(row)
        write_json(root / "work/provenance.json", rows)
    return row
