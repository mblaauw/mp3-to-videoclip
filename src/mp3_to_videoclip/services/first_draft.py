"""One authorised click to a watchable first draft: story, board, three stills, a cut.

Everything it approves says so (``via: "draft"``), and only the brief, the storyboard and the proof
can be. It spends inside the owner's one authorisation: at most three stills out of its reserve, and
a ceiling on model use checked before every turn. It stops, and says why, at anything a person has
to decide.
"""

from __future__ import annotations

import asyncio
from contextlib import aclosing
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from mp3_to_videoclip import operations
from mp3_to_videoclip import production as P
from mp3_to_videoclip.config import effective_settings
from mp3_to_videoclip.director import prompts as prompt_suite
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.director.llm import DirectorLLM
from mp3_to_videoclip.director.loop import run_turn
from mp3_to_videoclip.director.routing import route_for
from mp3_to_videoclip.storage import read_json, read_optional

CEILING_USD = Decimal("1.00")
STILLS_RESERVE_USD = Decimal("0.20")
RESERVE_PER_STILL = "0.05"
MAX_STILLS = 3
#: No text model has a verified price yet, so the model allowance is counted in tokens too.
MODEL_ALLOWANCE_USD = CEILING_USD - STILLS_RESERVE_USD
MAX_MODEL_TOKENS = 400_000
MAX_TURN_CALLS = 12
DRAFTING = (
    "You are making a first draft on your own. The cast is invented and fictional. Don't ask the "
    "owner anything: choose, say what you chose in a line, and move on. "
)
STEPS = (
    ("concepts", "Write one concept with update_treatments, choose it, and save its treatment."),
    (None, "Write the script for the chosen concept with update_brief."),
    ("profile", "Build the creative profile with set_creative_profile."),
    ("storyboard", "Make the storyboard and fill every shot; set three proof shots."),
    ("prompts", "Check every paid shot's image prompt and fix any that is not ready."),
)


class DraftStopped(Exception):
    """A person has to decide something, or the allowance is spent. Nothing here is a failure."""


def plan() -> dict:
    """What the dialog shows before anything starts."""
    return {
        "ceiling_usd": str(CEILING_USD),
        "stills_usd": str(STILLS_RESERVE_USD),
        "stills": MAX_STILLS,
        "model_usd": str(MODEL_ALLOWANCE_USD),
        "model_tokens": MAX_MODEL_TOKENS,
    }


def _used_tokens(root: Path, since: int) -> tuple[int, Decimal]:
    from mp3_to_videoclip.director import usage

    tokens = spent = 0
    total = Decimal(0)
    rows = usage.rows(root)[since:]
    for row in rows:
        tokens += int(row.get("prompt_tokens") or 0) + int(row.get("completion_tokens") or 0)
        if row.get("cost_usd") is not None:
            total += Decimal(str(row["cost_usd"]))
    return tokens + spent, total


def _check_allowance(root: Path, since: int) -> None:
    tokens, spent = _used_tokens(root, since)
    if tokens >= MAX_MODEL_TOKENS or spent >= MODEL_ALLOWANCE_USD:
        raise DraftStopped("The first draft used its model allowance and stopped here.")


async def _turn(
    root: Path, slug: str, role: str, task: str | None, message: str, stage: str, runner
) -> None:
    settings = effective_settings()
    route = route_for(settings, role)
    if not route.key:
        raise DraftStopped(f"The {role} has no key for {route.model}. Add one in Settings.")
    project = P.load_project(root, verify_source=False)
    bundle = prompt_suite.assemble(
        root, stage, role=role, kind=project.kind, style_preset=project.style_preset, task=task
    )
    snapshot = build_context(slug, root.parent, stage=stage, task=bundle.task)
    llm = DirectorLLM(
        base_url=route.base_url,
        api_key=route.key,
        model=route.model,
        kind=route.kind,
        session_id=f"draft-{slug}-{role}",
    )
    async with aclosing(
        run_turn(
            llm,
            root,
            slug,
            DRAFTING + message,
            bundle.text + "\n\n---\n\n" + snapshot,
            max_tool_calls=MAX_TURN_CALLS,
            runner=runner,
            projects_dir=root.parent,
            prompt_meta={**bundle.meta, "provider": route.provider, "model": route.model},
            role=role,
            provider=route.provider,
        )
    ) as events:
        async for event in events:
            if event.kind == "ask":
                raise DraftStopped(
                    f"The {role} needs an answer: {event.payload.get('question', '')}"
                )
            if event.kind == "done" and (event.payload or {}).get("error"):
                raise DraftStopped(str(event.payload["error"]))


def _names_to_protect(root: Path) -> set[str]:
    """People who may be real: the brand, the credits and whoever the owner named in their words."""
    settings = effective_settings().new_films.brand
    names = {settings.name, settings.partner}
    spec = read_optional(root / "work/graphics-spec.json") or {}
    for card in (spec.get("credits") or {}).get("cards") or []:
        names.add(str(card[-1]))
    brief = P.load_brief(root)
    if brief.intent is not None:
        names.update(word for word in brief.intent.about.split() if word[:1].isupper())
    idea = read_optional(root / "work/idea.json") or {}
    names.update(word for word in str(idea.get("paste") or "").split() if word[:1].isupper())
    return {name.strip(" .,;:").casefold() for name in names if name.strip()}


def confirm_invented_cast(root: Path) -> None:
    """The owner's dialog said the cast is invented; only those characters take its word."""
    brief = P.load_brief(root)
    protected = _names_to_protect(root)
    characters = []
    for character in brief.characters:
        if not character.permission_confirmed:
            says = character.id.replace("-", " ").replace("_", " ").casefold().split()
            if character.references or not character.identity or protected & {*says, character.id}:
                raise DraftStopped(f"Confirm {character.id} on Story's Characters card.")
        characters.append({**character.model_dump(), "permission_confirmed": True})
    if characters:
        P.update_brief(root, {"characters": characters}, owner=True)


def _approve(root: Path, stage: str, job_id: str) -> None:
    route = route_for(effective_settings(), "writer")
    P.approve(
        root,
        stage,
        "first draft, not reviewed by the owner",
        via="draft",
        drafted_by={"role": "writer", "model": route.model, "job_id": job_id},
    )


def _buy_proof(root: Path, client=None) -> list[str]:
    from mp3_to_videoclip import budget
    from mp3_to_videoclip import generation as G

    board = P.load_board(root)
    ids = P.proof_ids(board, P.load_brief(root))[:MAX_STILLS]
    quote = G.quote_images(root, "proof", RESERVE_PER_STILL, ids=ids, client=client)
    total = Decimal(quote["reserve_total_usd"])
    if total > STILLS_RESERVE_USD:
        raise DraftStopped(f"Three stills would reserve ${total}, more than this draft allows.")
    if G.quote_uploads_required(quote):
        raise DraftStopped("These stills would upload reference images; that needs you to agree.")
    budget.check_capacity(root, str(total), context="authorization")
    G.authorize(root, quote["id"], str(total), "first draft dialog: the owner's one authorisation")
    G.generate(root, quote["id"], client=client)
    return [task["shot_id"] for task in quote["tasks"]]


async def run(root: Path, *, job_id: str | None = None, runner=None, image_client=None) -> dict:
    """The whole draft. ``DraftStopped`` is reported as where it stopped, never as a crash."""
    from mp3_to_videoclip import edits, first_cut
    from mp3_to_videoclip.director import usage
    from mp3_to_videoclip.services import render

    root = Path(root)
    slug = root.name
    job_id = job_id or uuid4().hex
    since = len(usage.rows(root))
    if P.load_project(root, verify_source=False).spine == "soundtrack":
        return {"stopped": "A story film starts from its script; a first draft is for a song."}
    done: list[str] = []

    async def step(name: str, role: str, task: str | None, message: str, stage: str):
        if operations.stop_requested():
            raise DraftStopped("Stopped by you.")
        _check_allowance(root, since)
        operations.phase(f"draft-{name}")
        await _turn(root, slug, role, task, message, stage, runner)
        done.append(name)

    try:
        for task, message in STEPS:
            project_kind = P.load_project(root, verify_source=False).kind or "music_video"
            named = task or ("script_mv" if project_kind == "music_video" else "script_ad")
            if named == "storyboard":
                confirm_invented_cast(root)
                _approve(root, "brief", job_id)
            stage = "storyboard" if named in ("storyboard", "prompts") else "story"
            await step(named, "writer", named, message, stage)
        _approve(root, "storyboard", job_id)
        if operations.stop_requested():
            raise DraftStopped("Stopped by you.")
        operations.phase("draft-proof")
        done.extend(
            f"still {shot}" for shot in await asyncio.to_thread(_buy_proof, root, image_client)
        )
        _approve(root, "proof", job_id)
        edits.seed_edit(root)
        edits.save_edit(root, first_cut.suggest(root)["edit"])
        report = edits.report(root)
        if report.get("hard"):
            await step(
                "fix-cut",
                "editor",
                "edit",
                "The report has hard findings. Fix them with update_edit_shots.",
                "film",
            )
            if edits.report(root).get("hard"):
                raise DraftStopped("The cut has a problem that one more try did not fix.")
        operations.phase("draft-preview")
        preview = await asyncio.to_thread(render.render_preview, root)
    except DraftStopped as stopped:
        return {"stopped": str(stopped), "done": done}
    return {"done": done, "preview": str(preview.get("output"))}


def drafted_stages(root: Path) -> list[str]:
    approvals = read_json(root / "work/approvals.json")
    return [stage for stage, row in approvals.items() if (row or {}).get("via") == "draft"]
