"""OpenCode v2 gateway: app-owned process, client and event relay.

The Studio owns this gateway. It runs ``opencode serve`` from a dedicated
workspace with a generated Basic-auth password, a pinned 2.0.x version, a
Studio-only agent config and the local ``clipstudio`` MCP server. No process is
started unless the caller asks for it.

The event relay maps OpenCode's SSE vocabulary onto the Studio's existing
``TurnEvent`` stream, so the chat API and UI keep one shape regardless of
whether the direct OpenAI-compatible adapter or the gateway is in use.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from mp3_to_videoclip.storage import read_optional, write_json

from .conversation import append_message
from .llm import IDLE_LIMIT, NOTHING_LOST, stall_message
from .loop import TurnEvent

WRITER_MODEL = "openai/gpt-6.1-sol"
EDITOR_MODEL = "opencode-go/deepseek-v4.1-flash"
MIN_VERSION = (2, 1, 4)
MAX_VERSION = (2, 2, 0)
HEALTH_TIMEOUT = 20.0
STOP_GRACE = 5.0
WARMUP_DELAY = 0.5
TURN_LIMIT = 900.0
# The event stream opens a tool's arguments and then says nothing until they are
# complete, so an open tool call gets longer than the plain silence limit.
TOOL_INPUT_IDLE_LIMIT = 300.0

WRITER_SYSTEM = (
    "You are the Studio Writer: concepts, scripts, storyboards, shot prompts and "
    "image review. Read the project snapshot in the user message first. Use only "
    "the clipstudio_* tools for project state; never invent a shot, approval or "
    "asset. Never call execute, browser, opencode or any built-in tool. Read before "
    "writing, keep every other field intact, and use clipstudio_get_images before "
    "judging a still. If the user must decide, ask one focused question."
)
EDITOR_SYSTEM = (
    "You are the Studio Editor: music map, cut plan, transitions, text timing and "
    "the post pass. Read the project snapshot in the user message first. Use only "
    "the clipstudio_* tools for project state; never call execute, browser, "
    "opencode or any built-in tool. Every cut must have a musical or narrative "
    "reason; never invent a measurement or an asset."
)


class OpenCodeError(RuntimeError):
    """A gateway failure with a message the Studio can show the user."""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _version(value: str) -> tuple[int, int, int]:
    parts = value.strip().split(".")
    try:
        numbers = [int(part) for part in parts[:3]]
    except ValueError as exc:
        raise OpenCodeError(f"cannot read OpenCode version {value!r}") from exc
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers)  # type: ignore[return-value]


def parse_model(value: str) -> tuple[str, str, str | None]:
    """Split ``provider/model#variant`` into the gateway's model reference."""
    if "/" not in value:
        raise OpenCodeError("model must be provider/model")
    provider, rest = value.split("/", 1)
    model, _, variant = rest.partition("#")
    if not provider or not model:
        raise OpenCodeError("model must be provider/model")
    return provider, model, variant or None


def _binary_version(binary: str) -> tuple[int, int, int] | None:
    try:
        result = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout + result.stderr)
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def discover_binary(configured: str, search_roots=None) -> str:
    """Prefer a supported binary; otherwise fall back to the configured one.

    The desktop app ships its CLI outside PATH, and the 2.0.x line fails the
    Writer model with an auto-compaction error. A configured path wins when it
    is already in the verified range; the desktop CLI is the next candidate.
    """
    if search_roots is None:
        search_roots = (Path.home() / "Library/Application Support/ai.opencode.desktop/cli",)
    candidates: list[str] = []
    if Path(configured).is_file():
        candidates.append(configured)
    else:
        found = shutil.which(configured)
        if found:
            candidates.append(found)
    for root in search_roots:
        root = Path(root)
        if root.is_dir():
            candidates.extend(
                str(path) for path in sorted(root.glob("*/opencode-cli"), reverse=True)
            )
    for candidate in candidates:
        version = _binary_version(candidate)
        if version is not None and MIN_VERSION <= version < MAX_VERSION:
            return candidate
    return configured


def gateway_workspace() -> Path:
    return Path.home() / ".local" / "share" / "mp3-to-videoclip" / "opencode"


def gateway_config(
    *,
    projects_dir: Path,
    writer_model: str = WRITER_MODEL,
    editor_model: str = EDITOR_MODEL,
    python: str | None = None,
) -> dict[str, Any]:
    """The app-owned config. Built-in tools are denied, Studio MCP tools allowed."""
    executable = python or sys.executable
    projects_dir = Path(projects_dir).resolve()
    # A blanket "*" deny is a hard deny on 2.1.x and overrides the later allow,
    # so the built-in actions are denied one by one.
    builtin_actions = (
        "read",
        "edit",
        "shell",
        "glob",
        "grep",
        "webfetch",
        "websearch",
        "skill",
        "subagent",
        "question",
        "external_directory",
        "execute",
    )
    permissions = [
        *({"action": action, "resource": "*", "effect": "deny"} for action in builtin_actions),
        {"action": "clipstudio_*", "resource": "*", "effect": "allow"},
    ]
    return {
        "$schema": "https://opencode.ai/config.json",
        "default_agent": "writer",
        "agents": {
            "writer": {
                "description": "Studio Writer: concepts, scripts, storyboards, prompts.",
                "mode": "primary",
                "model": writer_model,
                "system": WRITER_SYSTEM,
                "permissions": permissions,
            },
            "editor": {
                "description": "Studio Editor: music map, cut plan, post pass.",
                "mode": "primary",
                "model": editor_model,
                "system": EDITOR_SYSTEM,
                "permissions": permissions,
            },
        },
        "mcp": {
            "servers": {
                "clipstudio": {
                    "type": "local",
                    "command": [
                        executable,
                        "-m",
                        "mp3_to_videoclip.director.mcp",
                        "--projects-dir",
                        str(projects_dir),
                    ],
                    "environment": {
                        "PYTHONPATH": str(Path(__file__).resolve().parents[3]),
                    },
                    "protocol": "legacy",
                    "codemode": False,
                }
            }
        },
    }


class OpenCodeClient:
    """Small async client for the endpoints the Studio actually uses."""

    def __init__(self, base_url: str, password: str, *, timeout: float = 60.0):
        auth = httpx.BasicAuth("opencode", password)
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=auth,
            timeout=httpx.Timeout(timeout, connect=5.0),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def info(self) -> dict[str, Any]:
        response = await self._client.get("/api/info")
        response.raise_for_status()
        return response.json()

    async def create_session(self, *, title: str, agent: str) -> str:
        response = await self._client.post("/api/session", json={"title": title, "agent": agent})
        response.raise_for_status()
        return response.json()["data"]["id"]

    async def delete_session(self, session_id: str) -> None:
        response = await self._client.delete(f"/api/session/{session_id}")
        response.raise_for_status()

    async def prompt(self, session_id: str, text: str, files: list[dict] | None = None) -> dict:
        body: dict[str, Any] = {"text": text}
        if files:
            body["files"] = files
        response = await self._client.post(f"/api/session/{session_id}/prompt", json=body)
        response.raise_for_status()
        return response.json()

    async def interrupt(self, session_id: str) -> dict:
        response = await self._client.post(
            f"/api/session/{session_id}/interrupt", params={"resume": "false"}
        )
        response.raise_for_status()
        return response.json()

    async def messages(self, session_id: str, *, limit: int = 50) -> list[dict]:
        response = await self._client.get(
            f"/api/session/{session_id}/message", params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()["data"]

    async def models(self) -> list[dict]:
        response = await self._client.get("/api/model")
        response.raise_for_status()
        return response.json()["data"]

    async def mcp_servers(self) -> list[dict]:
        response = await self._client.get("/api/mcp")
        response.raise_for_status()
        return response.json()["data"]

    async def wait_for_mcp(self, name: str = "clipstudio", timeout: float = 15.0) -> None:
        """Wait until the app-owned MCP server reports connected.

        The first prompt can otherwise race the MCP process and the model sees
        no Studio tools at all. A missing server is a startup error, not a turn.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for server in await self.mcp_servers():
                status = server.get("status") or {}
                if server.get("name") == name and status.get("status") == "connected":
                    return
            await asyncio.sleep(0.25)
        raise OpenCodeError(f"MCP server {name} did not connect")

    async def model_available(self, model: str) -> bool:
        provider, model_id, _variant = parse_model(model)
        return any(
            item.get("providerID") == provider and item.get("id") == model_id
            for item in await self.models()
        )

    async def set_model(self, session_id: str, model: str) -> None:
        provider, model_id, variant = parse_model(model)
        value: dict[str, Any] = {"id": model_id, "providerID": provider}
        if variant:
            value["variant"] = variant
        response = await self._client.post(
            f"/api/session/{session_id}/model", json={"model": value}
        )
        response.raise_for_status()

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield parsed SSE events until the consumer closes the generator."""
        timeout = httpx.Timeout(None, connect=5.0)
        async with httpx.AsyncClient(
            base_url=self.base_url, auth=self._client.auth, timeout=timeout
        ) as client:
            async with client.stream("GET", "/api/event") as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        yield json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue


class OpenCodeGateway:
    """Owns one ``opencode serve`` child and its app-owned config."""

    def __init__(
        self,
        *,
        binary: str = "opencode",
        workspace: Path | None = None,
        projects_dir: Path,
        writer_model: str = WRITER_MODEL,
        editor_model: str = EDITOR_MODEL,
    ):
        self.binary = binary
        self.workspace = workspace or gateway_workspace()
        self.projects_dir = Path(projects_dir).resolve()
        self.writer_model = writer_model
        self.editor_model = editor_model
        self.port: int | None = None
        self.password = ""
        self.process: subprocess.Popen | None = None
        self._log = None

    @property
    def base_url(self) -> str:
        if self.port is None:
            raise OpenCodeError("gateway is not running")
        return f"http://127.0.0.1:{self.port}"

    def client(self) -> OpenCodeClient:
        if not self.password:
            raise OpenCodeError("gateway is not running")
        return OpenCodeClient(self.base_url, self.password)

    def _write_config(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        write_json(
            self.workspace / "opencode.json",
            gateway_config(
                projects_dir=self.projects_dir,
                writer_model=self.writer_model,
                editor_model=self.editor_model,
            ),
        )

    def _tail(self, limit: int = 1600) -> str:
        path = self.workspace / "opencode.log"
        if not path.is_file():
            return ""
        return path.read_text(errors="replace")[-limit:]

    async def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        self._write_config()
        self.port = _free_port()
        self.password = secrets.token_urlsafe(32)
        env = {
            **dict(os.environ),
            "OPENCODE_SERVER_PASSWORD": self.password,
        }
        self._log = (self.workspace / "opencode.log").open("ab")
        try:
            self.process = subprocess.Popen(
                [
                    self.binary,
                    "serve",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(self.port),
                ],
                cwd=self.workspace,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise OpenCodeError(f"OpenCode binary not found: {self.binary}") from exc

        deadline = time.monotonic() + HEALTH_TIMEOUT
        async with httpx.AsyncClient(
            base_url=self.base_url,
            auth=httpx.BasicAuth("opencode", self.password),
            timeout=2.0,
        ) as client:
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    self.stop()
                    raise OpenCodeError("OpenCode exited during startup. " + self._tail())
                try:
                    response = await client.get("/api/info")
                    if response.status_code == 200:
                        version = _version(response.json().get("version", ""))
                        if not (MIN_VERSION <= version < MAX_VERSION):
                            self.stop()
                            raise OpenCodeError(
                                "OpenCode "
                                f"{response.json().get('version')} is outside the verified "
                                "2.1.x range (2.1.4+); the 2.0.x line fails the Writer model"
                            )
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.2)
        self.stop()
        raise OpenCodeError("OpenCode did not become healthy. " + self._tail())

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=STOP_GRACE)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=STOP_GRACE)
        if self._log is not None:
            self._log.close()
            self._log = None


def session_path(root: Path) -> Path:
    return root / "work" / "opencode-sessions.json"


def load_session(root: Path, role: str, model: str) -> dict[str, Any] | None:
    value = read_optional(session_path(root), {})
    if not isinstance(value, dict):
        return None
    entry = value.get(role)
    if not isinstance(entry, dict):
        return None
    if entry.get("model") != model or entry.get("agent") != role:
        return None
    if entry.get("warm") is not True:
        return None
    session_id = entry.get("id")
    return entry if isinstance(session_id, str) and session_id else None


def save_session(root: Path, role: str, session_id: str, model: str) -> None:
    value = read_optional(session_path(root), {})
    if not isinstance(value, dict):
        value = {}
    value[role] = {"id": session_id, "model": model, "agent": role, "warm": True}
    write_json(session_path(root), value)


def _tool_name(names: dict[str, str], data: dict[str, Any]) -> str:
    call_id = data.get("id")
    return names.get(call_id, str(call_id or "tool"))


def _text_content(content) -> str:
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(part.get("text", ""))
        for part in content
        if isinstance(part, dict) and part.get("type") == "text"
    ).strip()


async def _interrupt(client: OpenCodeClient, session_id: str) -> None:
    try:
        await asyncio.wait_for(client.interrupt(session_id), STOP_GRACE)
    except Exception:  # noqa: BLE001 - stopping must never mask the turn
        pass


async def run_gateway_turn(
    client: OpenCodeClient,
    root: Path,
    slug: str,
    role: str,
    message: str,
    context: str,
    *,
    model: str,
    timeout: float = TURN_LIMIT,
    idle_limit: float = IDLE_LIMIT,
    tool_input_idle_limit: float = TOOL_INPUT_IDLE_LIMIT,
    warmup_delay: float = WARMUP_DELAY,
    prompt_meta: dict | None = None,
) -> AsyncIterator[TurnEvent]:
    """Run one Studio turn through the gateway and persist the text history.

    The OpenCode session is reused per production and role until the model
    changes. The event stream is opened before the prompt so the first delta
    cannot be lost. Cancelling the consumer interrupts the gateway execution, and
    so does silence: only this session's events count as life, never heartbeats or
    another session's work.
    """
    wait_for_mcp = getattr(client, "wait_for_mcp", None)
    if wait_for_mcp is not None:
        # A session snapshots its tool catalog at creation; wait before it.
        await wait_for_mcp()

    entry = load_session(root, role, model)
    if entry is not None:
        session_id = entry["id"]
    else:
        # A fresh OpenCode session snapshots the MCP catalog. Create and drop a
        # warm-up session first so the real session sees the Studio tools.
        warm = await client.create_session(title=f"warmup {slug} {role}", agent=role)
        await asyncio.sleep(warmup_delay)
        session_id = await client.create_session(title=f"{slug} {role}", agent=role)
        delete = getattr(client, "delete_session", None)
        if delete is not None:
            try:
                await delete(warm)
            except Exception:  # noqa: BLE001 - an orphan warm-up is harmless
                pass
    save_session(root, role, session_id, model)
    if entry is None and hasattr(client, "set_model"):
        await client.set_model(session_id, model)

    entry = {"role": "user", "content": message}
    if prompt_meta is not None:
        entry["prompt"] = prompt_meta
    append_message(root, entry, agent=role)
    prompt_text = f"{context.strip()}\n\n---\n\n{message.strip()}" if context.strip() else message
    events = client.events()
    done = False
    assistant_text = ""
    names: dict[str, str] = {}
    writing: set[str] = set()
    limit = idle_limit

    async def ended(message: str) -> TurnEvent:
        # Stop the gateway first, so the turn is over before it says so. The text
        # already shown stays on record.
        nonlocal done
        done = True
        await _interrupt(client, session_id)
        if assistant_text.strip():
            append_message(
                root,
                {"role": "assistant", "content": assistant_text, "name": role, "interrupted": True},
                agent=role,
            )
        return TurnEvent(
            kind="done", text=assistant_text, payload={"error": message, "stalled": True}
        )

    clock = asyncio.get_running_loop().time
    turn_ends = clock() + timeout
    try:
        connected = clock() + idle_limit
        while True:
            event = await asyncio.wait_for(anext(events), connected - clock())
            if event.get("type") == "server.connected":
                break
        await client.prompt(session_id, prompt_text)

        last_heard = clock()
        while True:
            limit = tool_input_idle_limit if writing else idle_limit
            event = await asyncio.wait_for(
                anext(events), min(last_heard + limit, turn_ends) - clock()
            )
            kind = event.get("type", "")
            data = event.get("data") or {}
            if data.get("sessionID") not in (None, session_id):
                continue
            alive = kind.startswith(("session.", "permission."))
            if alive:
                last_heard = clock()

            if kind == "session.text.delta":
                delta = str(data.get("delta") or "")
                if delta:
                    assistant_text += delta
                    yield TurnEvent(kind="text", text=delta)
            elif kind == "session.text.ended" and not assistant_text:
                text = str(data.get("text") or "")
                if text:
                    assistant_text = text
                    yield TurnEvent(kind="text", text=text)
            elif kind == "session.tool.input.started":
                names[str(data.get("id"))] = str(data.get("name") or "tool")
                writing.add(str(data.get("id")))
                yield TurnEvent(kind="progress", tool=_tool_name(names, data))
            elif kind == "session.tool.called":
                writing.discard(str(data.get("id")))
                name = _tool_name(names, data)
                arguments = json.dumps(data.get("input") or {}, ensure_ascii=False)
                yield TurnEvent(kind="tool", tool=name, arguments=arguments)
            elif kind == "session.tool.success":
                name = _tool_name(names, data)
                result = _text_content(data.get("content"))
                append_message(
                    root,
                    {"role": "tool", "name": name, "content": result[:4000]},
                    agent=role,
                )
                yield TurnEvent(kind="tool", tool=name, result=result)
            elif kind == "session.tool.error":
                name = _tool_name(names, data)
                result = _text_content(data.get("content")) or "tool failed"
                yield TurnEvent(kind="tool", tool=name, result=result)
            elif kind == "permission.asked":
                yield TurnEvent(kind="permission", payload=data)
            elif kind == "session.execution.succeeded":
                append_message(
                    root,
                    {"role": "assistant", "content": assistant_text, "name": role},
                    agent=role,
                )
                done = True
                yield TurnEvent(kind="done", text=assistant_text)
                return
            elif kind == "session.execution.interrupted":
                append_message(
                    root,
                    {
                        "role": "assistant",
                        "content": assistant_text,
                        "name": role,
                        "interrupted": True,
                    },
                    agent=role,
                )
                done = True
                yield TurnEvent(kind="done", text=assistant_text, payload={"interrupted": True})
                return
            elif kind == "session.execution.failed":
                done = True
                error = data.get("error")
                if isinstance(error, dict):
                    error = error.get("message") or error.get("type")
                yield TurnEvent(
                    kind="done",
                    text=assistant_text,
                    payload={"error": str(error or "gateway execution failed")},
                )
                return
            elif kind == "session.tool.input.ended":
                writing.discard(str(data.get("id")))
                yield TurnEvent(kind="progress")
            elif alive:
                yield TurnEvent(kind="progress")
    except TimeoutError:
        if clock() >= turn_ends:
            minutes = round(timeout / 60)
            yield await ended(
                f"The {role.capitalize()} was still working after {minutes} minutes, "
                f"so this turn was ended. {NOTHING_LOST}"
            )
        else:
            yield await ended(stall_message(role, limit))
    except StopAsyncIteration:
        yield await ended(f"The connection to the {role.capitalize()} closed. {NOTHING_LOST}")
    except httpx.TimeoutException:
        yield await ended(stall_message(role, idle_limit))
    except httpx.HTTPError:
        yield await ended(f"The connection to the {role.capitalize()} was lost. {NOTHING_LOST}")
    finally:
        if not done:
            await _interrupt(client, session_id)
        await events.aclose()
