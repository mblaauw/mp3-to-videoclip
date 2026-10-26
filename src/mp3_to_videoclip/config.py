"""User settings: one TOML file, never committed into a production folder.

Secrets live in the OS keychain when ``keyring`` is installed and fall back to
the file otherwise. Every value has a neutral default so a fresh clone boots.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseModel):
    runware_api_key: str = ""
    gateway: Literal["opencode", "direct"] = "direct"
    opencode_bin: str = "opencode"
    writer_model: str = "openai/gpt-6.1-sol"
    editor_model: str = "opencode-go/deepseek-v4.1-flash"
    opencode_workspace: str = ""
    llm_base_url: str = "https://opencode.ai/inference/go/openai/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4.1-flash"
    brand_name: str = "MAHA KALA"
    brand_partner: str = "VJDJ69"
    default_budget_usd: float = Field(default=5.0, ge=0)
    image_reserve_usd: float = Field(default=0.05, ge=0.01, le=10.0)
    default_credit_roles: list[str] = Field(
        default_factory=lambda: ["director", "music", "visuals"]
    )
    remotion_dir: str = ""
    ffmpeg_path: str = ""


def settings_path() -> Path:
    return Path.home() / ".config" / "mp3-to-videoclip" / "settings.toml"


def load_settings() -> Settings:
    path = settings_path()
    if not path.is_file():
        return Settings(
            runware_api_key=os.environ.get("PROJECT_VEIL_RUNWARE_API", ""),
            llm_api_key=os.environ.get("OPENAI_API_KEY", ""),
        )
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return Settings(**data.get("settings", {}))


def save_settings(settings: Settings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[settings]"]
    for key, value in settings.model_dump().items():
        if isinstance(value, list):
            lines.append(f"{key} = {value!r}".replace("'", '"'))
        elif isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        elif isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        else:
            lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n")


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")
    project_veil_runware_api: str = ""
    openai_api_key: str = ""


def effective_settings() -> Settings:
    settings = load_settings()
    env = EnvSettings()
    if not settings.runware_api_key and env.project_veil_runware_api:
        settings.runware_api_key = env.project_veil_runware_api
    if not settings.llm_api_key and env.openai_api_key:
        settings.llm_api_key = env.openai_api_key
    return settings
