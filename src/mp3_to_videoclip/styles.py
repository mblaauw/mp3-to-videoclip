"""Style presets: one Markdown file per look, with a small JSON-valued header.

The photographic-painted preset keeps the approved core verbatim and is the only
protected preset. Other presets are ordinary choices, not a mandatory prefix.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPTS = Path(__file__).resolve().parent / "director" / "prompts" / "styles"
DEFAULT_PRESET = "clean-photographic-v1"


@dataclass(frozen=True)
class StylePreset:
    id: str
    name: str
    description: str
    look: str
    image_rules: tuple[str, ...]
    model: str | None
    settings: dict
    protected: bool
    version: int

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "protected": self.protected,
            "look": self.look,
            "image_rules": list(self.image_rules),
            "model": self.model,
            "settings": self.settings,
        }


def _value(raw: str):
    raw = raw.strip()
    if not raw:
        return ""
    if raw[0] in '[{"0123456789' or raw in ("true", "false", "null"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw


def _parse(path: Path) -> StylePreset:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"{path.name}: style preset needs a --- header")
    try:
        header, look = text[4:].split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError(f"{path.name}: style preset header is not closed") from exc
    meta: dict = {}
    for line in header.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, raw = line.partition(":")
        if not separator:
            raise ValueError(f"{path.name}: malformed header line {line!r}")
        meta[key.strip()] = _value(raw)
    look = look.strip()
    rules = meta.get("image_rules", [])
    if not isinstance(rules, list) or not all(
        isinstance(item, str) and item.strip() for item in rules
    ):
        raise ValueError(f"{path.name}: image_rules must be a JSON list of strings")
    if not isinstance(meta.get("id"), str) or not meta["id"]:
        raise ValueError(f"{path.name}: id is required")
    if not isinstance(meta.get("name"), str) or not meta["name"]:
        raise ValueError(f"{path.name}: name is required")
    if not look:
        raise ValueError(f"{path.name}: look text is required")
    return StylePreset(
        id=meta["id"],
        name=meta["name"],
        description=str(meta.get("description", "")),
        look=look,
        image_rules=tuple(rules),
        model=meta.get("model") or None,
        settings=meta.get("settings") if isinstance(meta.get("settings"), dict) else {},
        protected=meta.get("protected") is True,
        version=int(meta.get("version", 1)),
    )


@lru_cache(maxsize=1)
def presets() -> tuple[StylePreset, ...]:
    values = tuple(_parse(path) for path in sorted(PROMPTS.glob("*.md")))
    if not values:
        raise ValueError("no style presets found")
    ids = [value.id for value in values]
    if len(set(ids)) != len(ids):
        raise ValueError("style preset IDs must be unique")
    return values


def preset(preset_id: str) -> StylePreset:
    for value in presets():
        if value.id == preset_id:
            return value
    raise ValueError(f"unknown style preset {preset_id!r}")


def default_for(kind: str | None) -> StylePreset:
    from . import kinds

    return preset(kinds.get(kind).default_style)


def public_presets() -> list[dict]:
    return [value.public() for value in presets()]


def protected_preset(preset_id: str | None) -> StylePreset | None:
    if not preset_id:
        return None
    try:
        value = preset(preset_id)
    except ValueError:
        return None
    return value if value.protected else None


def core_problem(preset_id: str | None, look: str) -> str | None:
    """Return why a protected look was edited, or None when it is intact."""
    guarded = protected_preset(preset_id)
    if guarded is None:
        return None
    if look != guarded.look and not look.startswith(guarded.look + "\n\n"):
        return (
            "preserve the approved DEFAULT_STYLE core verbatim at the start of "
            "creative.look; append film-specific look after a blank line, or "
            "choose a custom/other preset"
        )
    return None
