#!/usr/bin/env python3
"""Split a validated master, normalize cells, and build a collision-safe chroma sheet."""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, UnidentifiedImageError

RESAMPLING = getattr(Image, "Resampling", Image)

try:
    from ._core import (
        JobError,
        atomic_write_bytes,
        load_job,
        publish_files_atomically,
        relative_job_path,
        resolve_job_path,
        sha256_file,
        update_status,
        verify_artifact_record,
    )
except ImportError:  # pragma: no cover
    from _core import (  # type: ignore
        JobError,
        atomic_write_bytes,
        load_job,
        publish_files_atomically,
        relative_job_path,
        resolve_job_path,
        sha256_file,
        update_status,
        verify_artifact_record,
    )


CHROMA_CANDIDATES: tuple[dict[str, Any], ...] = (
    {"name": "green", "display_name": "green", "hex": "#00FF00", "rgb": (0, 255, 0)},
    {"name": "blue", "display_name": "blue", "hex": "#0000FF", "rgb": (0, 0, 255)},
    {
        "name": "magenta",
        "display_name": "magenta",
        "hex": "#FF00FF",
        "rgb": (255, 0, 255),
    },
)

_NAMED_CHROMA = {
    "green": "#00FF00",
    "绿": "#00FF00",
    "绿色": "#00FF00",
    "blue": "#0000FF",
    "蓝": "#0000FF",
    "蓝色": "#0000FF",
    "magenta": "#FF00FF",
    "fuchsia": "#FF00FF",
    "洋红": "#FF00FF",
    "品红": "#FF00FF",
    "洋红色": "#FF00FF",
}


def _png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _write_png(path: Path, image: Image.Image, *, overwrite: bool = False) -> Path:
    return atomic_write_bytes(path, _png_bytes(image), overwrite=overwrite)


def _grid_edges(length: int) -> list[int]:
    return [round(index * length / 3) for index in range(4)]


def trim_transparency(
    image: Image.Image, *, alpha_threshold: int = 0
) -> Image.Image:
    """Crop transparent borders using Alpha while preserving partial edge pixels."""

    rgba = image.convert("RGBA")
    alpha = np.asarray(rgba.getchannel("A"), dtype=np.uint8)
    ys, xs = np.nonzero(alpha > alpha_threshold)
    if not xs.size:
        raise ValueError("cell contains no visible pixels")
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    return rgba.crop(box)


def pad_to_canvas(
    image: Image.Image,
    *,
    canvas_size: int = 512,
    content_size: int = 448,
) -> Image.Image:
    """Fit a trimmed sticker proportionally inside a transparent square canvas."""

    if canvas_size < 1 or content_size < 1 or content_size > canvas_size:
        raise ValueError("content_size must be positive and no larger than canvas_size")
    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width < 1 or height < 1:
        raise ValueError("cannot pad an empty image")
    scale = min(content_size / width, content_size / height, 2.5)
    new_size = (
        max(1, min(content_size, round(width * scale))),
        max(1, min(content_size, round(height * scale))),
    )
    if new_size != rgba.size:
        rgba = rgba.resize(new_size, RESAMPLING.LANCZOS)
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    offset = ((canvas_size - new_size[0]) // 2, (canvas_size - new_size[1]) // 2)
    canvas.alpha_composite(rgba, offset)
    return canvas


def split_sheet(
    image: Image.Image,
    *,
    canvas_size: int = 512,
    content_size: int = 448,
) -> list[Image.Image]:
    """Split a fixed 3×3 master in reading order and normalize every cell."""

    rgba = image.convert("RGBA")
    width, height = rgba.size
    x_edges = _grid_edges(width)
    y_edges = _grid_edges(height)
    cells: list[Image.Image] = []
    for row in range(3):
        for column in range(3):
            crop = rgba.crop(
                (
                    x_edges[column],
                    y_edges[row],
                    x_edges[column + 1],
                    y_edges[row + 1],
                )
            )
            cells.append(
                pad_to_canvas(
                    trim_transparency(crop),
                    canvas_size=canvas_size,
                    content_size=content_size,
                )
            )
    return cells


def chroma_collision_scores(image: Image.Image) -> dict[str, dict[str, Any]]:
    """Measure weighted foreground collisions for the three fixed key colors."""

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3].astype(np.float32) / 255.0
    foreground = alpha >= (32 / 255)
    if not np.any(foreground):
        raise ValueError("cannot choose a chroma color for an empty image")
    pixels = rgb[foreground]
    weights = alpha[foreground]
    weight_total = float(weights.sum())
    scores: dict[str, dict[str, Any]] = {}
    for candidate in CHROMA_CANDIDATES:
        key_rgb = np.asarray(candidate["rgb"], dtype=np.float32)
        distances = np.linalg.norm(pixels - key_rgb, axis=1)
        collision_rate = float(weights[distances <= 80].sum() / weight_total)
        soft_similarity = np.clip(1.0 - distances / 128.0, 0.0, 1.0)
        soft_score = float(np.sum(weights * soft_similarity) / weight_total)
        scores[candidate["name"]] = {
            "hex": candidate["hex"],
            "rgb": list(candidate["rgb"]),
            "collision_rate": round(collision_rate, 8),
            "soft_score": round(soft_score, 8),
        }
    return scores


def parse_chroma_key(value: str) -> dict[str, Any]:
    """Parse one of the three contractually fixed chroma colors."""

    normalized = value.strip().lower()
    color_hex = _NAMED_CHROMA.get(normalized, normalized.upper())
    fixed_hexes = {candidate["hex"] for candidate in CHROMA_CANDIDATES}
    if color_hex not in fixed_hexes:
        raise ValueError("chroma key must be green/#00FF00, blue/#0000FF, or magenta/#FF00FF")
    rgb = tuple(int(color_hex[offset : offset + 2], 16) for offset in (1, 3, 5))
    matching = next(
        (candidate for candidate in CHROMA_CANDIDATES if candidate["hex"] == color_hex),
        None,
    )
    assert matching is not None
    name = matching["name"]
    display_name = matching["display_name"]
    return {"name": name, "display_name": display_name, "hex": color_hex, "rgb": list(rgb)}


def choose_chroma(
    image: Image.Image,
    *,
    explicit: str | None = None,
    conflict_threshold: float = 0.15,
) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]], bool]:
    """Choose the least-colliding key or signal that all candidates conflict.

    Returns ``(selected, scores, needs_review)``. An explicit user choice must
    still be one of the three fixed contract colors.
    """

    if not 0 <= conflict_threshold <= 1:
        raise ValueError("conflict_threshold must be between 0 and 1")
    scores = chroma_collision_scores(image)
    if explicit:
        selected = parse_chroma_key(explicit)
        selected["selection"] = "explicit"
        return selected, scores, False
    candidate_by_name = {candidate["name"]: candidate for candidate in CHROMA_CANDIDATES}
    winner_name = min(
        scores,
        key=lambda name: (scores[name]["collision_rate"], scores[name]["soft_score"]),
    )
    all_conflict = all(
        score["collision_rate"] >= conflict_threshold for score in scores.values()
    )
    if all_conflict:
        return None, scores, True
    candidate = candidate_by_name[winner_name]
    selected = {
        "name": candidate["name"],
        "display_name": candidate["display_name"],
        "hex": candidate["hex"],
        "rgb": list(candidate["rgb"]),
        "selection": "automatic",
    }
    return selected, scores, False


# Readable alias for callers/tests that prefer a verb phrase.
select_chroma_color = choose_chroma


def composite_chroma(image: Image.Image, rgb: Sequence[int]) -> Image.Image:
    """Composite RGBA artwork over an opaque, exact key-color background."""

    if len(rgb) != 3 or any(value < 0 or value > 255 for value in rgb):
        raise ValueError("rgb must contain three values between 0 and 255")
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    foreground = rgba[:, :, :3].astype(np.float32)
    alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
    background = np.asarray(rgb, dtype=np.float32).reshape(1, 1, 3)
    composited = np.rint(foreground * alpha + background * (1.0 - alpha)).astype(np.uint8)
    opaque_alpha = np.full((*composited.shape[:2], 1), 255, dtype=np.uint8)
    return Image.fromarray(np.concatenate([composited, opaque_alpha], axis=2), "RGBA")


def _render_video_prompt(template: str, selected: dict[str, Any]) -> str:
    return template.replace("{{CHROMA_NAME}}", str(selected["display_name"])).replace(
        "{{CHROMA_HEX}}", str(selected["hex"])
    )


def prepare_job_assets(
    job_path: str | Path,
    *,
    chroma_key: str | None = None,
    route: str | None = None,
    conflict_threshold: float = 0.15,
    canvas_size: int = 512,
    content_size: int = 448,
) -> dict[str, Any]:
    """Prepare cell PNGs and a chroma master, then update the job manifest."""

    job = load_job(job_path)
    manifest_path = Path(job_path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "job.json"
    manifest_path = manifest_path.resolve()
    if job.get("status") not in {"sheet_validated", "chroma_review_required"}:
        raise JobError("asset preparation requires sheet_validated or chroma_review_required state")
    if job.get("status") == "chroma_review_required" and not chroma_key:
        raise JobError("chroma_review_required needs an explicit fixed chroma choice")
    if route is not None:
        if route not in {"local", "video"}:
            raise ValueError("route override must be local or video")
        current_route = job["options"]["route"]
        if current_route != "auto" and current_route != route:
            raise JobError("a preselected route cannot be changed during preparation")
        job["options"]["route"] = route
    sheet_qa = job.get("qa", {}).get("sheet", {})
    if not sheet_qa.get("passed"):
        raise JobError("transparent sheet has not passed automatic QA")
    transparent_path = verify_artifact_record(
        manifest_path, job["artifacts"].get("transparent_sheet"), "transparent sheet"
    )
    try:
        with Image.open(transparent_path) as source:
            transparent = source.convert("RGBA").copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"validated sheet is unreadable: {transparent_path}") from exc

    selected, scores, needs_review = choose_chroma(
        transparent,
        explicit=chroma_key,
        conflict_threshold=conflict_threshold,
    )
    job["chroma"] = {
        "selected": selected,
        "scores": scores,
        "conflict_threshold": conflict_threshold,
        "needs_review": needs_review,
    }
    if needs_review:
        update_status(
            manifest_path,
            job,
            "chroma_review_required",
            qa={
                "chroma": {
                    "passed": False,
                    "reason": "all_fixed_candidates_conflict",
                    "scores": scores,
                }
            },
            error={
                "code": "chroma_conflict",
                "message": "green, blue, and magenta all significantly collide with the character",
            },
        )
        return {
            "status": "chroma_review_required",
            "selected": None,
            "scores": scores,
            "needs_review": True,
        }
    assert selected is not None

    cells = split_sheet(
        transparent,
        canvas_size=canvas_size,
        content_size=content_size,
    )
    cell_records: list[dict[str, Any]] = []
    png_records: list[dict[str, Any]] = []
    target_pairs: list[tuple[int, bytes, Path, Path | None]] = []
    for content, cell in zip(job["contents"], cells):
        index = int(content["index"])
        basename = str(content["slug"]) + ".png"
        cell_path = resolve_job_path(
            manifest_path, f"{job['paths']['cells_dir']}/{basename}"
        )
        static_path = (
            resolve_job_path(manifest_path, f"{job['paths']['png_dir']}/{basename}")
            if job["options"]["static"]
            else None
        )
        # Encode every cell before creating any final media file.  A malformed
        # in-memory image therefore cannot strand a half-prepared job.
        target_pairs.append((index, _png_bytes(cell), cell_path, static_path))

    chroma_path = resolve_job_path(manifest_path, job["paths"]["chroma_sheet"])
    prompt_path = resolve_job_path(manifest_path, job["paths"]["video_prompt"])
    prompt_template_path = resolve_job_path(
        manifest_path, job["paths"]["video_prompt_template"]
    )
    prompt_template = prompt_template_path.read_text(encoding="utf-8")
    if "{{CHROMA_NAME}}" not in prompt_template or "{{CHROMA_HEX}}" not in prompt_template:
        raise JobError("video prompt template is missing chroma placeholders")
    rendered_prompt = _render_video_prompt(prompt_template, selected)
    chroma_bytes = _png_bytes(composite_chroma(transparent, selected["rgb"]))

    work_dir = resolve_job_path(manifest_path, "work")
    work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="da-assets-", dir=work_dir) as staging_name:
        staging = Path(staging_name)
        publications: list[tuple[Path, Path]] = []
        for index, cell_bytes, cell_path, static_path in target_pairs:
            staged_cell = staging / "cells" / cell_path.name
            atomic_write_bytes(staged_cell, cell_bytes)
            publications.append((staged_cell, cell_path))
            cell_records.append(
                {
                    "index": index,
                    "path": relative_job_path(manifest_path, cell_path),
                    "sha256": sha256_file(staged_cell),
                }
            )
            if static_path is not None:
                staged_static = staging / "png" / static_path.name
                atomic_write_bytes(staged_static, cell_bytes)
                publications.append((staged_static, static_path))
                png_records.append(
                    {
                        "index": index,
                        "path": relative_job_path(manifest_path, static_path),
                        "sha256": sha256_file(staged_static),
                    }
                )
        staged_chroma = staging / "chroma-sheet.png"
        staged_prompt = staging / "video-prompt.txt"
        atomic_write_bytes(staged_chroma, chroma_bytes)
        atomic_write_bytes(staged_prompt, rendered_prompt.encode("utf-8"))
        publications.extend(((staged_chroma, chroma_path), (staged_prompt, prompt_path)))
        publish_files_atomically(publications)

    chroma_artifact = {
        "path": relative_job_path(manifest_path, chroma_path),
        "sha256": sha256_file(chroma_path),
    }
    job["artifacts"]["cells"] = cell_records
    job["artifacts"]["pngs"] = png_records
    job["artifacts"]["chroma_sheet"] = chroma_artifact

    route = job["options"]["route"]
    status_by_route = {
        "auto": "awaiting_route",
        "local": "assets_prepared",
        "video": "waiting_for_video",
    }
    final_status = status_by_route[route]
    update_status(
        manifest_path,
        job,
        final_status,
        qa={
            "chroma": {
                "passed": True,
                "selected": selected,
                "scores": scores,
            },
            "assets": {
                "passed": True,
                "canvas_size": canvas_size,
                "content_size": content_size,
                "cell_count": len(cell_records),
                "static_count": len(png_records),
            },
        },
    )
    return {
        "status": final_status,
        "selected": selected,
        "scores": scores,
        "needs_review": False,
        "cells": cell_records,
        "pngs": png_records,
        "chroma_sheet": chroma_artifact,
    }


def select_prepared_route(job_path: str | Path, route: str) -> dict[str, Any]:
    """Resolve an awaiting_route job without regenerating prepared assets."""

    if route not in {"local", "video"}:
        raise ValueError("route must be local or video")
    job = load_job(job_path)
    manifest_path = Path(job_path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "job.json"
    manifest_path = manifest_path.resolve()
    if job.get("status") != "awaiting_route":
        raise JobError("route selection requires an awaiting_route job")
    if not job.get("artifacts", {}).get("cells") or not job.get("artifacts", {}).get("chroma_sheet"):
        raise JobError("prepared cell and chroma artifacts are required before route selection")
    if job.get("intake", {}).get("route_requested") != "auto":
        raise JobError("only an auto-route intake can be selected after preparation")
    for index, record in enumerate(job["artifacts"]["cells"], 1):
        verify_artifact_record(manifest_path, record, f"cell {index}", expected_index=index)
    verify_artifact_record(manifest_path, job["artifacts"]["chroma_sheet"], "chroma sheet")
    job["options"]["route"] = route
    status = "assets_prepared" if route == "local" else "waiting_for_video"
    update_status(
        manifest_path,
        job,
        status,
        qa={"route_selection": {"selected": route, "after_chroma_master": True}},
    )
    return {"status": status, "route": route}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Split a validated sheet and choose/build its chroma master."
    )
    parser.add_argument("--job", required=True, help="job.json or its containing directory")
    parser.add_argument(
        "--chroma-key",
        help="explicit green/#00FF00, blue/#0000FF, or magenta/#FF00FF after a conflict review",
    )
    parser.add_argument(
        "--route",
        choices=("local", "video"),
        help="resolve an awaiting_route job, or override route while preparing",
    )
    parser.add_argument("--conflict-threshold", type=float, default=0.15)
    parser.add_argument("--canvas-size", type=int, default=512)
    parser.add_argument("--content-size", type=int, default=448)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        existing = load_job(args.job)
        if existing.get("status") == "awaiting_route" and args.route:
            result = select_prepared_route(args.job, args.route)
        else:
            result = prepare_job_assets(
                args.job,
                chroma_key=args.chroma_key,
                route=args.route,
                conflict_threshold=args.conflict_threshold,
                canvas_size=args.canvas_size,
                content_size=args.content_size,
            )
    except (FileNotFoundError, FileExistsError, JobError, ValueError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result.get("needs_review") else 0


if __name__ == "__main__":
    sys.exit(main())
