"""Prompt-version evaluation reports from frozen fixtures and local runs.

The default run needs no model and no network. It writes one page for each
current Writer/Editor prompt version used by the three frozen fixtures, plus one
page for every stored run, rating-only or unbound prompt hash. A page says
"not run" until a real artifact bundle exists; it never invents a result.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path

from mp3_to_videoclip import edits, ratings, styles
from mp3_to_videoclip.director import prompts
from mp3_to_videoclip.models import (
    Brief,
    EditDecisionList,
    EventMap,
    Intent,
    MusicEvent,
    Project,
    Storyboard,
    Treatments,
)
from mp3_to_videoclip.storage import file_hash, write_json

from . import checks, rubric

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
REPORTS = HERE / "reports"


def _json(path: Path):
    return json.loads(path.read_text())


def _fixture_key(fixture: str) -> str:
    return fixture.strip()


def _artifact(run_dir: Path, meta: dict, key: str, default: str) -> Path | None:
    relative = (meta.get("artifacts") or {}).get(key, default)
    path = run_dir / relative
    return path if path.is_file() else None


@contextmanager
def _fixture_root(fixture: dict, board: Storyboard):
    """A throwaway project root for the edit report's brief/events lookups."""
    with tempfile.TemporaryDirectory(prefix="eval-fixture-") as directory:
        root = Path(directory) / "production"
        (root / "media").mkdir(parents=True)
        (root / "work").mkdir(parents=True)
        source = root / "media" / "song.mp3"
        source.write_bytes(b"eval fixture: no provider")
        project = Project(
            schema_version=3,
            slug="eval",
            title=fixture["name"],
            source="media/song.mp3",
            source_sha256=file_hash(source),
            duration=board.total_frames / board.fps,
            aspect=board.aspect,
            fps=board.fps,
            width=1920 if board.aspect == "16:9" else 1080,
            height=1080 if board.aspect == "16:9" else 1920,
            music_mode=fixture.get("music_mode"),
            kind=fixture.get("kind"),
            workflow_version=2,
            renderer_backend="remotion",
        )
        write_json(root / "project.json", project.model_dump())
        intent = Intent.model_validate(fixture["intent"]) if fixture.get("intent") else None
        write_json(root / "brief.json", Brief(intent=intent).model_dump())
        events = []
        for index, section in enumerate(fixture.get("music", {}).get("sections", [])):
            start = max(0, round(float(section["start"]) * board.fps))
            end = min(board.total_frames, round(float(section["end"]) * board.fps))
            if end <= start:
                continue
            events.append(
                MusicEvent(
                    id=f"section-{index + 1}",
                    frame=start,
                    end_frame=end,
                    kind="section",
                    label=str(section.get("label") or "section"),
                    timing_basis="manual",
                )
            )
        write_json(
            root / "work" / "events.json",
            EventMap(
                source_sha256=project.source_sha256,
                fps=board.fps,
                total_frames=board.total_frames,
                events=events,
            ).model_dump(),
        )
        yield root, project


def _normalise_ratings(values) -> list[dict]:
    clean = []
    for entry in values or []:
        if not isinstance(entry, dict):
            continue
        artifact = entry.get("artifact")
        rating = entry.get("rating")
        if artifact not in ratings.ARTIFACTS or rating not in ratings.RATINGS_CHOICES:
            continue
        files = entry.get("prompt_files")
        clean.append(
            {
                "artifact": artifact,
                "label": entry.get("label") or ratings.LABELS[artifact],
                "rating": rating,
                "note": str(entry.get("note") or ""),
                "prompt_hash": (
                    str(entry["prompt_hash"]) if entry.get("prompt_hash") is not None else None
                ),
                "prompt_files": files if isinstance(files, list) else [],
                "prompt_role": (
                    str(entry["prompt_role"]) if entry.get("prompt_role") is not None else None
                ),
                "prompt_task": (
                    str(entry["prompt_task"]) if entry.get("prompt_task") is not None else None
                ),
                "at": entry.get("at"),
            }
        )
    return clean


def _jsonl(text: str) -> list:
    "Parse append-only JSONL, skipping a damaged line instead of losing the file."
    values = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return values


def _load_ratings(path: Path | None) -> list[dict]:
    if path is None or not path.is_file():
        return []
    text = path.read_text()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return _normalise_ratings(_jsonl(text))
    if isinstance(value, dict) and value.get("artifact") in ratings.ARTIFACTS:
        value = [value]
    elif isinstance(value, dict):
        value = value.get("ratings") or value.get("entries") or []
    return _normalise_ratings(value)


def _load_meta_ratings(run_dir: Path, meta: dict) -> list[dict]:
    values = meta.get("ratings") or []
    path = run_dir / "ratings.jsonl"
    if not values and path.is_file():
        try:
            values = _jsonl(path.read_text())
        except OSError:
            values = []
    return _normalise_ratings(values)


def _cross_review(run_dir: Path, meta: dict, role: str) -> tuple[dict | None, str | None]:
    value = meta.get("cross_review")
    if value is None and (run_dir / "cross_review.json").is_file():
        try:
            value = _json(run_dir / "cross_review.json")
        except (OSError, json.JSONDecodeError) as exc:
            return None, f"cross_review.json is not readable JSON: {exc}"
    if value is None:
        return None, None
    try:
        return rubric.normalise(value, role), None
    except ValueError as exc:
        return None, str(exc)


def evaluate_run(run_dir: Path) -> dict:
    meta = _json(run_dir / "meta.json")
    fixture_name = _fixture_key(str(meta.get("fixture") or ""))
    role = str(meta.get("role") or "")
    prompt = meta.get("prompt") or {}
    result = {
        "id": run_dir.name,
        "fixture": fixture_name,
        "role": role,
        "model": str(meta.get("model") or "unknown"),
        "synthetic": bool(meta.get("synthetic")),
        "prompt": prompt,
        "prompt_hash": prompt.get("hash") or "unbound",
        "checks": {},
        "ok": False,
        "error": None,
        "cross_review": None,
        "cross_review_error": None,
        "ratings": _load_meta_ratings(run_dir, meta),
    }
    try:
        fixture = checks.fixture(fixture_name)
        if role == "writer":
            treatments_path = _artifact(run_dir, meta, "treatments", "treatments.json")
            storyboard_path = _artifact(run_dir, meta, "storyboard", "storyboard.json")
            if treatments_path is None or storyboard_path is None:
                raise ValueError("writer run needs treatments.json and storyboard.json")
            treatments = Treatments.model_validate(_json(treatments_path))
            board = Storyboard.model_validate(_json(storyboard_path))
            automatic = checks.report(fixture, treatments.model_dump(), board.model_dump())
            result["checks"] = automatic
            result["ok"] = automatic["ok"]
        elif role == "editor":
            storyboard_path = _artifact(run_dir, meta, "storyboard", "storyboard.json")
            edit_path = _artifact(run_dir, meta, "edit", "edit.json")
            if storyboard_path is None or edit_path is None:
                raise ValueError("editor run needs storyboard.json and edit.json")
            board = Storyboard.model_validate(_json(storyboard_path))
            edit = EditDecisionList.model_validate(_json(edit_path))
            with _fixture_root(fixture, board) as (root, project):
                cut_report = edits.report(root, edit=edit, board=board, project=project)
            automatic = checks.edit_report(fixture, board.model_dump(), cut_report)
            automatic["reasoned_techniques"] = len(
                [row for row in cut_report.get("techniques", []) if row.get("reasoned")]
            )
            automatic["hold_ratio"] = cut_report.get("counts", {}).get("hold_ratio")
            result["checks"] = automatic
            result["ok"] = automatic["ok"]
        else:
            raise ValueError("meta.role must be writer or editor")
    except Exception as exc:  # noqa: BLE001 - one damaged run must not stop the report
        result["error"] = str(exc)
        result["ok"] = False
    result["cross_review"], result["cross_review_error"] = _cross_review(run_dir, meta, role)
    return result


def discover_runs(directory: Path = RUNS) -> list[dict]:
    if not directory.is_dir():
        return []
    results = []
    for run_dir in sorted(path for path in directory.iterdir() if path.is_dir()):
        if not (run_dir / "meta.json").is_file():
            continue
        results.append(evaluate_run(run_dir))
    return results


@contextmanager
def _prompt_bundle(fixture: dict, role: str):
    kind = fixture["kind"]
    stage = "storyboard" if role == "writer" else "film"
    task = "storyboard" if role == "writer" else "edit"
    style = styles.default_for(kind).id if role == "writer" else None
    with tempfile.TemporaryDirectory(prefix="eval-prompt-") as directory:
        root = Path(directory) / "production"
        root.mkdir(parents=True)
        write_json(
            root / "project.json",
            {"schema_version": 3, "kind": kind, "style_preset": style},
        )
        yield prompts.assemble(
            root,
            stage,
            role=role,
            kind=kind,
            style_preset=style,
            task=task,
        )


def current_prompt_versions() -> list[dict]:
    versions = []
    for fixture in checks.load_fixtures():
        for role in ("writer", "editor"):
            with _prompt_bundle(fixture, role) as bundle:
                versions.append(
                    {
                        "fixture": fixture["name"],
                        "role": role,
                        "task": bundle.meta.get("task"),
                        "kind": fixture["kind"],
                        "prompt": bundle.meta,
                    }
                )
    return versions


def _fixtures_for(versions: list[dict]) -> str:
    return ", ".join(sorted({version["fixture"] for version in versions}))


def _format_files(files: list[dict]) -> str:
    if not files:
        return "not recorded"
    return ", ".join(f"{item.get('path')} v{item.get('version')}" for item in files)


def _status(value: bool) -> str:
    return "PASS" if value else "FAIL"


def _rating_rows(values: list[dict]) -> list[str]:
    rows = [
        "| Artifact | Rating | Note | Prompt |",
        "| --- | --- | --- | --- |",
    ]
    for value in values:
        rows.append(
            "| {artifact} | {rating} | {note} | {prompt} |".format(
                artifact=value.get("label") or value.get("artifact"),
                rating="Good" if value.get("rating") == "up" else "Needs work",
                note=(value.get("note") or "—").replace("|", "\\|"),
                prompt=(value.get("prompt_hash") or "unbound")[:10],
            )
        )
    return rows


def _run_rows(runs: list[dict]) -> list[str]:
    rows = [
        "| Fixture | Model | Automatic | Concepts | Board | Claims | Edit hard | Ad |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for run in runs:
        checks_value = run.get("checks") or {}
        writer = run["role"] == "writer"
        concepts = checks_value.get("concepts") or {}
        storyboard = checks_value.get("storyboard") or {}
        claims = checks_value.get("claims") or {}
        ad = (checks_value.get("ad") or {}).get("checks", [])
        automatic_ad = [item for item in ad if item.get("automatic", True)]
        ad_ok = all(item.get("ok") for item in automatic_ad) if automatic_ad else None
        rows.append(
            "| {fixture} | {model} | {auto} | {concepts} | {board} | {claims} | {hard} | {ad} |".format(
                fixture=run["fixture"],
                model=run["model"],
                auto=_status(run["ok"]),
                concepts=(
                    f"{concepts.get('distinct_structures', 0)}/{concepts.get('count', 0)}"
                    if writer
                    else "—"
                ),
                board=(f"{storyboard.get('shots', 0)} shots" if storyboard else "—"),
                claims=("none" if claims.get("ok") else ", ".join(claims.get("invented", [])))
                if claims
                else "—",
                hard=(str(len(checks_value.get("hard", []))) if not writer else "—"),
                ad=("—" if ad_ok is None else ("pass" if ad_ok else "fail")),
            )
        )
    return rows


def prompt_page(
    key: str,
    versions: list[dict],
    runs: list[dict],
    rating_values: list[dict],
    *,
    historical: bool = False,
) -> str:
    prompt = next(
        (run.get("prompt") or {} for run in runs if run.get("prompt")),
        versions[0]["prompt"] if versions else {},
    )
    role = (
        prompt.get("role")
        or (versions[0]["role"] if versions else None)
        or (runs[0]["role"] if runs else None)
        or next(
            (value.get("prompt_role") for value in rating_values if value.get("prompt_role")),
            None,
        )
        or "unknown"
    )
    task = (
        prompt.get("task")
        or (versions[0]["task"] if versions else None)
        or next(
            (value.get("prompt_task") for value in rating_values if value.get("prompt_task")),
            None,
        )
        or "unknown"
    )
    kind = prompt.get("kind") or (versions[0]["kind"] if versions else "unknown")
    files = prompt.get("files") or next(
        (value.get("prompt_files") for value in rating_values if value.get("prompt_files")),
        [],
    )
    fixtures = (
        _fixtures_for(versions) if versions else ", ".join(sorted({run["fixture"] for run in runs}))
    )
    lines = [
        "# Unbound ratings" if key == "unbound" else f"# Prompt `{key}`",
        "",
        f"- Role / task: **{role} / {task}**",
        f"- Kind: **{kind}**",
        f"- Words: {prompt.get('words', 'not recorded')}",
        f"- Files: {_format_files(files)}",
        f"- Fixtures: {fixtures or 'none'}",
    ]
    if historical:
        lines.append("- Status: historical prompt version; not in the current prompt set.")
    if any(run.get("synthetic") for run in runs):
        lines.append(
            "- Note: this run is marked synthetic; it is a harness check, not a model evaluation."
        )
    lines.append("")
    if not runs:
        lines.extend(
            [
                "## Automatic checks",
                "",
                "No run recorded for this prompt version. The fixtures are ready; run the "
                "Writer/Editor on a copy and place the bundle under `tests/evals/runs/`.",
                "",
                "## Cross-review",
                "",
                "Not run. This is a signal, not a gate.",
                "",
                "## Human ratings",
                "",
            ]
        )
        if rating_values:
            lines.extend(_rating_rows(rating_values))
        else:
            lines.append("No ratings recorded for this prompt version.")
        lines.extend(["", "## Rule of change", ""])
        if rating_values:
            lines.append(
                "No automatic evidence yet. Human ratings: "
                f"**{len(rating_values)}**. Do not ship a prompt edit on preference alone."
            )
        else:
            lines.append("No evidence yet. Do not ship a prompt edit on preference alone.")
        return "\n".join(lines) + "\n"

    passed = sum(1 for run in runs if run["ok"])
    lines.extend(
        [
            "## Automatic checks",
            "",
            f"**{passed} / {len(runs)} runs pass.**",
            "",
            *_run_rows(runs),
            "",
        ]
    )
    failures = [run for run in runs if not run["ok"]]
    if failures:
        lines.append("### Findings")
        for run in failures:
            if run.get("error"):
                lines.append(f"- {run['fixture']}: {run['error']}")
                continue
            checks_value = run.get("checks") or {}
            for issue in checks_value.get("issues", []):
                lines.append(f"- {run['fixture']}: {issue}")
            for finding in checks_value.get("hard", []):
                lines.append(
                    f"- {run['fixture']}: hard {finding.get('code')}: {finding.get('message')}"
                )
    lines.extend(["", "## Cross-review", ""])
    reviews = [run["cross_review"] for run in runs if run.get("cross_review")]
    review_summary = rubric.summarise(reviews)
    lines.append(rubric.markdown_table(review_summary))
    invalid = [run for run in runs if run.get("cross_review_error")]
    for run in invalid:
        lines.append(f"- {run['fixture']}: {run['cross_review_error']}")
    lines.extend(["", "## Human ratings", ""])
    values = [value for run in runs for value in run.get("ratings", [])]
    values.extend(rating_values)
    if not values:
        lines.append("No ratings recorded for this prompt version.")
    else:
        lines.extend(_rating_rows(values))
    lines.extend(
        [
            "",
            "## Rule of change",
            "",
            f"Automatic pass rate: **{passed}/{len(runs)}**. Cross-review: "
            f"**{review_summary['overall'] if review_summary['overall'] is not None else 'not run'} / 5** "
            f"from {review_summary['count']} review(s). Human ratings: **{len(values)}**.",
            "A prompt edit ships only when it does not lower the automatic pass rate on these "
            "fixtures and the owner prefers its output side by side.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_index(reports: list[Path], report_dir: Path) -> Path:
    lines = [
        "# Prompt evaluation reports",
        "",
        "One page per prompt version. Automatic checks are the gate; cross-review and "
        "human ratings are signals. No paid call is made by this command.",
        "",
        "| Prompt | Role / task | Fixtures | Report |",
        "| --- | --- | --- | --- |",
    ]
    for path in reports:
        text = path.read_text()
        role = next(
            (
                line.split("**")[1]
                for line in text.splitlines()
                if line.startswith("- Role / task:")
            ),
            "unknown",
        )
        fixtures = next(
            (
                line.split(": ", 1)[1]
                for line in text.splitlines()
                if line.startswith("- Fixtures:")
            ),
            "unknown",
        )
        lines.append(
            f"| `{path.stem.removeprefix('prompt-')}` | {role} | {fixtures} | [{path.name}]({path.name}) |"
        )
    path = report_dir / "index.md"
    path.write_text("\n".join(lines) + "\n")
    return path


def run(
    *,
    runs_dir: Path = RUNS,
    report_dir: Path = REPORTS,
    ratings_path: Path | None = None,
    strict: bool = False,
) -> tuple[list[Path], dict]:
    report_dir.mkdir(parents=True, exist_ok=True)
    run_values = discover_runs(runs_dir)
    versions = current_prompt_versions()
    global_ratings = _load_ratings(ratings_path)

    grouped_runs: dict[str, list[dict]] = defaultdict(list)
    for value in run_values:
        grouped_runs[value["prompt_hash"]].append(value)
    grouped_versions: dict[str, list[dict]] = defaultdict(list)
    for value in versions:
        grouped_versions[value["prompt"]["hash"]].append(value)
    grouped_ratings: dict[str, list[dict]] = defaultdict(list)
    for value in global_ratings:
        grouped_ratings[value.get("prompt_hash") or "unbound"].append(value)

    keys = set(grouped_versions) | set(grouped_runs) | set(grouped_ratings)
    paths: list[Path] = []
    for key in sorted(keys):
        page = prompt_page(
            key,
            grouped_versions.get(key, []),
            grouped_runs.get(key, []),
            grouped_ratings.get(key, []),
            historical=key not in grouped_versions and key != "unbound",
        )
        path = report_dir / f"prompt-{key}.md"
        path.write_text(page)
        paths.append(path)
    index = _write_index(paths, report_dir)
    summary = {
        "runs": len(run_values),
        "failed": sum(1 for value in run_values if not value["ok"]),
        "current_prompts": len(grouped_versions),
        "reports": [str(path) for path in paths],
        "index": str(index),
    }
    summary["strict"] = bool(strict)
    return paths, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=RUNS, help="directory of run bundles")
    parser.add_argument("--reports", type=Path, default=REPORTS, help="output directory")
    parser.add_argument(
        "--ratings",
        type=Path,
        default=None,
        help="optional exported work/ratings.jsonl to include by prompt hash",
    )
    parser.add_argument("--strict", action="store_true", help="exit 1 if a run fails")
    args = parser.parse_args(argv)
    paths, summary = run(
        runs_dir=args.runs,
        report_dir=args.reports,
        ratings_path=args.ratings,
        strict=args.strict,
    )
    print(
        f"{summary['current_prompts']} current prompt versions, "
        f"{summary['runs']} stored runs, {summary['failed']} failing."
    )
    for path in paths:
        print(path)
    print(summary["index"])
    return 1 if args.strict and summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
