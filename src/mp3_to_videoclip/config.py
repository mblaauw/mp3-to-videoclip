"""User settings: one TOML file, never committed into a production folder.

Saved keys are plain text in this file, which only the owner can read. Every value
has a neutral default so a fresh clone boots.

Schema 2 is nested by what a value is for. The old flat names stay readable as
properties, so a caller never has to know the difference, and an old file or a flat
keyword is accepted by moving each value to its new home.
"""

from __future__ import annotations

import copy
import os
import shutil
import tomllib
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SCHEMA_VERSION = 2
Thinking = Literal["off", "low", "medium", "high"]


def split_model(value: str) -> dict[str, str]:
    """``provider/model`` as stored by OpenCode; a bare id has no provider."""
    provider, slash, model = value.partition("/")
    return {"provider": provider, "model": model} if slash else {"provider": "", "model": value}


class Role(BaseModel):
    provider: str = ""
    model: str = ""
    thinking: Thinking = "medium"
    max_tokens_per_turn: int = Field(default=0, ge=0)

    @property
    def qualified(self) -> str:
        return f"{self.provider}/{self.model}" if self.provider else self.model


class Roles(BaseModel):
    writer: Role = Role(provider="openai", model="gpt-6.1-sol")
    editor: Role = Role(provider="opencode-go", model="deepseek-v4.1-flash")
    critic: Role = Role(provider="openai", model="gpt-6.1-sol")
    narrator: Role = Role(provider="runware", model="minimax-speech-2-8")


class Voices(BaseModel):
    provider: str = "runware"
    default_voice: str = "English_Magnetic_Male_2"
    favourites: list[str] = []


class Pictures(BaseModel):
    image_model_by_look: dict[str, str] = {}
    video_model: str = ""
    upscaler: str = ""
    reserve_usd_per_still: float = Field(default=0.05, ge=0.01, le=10.0)
    reserve_usd_per_clip_second: float = Field(default=0.10, ge=0.01, le=10.0)


class DirectEndpoint(BaseModel):
    """The one endpoint and model the direct path answers with until Phase E1."""

    key: str = ""
    base_url: str = "https://opencode.ai/inference/go/openai/v1"
    model: str = "deepseek-v4.1-flash"


class Keys(BaseModel):
    runware: str = ""
    openai_compatible: DirectEndpoint = DirectEndpoint()
    anthropic: str = ""
    gemini: str = ""
    opencode_go: str = ""
    elevenlabs: str = ""


class Brand(BaseModel):
    name: str = "MAHA KALA"
    partner: str = "VJDJ69"
    logo: str = ""
    palette: list[str] = []
    font: str = ""


class NewFilms(BaseModel):
    kind: str = "music_video"
    length_s: float = Field(default=0.0, ge=0)
    aspect: str = "16:9"
    fps: int = Field(default=24, ge=1)
    look: str = ""
    budget_usd: float = Field(default=5.0, ge=0)
    signature_package: bool = True
    credit_roles: list[str] = ["director", "music", "visuals"]
    brand: Brand = Brand()


class Computer(BaseModel):
    opencode_bin: str = "opencode"
    opencode_workspace: str = ""
    gateway: Literal["opencode", "direct"] = "direct"


#: Where each name of the flat schema 1 file lives now.
FLAT: dict[str, tuple[str, ...]] = {
    "runware_api_key": ("keys", "runware"),
    "gateway": ("computer", "gateway"),
    "opencode_bin": ("computer", "opencode_bin"),
    "opencode_workspace": ("computer", "opencode_workspace"),
    "llm_base_url": ("keys", "openai_compatible", "base_url"),
    "llm_api_key": ("keys", "openai_compatible", "key"),
    "llm_model": ("keys", "openai_compatible", "model"),
    "brand_name": ("new_films", "brand", "name"),
    "brand_partner": ("new_films", "brand", "partner"),
    "default_budget_usd": ("new_films", "budget_usd"),
    "default_credit_roles": ("new_films", "credit_roles"),
    "image_reserve_usd": ("pictures", "reserve_usd_per_still"),
}
FLAT_ROLES = {"writer_model": "writer", "editor_model": "editor", "critic_model": "critic"}


def _set(target: dict, path: tuple[str, ...], value: Any) -> None:
    for part in path[:-1]:
        target = target.setdefault(part, {})
    target[path[-1]] = value


def merge(base: dict, patch: dict) -> dict:
    """A deep copy of ``base`` with ``patch`` laid over it, table by table."""
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class Settings(BaseModel):
    schema_version: int = SCHEMA_VERSION
    roles: Roles = Roles()
    voices: Voices = Voices()
    pictures: Pictures = Pictures()
    keys: Keys = Keys()
    new_films: NewFilms = NewFilms()
    prices: dict[str, str] = {}
    computer: Computer = Computer()

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_names(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = copy.deepcopy(data)
        for name, path in FLAT.items():
            if name in data:
                _set(data, path, data.pop(name))
        for name, role in FLAT_ROLES.items():
            if name in data:
                _set(data, ("roles", role, "provider"), split_model(data[name])["provider"])
                _set(data, ("roles", role, "model"), split_model(data.pop(name))["model"])
        return data

    @property
    def runware_api_key(self) -> str:
        return self.keys.runware

    @property
    def gateway(self) -> str:
        return self.computer.gateway

    @property
    def opencode_bin(self) -> str:
        return self.computer.opencode_bin

    @property
    def writer_model(self) -> str:
        return self.roles.writer.qualified

    @property
    def editor_model(self) -> str:
        return self.roles.editor.qualified

    @property
    def critic_model(self) -> str:
        return self.roles.critic.qualified

    @property
    def opencode_workspace(self) -> str:
        return self.computer.opencode_workspace

    @property
    def llm_base_url(self) -> str:
        return self.keys.openai_compatible.base_url

    @property
    def llm_api_key(self) -> str:
        return self.keys.openai_compatible.key

    @property
    def llm_model(self) -> str:
        return self.keys.openai_compatible.model

    @property
    def brand_name(self) -> str:
        return self.new_films.brand.name

    @property
    def brand_partner(self) -> str:
        return self.new_films.brand.partner

    @property
    def default_budget_usd(self) -> float:
        return self.new_films.budget_usd

    @property
    def image_reserve_usd(self) -> float:
        return self.pictures.reserve_usd_per_still


def settings_path() -> Path:
    return Path.home() / ".config" / "mp3-to-videoclip" / "settings.toml"


def _read(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_settings() -> Settings:
    path = settings_path()
    if not path.is_file():
        return Settings(
            runware_api_key=os.environ.get("PROJECT_VEIL_RUNWARE_API", ""),
            llm_api_key=os.environ.get("OPENAI_API_KEY", ""),
        )
    data = _read(path)
    return Settings(**(data if "schema_version" in data else data.get("settings", {})))


def _keep_old_file(path: Path) -> None:
    """Copy a schema 1 file aside once, before the first save replaces it."""
    backup = path.with_name(path.name + ".v1.bak")
    if backup.exists() or not path.is_file() or "schema_version" in _read(path):
        return
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)


def save_settings(settings: Settings) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _keep_old_file(path)
    # Written private and swapped in, because this file can hold API keys.
    temporary = path.with_suffix(".toml.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        tomli_w.dump(settings.model_dump(), handle)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


class EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")
    project_veil_runware_api: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    opencode_api_key: str = ""
    elevenlabs_api_key: str = ""


def effective_settings() -> Settings:
    """The file first; the environment only fills a key the file does not have."""
    settings = load_settings()
    env = EnvSettings()
    keys = settings.keys
    keys.runware = keys.runware or env.project_veil_runware_api
    keys.openai_compatible.key = keys.openai_compatible.key or env.openai_api_key
    keys.anthropic = keys.anthropic or env.anthropic_api_key
    keys.gemini = keys.gemini or env.gemini_api_key
    keys.opencode_go = keys.opencode_go or env.opencode_api_key
    keys.elevenlabs = keys.elevenlabs or env.elevenlabs_api_key
    return settings
