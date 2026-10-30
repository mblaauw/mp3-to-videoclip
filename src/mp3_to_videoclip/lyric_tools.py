"""Put known words on a song with local tools: Demucs, then Parakeet.

The tools live in a private environment with pinned versions, set up only when the
owner asks, and run as a separate process. The Studio works without them, nothing
is uploaded, and no provider is called. Times stay estimates: a line whose words
weren't heard keeps no time rather than a guessed one.
"""

from __future__ import annotations

import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import unicodedata
from collections.abc import Callable
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np

from . import operations
from .domain import lyric_timing
from .storage import digest, read_json, read_optional, write_json

TOOLS_PYTHON = "3.11"
DOWNLOAD_GB = 3
LOCK = Path(__file__).with_name("lyric_tools.lock.txt")
WORKER = Path(__file__).with_name("lyric_tools_worker.py")
HEARD_DIR = "work/heard"
# A line needs this share of its words heard before it gets a time.
MIN_LINE_MATCH = 0.5
FUZZY_MATCH = 0.7
_EXACT, _CLOSE, _MISS, _GAP = 2.0, 1.0, -1.0, -0.5


def _home() -> Path:
    override = os.environ.get("STUDIO_LYRIC_TOOLS")
    return Path(override) if override else Path.home() / ".cache/mp3-to-videoclip/lyric-tools"


def _python() -> Path:
    return _home() / "env/bin/python"


def _lock_hash() -> str:
    return sha256(LOCK.read_bytes()).hexdigest()


def status() -> dict[str, Any]:
    """Whether this machine can run the tools, and whether they're set up."""
    reason = None
    if sys.platform != "darwin" or platform.machine() != "arm64":
        reason = "Automatic timing needs an Apple Silicon Mac. You can still tap the lines on."
    elif shutil.which("uv") is None:
        reason = "Automatic timing needs uv to set up its tools. You can still tap the lines on."
    marker = read_optional(_home() / "ready.json")
    ready = isinstance(marker, dict) and marker.get("lock") == _lock_hash() and _python().is_file()
    return {
        "supported": reason is None,
        "reason": reason,
        "ready": bool(ready and reason is None),
        "download_gb": DOWNLOAD_GB,
    }


def _run(command: list[str], on_line: Callable[[str], None] | None = None) -> None:
    """Run one step, stopping it if the owner presses Stop."""
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace"
    )
    lines: queue.Queue[str] = queue.Queue()
    tail: list[str] = []

    def pump_out() -> None:
        for line in process.stdout:  # type: ignore[union-attr]
            lines.put(line)

    def pump_err() -> None:
        for line in process.stderr:  # type: ignore[union-attr]
            tail.append(line)
            del tail[:-20]

    threads = [threading.Thread(target=pump, daemon=True) for pump in (pump_out, pump_err)]
    for thread in threads:
        thread.start()
    while True:
        try:
            line = lines.get(timeout=0.25)
        except queue.Empty:
            line = None
        if line and on_line:
            on_line(line)
        if operations.stop_requested():
            process.terminate()
            process.wait()
            raise ValueError("stopped by the user; nothing was changed")
        if process.poll() is not None and lines.empty():
            break
    for thread in threads:
        thread.join(timeout=2)
    if process.returncode:
        last = " ".join(part.strip() for part in tail[-3:])
        raise ValueError(f"the lyric tools failed: {last or f'exit code {process.returncode}'}")


def _worker_steps(line: str) -> None:
    try:
        step = json.loads(line).get("step")
    except (ValueError, AttributeError):
        return
    if step:
        operations.phase(step)


def install() -> dict[str, Any]:
    """Create the private environment and fetch the models. Safe to run again."""
    state = status()
    if not state["supported"]:
        raise ValueError(state["reason"])
    uv = shutil.which("uv")
    env = _home() / "env"
    _home().mkdir(parents=True, exist_ok=True)
    operations.phase("installing-tools")
    if not _python().is_file():
        _run([str(uv), "venv", "--python", TOOLS_PYTHON, str(env)])
    _run([str(uv), "pip", "sync", "--python", str(_python()), str(LOCK)])
    _run([str(_python()), "-I", str(WORKER), "prepare"], _worker_steps)
    write_json(_home() / "ready.json", {"lock": _lock_hash()})
    return status()


# ---- words -------------------------------------------------------------------


def _norm(word: str) -> str:
    plain = unicodedata.normalize("NFKD", word.lower())
    return "".join(char for char in plain if char.isascii() and char.isalnum())


def heard_words(tokens: list[dict]) -> list[dict]:
    """Join the recogniser's pieces into words: a piece starting with a space opens one."""
    words: list[dict] = []
    for token in tokens:
        text = str(token["text"])
        if text[:1].isspace() or not words:
            words.append({"text": text, "start": float(token["start"]), "end": float(token["end"])})
        else:
            words[-1]["text"] += text
            words[-1]["end"] = float(token["end"])
    for word in words:
        word["text"] = _norm(word["text"])
    return [word for word in words if word["text"]]


def _align(known: list[str], heard: list[str]) -> dict[int, int]:
    """Global word alignment with credit for close spellings: known index -> heard index."""
    scores: dict[tuple[str, str], float] = {}

    def score(left: str, right: str) -> float:
        key = (left, right)
        if key not in scores:
            ratio = 1.0 if left == right else SequenceMatcher(None, left, right).ratio()
            scores[key] = _EXACT if ratio == 1 else _CLOSE if ratio >= FUZZY_MATCH else _MISS
        return scores[key]

    rows, cols = len(known), len(heard)
    table = np.zeros((rows + 1, cols + 1))
    table[1:, 0] = _GAP * np.arange(1, rows + 1)
    table[0, 1:] = _GAP * np.arange(1, cols + 1)
    for i in range(1, rows + 1):
        for j in range(1, cols + 1):
            table[i, j] = max(
                table[i - 1, j - 1] + score(known[i - 1], heard[j - 1]),
                table[i - 1, j] + _GAP,
                table[i, j - 1] + _GAP,
            )
    pairs: dict[int, int] = {}
    i, j = rows, cols
    while i and j:
        step = score(known[i - 1], heard[j - 1])
        if table[i, j] == table[i - 1, j - 1] + step:
            if step > 0:
                pairs[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif table[i, j] == table[i - 1, j] + _GAP:
            i -= 1
        else:
            j -= 1
    return pairs


def match_lines(rows: list[dict], tokens: list[dict]) -> dict[int, tuple[float, float]]:
    """Each sung line's start and end, for lines whose words were really heard."""
    heard = heard_words(tokens)
    known: list[str] = []
    owner: list[int] = []
    totals: dict[int, int] = {}
    for row in rows:
        if row.get("tag"):
            continue
        for word in str(row["text"]).split():
            clean = _norm(word)
            if clean:
                known.append(clean)
                owner.append(row["index"])
                totals[row["index"]] = totals.get(row["index"], 0) + 1
    found: dict[int, list[int]] = {}
    for position, match in sorted(_align(known, [word["text"] for word in heard]).items()):
        found.setdefault(owner[position], []).append(match)
    return {
        index: (heard[matches[0]]["start"], heard[matches[-1]]["end"])
        for index, matches in found.items()
        if len(matches) / totals[index] >= MIN_LINE_MATCH
    }


def _heard_path(root: Path, audio: Path) -> Path:
    return (
        root
        / HEARD_DIR
        / f"{digest({'audio': sha256(audio.read_bytes()).hexdigest(), 'lock': _lock_hash()})}.json"
    )


def hear(root: Path, audio: Path) -> dict:
    """The words heard in this audio, reused if this exact audio was heard before."""
    path = _heard_path(root, audio)
    cached = read_optional(path)
    if isinstance(cached, dict) and isinstance(cached.get("tokens"), list):
        return cached
    if not status()["ready"]:
        raise ValueError("set up the lyric tools first")
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "heard.json"
        _run([str(_python()), "-I", str(WORKER), "hear", str(audio), str(out)], _worker_steps)
        heard = read_json(out)
    write_json(path, heard)
    return heard


def time_lyrics(root: Path) -> dict[str, Any]:
    """Time every line that isn't tapped. Tapped lines and an LRC's own times stay."""
    from . import production as P

    project = P.load_project(root)
    rows = lyric_timing.view(root)["lines"]
    if not any(not row["tag"] for row in rows):
        raise ValueError("add the words first")
    heard = hear(root, P.render_audio(root, project))
    operations.phase("matching-words")
    times = match_lines(rows, heard["tokens"])
    kept = {row["index"]: row for row in rows if row["source"] in ("tapped", "lrc")}
    lines = []
    previous = 0.0
    for row in rows:
        if row["tag"]:
            continue
        if row["index"] in kept:
            previous = max(previous, kept[row["index"]]["start"])
            if row["source"] == "tapped":
                lines.append(
                    {
                        "index": row["index"],
                        "start": row["start"],
                        "end": row["end"],
                        "source": "tapped",
                    }
                )
            continue
        time = times.get(row["index"])
        # A line that would land before a tapped line above it stays untimed.
        if time is None or time[0] < previous:
            continue
        start = time[0]
        end = time[1] if time[0] < time[1] <= project.duration else None
        if start >= project.duration:
            continue
        previous = start
        lines.append({"index": row["index"], "start": start, "end": end, "source": "auto"})
    view = lyric_timing.save(root, {"lines": lines}, project.duration)
    sung = [row for row in view["lines"] if not row["tag"]]
    return {"timed": sum(1 for row in sung if row["start"] is not None), "sung": len(sung)}
