#!/usr/bin/env python3
"""Create safe whole-sticker looping GIFs for a prepared job."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

RESAMPLING = getattr(Image, "Resampling", Image)

try:
    from ._media_qa import inspect_gif
except ImportError:  # pragma: no cover - direct CLI execution
    from _media_qa import inspect_gif  # type: ignore

try:
    from ._core import (
        atomic_write_json,
        find_ffmpeg,
        load_job,
        numbered_slug,
        publish_files_atomically,
        relative_job_path,
        resolve_job_path,
        save_job_atomic,
        sha256_file,
        update_status,
        verify_artifact_record,
    )
except ImportError:  # pragma: no cover - direct CLI execution
    from _core import (  # type: ignore
        atomic_write_json,
        find_ffmpeg,
        load_job,
        numbered_slug,
        publish_files_atomically,
        relative_job_path,
        resolve_job_path,
        save_job_atomic,
        sha256_file,
        update_status,
        verify_artifact_record,
    )


ALLOWED_MOTIONS = ("bob", "bounce", "shake", "nod", "sway", "pulse", "tilt", "hop")


def motion_parameters(template: str, phase: float) -> dict[str, float]:
    """Return periodic affine parameters; phase 0 and 1 are identical."""
    if template not in ALLOWED_MOTIONS:
        raise ValueError(f"unsupported motion template: {template}")
    angle = 2.0 * math.pi * (phase % 1.0)
    params = {"dx": 0.0, "dy": 0.0, "rotation": 0.0, "scale_x": 1.0, "scale_y": 1.0}
    if template == "bob":
        params["dy"] = -7.0 * math.sin(angle)
    elif template == "bounce":
        lift = 0.5 - 0.5 * math.cos(angle)
        params.update(dy=-14.0 * lift, scale_x=1.0 + 0.025 * lift, scale_y=1.0 - 0.025 * lift)
    elif template == "shake":
        params.update(dx=5.0 * math.sin(2.0 * angle), rotation=1.3 * math.sin(2.0 * angle))
    elif template == "nod":
        params.update(dy=2.0 * math.sin(angle), rotation=3.0 * math.sin(angle))
    elif template == "sway":
        params.update(dx=3.0 * math.sin(angle), rotation=3.5 * math.sin(angle))
    elif template == "pulse":
        scale = 1.0 + 0.035 * math.sin(angle)
        params.update(scale_x=scale, scale_y=scale)
    elif template == "tilt":
        params["rotation"] = 5.0 * math.sin(angle)
    elif template == "hop":
        lift = 0.5 - 0.5 * math.cos(angle)
        params.update(dy=-18.0 * lift, scale_x=1.0 + 0.035 * lift, scale_y=1.0 - 0.035 * lift)
    return params


def choose_motion(label: str, index: int) -> str:
    text = label.casefold()
    keyword_map = (
        (("跳", "jump", "冲", "走"), "hop"),
        (("怒", "气", "angry", "不", "no"), "shake"),
        (("点头", "好的", "ok", "yes", "收到"), "nod"),
        (("爱", "心", "赞", "love", "like"), "pulse"),
        (("疑", "问", "what", "why", "嗯"), "tilt"),
        (("等", "无聊", "wait", "later"), "sway"),
        (("笑", "喜", "开心", "happy", "yay"), "bounce"),
    )
    for keywords, motion in keyword_map:
        if any(keyword in text for keyword in keywords):
            return motion
    return ("bob", "bounce", "sway", "tilt")[index % 4]


def _item_label(item: Any, index: int) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("display_name") or item.get("label") or item.get("name") or f"Sticker {index + 1}")
    return f"Sticker {index + 1}"


def _cell_paths(job_path: Path, job: dict[str, Any]) -> list[Path]:
    candidates: Any = None
    for container_name in ("artifacts", "assets", "paths", "outputs"):
        container = job.get(container_name)
        if isinstance(container, dict) and container.get("cells"):
            candidates = container["cells"]
            break
    if not isinstance(candidates, list) or len(candidates) != 9:
        raise ValueError("job does not contain exactly nine prepared cell paths")
    paths: list[Path] = []
    for candidate in candidates:
        rel = candidate.get("path") if isinstance(candidate, dict) else candidate
        if not isinstance(rel, str):
            raise ValueError("invalid cell path in job")
        paths.append(verify_artifact_record(job_path, candidate, f"cell {len(paths) + 1}", expected_index=len(paths) + 1))
    return paths


def _render_frame(source: Image.Image, template: str, phase: float) -> Image.Image:
    canvas_size = (512, 512)
    rgba = source.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("prepared sticker is fully transparent")
    sticker = rgba.crop(bbox)
    p = motion_parameters(template, phase)
    width = max(1, round(sticker.width * p["scale_x"]))
    height = max(1, round(sticker.height * p["scale_y"]))
    sticker = sticker.resize((width, height), RESAMPLING.LANCZOS)
    sticker = sticker.rotate(p["rotation"], resample=RESAMPLING.BICUBIC, expand=True)

    # Fit after rotation before applying the bounded translation. This prevents clipping.
    max_width = max(1, 512 - 2 * (abs(round(p["dx"])) + 2))
    max_height = max(1, 512 - 2 * (abs(round(p["dy"])) + 2))
    fit = min(1.0, max_width / sticker.width, max_height / sticker.height)
    if fit < 1.0:
        sticker = sticker.resize(
            (max(1, round(sticker.width * fit)), max(1, round(sticker.height * fit))),
            RESAMPLING.LANCZOS,
        )
    x = round((512 - sticker.width) / 2 + p["dx"])
    y = round((512 - sticker.height) / 2 + p["dy"])
    x = min(max(0, x), 512 - sticker.width)
    y = min(max(0, y), 512 - sticker.height)
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    canvas.alpha_composite(sticker, (x, y))
    return canvas


def _encode_gif(ffmpeg: str, frames_dir: Path, destination: Path, fps: int) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp.gif")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame-%03d.png"),
        "-filter_complex",
        "[0:v]split[a][b];[a]palettegen=reserve_transparent=1:max_colors=192[p];[b][p]paletteuse=alpha_threshold=96:dither=sierra2_4a",
        "-loop",
        "0",
        str(temporary),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        frame_count = len(list(frames_dir.glob("frame-*.png")))
        properties = inspect_gif(
            temporary,
            expected_size=512,
            expected_frames=frame_count,
            expected_fps=fps,
        )
        os.link(temporary, destination)
        temporary.unlink()
        return properties
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "FFmpeg failed").strip()
        raise RuntimeError(f"GIF encoding failed: {detail}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def animate_job(job_path: Path, *, fps: int = 12, duration: float = 1.0) -> list[dict[str, Any]]:
    job_path = (job_path / "job.json" if job_path.is_dir() else job_path).resolve()
    if fps != 12:
        raise ValueError("v0.1 local animation is fixed at 12fps")
    if not 0.9 <= duration <= 1.1:
        raise ValueError("v0.1 local animation duration must remain about one second")
    frame_count = round(fps * duration)
    if frame_count < 2 or frame_count > 180:
        raise ValueError("duration must produce between 2 and 180 frames")
    job = load_job(job_path)
    if job.get("status") != "assets_prepared":
        raise ValueError("local animation requires an assets_prepared job")
    cells = _cell_paths(job_path, job)
    items = job.get("items") or job.get("contents") or []
    if len(items) != 9:
        raise ValueError("job must contain exactly nine content items")
    ffmpeg = find_ffmpeg("ffmpeg")
    gifs_dir = resolve_job_path(job_path, job["paths"]["gifs_dir"])
    work_dir = resolve_job_path(job_path, "work")
    work_dir.mkdir(parents=True, exist_ok=True)

    plans: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        label = _item_label(item, index)
        plans.append(
            {
                "index": index + 1,
                "display_name": label,
                "template": choose_motion(label, index),
                "fps": fps,
                "duration_seconds": frame_count / fps,
                "frames": frame_count,
                "whole_sticker_affine_only": True,
            }
        )
    motion_plan_path = resolve_job_path(job_path, job["paths"]["motion_plan"])
    results: list[dict[str, Any]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="da-motion-", dir=work_dir) as temp_name:
            temp_root = Path(temp_name)
            staged_plan = temp_root / "motion-plan.json"
            atomic_write_json(
                staged_plan,
                {"version": 1, "motions": plans},
                overwrite=False,
            )
            publications: list[tuple[Path, Path]] = [(staged_plan, motion_plan_path)]
            for index, (cell_path, plan) in enumerate(zip(cells, plans)):
                if not cell_path.is_file():
                    raise FileNotFoundError(f"prepared cell is missing: {cell_path}")
                frames_dir = temp_root / f"frames-{index + 1:02d}"
                frames_dir.mkdir()
                with Image.open(cell_path) as image:
                    source = image.convert("RGBA")
                for frame_index in range(frame_count):
                    frame = _render_frame(source, plan["template"], frame_index / frame_count)
                    frame.save(frames_dir / f"frame-{frame_index:03d}.png")
                slug = (
                    str(items[index]["slug"])
                    if isinstance(items[index], dict)
                    else numbered_slug(index + 1, plan["display_name"])
                )
                filename = f"{slug}.gif"
                output = resolve_job_path(
                    job_path, f"{job['paths']['gifs_dir']}/{filename}"
                )
                staged_output = temp_root / "encoded" / filename
                properties = _encode_gif(ffmpeg, frames_dir, staged_output, fps)
                results.append(
                    {
                        "index": index + 1,
                        "path": relative_job_path(job_path, output),
                        "sha256": sha256_file(staged_output),
                        "media": properties,
                    }
                )
                publications.append((staged_output, output))
            publish_files_atomically(publications)
    except Exception as exc:
        job.setdefault("errors", []).append(
            {"stage": "animate_local", "message": str(exc)}
        )
        save_job_atomic(job_path, job)
        raise

    job.setdefault("artifacts", {})["gifs"] = results
    job.setdefault("options", {})["route"] = "local"
    update_status(
        job_path,
        job,
        "local_animated",
        qa={
            "local_animation": {
                "ok": True,
                "count": 9,
                "motion_plan": relative_job_path(job_path, motion_plan_path),
                "gif_contract": {"width": 512, "height": 512, "fps": fps, "frames": frame_count, "loop": 0},
            }
        },
    )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path, help="Path to job.json")
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--duration", type=float, default=1.0, help="Loop duration in seconds")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        outputs = animate_job(args.job.resolve(), fps=args.fps, duration=args.duration)
    except Exception as exc:
        raise SystemExit(f"animate_local: {exc}") from exc
    print(json.dumps({"status": "local_animated", "outputs": outputs}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
