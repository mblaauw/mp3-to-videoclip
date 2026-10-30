"""The existing local graphics pipeline, required for newly versioned films only."""

from pathlib import Path

from . import operations
from .storage import (
    digest,
    file_hash,
    inside,
    project_lock,
    read_json,
    read_optional,
    read_snapshot,
    state_lock,
    write_json,
)

NAMES = "MAHA KALA  ×  VJDJ69"
FILMSTRIP_NAMES = "MAHA KALA  ◆  VJDJ69"
PRODUCTION_LINE = "A JOINT MAHA KALA & VJDJ69 PRODUCTION"
SPEC = "work/graphics-spec.json"
REVIEW = "work/graphics-review.json"
#: A titles review drawn from stills of the film composition itself (no base movie).
COMPOSITION_METHOD = "composition-v1"


def draft_spec(title: str) -> dict:
    """Never invent credits. Empty cards deliberately block brief approval."""
    return {
        "version": 1,
        "demo": False,
        "credit_roles_confirmed": False,
        "intro_seconds": 25.0,
        "credits_tail_seconds": 40.0,
        "lockup_seconds": 4.0,
        "intro": {
            "names": NAMES,
            "title": title,
            "tagline": PRODUCTION_LINE,
            "notes": [],
            "mini_credits": [],
        },
        "captions": [],
        "credits": {"cards": [], "lockup": PRODUCTION_LINE},
        "warning": "Draft: record this film's factual credit roles and confirm them before brief approval. Do not reuse randomized demo roles.",
    }


def _valid_cards(cards) -> list | None:
    """Accept only a bounded list of non-empty role/name pairs."""
    if not isinstance(cards, list) or not cards or len(cards) > 40:
        return None
    if not all(
        isinstance(card, list)
        and len(card) == 2
        and all(isinstance(item, str) and item.strip() for item in card)
        for card in cards
    ):
        return None
    return cards


def credits_template(projects_dir: Path) -> list | None:
    """Most recent factual role/name cards from a sibling production.

    An explicitly saved ``work/credits-template.json`` wins. Without one, a
    recorded ``work/graphics-spec.json`` is used as a read-only fallback so the
    current productions can prefill the next film too. New films are prefilled,
    never auto-confirmed: the user still confirms who actually worked on this
    film. Invalid or missing sources return ``None``.
    """
    best = None
    for path in Path(projects_dir).glob("*/work/credits-template.json"):
        value = read_optional(path)
        cards = _valid_cards(value.get("cards")) if isinstance(value, dict) else None
        if cards and (best is None or path.stat().st_mtime > best[0]):
            best = (path.stat().st_mtime, cards)
    if best:
        return best[1]
    for path in Path(projects_dir).glob("*/work/graphics-spec.json"):
        value = read_optional(path)
        credits = value.get("credits") if isinstance(value, dict) else None
        cards = _valid_cards(credits.get("cards")) if isinstance(credits, dict) else None
        if cards and (best is None or path.stat().st_mtime > best[0]):
            best = (path.stat().st_mtime, cards)
    return best[1] if best else None


def validate_spec(root: Path, project) -> dict:
    from .graphics import load_spec

    if project.aspect != "16:9":
        raise ValueError(
            "the required signature compositor supports 16:9 only; resolve portrait graphics before brief approval or production spending"
        )
    raw = read_json(root / SPEC)
    if raw.get("demo") is True or raw.get("credit_roles_confirmed") is not True:
        raise ValueError(
            "confirm this film's factual credit roles; demo/unconfirmed credits cannot be approved"
        )
    spec = load_spec(root)
    if spec["intro_seconds"] != 25 or spec["credits_tail_seconds"] != 40:
        raise ValueError("the signature requires 25-second opening and final 40-second credits")
    if project.duration < 65:
        raise ValueError(
            "source is too short for the 25/40 signature; obtain an explicit alternate plan, never append a tail"
        )
    expected_names = (
        FILMSTRIP_NAMES if spec["intro"].get("mark", {}).get("kind") == "filmstrip" else NAMES
    )
    if spec["intro"]["names"] != expected_names or spec["intro"].get("tagline") != PRODUCTION_LINE:
        raise ValueError("restore the approved shared production identity")
    if spec["credits"]["lockup"] != PRODUCTION_LINE:
        raise ValueError("closing joint-production lockup is required")
    if spec["intro"]["title"].casefold() != project.title.casefold():
        raise ValueError("graphics title must match the film title, not the MP3 filename")
    for card in spec["credits"]["cards"]:
        if (
            not isinstance(card, list)
            or len(card) != 2
            or not all(isinstance(x, str) and x.strip() for x in card)
        ):
            raise ValueError("credit cards require a confirmed nonempty role and name")
    return spec


def save_credits(root: Path, cards, *, use_as_template: bool = False) -> list:
    """Record the film's factual roles for a guided production.

    Late credits are deliberately outside the brief hash for guided films, so a
    factual correction here cannot silently invalidate image approvals. Older
    productions keep credits inside their brief decision and are refused.
    """
    from . import flow

    if not flow.guided(root):
        raise ValueError(
            "this film records credits inside its brief approval; ask your agent to "
            "revise the signature and approve the story again"
        )
    if type(use_as_template) is not bool:
        raise ValueError("use_as_template must be a boolean")
    raw = _valid_cards(cards)
    if raw is None:
        raise ValueError("record at least one factual role/name pair, at most 40")
    normalized = []
    for card in raw:
        role, name = (value.strip() for value in card)
        if len(role) > 120 or len(name) > 120:
            raise ValueError("a credit role or name must be at most 120 characters")
        normalized.append([role, name])
    with project_lock(root), state_lock(root):
        spec = read_json(root / SPEC)
        spec.setdefault("credits", {})
        spec["credits"]["cards"] = normalized
        spec["credit_roles_confirmed"] = True
        spec.pop("warning", None)
        write_json(root / SPEC, spec)
        if use_as_template:
            write_json(root / "work/credits-template.json", {"cards": normalized})
    return normalized


@operations.progress_scope(stage="graphics-review")
def prepare_review(root: Path, base: Path, project) -> dict:
    from .graphics import implementation_revision, preflight_frames

    resolved_spec = validate_spec(root, project)
    spec_hash, base_hash = digest(read_json(root / SPEC)), file_hash(base)
    # The implementation revision belongs in the key. The composited samples are a
    # function of the renderer's bytes as much as of the spec and the base, so
    # keying on spec+base alone reused preflights drawn by older code and handed
    # back composites that no longer matched what the renderer produces.
    revision = implementation_revision()
    resolved_hash = digest(resolved_spec)
    key = digest([spec_hash, resolved_hash, base_hash, revision])[:16]
    directory = root / "work/reviews" / f"signature-{key}"
    preflight = directory / "preflight.json"
    if not preflight.exists() or read_json(preflight).get("implementation_revision") != revision:
        operations.phase("sampling-graphics")
        report = preflight_frames(root, base, directory)
        preflight = Path(report["sidecar"])
    samples = {}
    for frame in read_json(preflight)["frames"]:
        path = Path(frame["image"])
        relative = (
            str(path.resolve().relative_to(root.resolve())) if path.is_absolute() else str(path)
        )
        samples[relative] = file_hash(inside(root, relative))
    value = {
        "base": str(base.relative_to(root)),
        "base_sha256": base_hash,
        "base_input_hash": current_input_hash(root),
        "spec_hash": spec_hash,
        "resolved_spec_hash": resolved_hash,
        "implementation_revision": revision,
        "preflight": str(preflight.relative_to(root)),
        "preflight_sha256": file_hash(preflight),
        "samples": samples,
        "warning": "Inspect the actual composited preflight samples in Studio, then approve graphics with the inspected attestation; this base is not final.",
    }
    write_json(root / REVIEW, value)
    operations.phase("awaiting-owner-review")
    return value


def _titles_facts(root: Path, project, *, for_render: bool = False) -> dict:
    """Everything a composition titles review binds, read from one snapshot.

    ``for_render`` also resolves the pictures and brand the stills are drawn on.
    """
    from . import production as P
    from . import titles
    from .domain.exports import input_metadata_hash
    from .graphics import resolve_palette
    from .remotion import implementation_hash, titles_input

    with read_snapshot(root):
        resolved_spec = validate_spec(root, project)
        spec, windows = titles.plan_for(root)
        payload = titles_input(spec, resolve_palette(spec), windows)
        facts = {
            "spec_hash": digest(read_json(root / SPEC)),
            "resolved_spec_hash": digest(resolved_spec),
            "titles_hash": digest(payload),
            "input_hash": current_input_hash(root),
            "input_metadata_hash": input_metadata_hash(root),
            "renderer_revision": implementation_hash(),
            "spec": spec,
            "windows": windows,
            "titles": payload,
        }
        if for_render:
            facts["shots"] = P.resolved_assets(root)
            facts["brand"] = P.load_brand(root)
        return facts


BOUND = (
    "spec_hash",
    "resolved_spec_hash",
    "titles_hash",
    "input_hash",
    "input_metadata_hash",
    "renderer_revision",
)


@operations.progress_scope(stage="graphics-review")
def prepare_titles_review(root: Path, project) -> dict:
    """Render review stills from the film composition and record what they show.

    The samples are the frames the final will draw at one moment of every
    opening phase and the middle of every other title window, rendered with the
    same composition, pictures and titles. No base movie is needed.
    """
    from . import timeline
    from .graphics import _preflight_samples, intro_phase_samples, resolve_design
    from .remotion import render_stills

    facts = _titles_facts(root, project, for_render=True)
    fps, total = project.fps, project.total_frames
    parts = [{**window, "start": window["start_frame"] / fps} for window in facts["windows"]]
    picks = _preflight_samples(facts["spec"], parts, fps, total, None)
    key = digest([facts[name] for name in BOUND])[:16]
    directory = root / "work/reviews" / f"titles-{key}"
    sidecar = directory / "samples.json"
    if not sidecar.is_file():
        operations.phase("sampling-graphics")
        rendered = render_stills(
            project,
            facts["shots"],
            [pick["frame"] for pick in picks],
            directory,
            root / "work",
            brand=facts["brand"],
            titles=facts["titles"],
        )
        files = {still["frame"]: still for still in rendered["stills"]}
        phases = {
            timeline.frame_number(phase["sample_seconds"], fps): phase["phase"]
            for phase in intro_phase_samples(
                float(facts["spec"]["intro_seconds"]), resolve_design(facts["spec"])
            )
        }
        samples = []
        for pick in sorted(picks, key=lambda item: item["frame"]):
            frame = pick["frame"]
            window = next(
                (
                    w
                    for w in facts["windows"]
                    if w["start_frame"] <= frame < w["start_frame"] + w["frames"]
                ),
                None,
            )
            samples.append(
                {
                    "frame": frame,
                    "seconds": frame / fps,
                    "phase": phases.get(frame),
                    "window": window["id"] if window else None,
                    "kind": window["kind"] if window else None,
                    "image": str((directory / files[frame]["file"]).relative_to(root)),
                    "sha256": files[frame]["sha256"],
                }
            )
        write_json(
            sidecar,
            {
                "method": COMPOSITION_METHOD,
                **{name: facts[name] for name in BOUND},
                "windows": facts["windows"],
                "frames": samples,
            },
        )
    recorded = read_json(sidecar)
    value = {
        "method": COMPOSITION_METHOD,
        **{name: facts[name] for name in BOUND},
        "preflight": str(sidecar.relative_to(root)),
        "preflight_sha256": file_hash(sidecar),
        "samples": {
            sample["image"]: file_hash(inside(root, sample["image"]))
            for sample in recorded["frames"]
        },
        "warning": "Inspect every sample in Studio: each is a frame of the real film with its "
        "titles. Then approve intro/credits with the inspected attestation; nothing is final yet.",
    }
    write_json(root / REVIEW, value)
    operations.phase("awaiting-owner-review")
    return value


def validate_titles_review(root: Path, project, value: dict) -> dict:
    """A composition review is current only while every bound input and sample is."""
    facts = _titles_facts(root, project)
    reasons = {
        "spec_hash": "graphics spec changed",
        "resolved_spec_hash": "graphics identity changed",
        "titles_hash": "the planned titles changed",
        "input_hash": "the storyboard or stills changed",
        "input_metadata_hash": "the cut or a production input changed",
        "renderer_revision": "the renderer changed",
    }
    for name, reason in reasons.items():
        if value.get(name) != facts[name]:
            raise ValueError(f"{reason}; check the titles again and renew the review")
    preflight = inside(root, value["preflight"])
    if value["preflight_sha256"] != file_hash(preflight):
        raise ValueError("titles review samples record changed; check the titles again")
    recorded = read_json(preflight)
    if any(recorded.get(name) != value[name] for name in BOUND):
        raise ValueError("titles review samples belong to other inputs; check the titles again")
    frames = recorded.get("frames") or []
    if not frames or len(value.get("samples", {})) != len(frames):
        raise ValueError("graphics review must bind every sampled image")
    for relative, expected in value["samples"].items():
        if file_hash(inside(root, relative)) != expected:
            raise ValueError("graphics review sample changed; renew inspection")
    return value


def current_input_hash(root: Path) -> str:
    from . import production as P
    from .remotion import renderer_binding

    return digest(
        {
            "storyboard": read_json(root / "work/storyboard.json"),
            "stills": P.stage_hash(root, "stills"),
            **renderer_binding(P.load_project(root)),
        }
    )


def validate_review(root: Path, project) -> dict:
    from .graphics import implementation_revision

    value = read_json(root / REVIEW)
    if value.get("method") == COMPOSITION_METHOD:
        return validate_titles_review(root, project, value)
    resolved_spec = validate_spec(root, project)
    if value["spec_hash"] != digest(read_json(root / SPEC)):
        raise ValueError("graphics spec changed; recreate preflight and renew graphics review")
    if value["base_sha256"] != file_hash(inside(root, value["base"])):
        raise ValueError("graphics base changed; recreate preflight and renew graphics review")
    base_report = read_json(inside(root, value["base"]).with_suffix(".json"))
    current = current_input_hash(root)
    if value.get("base_input_hash") != current or base_report.get("input_hash") != current:
        raise ValueError(
            "graphics base belongs to obsolete storyboard/stills inputs; render a current base and renew graphics review"
        )
    preflight = inside(root, value["preflight"])
    if value["preflight_sha256"] != file_hash(preflight):
        raise ValueError("graphics preflight changed; renew review")
    facts = read_json(preflight)
    revision = implementation_revision()
    if (
        value.get("implementation_revision") != revision
        or facts.get("implementation_revision") != revision
    ):
        raise ValueError(
            "graphics implementation changed; recreate preflight and renew graphics review"
        )
    if value.get("resolved_spec_hash") != digest(resolved_spec) or facts.get(
        "spec_sha256"
    ) != digest(resolved_spec):
        raise ValueError("graphics identity changed; recreate preflight and renew graphics review")
    if facts["base"]["sha256"] != value["base_sha256"]:
        raise ValueError("graphics preflight belongs to another base")
    if facts.get("truncated") or not facts.get("frames"):
        raise ValueError("graphics preflight must cover the complete signature")
    if len(value.get("samples", {})) != len(facts["frames"]):
        raise ValueError("graphics review must bind every sampled image")
    for relative, expected in value["samples"].items():
        if file_hash(inside(root, relative)) != expected:
            raise ValueError("graphics review sample changed; renew inspection")
    return value
