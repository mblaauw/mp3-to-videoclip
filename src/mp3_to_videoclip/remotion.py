"""Project-local Remotion adapter; derived inputs, never a second edit timeline."""

import base64
import fcntl
import os
import shutil
import signal
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from threading import Thread

from PIL import Image

from . import operations
from .models import Project, RenderShot
from .storage import digest, file_hash, read_json, write_json

ENGINE = Path(__file__).resolve().parents[2] / "renderers/remotion"

# Seconds without any change in the renderer's progress before it counts as hung.
STALL_SECONDS = {"rendering-frames": 120, "rendering-stills": 120}
STALL_SECONDS_OTHER = 300
# Previews and bases: much faster than PNG. Finals stay PNG until the owner has
# judged a JPEG film at full screen (.opencode/tasks/render-speed.md, D1).
WORKING_CAPTURE = {"format": "jpeg", "quality": 95}
# The renderer's limit on stills per request.
MAX_STILLS = 64


class AssetCacheCorruption(ValueError):
    """An immutable cached asset differs from its content-addressed name."""


def _stage_asset(source: Path, assets: Path) -> tuple[str, str]:
    sha = file_hash(source)
    with Image.open(source) as image:
        image.verify()
    name = sha + source.suffix.lower()
    target = assets / name
    if not target.exists():
        # Publish only complete bytes, without replacing another process's file.
        with tempfile.NamedTemporaryFile(dir=assets, prefix=".asset-") as handle:
            shutil.copyfile(source, handle.name)
            if file_hash(Path(handle.name)) != sha:
                raise AssetCacheCorruption("Remotion source changed during asset staging")
            try:
                os.link(handle.name, target)
            except FileExistsError:
                pass
    if target.is_symlink() or not target.is_file() or file_hash(target) != sha:
        raise AssetCacheCorruption("Remotion asset cache corruption")
    return name, sha


def selected_asset_root(compiled: list[dict], assets: Path) -> Path:
    """Publish exactly the selected manifest, never the accumulating staging cache.

    The lock serializes validation/publication across processes. A complete sibling
    directory is renamed into place; existing publications are verified, not repaired.
    """
    manifest = {}
    for shot in compiled:
        entries = [shot, *shot.get("split_panes", [])]
        for entry in entries:
            name = entry["image"]
            sha = entry.get("image_sha256", name.split(".", 1)[0])
            if Path(name).name != name or len(sha) != 64 or not name.startswith(sha + "."):
                raise AssetCacheCorruption("Invalid Remotion selected asset identity")
            source = assets / name
            if source.is_symlink() or file_hash(source) != sha:
                raise AssetCacheCorruption("Remotion asset cache corruption")
            manifest[name] = sha
    identity = digest({"version": 1, "files": manifest})
    publications = assets.parent / "remotion-asset-selections"
    publications.mkdir(parents=True, exist_ok=True)
    selected = publications / identity
    with (publications / ".publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not selected.exists():
            staging = Path(tempfile.mkdtemp(prefix=".selection-", dir=publications))
            for name, sha in manifest.items():
                shutil.copyfile(assets / name, staging / name)
                if file_hash(staging / name) != sha:
                    raise AssetCacheCorruption("Remotion asset changed during publication")
            os.rename(staging, selected)
        if selected.is_symlink() or {p.name for p in selected.iterdir()} != set(manifest):
            raise AssetCacheCorruption("Remotion selected asset publication corruption")
        for name, sha in manifest.items():
            target = selected / name
            if target.is_symlink() or not target.is_file() or file_hash(target) != sha:
                raise AssetCacheCorruption("Remotion selected asset publication corruption")
    return selected


def visual_identity(project: Project, inputs: dict, revision: str) -> str:
    """Versioned visual dependencies only; money and source-audio metadata do not render."""
    return digest(
        {
            "version": 1,
            "width": project.width,
            "height": project.height,
            "fps": project.fps,
            "total_frames": project.total_frames,
            "inputs": inputs,
            "implementation_revision": revision,
        }
    )


def implementation_hash() -> str:
    """Bind renderer code, locked dependencies and font bytes; never the browser.

    A browser security update changes produced bytes only if the renderer source
    changes, so hashing the desktop binary would revoke a reviewed preview for no
    content reason. Local Node and Chrome are checked when a render starts, not
    when an approval is compared.
    """
    from .graphics import resolve_font

    names = ["package.json", "package-lock.json", "render.mjs"]
    paths = [ENGINE / n for n in names] + sorted((ENGINE / "src").glob("*"))
    missing = [str(p) for p in paths if not p.is_file()]
    if missing or not (ENGINE / "src/index.jsx").is_file():
        raise ValueError(f"Remotion source bundle incomplete: {missing}")
    font = resolve_font()[0]
    return digest(
        {
            "files": {str(p.relative_to(ENGINE)): file_hash(p) for p in paths},
            "adapter": file_hash(Path(__file__)),
            "font": file_hash(font),
        }
    )


def renderer_binding(project: Project) -> dict:
    if not project.uses_remotion:
        return {}
    return {"renderer_backend": "remotion", "renderer_revision": implementation_hash()}


def data_url(path: Path, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def request(
    kind: str, output: Path, asset_root: Path, canvas, fps, frames, inputs: dict, chunks=None
) -> dict:
    """The exact renderer request object; pure, so a contract test can pin it."""
    body = {
        "kind": kind,
        "output": str(output.resolve()),
        "assetRoot": str(asset_root.resolve()),
        "width": canvas[0],
        "height": canvas[1],
        "fps": fps,
        "frames": frames,
        "chrome": os.environ.get(
            "REMOTION_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        ),
        "input": inputs,
    }
    if chunks is not None:
        body["chunks"] = chunks
    return body


def invoke(
    kind: str, output: Path, asset_root: Path, canvas, fps, frames, inputs: dict, chunks=None
) -> dict:
    """Explicit local subprocess; never npx installs, uploads or implicit fallback.

    stdout/stderr are streamed to a log instead of being buffered for the whole
    render, and the renderer's throttled progress file advances the active
    operation receipt so a long silent render is observable while it runs.
    """
    if output.exists():
        raise FileExistsError(output)
    revision = implementation_hash()
    if not (ENGINE / "node_modules/@remotion/renderer").is_dir():
        raise ValueError(
            "Install pinned local renderer first: npm ci --prefix renderers/remotion --ignore-scripts"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    asset_root.mkdir(parents=True, exist_ok=True)
    request_body = request(kind, output, asset_root, canvas, fps, frames, inputs, chunks)
    request_path = output.with_suffix(".request.json")
    write_json(request_path, request_body)
    progress_path = output.with_name(f".{output.stem}.progress.json")
    operations.phase("validating-request", note=f"{kind} {frames} frames")
    argv = [
        "node",
        str(ENGINE / "render.mjs"),
        str(request_path.resolve()),
        "--progress",
        str(progress_path.resolve()),
    ]
    started = time.perf_counter()
    with _one_render_at_a_time():
        stdout, stderr = _run_streaming(argv, output, progress_path, frames)
    invoke_seconds = time.perf_counter() - started
    progress_path.unlink(missing_ok=True)
    if stdout is None:
        raise ValueError("Local Remotion render failed: " + stderr[-4000:])
    if chunks is not None:
        if not all(Path(chunk["output"]).is_file() for chunk in chunks):
            raise ValueError("Remotion returned without every chunk")
    elif not (output.is_dir() if kind == "stills" else output.is_file()):
        raise ValueError("Remotion returned without an output")
    sidecar = Path(f"{output}.render.json")
    return {
        "renderer_revision": revision,
        "request_sha256": file_hash(request_path),
        "invoke_seconds": invoke_seconds,
        "renderer_report": read_json(sidecar) if sidecar.is_file() else None,
    }


@contextmanager
def _one_render_at_a_time():
    """Hold the machine-wide render lock: two films at once crash their browser pages.

    The job runner only serializes per project and the CLI is a separate process,
    so the lock lives with the renderer. Waiting stays stoppable and says why.
    """
    (ENGINE / ".cache").mkdir(parents=True, exist_ok=True)
    with (ENGINE / ".cache/render.lock").open("a") as lock:
        told = False
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if not told:
                    operations.phase("waiting-for-another-render")
                    told = True
                if operations.stop_requested():
                    raise ValueError("stopped by the user before rendering began") from None
                time.sleep(1)
        yield


def _descendants(pid: int) -> list[int]:
    """Every live process under ``pid``; Chrome detaches from the renderer's group."""
    try:
        table = subprocess.run(
            ["ps", "-axo", "pid=,ppid="], capture_output=True, text=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return []
    children: dict[int, list[int]] = {}
    for line in table.splitlines():
        child, parent = line.split()
        children.setdefault(int(parent), []).append(int(child))
    found, queue = [], [pid]
    while queue:
        for child in children.get(queue.pop(), []):
            found.append(child)
            queue.append(child)
    return found


def _signal_all(pids: list[int], number: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, number)
        except (ProcessLookupError, PermissionError):
            pass


def _end_renderer(process: subprocess.Popen) -> None:
    """End the renderer and the browser under it, politely and then for certain."""
    family = _descendants(process.pid)
    _signal_all([process.pid, *family], signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    _signal_all([process.pid, *family], signal.SIGKILL)
    process.wait()


def _run_streaming(argv: list[str], output: Path, progress_path: Path, frames: int):
    """Run the renderer, mirroring its output to a log and polling progress.

    Returns ``(stdout_text, stderr_text)``; ``stdout_text`` is ``None`` when the
    renderer exited non-zero. Nothing here retries: a failed render is a failed
    render, and the caller decides what to do after inspecting the log. A render
    whose progress stops moving is ended and fails, as does one the user stops.
    """
    log = output.with_suffix(".render.log")
    collector = _OutputCollector(log)
    process = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
    )
    readers = [
        Thread(target=collector.drain, args=(process.stdout,), daemon=True),
        Thread(target=collector.drain, args=(process.stderr,), daemon=True),
    ]
    for reader in readers:
        reader.start()
    watch = _StallWatch()
    failure = None
    while process.poll() is None:
        watch.saw(_relay_progress(progress_path, frames))
        if operations.stop_requested():
            failure = "stopped by the user; nothing was published"
        elif watch.stalled():
            failure = (
                f"the render stopped moving during {watch.phase or 'startup'} and was ended "
                f"after {watch.limit()} seconds at {watch.done} frames; see {log.name}"
            )
        if failure:
            _end_renderer(process)
            break
        time.sleep(0.5)
    _relay_progress(progress_path, frames)
    for reader in readers:
        reader.join(timeout=5)
    collector.close()
    if failure:
        raise ValueError(failure)
    if process.returncode == 0:
        return _tail(collector.stdout), _tail(collector.stderr)
    return None, _tail(collector.stderr) + _tail(collector.stdout, 1000)


class _StallWatch:
    """Time since the renderer's phase or frame count last changed.

    Only those two count: the progress file's timestamp kept moving in the renders
    that hung for an hour.
    """

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.moved = clock()
        self.phase = None
        self.done = None

    def saw(self, info: dict | None) -> None:
        if not info:
            return
        phase, done = info.get("phase"), info.get("done")
        if (phase, done) != (self.phase, self.done):
            self.phase, self.done = phase, done
            self.moved = self.clock()

    def limit(self) -> int:
        return STALL_SECONDS.get(self.phase, STALL_SECONDS_OTHER)

    def stalled(self) -> bool:
        return self.clock() - self.moved > self.limit()


def _relay_progress(progress_path: Path, frames: int) -> dict | None:
    """Best-effort: a missing or partially written progress file is not an error."""
    try:
        info = read_json(progress_path)
    except (OSError, ValueError):
        return None
    if not isinstance(info, dict):
        return None
    operations.tick(
        phase=info.get("phase"),
        done=info.get("done"),
        total=info.get("total"),
        unit=info.get("unit"),
    )
    return info


class _OutputCollector:
    """Bounded in-process mirror of the renderer's own output, with a local log."""

    LIMIT = 4000

    def __init__(self, log: Path):
        self.log = log
        self.stdout: list[str] = []
        self.stderr: list[str] = []
        self._handle = None

    def drain(self, stream) -> None:
        try:
            for line in stream:
                self._keep(self.stdout, line)
        except (OSError, ValueError):
            pass

    def _keep(self, sink: list[str], line: str) -> None:
        sink.append(line)
        del sink[: -self.LIMIT]
        try:
            self._log(line)
        except OSError:
            pass

    def _log(self, line: str) -> None:
        if self._handle is None:
            self.log.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.log.open("a")
        self._handle.write(line)

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def _tail(lines: list[str], limit: int = 4000) -> str:
    return "".join(lines)[-limit:]


def compile_shots(shots: list[RenderShot], workdir: Path, assets: Path) -> list[dict]:
    """Compile resolved shots and their edit payload into renderer inputs.

    Pure apart from copying selected bytes into the flat asset cache. Kept
    separate from the render/subprocess path so the MP4 payload can be tested
    against the same shape the Player receives.
    """
    compiled = []
    root = Path(workdir).resolve().parent
    for rs in shots:
        name, sha = _stage_asset(Path(rs.image), assets)
        entry = {**rs.shot.model_dump(), "image": name, "image_sha256": sha}
        if rs.edit is not None:
            entry["edit"] = rs.edit.model_dump(by_alias=True)
        if rs.grade is not None:
            entry["grade"] = rs.grade.model_dump(by_alias=True)
        if rs.shot.kind == "split" and rs.shot.panes:
            # Native split panes are preferred when every source still is current;
            # the precomposed local plate remains the fallback.
            try:
                from . import production as P

                panes = []
                for pane in rs.shot.panes:
                    resolved = P.resolved_assets(root, [pane.shot_id])[0]
                    pane_name, _ = _stage_asset(Path(resolved.image), assets)
                    panes.append(
                        {
                            "shot_id": pane.shot_id,
                            "image": pane_name,
                            "crop": pane.crop.model_dump(),
                        }
                    )
            except AssetCacheCorruption:
                raise
            except (OSError, ValueError):
                panes = []
            if panes:
                entry["split_panes"] = panes
        compiled.append(entry)
    return compiled


def _brand_inputs(project: Project, brand, assets: Path) -> dict:
    """The rasterised opening brand plate, when the production has one."""
    from .branding import pack_hash, render_brand_plate

    if brand is None or not brand.plate:
        return {}
    plate = assets / f"brand-{pack_hash(brand)}-{project.width}x{project.height}.png"
    if not plate.exists():
        if brand.mark == "filmstrip":
            raise ValueError(
                "filmstrip identity belongs in Remotion graphics; set brand.plate=false"
            )
        render_brand_plate(brand, project, plate)
    return {
        "brand_plate": data_url(plate, "image/png"),
        "brand_duration_frames": round(brand.duration_seconds * project.fps),
    }


def render_stills(
    project: Project,
    shots: list[RenderShot],
    frames: list[int],
    output: Path,
    workdir: Path,
    *,
    brand=None,
    titles: dict | None = None,
) -> dict:
    """PNG frames of the exact film composition (pictures, brand plate, titles).

    ``output`` is a new directory; the renderer publishes it whole or not at all.
    Returns the renderer's report, whose ``stills`` list each frame's file and
    SHA-256. Nothing is encoded and no audio is read.
    """
    from . import render as R

    R._validate_shots(project, shots)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    assets = Path(workdir).resolve() / "remotion-assets"
    assets.mkdir(parents=True, exist_ok=True)
    compiled = compile_shots(shots, workdir, assets)
    inputs = {
        "shots": compiled,
        "preview_banner": False,
        "preview_placeholders": [],
        "still_frames": sorted(set(frames)),
        **_brand_inputs(project, brand, assets),
    }
    if titles is not None:
        inputs["titles"] = titles
    result = invoke(
        "stills",
        output,
        selected_asset_root(compiled, assets),
        (project.width, project.height),
        project.fps,
        project.total_frames,
        inputs,
    )
    report = result.get("renderer_report") or {}
    stills = report.get("stills") or []
    if [still.get("frame") for still in stills] != inputs["still_frames"]:
        raise ValueError("Remotion returned a different set of stills than requested")
    for still in stills:
        if file_hash(output / still["file"]) != still["sha256"]:
            raise ValueError(f"still {still['file']} changed after rendering")
    return {**result, "stills": stills}


def _fresh_frames(frames: list[int], selected, canvas, fps, total, inputs, directory) -> dict:
    """Render ``frames`` of the film once more, as PNGs in ``directory``, by frame number."""
    found = {}
    for start in range(0, len(frames), MAX_STILLS):
        batch = frames[start : start + MAX_STILLS]
        output = directory / f"frames-{start}"
        result = invoke(
            "stills",
            output,
            selected,
            canvas,
            fps,
            total,
            {
                **{key: value for key, value in inputs.items() if key != "capture"},
                "still_frames": batch,
            },
        )
        report = result.get("renderer_report") or {}
        for still in report.get("stills") or []:
            found[still["frame"]] = output / still["file"]
    if set(found) != set(frames):
        raise ValueError("Remotion returned a different set of frames than requested")
    return found


def check_movies(movies: list[tuple[Path, int]], selected, canvas, fps, total, inputs) -> list:
    """Look for broken frames in movies, each given with the film frame it begins at.

    All suspects are confirmed in one renderer run, which is why this takes a list.
    """
    from . import framecheck

    if not movies:
        return []
    scanned = [(framecheck.small_frames(movie), start) for movie, start in movies]
    found = [framecheck.suspects(frames) for frames, _ in scanned]
    wanted = sorted(
        start + i for (_, start), hits in zip(scanned, found, strict=True) for i in hits
    )
    fresh: dict[int, Path] = {}
    directory = None
    if wanted:
        operations.phase("checking-frames", note=f"{len(wanted)} frames to look at again")
        directory = tempfile.TemporaryDirectory(dir=movies[0][0].parent, prefix=".frame-check-")
    try:
        if wanted:
            fresh = _fresh_frames(
                wanted, selected, canvas, fps, total, inputs, Path(directory.name)
            )
        checks = []
        for (frames, start), hits in zip(scanned, found, strict=True):
            broken = framecheck.broken_frames(
                frames, hits, {index: fresh[start + index] for index in hits}
            )
            checks.append(
                {
                    "scanned": len(frames),
                    "suspects": [start + index for index in hits],
                    "broken": [start + index for index in broken],
                }
            )
        return checks
    finally:
        if directory is not None:
            directory.cleanup()


def check_frames(movie: Path, start: int, selected, canvas, fps, total, inputs) -> dict:
    """Look for broken frames in ``movie``, which begins at film frame ``start``."""
    return check_movies([(movie, start)], selected, canvas, fps, total, inputs)[0]


def _chunk_receipt(path: Path) -> Path:
    return path.with_suffix(".chunk.json")


def _trusted_chunk(path: Path, chunk) -> bool:
    """Whether a finished chunk may be reused; damage fails loudly, like the base cache."""
    receipt = _chunk_receipt(path)
    if not receipt.exists():
        return False
    try:
        record = read_json(receipt)
    except (OSError, ValueError):
        record = None
    expected = {"sha256": file_hash(path) if path.is_file() else None, "key": chunk.key}
    if not isinstance(record, dict) or {k: record.get(k) for k in expected} != expected:
        raise ValueError(
            f"Remotion chunk cache corruption at {path.name}; preserve and investigate"
        )
    return True


def _join_chunks(paths: list[Path], output: Path, fps: int) -> None:
    """Join movies without re-encoding, publishing only a join with even timing."""
    from . import render as R

    partial = output.with_name(f".{output.stem}.joining.mp4")
    listing = output.with_name(f".{output.stem}.joining.txt")
    quoted = [str(path).replace("'", "'\\''") for path in paths]
    listing.write_text("".join(f"file '{path}'\n" for path in quoted))
    try:
        R._run(
            [
                R._binary("ffmpeg"),
                "-nostdin",
                "-v",
                "error",
                "-n",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(partial),
            ]
        )
        _require_even_timing(partial, fps)
        os.link(partial, output)
    finally:
        listing.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)


def _require_even_timing(movie: Path, fps: int) -> None:
    """Every frame one tick after the last: a bad join would show here first."""
    from . import render as R

    out = R._run(
        [
            R._binary("ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "packet=pts_time",
            "-of",
            "csv=p=0",
            str(movie),
        ]
    )
    times = sorted(float(line.strip().rstrip(",")) for line in out.split() if line.strip(", "))
    gaps = [later - earlier for earlier, later in zip(times, times[1:], strict=False)]
    if (
        not times
        or abs(times[0]) > 0.5 / fps
        or any(abs(gap - 1 / fps) > 0.25 / fps for gap in gaps)
    ):
        raise ValueError(f"joined chunks have uneven timing in {movie.name}")


def _render_silent(kind, silent: Path, selected, canvas, fps, frames, inputs, reuse=False) -> None:
    """Render the film's pictures to ``silent``, shot by shot.

    With ``reuse``, a shot whose key matches a checked chunk isn't rendered again, and
    an interrupted render resumes. Without it, as for a final, every chunk is fresh, so
    a key bug can't reach a delivered film. A chunk with a broken frame is set aside and
    rendered once more; a second failure fails the render and names the frames.
    """
    from .chunks import film_chunks

    plan = film_chunks(inputs, canvas, fps, implementation_hash())
    shared = silent.parent / "remotion-chunks"
    shared.mkdir(parents=True, exist_ok=True)
    store = shared if reuse else Path(tempfile.mkdtemp(prefix="fresh-", dir=shared))
    paths = {chunk.key: store / f"{chunk.key[:40]}.mp4" for chunk in plan}
    with (shared / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        check = {"scanned": 0, "suspects": [], "broken": [], "chunks": len(plan)}
        check["reused"] = sum(_trusted_chunk(paths[chunk.key], chunk) for chunk in plan)
        for attempt in range(2):
            pending = [c for c in plan if not _chunk_receipt(paths[c.key]).exists()]
            # Two identical shots can share a key, and only one of them needs rendering.
            pending = list({chunk.key: chunk for chunk in pending}.values())
            missing = [c for c in pending if not paths[c.key].exists()]
            if missing:
                invoke(
                    kind,
                    store / f".run-{uuid.uuid4().hex[:12]}.mp4",
                    selected,
                    canvas,
                    fps,
                    frames,
                    inputs,
                    [
                        {"start": c.start, "frames": c.frames, "output": str(paths[c.key])}
                        for c in missing
                    ],
                )
            results = check_movies(
                [(paths[c.key], c.start) for c in pending], selected, canvas, fps, frames, inputs
            )
            broken = []
            for chunk, result in zip(pending, results, strict=True):
                check["scanned"] += result["scanned"]
                check["suspects"] += result["suspects"]
                if result["scanned"] != chunk.frames:
                    raise ValueError(
                        f"Remotion chunk for {chunk.shot_id} has {result['scanned']} frames, "
                        f"not {chunk.frames}"
                    )
                if result["broken"]:
                    broken += result["broken"]
                    aside = paths[chunk.key].with_suffix(f".broken-{uuid.uuid4().hex[:8]}.mp4")
                    os.rename(paths[chunk.key], aside)
                    continue
                write_json(
                    _chunk_receipt(paths[chunk.key]),
                    {
                        "sha256": file_hash(paths[chunk.key]),
                        "key": chunk.key,
                        "shot_id": chunk.shot_id,
                        "frames": chunk.frames,
                    },
                )
            check["broken"] += broken
            if not broken:
                break
            if attempt == 1:
                raise ValueError(
                    f"broken frames at {sorted(broken)} came back after rendering again; "
                    f"the chunks are kept in {store.name}"
                )
        operations.phase("joining-shots", note=f"{len(plan)} shots")
        _join_chunks([paths[chunk.key] for chunk in plan], silent, fps)
    write_json(silent.with_suffix(".frames.json"), check)
    if not reuse:
        shutil.rmtree(store)


def render_base(
    project: Project,
    shots: list[RenderShot],
    audio: Path,
    output: Path,
    workdir: Path,
    *,
    preview_banner=False,
    preview_placeholders=(),
    brand=None,
    titles: dict | None = None,
    capture: dict | None = None,
    reuse_chunks: bool = False,
) -> dict:
    """Remotion visuals + existing atomic FFmpeg/audio/verification contracts.

    ``titles`` (see :func:`titles_input`) draws the planned titles in the same
    pass; without it the request and the visual cache key are unchanged. ``capture``
    (see :data:`WORKING_CAPTURE`) is how frames leave the browser; absent means PNG.
    """
    from . import render as R

    R._validate_shots(project, shots)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    assets = Path(workdir).resolve() / "remotion-assets"
    assets.mkdir(parents=True, exist_ok=True)
    compiled = compile_shots(shots, workdir, assets)
    inputs = {
        "shots": compiled,
        "preview_banner": preview_banner,
        "preview_placeholders": list(preview_placeholders),
    }
    if titles is not None:
        inputs["titles"] = titles
    if capture is not None:
        inputs["capture"] = capture
    inputs.update(_brand_inputs(project, brand, assets))
    revision = implementation_hash()
    selected = selected_asset_root(compiled, assets)
    key = visual_identity(project, inputs, revision)
    silent = Path(workdir).resolve() / f"remotion-base-{key[:20]}.mp4"
    cached = silent.with_suffix(".cache.json")
    # Only this visual cache is locked during rendering, never project state or
    # the selected-asset publication. Waiters must inspect the completed receipt.
    with silent.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        cache_hit = silent.exists()
        if cache_hit:
            try:
                record = read_json(cached)
            except (OSError, ValueError):
                record = None
            if not isinstance(record, dict) or record != {"sha256": file_hash(silent), "key": key}:
                raise ValueError("Remotion base cache corruption; preserve and investigate")
        else:
            if cached.exists():
                raise ValueError("Remotion base cache corruption; orphan sidecar preserved")
            _render_silent(
                "base",
                silent,
                selected,
                (project.width, project.height),
                project.fps,
                project.total_frames,
                inputs,
                reuse_chunks,
            )
            if R._count_frames(silent) != project.total_frames:
                raise ValueError("Remotion silent base has incorrect frame count")
            write_json(cached, {"sha256": file_hash(silent), "key": key})
    partial = output.with_name(f".{output.stem}.partial.mp4")
    if partial.exists():
        raise ValueError(f"Unresolved partial render: {partial}")
    operations.phase("muxing-audio", note="original audio muxed over the silent visual base")
    mux_started = time.perf_counter()
    try:
        R._run(
            [
                R._binary("ffmpeg"),
                "-nostdin",
                "-v",
                "error",
                "-n",
                "-i",
                str(silent),
                "-i",
                str(audio),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                R.AUDIO_BITRATE,
                "-t",
                f"{project.total_frames / project.fps:.9f}",
                "-movflags",
                "+faststart",
                str(partial),
            ]
        )
        mux_seconds = time.perf_counter() - mux_started
        verification_started = time.perf_counter()
        facts = R._validate_output(partial, project, audio, R.audio_seconds(audio))
        operations.phase("verifying-output", note="frames, fps, dimensions and audio identity")
        if facts["video"]["frames"] != project.total_frames:
            raise ValueError("Remotion mux changed the exact frame count")
        verification_seconds = time.perf_counter() - verification_started
        os.link(partial, output)
    finally:
        partial.unlink(missing_ok=True)
    report = {
        "output": str(output),
        "timings_seconds": {"mux": mux_seconds, "output_verification": verification_seconds},
        "visual_cache_hit": cache_hit,
        "frame_check": (
            read_json(silent.with_suffix(".frames.json"))
            if silent.with_suffix(".frames.json").is_file()
            else None
        ),
        "renderer_report": (
            read_json(Path(f"{silent}.render.json"))
            if not cache_hit and Path(f"{silent}.render.json").is_file()
            else None
        ),
        "historical_renderer_report": (
            read_json(Path(f"{silent}.render.json"))
            if cache_hit and Path(f"{silent}.render.json").is_file()
            else None
        ),
        **facts,
        "verified": True,
        "renderer_backend": "remotion",
        "renderer_revision": revision,
        "input_hash": key,
        "visual_sha256": file_hash(silent),
        "source_sha256": file_hash(audio),
        "preview": preview_banner,
        "rendered_shots": len(shots),
        "titles": [window["id"] for window in titles["windows"]] if titles else [],
        "dissolves": sum(s.shot.dissolve_frames > 0 for s in shots),
        "preview_placeholders": list(preview_placeholders),
        "verification": "Measured exact frames/dimensions/fps/audio/duration/faststart; not artistic acceptance",
    }
    report["video"]["fps"] = project.fps
    return report


def title_assets(spec: dict, palette: dict) -> dict:
    """The spec, palette, logo and font every title element is drawn from."""
    from .branding import filmstrip_svg

    if spec.get("intro", {}).get("mark", {}).get("kind") != "filmstrip":
        raise ValueError("Remotion identity currently requires the explicit filmstrip mark")
    colours = {key: "#" + "".join(f"{v:02x}" for v in val[:3]) for key, val in palette.items()}
    logo = (
        "data:image/svg+xml;base64,"
        + base64.b64encode(filmstrip_svg(colours["accent"]).encode()).decode()
    )
    return {
        "spec": spec,
        "intro": spec["intro"],
        "palette": colours,
        "logo": logo,
        # Local Avenir Next is resolved by Chromium's system font stack; .ttc is
        # not a portable webfont. Its source bytes are still in the fingerprint.
        "font": None,
    }


def titles_input(spec: dict, palette: dict, windows: list[dict]) -> dict:
    """``input.titles`` for the Film composition: assets plus the planned windows."""
    return {**title_assets(spec, palette), "windows": windows}


def graphics_clip(part, spec, palette, canvas, fps, output: Path) -> None:
    """Render one alpha element; existing compositor retains audio packet copying."""
    inputs = {"part": part, **title_assets(spec, palette)}
    invoke(
        "graphics", output, output.parent / "remotion-assets", canvas, fps, part["frames"], inputs
    )


def overlay_clip(part, spec, palette, canvas, fps, directory: Path) -> Path:
    """Alpha cache compatible with the current sparse qtrle track builder."""
    from . import graphics as G

    key = digest(
        {
            "part": part,
            "spec": spec,
            "palette": palette,
            "canvas": canvas,
            "fps": fps,
            "renderer_revision": implementation_hash(),
        }
    )[:24]
    path = directory / f"remotion-overlay-{key}.mov"
    if path.exists():
        G._validate_overlay(path, canvas, part["frames"])
        G._cache_integrity(path, created=False)
        return path
    alpha = directory / f"remotion-prores-{key}.mov"
    if not alpha.exists():
        graphics_clip(part, spec, palette, canvas, fps, alpha)
        G._cache_integrity(alpha, created=True)
    else:
        G._cache_integrity(alpha, created=False)
    temp = path.with_name(f".{path.stem}.partial.mov")
    conversion_started = time.perf_counter()
    try:
        G._run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-n",
                "-i",
                str(alpha),
                "-an",
                "-c:v",
                "qtrle",
                "-pix_fmt",
                "argb",
                str(temp),
            ]
        )
        conversion_seconds = time.perf_counter() - conversion_started
        verification_started = time.perf_counter()
        G._validate_overlay(temp, canvas, part["frames"])
        verification_seconds = time.perf_counter() - verification_started
        os.link(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    G._cache_integrity(path, created=True)
    write_json(
        path.with_suffix(".timings.json"),
        {
            "conversion_seconds": conversion_seconds,
            "output_verification_seconds": verification_seconds,
        },
    )
    return path


def overlay_frame(clip: Path, local_frame: int) -> Image.Image:
    """Decode an actual cached Remotion frame; never substitute Pillow samples."""
    import io

    from .render import _binary

    result = subprocess.run(
        [
            _binary("ffmpeg"),
            "-v",
            "error",
            "-i",
            str(clip),
            "-vf",
            f"select=eq(n\\,{local_frame})",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return Image.open(io.BytesIO(result.stdout)).convert("RGBA")
