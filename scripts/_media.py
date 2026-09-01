#!/usr/bin/env python3
"""Shared deterministic image and GIF helpers."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from collections import deque
from itertools import chain
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image


LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS", Image.LANCZOS)
BICUBIC = getattr(getattr(Image, "Resampling", Image), "BICUBIC", Image.BICUBIC)
MEDIANCUT = getattr(getattr(Image, "Quantize", Image), "MEDIANCUT", Image.MEDIANCUT)


SCREEN_COLORS: Dict[str, Dict[str, object]] = {
    "green": {"name_zh": "纯绿色", "rgb": (0, 255, 0), "hex": "#00FF00"},
    "blue": {"name_zh": "纯蓝色", "rgb": (0, 0, 255), "hex": "#0000FF"},
    "magenta": {"name_zh": "纯洋红色", "rgb": (255, 0, 255), "hex": "#FF00FF"},
    "white": {"name_zh": "纯白色", "rgb": (255, 255, 255), "hex": "#FFFFFF"},
}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_rgba(path: Path) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        return image.convert("RGBA")


def alpha_stats(image: Image.Image) -> Dict[str, float]:
    alpha = np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, 3]
    return {
        "min": int(alpha.min()),
        "max": int(alpha.max()),
        "mean": round(float(alpha.mean()), 4),
        "transparent_fraction": round(float((alpha <= 8).mean()), 6),
        "partial_fraction": round(float(((alpha > 8) & (alpha < 247)).mean()), 6),
        "opaque_fraction": round(float((alpha >= 247).mean()), 6),
    }


def estimate_background_color(images: Sequence[Image.Image], patch: int = 8) -> Tuple[int, int, int]:
    samples: List[np.ndarray] = []
    for image in images:
        rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
        height, width = rgb.shape[:2]
        size = max(1, min(patch, height // 5, width // 5))
        samples.extend(
            [
                rgb[:size, :size].reshape(-1, 3),
                rgb[:size, width - size :].reshape(-1, 3),
                rgb[height - size :, :size].reshape(-1, 3),
                rgb[height - size :, width - size :].reshape(-1, 3),
            ]
        )
    pixels = np.concatenate(samples, axis=0).astype(np.float32)
    median = np.median(pixels, axis=0)
    return tuple(int(round(value)) for value in median)  # type: ignore[return-value]


def _border_pixels(rgb: np.ndarray) -> np.ndarray:
    return np.concatenate((rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]), axis=0)


def border_consistency(image: Image.Image, color: Sequence[int], threshold: float = 45.0) -> float:
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    border = _border_pixels(rgb)
    distance = np.linalg.norm(border - np.asarray(color, dtype=np.float32), axis=1)
    return float((distance <= threshold).mean())


def edge_connected(mask: np.ndarray) -> np.ndarray:
    """Return mask pixels connected to any outer edge with 4-neighbour connectivity."""
    if mask.ndim != 2:
        raise ValueError("edge_connected expects a 2-D mask")
    height, width = mask.shape
    connected = np.zeros((height, width), dtype=bool)
    queue: deque[Tuple[int, int]] = deque()

    for x in range(width):
        if mask[0, x]:
            connected[0, x] = True
            queue.append((0, x))
        if height > 1 and mask[height - 1, x] and not connected[height - 1, x]:
            connected[height - 1, x] = True
            queue.append((height - 1, x))
    for y in range(1, height - 1):
        if mask[y, 0]:
            connected[y, 0] = True
            queue.append((y, 0))
        if width > 1 and mask[y, width - 1] and not connected[y, width - 1]:
            connected[y, width - 1] = True
            queue.append((y, width - 1))

    while queue:
        y, x = queue.popleft()
        if y and mask[y - 1, x] and not connected[y - 1, x]:
            connected[y - 1, x] = True
            queue.append((y - 1, x))
        if y + 1 < height and mask[y + 1, x] and not connected[y + 1, x]:
            connected[y + 1, x] = True
            queue.append((y + 1, x))
        if x and mask[y, x - 1] and not connected[y, x - 1]:
            connected[y, x - 1] = True
            queue.append((y, x - 1))
        if x + 1 < width and mask[y, x + 1] and not connected[y, x + 1]:
            connected[y, x + 1] = True
            queue.append((y, x + 1))
    return connected


def remove_connected_background(
    image: Image.Image,
    key_color: Sequence[int],
    threshold: float = 55.0,
    feather: float = 45.0,
) -> Tuple[Image.Image, Dict[str, float]]:
    """Remove only key-like pixels connected to the image edge.

    `threshold` is fully transparent. The next `feather` RGB-distance units
    form a soft antialiasing band, but only when connected to an outer edge.
    """
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    rgb = rgba[:, :, :3].astype(np.float32)
    original_alpha = rgba[:, :, 3].astype(np.float32)
    distance = np.linalg.norm(rgb - np.asarray(key_color, dtype=np.float32), axis=2)
    outer = threshold + max(feather, 1.0)
    connected = edge_connected(distance <= outer)
    key_alpha = np.clip((distance - threshold) / max(feather, 1.0), 0.0, 1.0) * 255.0
    repaired_alpha = original_alpha.copy()
    repaired_alpha[connected] = np.minimum(repaired_alpha[connected], key_alpha[connected])
    rgba[:, :, 3] = np.rint(repaired_alpha).astype(np.uint8)
    removed = connected & (repaired_alpha <= 8)
    return Image.fromarray(rgba, "RGBA"), {
        "edge_connected_fraction": round(float(connected.mean()), 6),
        "fully_removed_fraction": round(float(removed.mean()), 6),
        "threshold": float(threshold),
        "feather": float(feather),
    }


def screen_scores(image: Image.Image) -> Dict[str, Dict[str, float]]:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    visible = rgba[:, :, 3] >= 32
    pixels = rgba[:, :, :3][visible].astype(np.float32)
    if pixels.size == 0:
        raise ValueError("cannot choose a screen color for an empty transparent image")
    if len(pixels) > 100_000:
        step = int(math.ceil(len(pixels) / 100_000))
        pixels = pixels[::step]

    results: Dict[str, Dict[str, float]] = {}
    for key, definition in SCREEN_COLORS.items():
        color = np.asarray(definition["rgb"], dtype=np.float32)
        distance = np.linalg.norm(pixels - color, axis=1)
        collision = float((distance < 72.0).mean())
        p10 = float(np.percentile(distance, 10))
        mean = float(distance.mean())
        white_penalty = 24.0 if key == "white" else 0.0
        score = p10 + mean * 0.20 - collision * 420.0 - white_penalty
        results[key] = {
            "score": round(score, 4),
            "collision_fraction": round(collision, 6),
            "distance_p10": round(p10, 4),
            "distance_mean": round(mean, 4),
        }
    return results


def choose_screen(image: Image.Image, requested: str = "auto") -> Tuple[str, Dict[str, Dict[str, float]]]:
    scores = screen_scores(image)
    if requested != "auto":
        if requested not in SCREEN_COLORS:
            raise ValueError("unknown screen color: %s" % requested)
        return requested, scores
    selected = max(scores, key=lambda name: scores[name]["score"])
    return selected, scores


def composite_on_color(image: Image.Image, color: Sequence[int]) -> Image.Image:
    rgba = image.convert("RGBA")
    background = Image.new("RGBA", rgba.size, tuple(color) + (255,))
    return Image.alpha_composite(background, rgba).convert("RGB")


def _compress_ranges(indices: np.ndarray) -> List[Tuple[int, int]]:
    if indices.size == 0:
        return []
    ranges: List[Tuple[int, int]] = []
    start = previous = int(indices[0])
    for raw in indices[1:]:
        value = int(raw)
        if value == previous + 1:
            previous = value
        else:
            ranges.append((start, previous))
            start = previous = value
    ranges.append((start, previous))
    return ranges


def _bounds_from_background_ratio(
    ratio: np.ndarray,
    parts: int,
    minimum_ratio: float,
    minimum_gap: int,
) -> Tuple[List[int], float, List[str]]:
    length = len(ratio)
    warnings: List[str] = []
    ranges = _compress_ranges(np.where(ratio >= minimum_ratio)[0])
    ranges = [
        item
        for item in ranges
        if item[0] > 0 and item[1] < length - 1 and item[1] - item[0] + 1 >= minimum_gap
    ]
    selected: List[Tuple[int, int]] = []
    used: set[int] = set()
    for part in range(1, parts):
        expected = length * part / parts
        ranked = sorted(
            enumerate(ranges),
            key=lambda pair: (
                abs(((pair[1][0] + pair[1][1]) / 2.0) - expected)
                - 0.15 * (pair[1][1] - pair[1][0] + 1)
            ),
        )
        choice: Optional[Tuple[int, int, int]] = None
        for index, item in ranked:
            midpoint = (item[0] + item[1]) / 2.0
            if index not in used and abs(midpoint - expected) <= length * 0.14:
                choice = (index, item[0], item[1])
                break
        if choice is None:
            warnings.append("未能可靠找到第 %d 条内部网格缝，已退化为等分。" % part)
            return [round(index * length / parts) for index in range(parts + 1)], 0.5, warnings
        used.add(choice[0])
        selected.append((choice[1], choice[2]))

    selected.sort()
    mids = [(start + end) // 2 for start, end in selected]
    confidence = min(0.99, 0.86 + sum(end - start + 1 for start, end in selected) / max(length, 1) * 0.4)
    return [0] + mids + [length], round(confidence, 4), warnings


def detect_alpha_grid(
    image: Image.Image,
    rows: int = 3,
    cols: int = 3,
    alpha_threshold: int = 8,
) -> Tuple[List[int], List[int], float, List[str]]:
    alpha = np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, 3]
    background = alpha <= alpha_threshold
    col_ratio = background.mean(axis=0)
    row_ratio = background.mean(axis=1)
    minimum_gap = max(2, round(min(alpha.shape) * 0.004))
    col_bounds, col_confidence, col_warnings = _bounds_from_background_ratio(
        col_ratio, cols, 0.985, minimum_gap
    )
    row_bounds, row_confidence, row_warnings = _bounds_from_background_ratio(
        row_ratio, rows, 0.985, minimum_gap
    )
    return col_bounds, row_bounds, min(col_confidence, row_confidence), col_warnings + row_warnings


def detect_color_grid(
    images: Sequence[Image.Image],
    key_color: Sequence[int],
    rows: int = 3,
    cols: int = 3,
    threshold: float = 72.0,
) -> Tuple[List[int], List[int], float, List[str]]:
    if not images:
        raise ValueError("at least one image is required for grid detection")
    col_ratios: List[np.ndarray] = []
    row_ratios: List[np.ndarray] = []
    key = np.asarray(key_color, dtype=np.float32)
    for image in images:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
        near = np.linalg.norm(rgb - key, axis=2) <= threshold
        col_ratios.append(near.mean(axis=0))
        row_ratios.append(near.mean(axis=1))
    col_ratio = np.stack(col_ratios).min(axis=0)
    row_ratio = np.stack(row_ratios).min(axis=0)
    height, width = np.asarray(images[0]).shape[:2]
    minimum_gap = max(2, round(min(height, width) * 0.004))
    col_bounds, col_confidence, col_warnings = _bounds_from_background_ratio(
        col_ratio, cols, 0.94, minimum_gap
    )
    row_bounds, row_confidence, row_warnings = _bounds_from_background_ratio(
        row_ratio, rows, 0.94, minimum_gap
    )
    return col_bounds, row_bounds, min(col_confidence, row_confidence), col_warnings + row_warnings


def grid_cells(col_bounds: Sequence[int], row_bounds: Sequence[int]) -> List[Dict[str, int]]:
    cells: List[Dict[str, int]] = []
    for row in range(len(row_bounds) - 1):
        for col in range(len(col_bounds) - 1):
            left, right = col_bounds[col], col_bounds[col + 1]
            top, bottom = row_bounds[row], row_bounds[row + 1]
            cells.append(
                {
                    "row": row,
                    "col": col,
                    "x": left,
                    "y": top,
                    "width": right - left,
                    "height": bottom - top,
                }
            )
    return cells


def fit_rgba(image: Image.Image, size: int = 512, trim: bool = True, padding_fraction: float = 0.08) -> Image.Image:
    rgba = image.convert("RGBA")
    if trim:
        alpha = rgba.getchannel("A")
        bbox = alpha.point(lambda value: 255 if value > 8 else 0).getbbox()
        if bbox is None:
            raise ValueError("empty transparent cell")
        left, top, right, bottom = bbox
        content_size = max(right - left, bottom - top)
        padding = max(2, round(content_size * padding_fraction))
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(rgba.width, right + padding)
        bottom = min(rgba.height, bottom + padding)
        rgba = rgba.crop((left, top, right, bottom))

    available = max(1, size - 2 * max(2, round(size * 0.04)))
    scale = min(available / rgba.width, available / rgba.height)
    width = max(1, round(rgba.width * scale))
    height = max(1, round(rgba.height * scale))
    resized = rgba.resize((width, height), LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(resized, ((size - width) // 2, (size - height) // 2))
    return canvas


def split_sheet(
    image: Image.Image,
    col_bounds: Sequence[int],
    row_bounds: Sequence[int],
    size: int = 512,
) -> List[Image.Image]:
    outputs: List[Image.Image] = []
    for cell in grid_cells(col_bounds, row_bounds):
        crop = image.crop(
            (
                cell["x"],
                cell["y"],
                cell["x"] + cell["width"],
                cell["y"] + cell["height"],
            )
        )
        outputs.append(fit_rgba(crop, size=size, trim=True))
    return outputs


def rgba_frames_to_gif(
    frames: Sequence[Image.Image],
    output: Path,
    duration_ms: Union[int, List[int]],
    alpha_threshold: int = 96,
) -> None:
    if len(frames) < 2:
        raise ValueError("an animated GIF requires at least two frames")
    paletted: List[Image.Image] = []
    transparent_index = 255
    for frame in frames:
        rgba = frame.convert("RGBA")
        alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
        quantized = rgba.convert("RGB").quantize(colors=255, method=MEDIANCUT)
        indices = np.asarray(quantized, dtype=np.uint8).copy()
        indices[alpha < alpha_threshold] = transparent_index
        converted = Image.fromarray(indices, mode="P")
        palette = list(chain(quantized.getpalette() or [], [0] * 768))[:768]
        palette[transparent_index * 3 : transparent_index * 3 + 3] = [0, 255, 0]
        converted.putpalette(palette)
        converted.info["transparency"] = transparent_index
        converted.info["disposal"] = 2
        paletted.append(converted)
    output.parent.mkdir(parents=True, exist_ok=True)
    paletted[0].save(
        output,
        save_all=True,
        append_images=paletted[1:],
        duration=duration_ms,
        loop=0,
        transparency=transparent_index,
        disposal=2,
        optimize=False,
    )


def frame_durations_ms(frame_count: int, fps: float) -> List[int]:
    if frame_count < 1:
        raise ValueError("frame_count must be at least 1")
    if fps < 1:
        raise ValueError("fps must be at least 1")
    boundaries = [round(index * 1000 / fps) for index in range(frame_count + 1)]
    return [max(1, right - left) for left, right in zip(boundaries, boundaries[1:])]


def choose_gif_alpha_threshold(
    images: Sequence[Image.Image], candidates: Sequence[int] = (96, 128, 160, 192)
) -> Tuple[int, Dict[str, object]]:
    if not images:
        raise ValueError("GIF threshold selection requires at least one frame")
    if not candidates or any(value < 1 or value > 254 for value in candidates):
        raise ValueError("GIF alpha threshold candidates must be between 1 and 254")
    scores: List[Dict[str, object]] = []
    for threshold in candidates:
        fringe = 0.0
        erosion = 0.0
        coverages: List[float] = []
        for image in images:
            alpha = np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, 3]
            visible = alpha >= threshold
            intended = alpha >= 128
            fringe += float(np.mean(visible & (alpha < 128)))
            erosion += float(np.count_nonzero(intended & ~visible) / max(1, np.count_nonzero(intended)))
            coverages.append(float(np.mean(visible)))
        score = 2.0 * fringe / len(images) + 1.25 * erosion / len(images) + 0.25 * float(np.std(coverages))
        scores.append({"threshold": int(threshold), "score": round(score, 8)})
    selected = min(scores, key=lambda item: (float(item["score"]), abs(int(item["threshold"]) - 128)))
    return int(selected["threshold"]), {"selected": selected, "candidates": scores}


def encode_gif_images(
    images: Sequence[Image.Image],
    output: Path,
    fps: float,
    max_colors: int = 192,
) -> Dict[str, object]:
    if len(images) < 2:
        raise ValueError("animated GIF requires at least two frames")
    if max_colors < 2 or max_colors > 255:
        raise ValueError("max_colors must be between 2 and 255")
    threshold, threshold_report = choose_gif_alpha_threshold(images)
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_error: Optional[str] = None
    if shutil.which("ffmpeg"):
        with tempfile.TemporaryDirectory(prefix="da-keypose-gif-") as temporary_name:
            temporary = Path(temporary_name)
            for index, image in enumerate(images, start=1):
                image.convert("RGBA").save(temporary / ("%04d.png" % index))
            command = [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-framerate",
                str(fps),
                "-i",
                str(temporary / "%04d.png"),
                "-vf",
                "split[s0][s1];[s0]palettegen=reserve_transparent=1:max_colors=%d[p];"
                "[s1][p]paletteuse=dither=none:diff_mode=rectangle:alpha_threshold=%d" % (max_colors, threshold),
                "-loop",
                "0",
                str(output),
            ]
            completed = subprocess.run(command, capture_output=True, text=True)
            if completed.returncode == 0 and output.is_file() and output.stat().st_size > 0:
                return {
                    "encoder": "ffmpeg-two-stage-palette",
                    "fps": fps,
                    "max_colors": max_colors,
                    "alpha_threshold": threshold,
                    "threshold_selection": threshold_report,
                    "warning": None,
                }
            ffmpeg_error = completed.stderr.strip() or "ffmpeg returned no output"
    rgba_frames_to_gif(
        images,
        output,
        duration_ms=frame_durations_ms(len(images), fps),
        alpha_threshold=threshold,
    )
    return {
        "encoder": "pillow-fallback",
        "fps": fps,
        "max_colors": 255,
        "alpha_threshold": threshold,
        "threshold_selection": threshold_report,
        "warning": ffmpeg_error or "ffmpeg unavailable; used Pillow fallback",
    }


def encode_webp_images(images: Sequence[Image.Image], output: Path, fps: float) -> None:
    if len(images) < 2:
        raise ValueError("animated WebP requires at least two frames")
    converted = [image.convert("RGBA") for image in images]
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        converted[0].save(
            output,
            save_all=True,
            append_images=converted[1:],
            duration=frame_durations_ms(len(converted), fps),
            loop=0,
            lossless=True,
            method=4,
        )
    finally:
        for image in converted:
            image.close()


def inspect_gif(path: Path) -> Dict[str, object]:
    with Image.open(path) as image:
        frame_count = int(getattr(image, "n_frames", 1))
        loop = image.info.get("loop")
        size = [image.width, image.height]
        alpha_min = 255
        alpha_max = 0
        nonempty = False
        durations: List[int] = []
        for index in range(frame_count):
            image.seek(index)
            durations.append(int(image.info.get("duration", 0)))
            alpha = np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, 3]
            alpha_min = min(alpha_min, int(alpha.min()))
            alpha_max = max(alpha_max, int(alpha.max()))
            nonempty = nonempty or bool((alpha > 8).any())
    return {
        "path": str(path),
        "size": size,
        "frames": frame_count,
        "loop": loop,
        "duration_ms": sum(durations),
        "alpha_min": alpha_min,
        "alpha_max": alpha_max,
        "has_transparency": alpha_min < 255,
        "nonempty": nonempty,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def numbered_files(directory: Path, suffix: str) -> List[Path]:
    return [directory / ("%02d%s" % (index, suffix)) for index in range(1, 10)]
