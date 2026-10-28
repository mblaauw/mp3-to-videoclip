"""Project-local Remotion adapter; derived inputs, never a second edit timeline."""

import base64
import fcntl
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from threading import Thread

from PIL import Image

from . import operations
from .models import Project, RenderShot
from .storage import digest, file_hash, read_json, write_json

ENGINE = Path(__file__).resolve().parents[2] / "renderers/remotion"


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


def request(kind: str, output: Path, asset_root: Path, canvas, fps, frames, inputs: dict) -> dict:
    """The exact renderer request object; pure, so a contract test can pin it."""
    return {
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


def invoke(kind: str, output: Path, asset_root: Path, canvas, fps, frames, inputs: dict) -> dict:
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
    request_body = request(kind, output, asset_root, canvas, fps, frames, inputs)
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
    stdout, stderr = _run_streaming(argv, output, progress_path, frames)
    invoke_seconds = time.perf_counter() - started
    progress_path.unlink(missing_ok=True)
    if stdout is None:
        raise ValueError("Local Remotion render failed: " + stderr[-4000:])
    if not output.is_file():
        raise ValueError("Remotion returned without an output")
    sidecar = Path(f"{output}.render.json")
    return {
        "renderer_revision": revision,
        "request_sha256": file_hash(request_path),
        "invoke_seconds": invoke_seconds,
        "renderer_report": read_json(sidecar) if sidecar.is_file() else None,
    }


def _run_streaming(argv: list[str], output: Path, progress_path: Path, frames: int):
    """Run the renderer, mirroring its output to a log and polling progress.

    Returns ``(stdout_text, stderr_text)``; ``stdout_text`` is ``None`` when the
    renderer exited non-zero. Nothing here retries: a failed render is a failed
    render, and the caller decides what to do after inspecting the log.
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
    while process.poll() is None:
        _relay_progress(progress_path, frames)
        time.sleep(0.5)
    _relay_progress(progress_path, frames)
    for reader in readers:
        reader.join(timeout=5)
    collector.close()
    if process.returncode == 0:
        return _tail(collector.stdout), _tail(collector.stderr)
    return None, _tail(collector.stderr) + _tail(collector.stdout, 1000)


def _relay_progress(progress_path: Path, frames: int) -> None:
    """Best-effort: a missing or partially written progress file is not an error."""
    try:
        info = read_json(progress_path)
    except (OSError, ValueError):
        return
    if not isinstance(info, dict):
        return
    operations.tick(
        phase=info.get("phase"),
        done=info.get("done"),
        total=info.get("total"),
        unit=info.get("unit"),
    )


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
) -> dict:
    """Remotion visuals + existing atomic FFmpeg/audio/verification contracts."""
    from . import render as R
    from .branding import pack_hash, render_brand_plate

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
    if brand is not None and brand.plate:
        plate = assets / f"brand-{pack_hash(brand)}-{project.width}x{project.height}.png"
        if not plate.exists():
            if brand.mark == "filmstrip":
                raise ValueError(
                    "filmstrip identity belongs in Remotion graphics; set brand.plate=false"
                )
            render_brand_plate(brand, project, plate)
        inputs["brand_plate"] = data_url(plate, "image/png")
        inputs["brand_duration_frames"] = round(brand.duration_seconds * project.fps)
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
            invoke(
                "base",
                silent,
                selected,
                (project.width, project.height),
                project.fps,
                project.total_frames,
                inputs,
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
        "dissolves": sum(s.shot.dissolve_frames > 0 for s in shots),
        "preview_placeholders": list(preview_placeholders),
        "verification": "Measured exact frames/dimensions/fps/audio/duration/faststart; not artistic acceptance",
    }
    report["video"]["fps"] = project.fps
    return report


def graphics_clip(part, spec, palette, canvas, fps, output: Path) -> None:
    """Render one alpha element; existing compositor retains audio packet copying."""
    from .branding import filmstrip_svg

    if spec.get("intro", {}).get("mark", {}).get("kind") != "filmstrip":
        raise ValueError("Remotion identity currently requires the explicit filmstrip mark")
    colours = {key: "#" + "".join(f"{v:02x}" for v in val[:3]) for key, val in palette.items()}
    logo = (
        "data:image/svg+xml;base64,"
        + base64.b64encode(filmstrip_svg(colours["accent"]).encode()).decode()
    )
    inputs = {
        "part": part,
        "spec": spec,
        "intro": spec["intro"],
        "palette": colours,
        "logo": logo,
        # Local Avenir Next is resolved by Chromium's system font stack; .ttc is
        # not a portable webfont. Its source bytes are still in the fingerprint.
        "font": None,
    }
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
