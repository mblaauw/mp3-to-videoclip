"""The Publish stage: what the upload form asks for, and the checklist that says the film is ready.

Everything here is derived from a verified final and the brief. The copy is written under the
truth rules and checked in code: a URL that is not the call to action's, a price or a
percentage the brief never stated, are refused. Thumbnails are three JPEG candidates drawn
beside the final with Pillow and FFmpeg, never a provider. The release checklist's first line
is measured: the owner has heard the whole final with the sound on. Releasing records a fact;
uploading stays outside the app.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw

from . import delivery, localplate, watched
from .production.project import load_project, now
from .storage import file_hash, inside, read_optional, state_mutation, write_json

FILE = "work/publish.json"
VERSION = 1
MAX_TITLE = 100
MAX_TITLES = 3
MAX_DESCRIPTION = 5000
MAX_TAGS = 30
MAX_TAG = 60
THUMB_SIZE = (1280, 720)
THUMB_BYTES = 2_000_000
THUMB_SAMPLE_SECONDS = 2.0
PRESETS = {
    "youtube": {"label": "YouTube", "aspect": "16:9", "wants": ["chapters", "captions"]},
    "shorts": {"label": "YouTube Shorts", "aspect": "9:16", "wants": []},
    "reels": {"label": "Instagram Reels", "aspect": "9:16", "wants": []},
    "square": {"label": "Square feed", "aspect": "1:1", "wants": []},
}
_URL = re.compile(r"https?://[^\s)]+|\b[a-z0-9.-]+\.(?:com|net|org|io|nl|be|de|fr|uk|tv|ai|app|co)(?:/\S*)?", re.I)  # fmt: skip
_MONEY = re.compile(r"(?:[$€£]\s?\d[\d.,]*|\b\d[\d.,]*\s?(?:%|\b(?:percent|euros?|dollars?|pounds?)\b))", re.I)  # fmt: skip


# ------------------------------------------------------------------ the record


def read(root: Path) -> dict:
    value = read_optional(Path(root) / FILE)
    if not isinstance(value, dict):
        return {"version": VERSION, "presets": ["youtube"], "copy": None, "thumbnail": None, "released": None}  # fmt: skip
    value.setdefault("presets", ["youtube"])
    for key in ("copy", "thumbnail", "released"):
        value.setdefault(key, None)
    return value


def _write(root: Path, value: dict) -> dict:
    write_json(Path(root) / FILE, value)
    return value


# ------------------------------------------------------------------ the final


def current_final(root: Path) -> Path | None:
    """The newest final that is verified and still current, or ``None``."""
    from .domain.exports import describe

    root = Path(root)
    renders = root / "renders"
    if not renders.is_dir():
        return None
    for path in sorted(renders.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
        facts = describe(root, "renders", path.name)
        if facts["classification"] == "final" and facts["verified"] and facts["current"]:
            return path
    return None


def _final_sha(film: Path) -> str:
    report = read_optional(Path(film).with_suffix(".json"))
    if isinstance(report, dict) and isinstance(report.get("output_sha256"), str):
        return report["output_sha256"]
    return file_hash(film)


# ------------------------------------------------------------------ the copy


def _allowed_facts(root: Path) -> tuple[set[str], str]:
    """The URL the brief allows, and every text a stated number may come from."""
    from .production import load_brief
    from .production.script import load_script

    brief = load_brief(root)
    urls: set[str] = set()
    texts = [brief.treatment, brief.direction, " ".join(brief.visual_rules)]
    if brief.intent is not None:
        intent = brief.intent
        if intent.cta is not None and intent.cta.url.strip():
            urls.add(intent.cta.url.strip().lower().rstrip("/"))
            urls.add(re.sub(r"^https?://", "", intent.cta.url.strip().lower()).rstrip("/"))
        texts += [intent.objective, intent.message, intent.about, intent.notes, *intent.reasons, *intent.mandatories]  # fmt: skip
    for passage in brief.script:
        texts.append(passage.text)
    script = load_script(root)
    if script is not None:
        for line in script.lines:
            texts.append(line.text)
            texts += [claim.text for claim in line.claims]
    return urls, "\n".join(text for text in texts if text)


def check_copy(root: Path, copy: dict) -> list[str]:
    """Why this copy may not be published, in sentences; empty when it may."""
    problems: list[str] = []
    titles = copy.get("titles")
    if not isinstance(titles, list) or not titles or len(titles) > MAX_TITLES:
        problems.append(f"One to {MAX_TITLES} titles.")
        titles = []
    for title in titles:
        if not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE:
            problems.append(f"A title is one to {MAX_TITLE} characters.")
    description = copy.get("description", "")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION:
        problems.append(f"The description is at most {MAX_DESCRIPTION} characters.")
        description = ""
    tags = copy.get("tags", [])
    if not isinstance(tags, list) or len(tags) > MAX_TAGS or not all(isinstance(t, str) and 0 < len(t) <= MAX_TAG for t in tags):  # fmt: skip
        problems.append(f"At most {MAX_TAGS} tags of {MAX_TAG} characters.")
    allowed_urls, facts = _allowed_facts(root)
    everything = "\n".join([*[t for t in titles if isinstance(t, str)], description, *[t for t in tags if isinstance(t, str)]])  # fmt: skip
    for found in _URL.findall(everything):
        bare = re.sub(r"^https?://", "", found.strip().lower()).rstrip("/").rstrip(".")
        if bare not in allowed_urls and found.strip().lower().rstrip("/") not in allowed_urls:
            problems.append(f"The link {found} is not the brief's call to action.")
    for found in _MONEY.findall(everything):
        figure = found.strip().rstrip(".,;:!?")
        if figure not in facts:
            problems.append(f"The figure {figure} is not in the brief or the script.")
    return problems


@state_mutation
def set_copy(root: Path, copy: dict, *, by: str = "owner") -> dict:
    """Keep the copy only when the check passes. The last copy stays in the history."""
    if not isinstance(copy, dict):
        raise ValueError("the copy is an object")
    problems = check_copy(root, copy)
    if problems:
        raise ValueError(" ".join(problems))
    value = read(root)
    clean = {
        "titles": [t.strip() for t in copy["titles"]],
        "description": (copy.get("description") or "").strip(),
        "tags": [t.strip() for t in copy.get("tags", []) if t.strip()],
        "by": by,
        "at": now(),
    }
    previous = value.get("copy")
    if previous:
        history = root / "work/publish-history"
        history.mkdir(parents=True, exist_ok=True)
        write_json(history / f"copy-{previous.get('at', 'undated').replace(':', '-')}.json", previous)  # fmt: skip
    value["copy"] = clean
    return _write(root, value)


# ------------------------------------------------------------------ thumbnails


def _frames_to_try(root: Path, film: Path, total: int, fps: int) -> list[int]:
    """The poster frame, the loudest second and the frame with the most contrast."""
    project = load_project(root, verify_source=False)
    poster = delivery.poster_frame(root, film, project, total)
    loud = None
    music = read_optional(root / "work/music.json")
    points = [p for p in (music or {}).get("energy_curve", []) if isinstance(p, dict)] if isinstance(music, dict) else []  # fmt: skip
    if points:
        best = max(points, key=lambda p: float(p.get("energy") or 0))
        loud = min(total - 1, round(float(best.get("time") or 0) * fps))
    step = max(1, round(THUMB_SAMPLE_SECONDS * fps))
    raw = delivery._run(
        "-i", str(film),
        "-vf", f"select='not(mod(n\\,{step}))',scale=32:18,format=gray",
        "-fps_mode", "vfr",
        "-f", "rawvideo", "-",
    )  # fmt: skip
    contrast = None
    best_spread = -1.0
    for index in range(0, len(raw) // 576):
        block = raw[index * 576 : (index + 1) * 576]
        mean = sum(block) / 576
        spread = sum((b - mean) ** 2 for b in block) / 576
        if spread > best_spread:
            best_spread, contrast = spread, index * step
    chosen = []
    for frame in (poster, loud, contrast):
        if frame is not None and 0 <= frame < total and frame not in chosen:
            chosen.append(frame)
    return chosen[:3]


def _grab(film: Path, frame: int) -> Image.Image:
    raw = delivery._run(
        "-i", str(film),
        "-vf", f"select='eq(n\\,{frame})',scale={THUMB_SIZE[0]}:{THUMB_SIZE[1]}:force_original_aspect_ratio=increase,crop={THUMB_SIZE[0]}:{THUMB_SIZE[1]}",
        "-frames:v", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    )  # fmt: skip
    if len(raw) < THUMB_SIZE[0] * THUMB_SIZE[1] * 3:
        raise ValueError("that frame could not be read")
    return Image.frombytes("RGB", THUMB_SIZE, raw[: THUMB_SIZE[0] * THUMB_SIZE[1] * 3])


def _draw_title(image: Image.Image, title: str, brand: str) -> Image.Image:
    width, height = image.size
    band = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gradient = ImageDraw.Draw(band)
    top = int(height * 0.45)
    for y in range(top, height):
        alpha = int(200 * (y - top) / max(1, height - top))
        gradient.line([(0, y), (width, y)], fill=(8, 10, 14, alpha))
    out = Image.alpha_composite(image.convert("RGBA"), band)
    draw = ImageDraw.Draw(out)
    margin = int(width * 0.06)
    font, lines, advance = localplate._fitted(
        draw,
        [title],
        face="bold",
        nominal=height * 0.12,
        max_width=width - 2 * margin,
        max_height=height * 0.34,
        minimum=28,  # fmt: skip
    )
    y = height - margin - len(lines) * advance - (int(height * 0.05) if brand else 0)
    for line in lines:
        draw.text((margin + 3, y + 3), line, font=font, fill=(0, 0, 0, 160))
        draw.text((margin, y), line, font=font, fill=(250, 248, 242, 255))
        y += advance
    if brand:
        small = localplate._font("demi", height * 0.035)
        draw.text((margin, height - margin - height * 0.035), brand.upper(), font=small, fill=(220, 215, 205, 255))  # fmt: skip
    return out.convert("RGB")


def _brand_name(root: Path) -> str:
    from .branding import load_brand
    from .config import load_settings

    brand = load_brand(root)
    if brand is not None and brand.name.strip():
        return brand.name.strip()
    return load_settings().new_films.brand.name.strip()


def thumbnails(root: Path, film: Path, *, title: str | None = None) -> list[dict]:
    """Three 1280×720 candidates beside the final, each named by its frame. Never overwrites."""
    root, film = Path(root), Path(film)
    report = delivery._verified_final(root, film)
    project = load_project(root, verify_source=False)
    total = int(report.get("video", {}).get("frames") or project.total_frames)
    copy = read(root).get("copy") or {}
    words = (title or (copy.get("titles") or [project.title])[0]).strip() or project.title
    brand = _brand_name(root)
    rows = []
    for number, frame in enumerate(_frames_to_try(root, film, total, project.fps), start=1):
        path = film.with_suffix(f".thumb-f{frame:06d}-{number}.jpg")
        if not path.exists():
            image = _draw_title(_grab(film, frame), words, brand)
            quality = 88
            temporary = path.with_suffix(".partial.jpg")
            while True:
                image.save(temporary, "JPEG", quality=quality, optimize=True)
                if temporary.stat().st_size <= THUMB_BYTES or quality <= 50:
                    break
                quality -= 8
            temporary.replace(path)
        rows.append({"name": path.name, "frame": frame, "bytes": path.stat().st_size, "sha256": file_hash(path)})  # fmt: skip
    return rows


def listing(film: Path) -> list[dict]:
    film = Path(film)
    rows = []
    for path in sorted(film.parent.glob(f"{film.stem}.thumb-f*.jpg")):
        match = re.search(r"\.thumb-f(\d+)-(\d)\.jpg$", path.name)
        if match:
            rows.append({"name": path.name, "frame": int(match.group(1)), "bytes": path.stat().st_size, "sha256": file_hash(path)})  # fmt: skip
    return rows


@state_mutation
def choose_thumbnail(root: Path, film: Path, name: str) -> dict:
    film = Path(film)
    candidates = {row["name"]: row for row in listing(film)}
    if name not in candidates:
        raise ValueError("choose one of the thumbnails made for this final")
    value = read(root)
    value["thumbnail"] = {**candidates[name], "final": film.name}
    return _write(root, value)


@state_mutation
def set_presets(root: Path, presets: list) -> dict:
    if not isinstance(presets, list) or not presets or not all(p in PRESETS for p in presets):
        raise ValueError(f"presets are some of {', '.join(PRESETS)}")
    value = read(root)
    value["presets"] = list(dict.fromkeys(presets))
    return _write(root, value)


# ------------------------------------------------------------------ the plan and the checklist


def _versions(root: Path, final: Path) -> dict[str, dict]:
    """Rendered versions of this final by aspect, from their reports."""
    from .domain.exports import describe

    found = {}
    for path in (root / "renders").glob("*.mp4"):
        report = read_optional(path.with_suffix(".json"))
        variant = (report or {}).get("variant_of") if isinstance(report, dict) else None
        if isinstance(variant, dict) and variant.get("sha256") == _final_sha(final):
            facts = describe(root, "renders", path.name)
            if facts["verified"]:
                found[variant.get("aspect")] = {"name": path.name, "current": facts["current"]}
    return found


def _has_words(root: Path) -> bool:
    from .captions import timed_lines

    project = load_project(root, verify_source=False)
    try:
        return bool(timed_lines(root, project.fps, project.total_frames))
    except (OSError, ValueError):
        return False


def plan(root: Path, final: Path | None) -> list[dict]:
    """Per chosen preset: the files it has and what is still to make, naming the route."""
    root = Path(root)
    chosen = read(root)["presets"]
    rows = []
    if final is None:
        return [{"id": p, "label": PRESETS[p]["label"], "has": [], "missing": ["a verified final"]} for p in chosen]  # fmt: skip
    package = delivery.listing(final)
    versions = _versions(root, final)
    for preset in chosen:
        spec = PRESETS[preset]
        has, missing = [], []
        if spec["aspect"] == "16:9":
            has.append(final.name)
        elif spec["aspect"] in versions:
            has.append(versions[spec["aspect"]]["name"])
        else:
            missing.append(f"the {spec['aspect']} version (Film, Render {spec['aspect']})")
        for want in spec["wants"]:
            names = [n for n in package if (want == "chapters" and n.endswith(".chapters.txt")) or (want == "captions" and n.endswith(".srt"))]  # fmt: skip
            if names:
                has += names
            elif want == "captions" and not _has_words(root):
                continue
            else:
                missing.append(f"the {want} (Film, Make the package)")
        rows.append({"id": preset, "label": spec["label"], "aspect": spec["aspect"], "has": has, "missing": missing})  # fmt: skip
    return rows


def _line(identifier: str, label: str, done: bool, detail: str, *, required: bool = True, stage: str = "publish") -> dict:  # fmt: skip
    return {
        "id": identifier,
        "label": label,
        "stage": stage,
        "state": "done" if done else ("you" if required else "optional"),
        "required": required,
        "detail": detail,
    }


def checklist(root: Path) -> dict:
    """The release gates. The first is measured, the rest are facts the film already keeps."""
    from .budget import unresolved_tasks
    from .production import load_brief, unconfirmed_permissions

    root = Path(root)
    value = read(root)
    final = current_final(root)
    heard = watched.final_heard(root, final) if final else {"heard": 0, "total": 0, "share": 0.0, "watched": False}  # fmt: skip
    copy = value.get("copy")
    thumbnail = value.get("thumbnail")
    thumbnail_ok = bool(final and thumbnail and thumbnail.get("final") == final.name and (final.parent / thumbnail["name"]).is_file())  # fmt: skip
    waiting = unconfirmed_permissions(load_brief(root))
    unresolved = unresolved_tasks(root)
    lines = [
        _line(
            "final",
            "A current, verified final",
            final is not None,
            final.name if final else "Render the final on Film first.",
            stage="film",
        ),  # fmt: skip
        _line(
            "heard",
            "Heard start to finish with the sound on",
            bool(heard["watched"]),
            f"{heard['heard']} of {heard['total']} seconds heard."
            if heard["total"]
            else "Play the final in the Studio with the sound up.",  # fmt: skip
        ),
        _line(
            "copy",
            "Title, description and tags written and checked",
            bool(copy),
            f"{len(copy['titles'])} titles, {len(copy['tags'])} tags."
            if copy
            else "Write them, or ask the Writer.",
        ),  # fmt: skip
        _line(
            "thumbnail",
            "A thumbnail chosen",
            thumbnail_ok,
            thumbnail["name"] if thumbnail_ok else "Make three and pick one.",
        ),  # fmt: skip
        _line(
            "rights",
            "Everyone depicted has given permission",
            not waiting,
            "Permissions are recorded on Story."
            if not waiting
            else "Waiting for: " + ", ".join(waiting),
            stage="story",
        ),  # fmt: skip
        _line(
            "money",
            "No paid task still out",
            not unresolved,
            "The journal is settled."
            if not unresolved
            else f"{len(unresolved)} task{'s' if len(unresolved) != 1 else ''} unresolved under the budget.",
        ),  # fmt: skip
    ]
    if _has_words(root):
        captions_ok = bool(final and any(n.endswith(".srt") for n in delivery.listing(final)))
        lines.append(_line("captions", "Captions made", captions_ok, "SRT and VTT beside the final." if captions_ok else "Make the package on Film.", required=False, stage="film"))  # fmt: skip
    presets = value["presets"]
    if final and any(PRESETS[p]["aspect"] != "16:9" for p in presets):
        versions = _versions(root, final)
        wanted = sorted({PRESETS[p]["aspect"] for p in presets if PRESETS[p]["aspect"] != "16:9"})
        have = all(aspect in versions for aspect in wanted)
        lines.append(_line("versions", "Versions for the chosen presets", have, ", ".join(wanted) + (" rendered." if have else " still to render on Film."), required=False, stage="film"))  # fmt: skip
    required = [line for line in lines if line["required"]]
    return {
        "final": final.name if final else None,
        "heard": heard,
        "lines": lines,
        "can_release": all(line["state"] == "done" for line in required),
        "outstanding": [line["label"] for line in required if line["state"] != "done"],
        "released": value.get("released"),
        "presets": presets,
    }


@state_mutation
def release(root: Path, note: str = "") -> dict:
    """Record the release of the current final. Refused while a required line is open."""
    root = Path(root)
    facts = checklist(root)
    if not facts["can_release"]:
        raise ValueError("not ready to release: " + "; ".join(facts["outstanding"]))
    final = current_final(root)
    value = read(root)
    sha = _final_sha(final)
    files = {final.name: sha}
    for name in delivery.listing(final):
        files[name] = file_hash(final.parent / name)
    if value.get("thumbnail"):
        files[value["thumbnail"]["name"]] = value["thumbnail"]["sha256"]
    for row in plan(root, final):
        for name in row["has"]:
            path = final.parent / name
            if path.is_file() and name not in files:
                files[name] = file_hash(path)
    manifest = {
        "final": final.name,
        "final_sha256": sha,
        "presets": value["presets"],
        "copy": value.get("copy"),
        "thumbnail": value.get("thumbnail"),
        "files": files,
        "released_at": now(),
        "note": note.strip()[:300],
    }
    listing_path = final.with_suffix(".publish.json")
    if not listing_path.exists():
        write_json(listing_path, manifest)
    value["released"] = {"at": manifest["released_at"], "final": final.name, "final_sha256": sha, "presets": value["presets"]}  # fmt: skip
    _write(root, value)
    return manifest


def view(root: Path) -> dict:
    root = Path(root)
    final = current_final(root)
    value = read(root)
    return {
        **checklist(root),
        "copy": value.get("copy"),
        "thumbnail": value.get("thumbnail"),
        "thumbnails": listing(final) if final else [],
        "plan": plan(root, final),
        "presets_available": [{"id": key, **spec} for key, spec in PRESETS.items()],
        "has_words": _has_words(root),
    }


def manifest_path(root: Path, name: str) -> Path:
    return inside(root, f"renders/{name}")
