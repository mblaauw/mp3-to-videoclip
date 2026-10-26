"""Cross-review rubric: a signal from the other role, never an automatic gate."""

from __future__ import annotations

RUBRIC_ID = "cross-review-v1"
ROLES = ("writer", "editor")
QUESTIONS = (
    {
        "id": "routes",
        "label": "Distinct routes",
        "question": (
            "Are the three routes structurally different, rather than one film "
            "with three grades or three versions of the same shot list?"
        ),
    },
    {
        "id": "jobs",
        "label": "Every shot has a job",
        "question": (
            "Does every shot have one thing it must communicate, and would the "
            "film lose something real if it were removed?"
        ),
    },
    {
        "id": "rhythm",
        "label": "Rhythm and technique",
        "question": (
            "Do cuts, holds, motion, transitions and accents follow the music and "
            "the intended feeling, with every non-cut join justified?"
        ),
    },
    {
        "id": "truth",
        "label": "Truth and claims",
        "question": (
            "Does every claim, date, price, URL, lyric and character fact trace "
            "to the supplied intent or evidence?"
        ),
    },
)
IDS = tuple(question["id"] for question in QUESTIONS)
SCALE = (1, 5)


def normalise(value: dict, run_role: str) -> dict:
    """Validate one other-role review and return a stable shape."""
    if not isinstance(value, dict):
        raise ValueError("cross_review must be a JSON object")
    reviewer = value.get("reviewer_role")
    if reviewer not in ROLES:
        raise ValueError("cross_review.reviewer_role must be writer or editor")
    if run_role in ROLES and reviewer == run_role:
        raise ValueError("cross-review must come from the other role")
    scores = value.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("cross_review.scores must be an object")
    missing = [key for key in IDS if key not in scores]
    if missing:
        raise ValueError("cross_review is missing scores: " + ", ".join(missing))
    clean = {}
    for key in IDS:
        score = scores[key]
        if (
            isinstance(score, bool)
            or not isinstance(score, int)
            or not SCALE[0] <= score <= SCALE[1]
        ):
            raise ValueError(f"cross_review.scores.{key} must be an integer 1–5")
        clean[key] = score
    notes = value.get("notes", "")
    if not isinstance(notes, str):
        raise ValueError("cross_review.notes must be text")
    return {
        "rubric": RUBRIC_ID,
        "reviewer_role": reviewer,
        "run_role": run_role,
        "scores": clean,
        "notes": notes.strip(),
    }


def summarise(values: list[dict]) -> dict:
    if not values:
        return {
            "rubric": RUBRIC_ID,
            "count": 0,
            "overall": None,
            "scores": {key: None for key in IDS},
            "reviews": [],
        }
    scores = {
        key: round(sum(value["scores"][key] for value in values) / len(values), 2) for key in IDS
    }
    overall = round(sum(scores.values()) / len(scores), 2)
    return {
        "rubric": RUBRIC_ID,
        "count": len(values),
        "overall": overall,
        "scores": scores,
        "reviews": values,
    }


def prompt(reviewer_role: str, run_role: str) -> str:
    """A copyable prompt for the other role; the runner never sends it itself."""
    if reviewer_role not in ROLES:
        raise ValueError("reviewer_role must be writer or editor")
    if reviewer_role == run_role:
        raise ValueError("the cross-reviewer must be the other role")
    questions = "\n".join(
        f"- `{question['id']}` ({question['label']}): {question['question']}"
        for question in QUESTIONS
    )
    return (
        f"You are the {reviewer_role} reviewing the {run_role}'s artifacts as a peer, "
        "not as the owner. Score each question from 1 (fails) to 5 (excellent).\n\n"
        f"{questions}\n\n"
        "Return only a JSON object with this shape:\n"
        '{"reviewer_role": "%s", "scores": {"routes": 1, "jobs": 1, "rhythm": 1, '
        '"truth": 1}, "notes": "one short paragraph"}\n' % reviewer_role
    )


def markdown_table(summary: dict) -> str:
    if summary["count"] == 0:
        return "No cross-review recorded."
    rows = [
        f"| {question['label']} | {summary['scores'][question['id']]} / 5 |"
        for question in QUESTIONS
    ]
    return "\n".join(
        [
            f"Cross-review `{summary['rubric']}` from {summary['count']} review"
            f"{'s' if summary['count'] != 1 else ''}; overall **{summary['overall']} / 5**.",
            "",
            "| Rubric | Score |",
            "| --- | --- |",
            *rows,
        ]
    )
