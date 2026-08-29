#!/usr/bin/env python3
"""Resume a video-route job and convert a chroma-key 3x3 video into GIFs."""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image, ImageDraw

RESAMPLING = getattr(Image, "Resampling", Image)

try:
    from ._core import (
        atomic_copy,
        atomic_write_json,
        atomic_write_or_adopt_bytes,
        find_ffmpeg,
        load_job,
        publish_files_atomically,
        relative_job_path,
        resolve_job_path,
        save_job_atomic,
        sha256_file,
        update_status,
        verify_artifact_record,
    )
    from .animate_local import _encode_gif
except ImportError:  # pragma: no cover - direct CLI execution
    from _core import (  # type: ignore
        atomic_copy,
        atomic_write_json,
        atomic_write_or_adopt_bytes,
        find_ffmpeg,
        load_job,
        publish_files_atomically,
        relative_job_path,
        resolve_job_path,
        save_job_atomic,
        sha256_file,
        update_status,
        verify_artifact_record,
    )
    from animate_local import _encode_gif  # type: ignore


class ReviewRequired(RuntimeError):
    """Raised when deterministic processing needs a human grid decision."""


class CellQualityError(ValueError):
    """A per-cell media-quality failure that may be reported as partial delivery."""


@dataclass(frozen=True)
class GridDetection:
    x_cuts: tuple[int, int]
    y_cuts: tuple[int, int]
    confidence: float
    scores: dict[str, list[float]]


def _parse_hex(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"invalid chroma color: {value}")
    try:
        return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError as exc:
        raise ValueError(f"invalid chroma color: {value}") from exc


def _chroma_rgb(job: dict[str, Any]) -> tuple[int, int, int]:
    chroma = job.get("chroma") or {}
    for key in ("hex", "selected_hex", "color"):
        if isinstance(chroma.get(key), str):
            return _parse_hex(chroma[key])
    selected = chroma.get("selected")
    if isinstance(selected, dict):
        if isinstance(selected.get("hex"), str):
            return _parse_hex(selected["hex"])
        if isinstance(selected.get("rgb"), list) and len(selected["rgb"]) == 3:
            return tuple(int(v) for v in selected["rgb"])  # type: ignore[return-value]
    if isinstance(selected, str):
        return _parse_hex(selected)
    raise ValueError("job does not record a selected chroma color")


def _probe_video(ffprobe: str, video: Path) -> dict[str, Any]:
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,duration:format=duration",
        "-of",
        "json",
        str(video),
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise ValueError((exc.stderr or "ffprobe could not read the video").strip()) from exc
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise ValueError("input has no readable video stream")
    stream = streams[0]
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    if width < 3 or height < 3:
        raise ValueError("video dimensions are too small for a 3x3 grid")
    raw_duration = stream.get("duration") or (payload.get("format") or {}).get("duration") or 0
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        duration = 0.0
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("video duration is not finite")
    if duration > 30.0:
        raise ValueError("video is longer than the 30 second safety limit")
    if width > 4096 or height > 4096:
        raise ValueError("video dimensions exceed the 4096 pixel edge limit")
    estimated_frames = 360 if duration == 0 else max(1, math.ceil(duration * 12))
    if width * height * estimated_frames > 250_000_000:
        raise ValueError("video exceeds the decoded-pixel safety budget")
    return {"width": width, "height": height, "duration": duration, "avg_frame_rate": stream.get("avg_frame_rate")}


def _decode_once(ffmpeg: str, video: Path, destination: Path, fps: int) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=False)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-map",
        "0:v:0",
        "-vf",
        f"fps=fps={fps}:start_time=0:eof_action=pass",
        "-frames:v",
        "360",
        "-start_number",
        "0",
        str(destination / "full-%05d.png"),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError((exc.stderr or "FFmpeg frame decoding failed").strip()) from exc
    frames = sorted(destination.glob("full-*.png"))
    if not frames:
        raise ValueError("video produced no frames at the requested timeline")
    return frames


def _sample_arrays(frame_paths: list[Path], limit: int = 24) -> list[np.ndarray]:
    if len(frame_paths) <= limit:
        selected = frame_paths
    else:
        indices = np.linspace(0, len(frame_paths) - 1, num=limit, dtype=int)
        selected = [frame_paths[int(index)] for index in indices]
    arrays: list[np.ndarray] = []
    expected_size: tuple[int, int] | None = None
    for path in selected:
        with Image.open(path) as image:
            rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
        size = (rgba.shape[1], rgba.shape[0])
        if expected_size is None:
            expected_size = size
        elif size != expected_size:
            raise ValueError("decoded video frames have inconsistent dimensions")
        arrays.append(rgba)
    return arrays


def _load_keyed_cell_frames(
    frame_paths: list[Path],
    rectangle: tuple[int, int, int, int],
    key_rgb: tuple[int, int, int],
) -> list[np.ndarray]:
    """Read the once-decoded frame files one at a time, keeping only one cell in memory."""
    left, top, right, bottom = rectangle
    frames: list[np.ndarray] = []
    for path in frame_paths:
        with Image.open(path) as image:
            crop = np.asarray(image.convert("RGBA").crop((left, top, right, bottom)), dtype=np.uint8)
        frames.append(soft_chroma_key(crop, key_rgb))
    return frames


def _separator_profile(arrays: Iterable[np.ndarray], key_rgb: tuple[int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    key = np.asarray(key_rgb, dtype=np.float32)
    row_profiles: list[np.ndarray] = []
    col_profiles: list[np.ndarray] = []
    for rgba in arrays:
        distance = np.linalg.norm(rgba[..., :3].astype(np.float32) - key, axis=2)
        is_background = (distance <= 72.0) | (rgba[..., 3] <= 8)
        row_profiles.append(is_background.mean(axis=1))
        col_profiles.append(is_background.mean(axis=0))
    # Allow a few generated frames to cross a gutter without destroying the candidate.
    return np.quantile(np.stack(row_profiles), 0.25, axis=0), np.quantile(np.stack(col_profiles), 0.25, axis=0)


def _best_cut(profile: np.ndarray, expected: float, cell: float) -> tuple[int, float]:
    radius = max(2, round(cell * 0.16))
    start = max(2, round(expected) - radius)
    end = min(len(profile) - 2, round(expected) + radius)
    if start > end:
        return round(expected), 0.0
    candidates: list[tuple[float, int]] = []
    for position in range(start, end + 1):
        gutter = float(np.mean(profile[max(0, position - 2) : min(len(profile), position + 3)]))
        positional = max(0.0, 1.0 - abs(position - expected) / max(1.0, radius))
        score = 0.82 * gutter + 0.18 * positional
        candidates.append((score, position))
    score, position = max(candidates)
    return position, score


def detect_grid(arrays: list[np.ndarray], key_rgb: tuple[int, int, int]) -> GridDetection:
    if not arrays:
        raise ValueError("grid detection needs at least one frame")
    height, width = arrays[0].shape[:2]
    row_profile, col_profile = _separator_profile(arrays, key_rgb)
    x1, sx1 = _best_cut(col_profile, width / 3.0, width / 3.0)
    x2, sx2 = _best_cut(col_profile, 2.0 * width / 3.0, width / 3.0)
    y1, sy1 = _best_cut(row_profile, height / 3.0, height / 3.0)
    y2, sy2 = _best_cut(row_profile, 2.0 * height / 3.0, height / 3.0)
    geometry_ok = x1 < x2 and y1 < y2 and min(x1, x2 - x1, width - x2, y1, y2 - y1, height - y2) >= 2
    confidence = min(sx1, sx2, sy1, sy2) if geometry_ok else 0.0
    return GridDetection(
        x_cuts=(x1, x2),
        y_cuts=(y1, y2),
        confidence=round(confidence, 6),
        scores={"x": [round(sx1, 6), round(sx2, 6)], "y": [round(sy1, 6), round(sy2, 6)]},
    )


def _grid_rectangles(width: int, height: int, detection: GridDetection) -> list[tuple[int, int, int, int]]:
    xs = (0, *detection.x_cuts, width)
    ys = (0, *detection.y_cuts, height)
    return [(xs[col], ys[row], xs[col + 1], ys[row + 1]) for row in range(3) for col in range(3)]


def _write_grid_preview(frame: Path, detection: GridDetection, destination: Path) -> None:
    with Image.open(frame) as source:
        image = source.convert("RGBA")
    draw = ImageDraw.Draw(image)
    for x in detection.x_cuts:
        draw.line((x, 0, x, image.height), fill=(255, 255, 0, 255), width=max(2, image.width // 300))
    for y in detection.y_cuts:
        draw.line((0, y, image.width, y), fill=(255, 255, 0, 255), width=max(2, image.height // 300))
    payload = io.BytesIO()
    image.save(payload, format="PNG", optimize=True)
    atomic_write_or_adopt_bytes(destination, payload.getvalue())


def soft_chroma_key(rgba: np.ndarray, key_rgb: tuple[int, int, int], inner: float = 34.0, outer: float = 92.0) -> np.ndarray:
    """Apply a soft RGB-distance matte plus key-channel edge despill."""
    source = rgba.astype(np.float32)
    rgb = source[..., :3]
    key = np.asarray(key_rgb, dtype=np.float32)
    distance = np.linalg.norm(rgb - key, axis=2)
    matte = np.clip((distance - inner) / (outer - inner), 0.0, 1.0)
    matte *= source[..., 3] / 255.0
    edge = (matte > 0.0) & (matte < 0.98)
    output_rgb = rgb.copy()
    dominant = [index for index, component in enumerate(key_rgb) if component >= 250]
    other = [index for index in range(3) if index not in dominant]
    for channel in dominant:
        if other:
            ceiling = np.max(output_rgb[..., other], axis=2) + 12.0
        else:
            ceiling = np.full(matte.shape, 255.0)
        output_rgb[..., channel] = np.where(edge, np.minimum(output_rgb[..., channel], ceiling), output_rgb[..., channel])
    output = np.empty_like(rgba)
    output[..., :3] = np.clip(output_rgb, 0, 255).astype(np.uint8)
    output[..., 3] = np.round(matte * 255.0).astype(np.uint8)
    output[output[..., 3] == 0, :3] = 0
    return output


def _union_bbox(frames: list[np.ndarray], threshold: int = 12) -> tuple[int, int, int, int] | None:
    combined = np.zeros(frames[0].shape[:2], dtype=bool)
    for frame in frames:
        combined |= frame[..., 3] > threshold
    ys, xs = np.nonzero(combined)
    if len(xs) == 0:
        return None
    left, right = int(xs.min()), int(xs.max()) + 1
    top, bottom = int(ys.min()), int(ys.max()) + 1
    margin = max(2, round(max(right - left, bottom - top) * 0.04))
    return max(0, left - margin), max(0, top - margin), min(combined.shape[1], right + margin), min(combined.shape[0], bottom + margin)


def _pad_512(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> Image.Image:
    left, top, right, bottom = bbox
    cropped = Image.fromarray(frame[top:bottom, left:right], mode="RGBA")
    scale = min(4.0, 480.0 / max(cropped.width, cropped.height))
    if abs(scale - 1.0) > 1e-9:
        cropped = cropped.resize((max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale))), RESAMPLING.LANCZOS)
    canvas = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    canvas.alpha_composite(cropped, ((512 - cropped.width) // 2, (512 - cropped.height) // 2))
    return canvas


def _difference(a: np.ndarray, b: np.ndarray) -> float:
    a_small = np.asarray(Image.fromarray(a, mode="RGBA").resize((64, 64), RESAMPLING.BILINEAR), dtype=np.int16)
    b_small = np.asarray(Image.fromarray(b, mode="RGBA").resize((64, 64), RESAMPLING.BILINEAR), dtype=np.int16)
    foreground = (a_small[..., 3] > 8) | (b_small[..., 3] > 8)
    if not np.any(foreground):
        return 0.0
    return float(np.abs(a_small - b_small)[foreground].mean())


def choose_loop(frames: list[np.ndarray], target_frames: int = 12) -> tuple[list[int], dict[str, Any]]:
    if not frames:
        raise ValueError("cannot choose a loop from no frames")
    if len(frames) == 1:
        raise ValueError("cell has only one decoded frame and no valid motion")
    window = min(target_frames, len(frames))
    choices: list[tuple[float, float, int]] = []
    for start in range(0, len(frames) - window + 1):
        section = frames[start : start + window]
        motion = float(np.mean([_difference(a, b) for a, b in zip(section, section[1:])]))
        endpoint = _difference(section[0], section[-1])
        static_penalty = max(0.0, 1.2 - motion) * 20.0
        choices.append((endpoint + static_penalty, motion, start))
    score, motion, start = min(choices, key=lambda value: value[0])
    if motion < 0.25:
        raise ValueError("cell has no measurable motion")
    natural = score < 26.0 and window == target_frames
    base = list(range(start, start + window))
    if natural:
        return base, {"method": "natural", "start_frame": start, "frames": len(base), "endpoint_score": round(score, 4), "motion_score": round(motion, 4)}

    # Recorded deterministic fallback: forward then backward without duplicate turns.
    pingpong = base + base[-2:0:-1]
    if not pingpong:
        pingpong = [start, start + 1]
    indices = [pingpong[index % len(pingpong)] for index in range(target_frames)]
    return indices, {"method": "ping_pong", "start_frame": start, "frames": len(indices), "endpoint_score": round(score, 4), "motion_score": round(motion, 4)}


def _parse_manual_grid(value: str, width: int, height: int) -> GridDetection:
    try:
        x1, x2, y1, y2 = (int(part.strip()) for part in value.split(","))
    except Exception as exc:
        raise ValueError("--grid must be x1,x2,y1,y2") from exc
    if not (0 < x1 < x2 < width and 0 < y1 < y2 < height):
        raise ValueError("manual grid cuts are outside the video")
    return GridDetection((x1, x2), (y1, y2), 1.0, {"x": [1.0, 1.0], "y": [1.0, 1.0]})


def _safe_video_suffix(video: Path) -> str:
    suffix = video.suffix.lower()
    return suffix if suffix in {".mp4", ".mov", ".mkv", ".webm", ".avi"} else ".video"


def _next_owned_video(source_dir: Path, suffix: str) -> Path:
    for index in range(1, 100):
        infix = "" if index == 1 else f"-{index}"
        candidate = source_dir / f"input-video{infix}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise FileExistsError("could not allocate a unique job-owned video path")


def _owned_video_with_hash(source_dir: Path, video_hash: str) -> Path | None:
    """Find a safe byte-identical orphan from a failed bind attempt."""

    if not source_dir.is_dir():
        return None
    for candidate in sorted(source_dir.glob("input-video*")):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        if sha256_file(candidate) == video_hash:
            return candidate
    return None


def _tool_version(executable: str) -> str:
    """Return a short, bounded FFmpeg-family version string for the report."""

    try:
        completed = subprocess.run(
            [executable, "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    first_line = (completed.stdout or completed.stderr or "unknown").splitlines()[0]
    return first_line[:200]


def _write_failure_diagnostic(
    frame: Path,
    rectangle: tuple[int, int, int, int],
    destination: Path,
    index: int,
) -> None:
    """Write a bounded raw-crop locator for one rejected cell."""

    with Image.open(frame) as source:
        diagnostic = source.convert("RGB").crop(rectangle)
    draw = ImageDraw.Draw(diagnostic)
    border = max(2, min(diagnostic.size) // 80)
    draw.rectangle(
        (0, 0, diagnostic.width - 1, diagnostic.height - 1),
        outline=(255, 32, 32),
        width=border,
    )
    draw.rectangle((4, 4, 54, 28), fill=(0, 0, 0))
    draw.text((10, 9), f"#{index:02d}", fill=(255, 255, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    diagnostic.save(destination, format="PNG", optimize=True)


def process_job(
    job_path: Path,
    video: Path,
    *,
    fps: int = 12,
    manual_grid: str | None = None,
    accept_low_confidence: bool = False,
    replace_video: bool = False,
) -> dict[str, Any]:
    job_path = (job_path / "job.json" if job_path.is_dir() else job_path).resolve()
    if fps != 12:
        raise ValueError("v0.1 video processing is fixed at 12fps")
    job = load_job(job_path)
    if job.get("status") not in {"waiting_for_video", "video_review_required"}:
        raise ValueError("video processing requires waiting_for_video or video_review_required state")
    source_video = video.resolve()
    if not source_video.is_file():
        raise FileNotFoundError(f"video does not exist: {source_video}")
    if source_video.stat().st_size > 512 * 1024 * 1024:
        raise ValueError("video exceeds the 512 MiB file-size safety limit")
    video_hash = sha256_file(source_video)
    recorded = job.get("video_input")
    replacing = False
    if isinstance(recorded, dict) and recorded.get("sha256") != video_hash:
        if not (replace_video and job.get("status") == "video_review_required"):
            raise ValueError("uploaded video hash does not match this unfinished job")
        replacing = True
    verify_artifact_record(job_path, job["artifacts"].get("transparent_sheet"), "transparent sheet")
    verify_artifact_record(job_path, job["artifacts"].get("chroma_sheet"), "chroma sheet")
    video_prompt = resolve_job_path(job_path, job["paths"]["video_prompt"])
    if not video_prompt.is_file() or "{{CHROMA_" in video_prompt.read_text(encoding="utf-8"):
        raise ValueError("prepared video prompt is missing or still contains chroma placeholders")
    if (
        job.get("status") == "video_review_required"
        and not replacing
        and not manual_grid
        and not accept_low_confidence
    ):
        preview_relative = (job.get("qa", {}).get("video_grid") or {}).get("preview")
        message = f"grid confirmation is still required; inspect {preview_relative or 'the stored preview'}"
        raise ReviewRequired(message)
    source_dir = resolve_job_path(job_path, "source")
    source_dir.mkdir(parents=True, exist_ok=True)
    if recorded and not replacing:
        owned_video = resolve_job_path(job_path, recorded["path"])
        if not owned_video.is_file() or sha256_file(owned_video) != video_hash:
            raise ValueError("recorded job video is missing or changed")
        decode_video = owned_video
    else:
        owned_video = _owned_video_with_hash(source_dir, video_hash) or _next_owned_video(
            source_dir, _safe_video_suffix(source_video)
        )
        decode_video = source_video

    ffmpeg, ffprobe = find_ffmpeg("ffmpeg"), find_ffmpeg("ffprobe")
    metadata = _probe_video(ffprobe, decode_video)
    key_rgb = _chroma_rgb(job)
    work_dir = resolve_job_path(job_path, "work")
    work_dir.mkdir(parents=True, exist_ok=True)
    qa_dir = resolve_job_path(job_path, job["paths"]["qa_dir"])

    with tempfile.TemporaryDirectory(prefix="da-video-", dir=work_dir) as temp_name:
        temp_root = Path(temp_name)
        frame_paths = _decode_once(ffmpeg, decode_video, temp_root / "decoded", fps)
        if not recorded or replacing:
            if not owned_video.exists():
                atomic_copy(source_video, owned_video, overwrite=False)
            if replacing and isinstance(recorded, dict):
                job.setdefault("video_history", []).append(recorded)
            job["video_input"] = {
                "path": relative_job_path(job_path, owned_video),
                "sha256": video_hash,
            }
            save_job_atomic(job_path, job)
        sampled = _sample_arrays(frame_paths)
        if manual_grid:
            detection = _parse_manual_grid(manual_grid, metadata["width"], metadata["height"])
        else:
            detection = detect_grid(sampled, key_rgb)
        if detection.confidence < 0.70 and not accept_low_confidence:
            preview = qa_dir / f"video-grid-preview-{video_hash[:8]}.png"
            _write_grid_preview(frame_paths[len(frame_paths) // 2], detection, preview)
            update_status(
                job_path,
                job,
                "video_review_required",
                qa={"video_grid": {"ok": False, "confidence": detection.confidence, "preview": relative_job_path(job_path, preview)}},
            )
            raise ReviewRequired(f"grid confidence {detection.confidence:.3f}; inspect {preview}")

        rectangles = _grid_rectangles(metadata["width"], metadata["height"], detection)
        contents = job.get("contents") or []
        if len(contents) != 9:
            raise ValueError("job must contain exactly nine content items")
        successes: list[dict[str, Any]] = []
        item_reports: list[dict[str, Any]] = []
        publications: list[tuple[Path, Path]] = []
        for index, (content, rectangle) in enumerate(zip(contents, rectangles), 1):
            left, top, right, bottom = rectangle
            try:
                keyed = _load_keyed_cell_frames(frame_paths, rectangle, key_rgb)
                bbox = _union_bbox(keyed)
                if bbox is None:
                    raise CellQualityError("no foreground survived chroma keying")
                if (
                    bbox[2] - bbox[0] < max(4, round((right - left) * 0.08))
                    or bbox[3] - bbox[1] < max(4, round((bottom - top) * 0.08))
                ):
                    raise CellQualityError("foreground is too small to be a complete sticker")
                try:
                    loop_indices, loop_report = choose_loop(keyed, target_frames=fps)
                except ValueError as exc:
                    raise CellQualityError(str(exc)) from exc
                frame_dir = temp_root / f"cell-{index:02d}"
                frame_dir.mkdir()
                for output_index, source_index in enumerate(loop_indices):
                    _pad_512(keyed[source_index], bbox).save(
                        frame_dir / f"frame-{output_index:03d}.png"
                    )
                slug = str(content["slug"])
                filename = f"{slug}.gif"
                output = resolve_job_path(
                    job_path, f"{job['paths']['gifs_dir']}/{filename}"
                )
                staged_output = temp_root / "encoded" / filename
                properties = _encode_gif(ffmpeg, frame_dir, staged_output, fps)
                artifact = {
                    "index": index,
                    "path": relative_job_path(job_path, output),
                    "sha256": sha256_file(staged_output),
                    "media": properties,
                }
                successes.append(artifact)
                publications.append((staged_output, output))
                item_reports.append(
                    {
                        "index": index,
                        "display_name": content.get("display_name"),
                        "status": "success",
                        "loop": loop_report,
                        "crop": list(bbox),
                        "gif": properties,
                    }
                )
            except CellQualityError as exc:
                diagnostic_rel = f"{job['paths']['qa_dir']}/video-cell-{index:02d}-diagnostic.png"
                diagnostic_final = resolve_job_path(job_path, diagnostic_rel)
                diagnostic_staged = temp_root / "diagnostics" / diagnostic_final.name
                _write_failure_diagnostic(
                    frame_paths[len(frame_paths) // 2], rectangle, diagnostic_staged, index
                )
                publications.append((diagnostic_staged, diagnostic_final))
                item_reports.append(
                    {
                        "index": index,
                        "display_name": content.get("display_name"),
                        "status": "failed",
                        "error": str(exc),
                        "grid_rect": list(rectangle),
                        "diagnostic": diagnostic_rel,
                    }
                )

        report = {
            "version": 1,
            "route": "video",
            "video": {
                "path": relative_job_path(job_path, owned_video),
                "sha256": video_hash,
                **metadata,
            },
            "timeline": {
                "strategy": "ffmpeg fps filter from source timestamps",
                "fps": fps,
                "decoded_frames": len(frame_paths),
            },
            "tools": {"ffmpeg": _tool_version(ffmpeg), "ffprobe": _tool_version(ffprobe)},
            "grid": {
                "x_cuts": list(detection.x_cuts),
                "y_cuts": list(detection.y_cuts),
                "confidence": detection.confidence,
                "scores": detection.scores,
                "manual": bool(manual_grid),
            },
            "chroma": {
                "rgb": list(key_rgb),
                "soft_key_inner": 34,
                "soft_key_outer": 92,
                "despill": True,
            },
            "items": item_reports,
            "summary": {
                "succeeded": len(successes),
                "failed": 9 - len(successes),
                "partial_delivery": 0 < len(successes) < 9,
            },
        }
        report_path = resolve_job_path(job_path, job["paths"]["processing_report"])
        staged_report = temp_root / "processing-report.json"
        atomic_write_json(staged_report, report, overwrite=False)
        publications.append((staged_report, report_path))
        publish_files_atomically(publications)

    job["artifacts"]["gifs"] = successes
    job.setdefault("options", {})["route"] = "video"
    qa = {"video_processing": {"ok": bool(successes), "succeeded": len(successes), "failed": 9 - len(successes), "report": relative_job_path(job_path, report_path)}}
    if successes:
        update_status(job_path, job, "video_processed", qa=qa)
    else:
        update_status(job_path, job, "video_failed", qa=qa, error={"stage": "process_video", "message": "all nine items failed"})
        raise RuntimeError("all nine items failed; no empty package will be created")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path, help="Explicit job.json; jobs are never guessed")
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--grid", help="Approved manual cuts as x1,x2,y1,y2")
    parser.add_argument("--accept-low-confidence", action="store_true", help="Use detected cuts despite low confidence")
    parser.add_argument(
        "--replace-video",
        action="store_true",
        help="after video_review_required, bind a different validated upload without deleting the old one",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        report = process_job(
            args.job.resolve(),
            args.video.resolve(),
            fps=args.fps,
            manual_grid=args.grid,
            accept_low_confidence=args.accept_low_confidence,
            replace_video=args.replace_video,
        )
    except ReviewRequired as exc:
        print(json.dumps({"status": "video_review_required", "message": str(exc)}, ensure_ascii=False))
        return 2
    except Exception as exc:
        raise SystemExit(f"process_video: {exc}") from exc
    print(json.dumps({"status": "video_processed", "summary": report["summary"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
