"""Deterministic final-media validation shared by encoders and packaging."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, UnidentifiedImageError


class MediaQAError(ValueError):
    """Raised when a deliverable violates the v0.1 media contract."""


def inspect_gif(
    path: str | Path,
    *,
    expected_size: int = 512,
    expected_frames: int = 12,
    expected_fps: int = 12,
) -> dict[str, Any]:
    """Validate transparency, dimensions, timeline, loop, and safe visible bounds."""

    media = Path(path)
    if not media.is_file() or media.is_symlink():
        raise MediaQAError(f"GIF is missing or is a symlink: {media.name}")
    if media.stat().st_size <= 0 or media.stat().st_size > 8 * 1024 * 1024:
        raise MediaQAError(f"GIF size is outside the 0–8 MiB contract: {media.name}")
    try:
        with Image.open(media) as image:
            if image.format != "GIF":
                raise MediaQAError(f"artifact is not a GIF: {media.name}")
            if image.size != (expected_size, expected_size):
                raise MediaQAError(f"GIF must be {expected_size}x{expected_size}: {media.name}")
            if image.n_frames != expected_frames:
                raise MediaQAError(
                    f"GIF must contain {expected_frames} frames; received {image.n_frames}: {media.name}"
                )
            if image.info.get("loop") != 0:
                raise MediaQAError(f"GIF must loop forever: {media.name}")
            if "transparency" not in image.info:
                raise MediaQAError(f"GIF has no transparent palette index: {media.name}")
            duration_ms = 0
            union = np.zeros((expected_size, expected_size), dtype=bool)
            transparent_seen = False
            for frame_index in range(image.n_frames):
                image.seek(frame_index)
                duration = int(image.info.get("duration") or 0)
                if duration <= 0:
                    raise MediaQAError(f"GIF frame {frame_index} has no duration: {media.name}")
                duration_ms += duration
                rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
                alpha = rgba[..., 3]
                visible = alpha > 8
                if not np.any(visible):
                    raise MediaQAError(f"GIF frame {frame_index} is empty: {media.name}")
                union |= visible
                transparent_seen |= bool(np.any(alpha == 0))
            if not transparent_seen:
                raise MediaQAError(f"GIF has no actual transparent pixels: {media.name}")
            target_ms = 1000.0 * expected_frames / expected_fps
            if not target_ms * 0.85 <= duration_ms <= target_ms * 1.15:
                raise MediaQAError(
                    f"GIF duration {duration_ms}ms is outside the loop contract: {media.name}"
                )
            ys, xs = np.nonzero(union)
            bbox = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
            clearance = min(bbox[0], bbox[1], expected_size - bbox[2], expected_size - bbox[3])
            if clearance < 1:
                raise MediaQAError(f"GIF artwork touches the canvas edge: {media.name}")
            return {
                "format": "GIF",
                "width": expected_size,
                "height": expected_size,
                "frames": image.n_frames,
                "fps": expected_fps,
                "duration_ms": duration_ms,
                "loop": 0,
                "transparent": True,
                "visible_bbox": bbox,
                "bytes": media.stat().st_size,
            }
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaQAError(f"GIF cannot be decoded: {media.name}") from exc


def inspect_static_png(path: str | Path, *, expected_size: int = 512) -> dict[str, Any]:
    """Validate a normalized static transparent sticker PNG."""

    media = Path(path)
    if not media.is_file() or media.is_symlink():
        raise MediaQAError(f"PNG is missing or is a symlink: {media.name}")
    try:
        with Image.open(media) as image:
            if image.format != "PNG" or image.size != (expected_size, expected_size):
                raise MediaQAError(f"static sticker must be a {expected_size}x{expected_size} PNG: {media.name}")
            if "A" not in image.getbands():
                raise MediaQAError(f"static sticker has no Alpha channel: {media.name}")
            alpha = np.asarray(image.convert("RGBA"), dtype=np.uint8)[..., 3]
            if not np.any(alpha == 0) or not np.any(alpha > 8):
                raise MediaQAError(f"static sticker needs visible and transparent pixels: {media.name}")
            ys, xs = np.nonzero(alpha > 8)
            bbox = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
            if min(bbox[0], bbox[1], expected_size - bbox[2], expected_size - bbox[3]) < 1:
                raise MediaQAError(f"static sticker touches the canvas edge: {media.name}")
            return {"format": "PNG", "width": expected_size, "height": expected_size, "transparent": True, "visible_bbox": bbox}
    except (UnidentifiedImageError, OSError) as exc:
        raise MediaQAError(f"PNG cannot be decoded: {media.name}") from exc

