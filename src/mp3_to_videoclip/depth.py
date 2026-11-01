"""Depth for the stills of a film: three feathered layers that move against each other.

The estimate runs in a private environment with pinned versions, set up only when the
owner asks, on this computer, for free. A map is kept per still hash outside any film.
A film keeps its layer sets in ``work/depth/``: derived, immutable once written, never
under ``assets/``. A still's own bytes are never touched.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from . import operations
from .storage import file_hash, read_optional, write_json

TOOLS_PYTHON = "3.12"
DOWNLOAD_GB = 1.5
LOCK = Path(__file__).with_name("depth_tools.lock.txt")
WORKER = Path(__file__).with_name("depth_tools_worker.py")
#: Where the mid and near layers begin, as shares of the still's own depth values.
MID_FROM, NEAR_FROM = 0.40, 0.70
#: The soft edge of a layer, as a share of the still's short side.
FEATHER = 0.006
#: Bumped when the layers change, so old sets are not reused.
LAYER_VERSION = 3
LAYERS = ("far", "mid", "near")


def _home() -> Path:
    override = os.environ.get("STUDIO_DEPTH_TOOLS")
    return Path(override) if override else Path.home() / ".cache/mp3-to-videoclip/depth-tools"


def _python() -> Path:
    return _home() / "env/bin/python"


def model_key() -> str:
    """Names a map and a layer set by the exact tools that made them."""
    digest = sha256(LOCK.read_bytes() + WORKER.read_bytes()).hexdigest()
    return digest[:12]


def status() -> dict[str, Any]:
    """Whether this machine can run the tool, and whether it's set up."""
    reason = None
    if shutil.which("uv") is None:
        reason = "Depth needs uv to set up its tools."
    marker = read_optional(_home() / "ready.json")
    ready = isinstance(marker, dict) and marker.get("key") == model_key() and _python().is_file()
    return {
        "supported": reason is None,
        "reason": reason,
        "ready": bool(ready and reason is None),
        "download_gb": DOWNLOAD_GB,
    }


def _run(argv: list[str]) -> None:
    """Run a tool, stoppable, keeping the last lines to explain a failure."""
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    lines: queue.Queue[str] = queue.Queue()
    tail: list[str] = []

    def drain() -> None:
        for line in process.stdout:
            lines.put(line)

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    while True:
        try:
            line = lines.get(timeout=0.25)
        except queue.Empty:
            line = None
        if line:
            tail = [*tail[-2:], line]
            try:
                step = json.loads(line).get("step")
            except (ValueError, AttributeError):
                step = None
            if step:
                operations.phase(step)
        if operations.stop_requested():
            process.terminate()
            process.wait()
            raise ValueError("stopped by the user; nothing was changed")
        if process.poll() is not None and lines.empty():
            break
    reader.join(timeout=2)
    if process.returncode:
        last = " ".join(part.strip() for part in tail)
        raise ValueError(f"the depth tools failed: {last or f'exit code {process.returncode}'}")


def install() -> dict[str, Any]:
    """Create the private environment and fetch the model. Safe to run again."""
    state = status()
    if not state["supported"]:
        raise ValueError(state["reason"])
    uv = shutil.which("uv")
    env = _home() / "env"
    _home().mkdir(parents=True, exist_ok=True)
    operations.phase("installing-depth-tools")
    if not _python().is_file():
        _run([str(uv), "venv", "--python", TOOLS_PYTHON, str(env)])
    _run([str(uv), "pip", "sync", "--python", str(_python()), str(LOCK)])
    _run([str(_python()), "-I", str(WORKER), "prepare"])
    write_json(_home() / "ready.json", {"key": model_key()})
    return status()


def depth_map(still: Path) -> Path:
    """The still's map, made once per still hash and set of tools."""
    path = _home() / "maps" / model_key() / f"{file_hash(still)}.png"
    if path.is_file():
        return path
    if not status()["ready"]:
        raise ValueError("set up the depth tools first")
    with tempfile.TemporaryDirectory() as folder:
        made = Path(folder) / "depth.png"
        _run([str(_python()), "-I", str(WORKER), "estimate", str(still), str(made)])
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(made, path.with_suffix(".part"))
        os.replace(path.with_suffix(".part"), path)
    return path


def _layer_dir(root: Path, still: Path) -> Path:
    name = f"{file_hash(still)}-{model_key()}-v{LAYER_VERSION}"
    return Path(root) / "work" / "depth" / name


def layer_set(root: Path, still: Path) -> dict | None:
    """The still's finished layers with their hashes, or None if it has none whole."""
    folder = _layer_dir(root, still)
    record = read_optional(folder / "layers.json")
    if not isinstance(record, dict):
        return None
    for name in LAYERS:
        path = folder / f"{name}.png"
        if not path.is_file() or file_hash(path) != record.get(name):
            return None
    return {**record, "folder": folder}


def _band(depth: np.ndarray, share: float, radius: float) -> Image.Image:
    """Everything nearer than that share of the still's depths, with a soft edge."""
    mask = Image.fromarray(((depth >= np.quantile(depth, share)) * 255).astype(np.uint8), mode="L")
    return mask.filter(ImageFilter.GaussianBlur(radius))


def _behind(picture: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """The picture with what a nearer layer covers replaced by the nearest pixels around it.

    A layer that moves uncovers what is behind it. If that were the same subject again, its
    edge would show twice; this way it uncovers background. Only pixels inside the nearer
    layer's shape change, so nothing that is always on screen does, and only a thin rim of
    them is ever seen.
    """
    from scipy import ndimage

    if not mask.any() or mask.all():
        return picture
    nearest = ndimage.distance_transform_edt(mask, return_distances=False, return_indices=True)
    return picture[nearest[0], nearest[1]]


def make_layers(root: Path, still: Path, depth: Path) -> dict:
    """Cut a still into its layers. Far covers the frame, so nothing shows through."""
    existing = layer_set(root, still)
    if existing is not None:
        return existing
    image = Image.open(still).convert("RGB")
    grey = Image.open(depth).convert("L").resize(image.size, Image.Resampling.BICUBIC)
    values = np.asarray(grey, dtype=np.float32)
    radius = max(1.0, FEATHER * min(image.size))
    pixels = np.asarray(image)
    mid_from = np.quantile(values, MID_FROM)
    near_from = np.quantile(values, NEAR_FROM)
    far = Image.fromarray(_behind(pixels, values >= mid_from), mode="RGB")
    mid = Image.fromarray(_behind(pixels, values >= near_from), mode="RGB")
    layers = {
        "far": far.convert("RGBA"),
        "mid": Image.merge("RGBA", (*mid.split(), _band(values, MID_FROM, radius))),
        "near": Image.merge("RGBA", (*image.split(), _band(values, NEAR_FROM, radius))),
    }
    folder = _layer_dir(root, still)
    folder.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {"still": file_hash(still), "model": model_key()}
    for name, picture in layers.items():
        path = folder / f"{name}.png"
        partial = path.with_suffix(".part.png")
        picture.save(partial)
        os.replace(partial, path)
        record[name] = file_hash(path)
    write_json(folder / "layers.json", record)
    return {**record, "folder": folder}


def _selected_stills(root: Path) -> dict[str, Path]:
    """Each paid shot's selected still, by shot. A local card or plate has no depth."""
    from . import production as P
    from . import shotkinds

    board = P.load_board(root, verify_source=False)
    assets = read_optional(root / "work" / "assets.json")
    assets = assets if isinstance(assets, dict) else {}
    found: dict[str, Path] = {}
    for shot in board.shots:
        if shot.asset_shot_id is None and shotkinds.is_local(shot):
            continue
        owner = shot.asset_shot_id or shot.id
        entry = assets.get(owner) or {}
        chosen = next(
            (v for v in entry.get("versions", []) if v["version"] == entry.get("selected")), None
        )
        if chosen and (root / chosen["path"]).is_file():
            found[shot.id] = root / chosen["path"]
    return found


def coverage(root: Path) -> dict[str, Any]:
    """How many selected stills have their layers, per shot."""
    stills = _selected_stills(Path(root))
    with_layers = [shot for shot, still in stills.items() if layer_set(root, still) is not None]
    return {
        "stills": len(stills),
        "with_depth": len(with_layers),
        "shots": with_layers,
        "tools": status(),
    }


def ensure_for_render(root: Path) -> None:
    """Make any layers a film with depth is missing, before a render needs them.

    Free and local, so it needs no click. Without the tools the render's own refusal says so.
    """
    from . import edits

    root = Path(root)
    edit = edits.load_edit(root)
    look = edit.grade.look if edit is not None else None
    if look is not None and look.depth > 0 and status()["ready"]:
        run(root)


def run(root: Path) -> dict[str, Any]:
    """Make the layers of every selected still that lacks them. Free, and only local."""
    root = Path(root)
    stills = list(dict.fromkeys(_selected_stills(root).values()))
    missing = [still for still in stills if layer_set(root, still) is None]
    operations.phase("reading-depth", total=len(missing), unit="stills", done=0)
    for done, still in enumerate(missing, start=1):
        make_layers(root, still, depth_map(still))
        operations.tick(done=done, total=len(missing), unit="stills")
    return {"made": len(missing), "stills": len(stills)}
