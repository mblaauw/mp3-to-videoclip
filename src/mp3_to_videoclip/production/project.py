"""Where a film lives: its stages, its project record and its audio."""

from datetime import UTC, datetime
from pathlib import Path

from .. import kinds
from ..models import (
    Project,
)
from ..storage import (
    file_hash,
    inside,
    read_json,
    snapshot_read,
)

STAGE_FILES = {
    "analysis": "work/music.json",
    "lyrics": "work/lyrics.json",
    "events": "work/events.json",
    "brief": "brief.json",
    "storyboard": "work/storyboard.json",
    "preview": "work/preview-review.json",
    "listening": "work/music-listening.json",
    "brand": "brand.json",
    "graphics": "work/graphics-review.json",
}
UPSTREAM = {
    "analysis": None,
    "lyrics": "analysis",
    "events": "analysis",
    "listening": "analysis",
    "brand": "analysis",
    "brief": "lyrics",
    "storyboard": "brief",
    "proof": "storyboard",
    "preview": "proof",
    "stills": "proof",
    "graphics": "stills",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


@snapshot_read
def load_project(root: Path, verify_source=True) -> Project:
    project = Project.model_validate(read_json(root / "project.json"))
    if verify_source and file_hash(inside(root, project.source)) != project.source_sha256:
        raise ValueError("copied source changed; create a new production instead")
    return project


def creative_workflow(project: Project) -> bool:
    """The guided creative workflow, whether recorded as v2 or as schema 3.

    Schema 3 is the migrated/native form of workflow 2: creative profile, resolved
    character state, bound references, accepted image reviews. Schema-1 projects
    without the v2 marker keep their historical legacy behaviour.
    """
    return project.workflow_version == 2 or project.schema_version == 3


def requires_signature(root: Path, project: Project | None = None) -> bool:
    """Whether delivery needs the graphics signature pass.

    The recorded flag is authoritative. A migrated schema-3 production may have
    lost it; its graphics spec proves the film was authored with a signature, so
    a missing flag must never silently turn a base into a delivery render.
    """
    project = project or load_project(root)
    if project.signature_required is not None:
        return project.signature_required
    if project.kind is not None:
        return kinds.get(project.kind).signature_required
    return project.schema_version == 3 and (root / "work" / "graphics-spec.json").is_file()


def prompt_look_first(project: Project) -> bool:
    """The v2 prompt layout puts the global look before the shot text."""
    return project.prompt_version == 2 or project.schema_version == 3


def project_payload(project: Project) -> dict:
    """Legacy projects never serialized ``music_mode``; keep their hashes stable."""
    value = project.model_dump()
    # Backend choice cannot change measured music or generation inputs. Render
    # receipts/previews bind it explicitly with the implementation revision.
    value.pop("renderer_backend", None)
    # The cap and its top-up history are administrative: adding budget must not
    # invalidate a creative approval.
    value.pop("budget", None)
    if value.get("music_mode") is None:
        value.pop("music_mode", None)
    return value


def render_audio(root: Path, project: Project | None = None) -> Path:
    """The excerpt for a promo/advert, or the original for a music video."""
    from .. import audio

    return audio.render_audio(root, project or load_project(root))
