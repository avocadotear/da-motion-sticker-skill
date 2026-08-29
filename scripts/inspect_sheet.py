#!/usr/bin/env python3
"""Key and validate a chroma-screen 3×3 master, then render an overlay."""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

try:
    from ._core import (
        JobError,
        atomic_write_or_adopt_bytes,
        load_job,
        relative_job_path,
        resolve_job_path,
        sha256_file,
        update_status,
    )
except ImportError:  # pragma: no cover
    from _core import (  # type: ignore
        JobError,
        atomic_write_or_adopt_bytes,
        load_job,
        relative_job_path,
        resolve_job_path,
        sha256_file,
        update_status,
    )

try:
    from .prepare_assets import composite_chroma, key_chroma_image
except ImportError:  # pragma: no cover
    from prepare_assets import composite_chroma, key_chroma_image  # type: ignore


ALPHA_FOREGROUND_THRESHOLD = 8
MIN_CELL_OCCUPANCY = 0.01
MIN_TRANSPARENT_RATIO = 0.985


def _issue(code: str, message: str, **details: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "message": message}
    if details:
        result["details"] = details
    return result


def _grid_edges(length: int) -> list[int]:
    return [round(index * length / 3) for index in range(4)]


def _dominant_fake_checkerboard(rgb: np.ndarray, alpha: np.ndarray) -> dict[str, Any]:
    """Conservatively detect an opaque gray checkerboard used as fake Alpha."""

    opaque = alpha >= 250
    opaque_ratio = float(np.mean(opaque))
    result: dict[str, Any] = {
        "suspected": False,
        "opaque_ratio": round(opaque_ratio, 6),
        "dominant_coverage": 0.0,
    }
    if opaque_ratio < 0.55 or np.count_nonzero(opaque) < 64:
        return result
    pixels = rgb[opaque]
    # Analyze near-neutral pixels separately so a colorful subject cannot displace
    # one of the two checker colors from the dominant-color pair.
    neutral_pixels = pixels[np.ptp(pixels.astype(np.int16), axis=1) <= 28]
    neutral_ratio = float(len(neutral_pixels) / max(1, len(pixels)))
    result["neutral_ratio"] = round(neutral_ratio, 6)
    if len(neutral_pixels) < 64 or neutral_ratio < 0.35:
        return result
    # Coarse quantization tolerates antialiasing and mild compression drift.
    quantized = (neutral_pixels.astype(np.uint16) // 8).astype(np.uint8)
    colors, counts = np.unique(quantized, axis=0, return_counts=True)
    if len(counts) < 2:
        return result
    order = np.argsort(counts)[-2:]
    top_colors = colors[order].astype(np.int16) * 8 + 4
    top_counts = counts[order]
    neutral_coverage = float(top_counts.sum() / max(1, neutral_pixels.shape[0]))
    coverage = float(top_counts.sum() / max(1, pixels.shape[0]))
    result["dominant_coverage"] = round(coverage, 6)
    result["neutral_dominant_coverage"] = round(neutral_coverage, 6)
    neutral = bool(np.all(np.ptp(top_colors, axis=1) <= 28))
    luminance = np.mean(top_colors, axis=1)
    separated = bool(6 <= abs(float(luminance[0] - luminance[1])) <= 96)
    balanced = bool(np.min(top_counts) / np.max(top_counts) >= 0.18)
    result["suspected"] = bool(
        coverage >= 0.40
        and neutral_coverage >= 0.65
        and neutral
        and separated
        and balanced
    )
    result["dominant_rgb"] = top_colors.astype(int).tolist()
    return result


def validate_sheet(
    image_path: str | Path | Image.Image,
    *,
    alpha_threshold: int = ALPHA_FOREGROUND_THRESHOLD,
) -> tuple[dict[str, Any], Image.Image]:
    """Return a JSON-safe QA report and the normalized RGBA master image."""

    path = Path(image_path) if not isinstance(image_path, Image.Image) else None
    try:
        if isinstance(image_path, Image.Image):
            source = image_path
            original_mode = source.mode
            original_format = source.format
            frame_count = int(getattr(source, "n_frames", 1))
            has_alpha_channel = "A" in source.getbands() or "transparency" in source.info
            rgba_image = ImageOps.exif_transpose(source).convert("RGBA").copy()
        else:
            assert path is not None
            with Image.open(path) as source:
                original_mode = source.mode
                original_format = source.format
                frame_count = int(getattr(source, "n_frames", 1))
                has_alpha_channel = "A" in source.getbands() or "transparency" in source.info
                source.seek(0)
                rgba_image = ImageOps.exif_transpose(source).convert("RGBA").copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"sheet is not a readable image: {path}") from exc

    width, height = rgba_image.size
    rgba = np.asarray(rgba_image, dtype=np.uint8)
    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]
    foreground = alpha > alpha_threshold
    nontransparent = alpha > 0
    fully_transparent = alpha == 0
    issues: list[dict[str, Any]] = []

    if width != height:
        issues.append(
            _issue(
                "not_square",
                "master sheet must use a square 1:1 canvas",
                width=width,
                height=height,
            )
        )
    if frame_count != 1:
        issues.append(
            _issue(
                "animated_master",
                "transparent master must be a single still image",
                frames=frame_count,
            )
        )
    if not has_alpha_channel:
        issues.append(
            _issue("missing_alpha_channel", "image does not contain an Alpha channel")
        )
    transparent_ratio = float(np.mean(fully_transparent))
    foreground_ratio = float(np.mean(foreground))
    if transparent_ratio < 0.10:
        issues.append(
            _issue(
                "no_real_transparency",
                "sheet needs substantial actual Alpha=0 pixels, not a drawn background",
                transparent_ratio=round(transparent_ratio, 6),
            )
        )
    if foreground_ratio < 0.005:
        issues.append(
            _issue(
                "empty_sheet",
                "sheet contains no meaningful non-transparent artwork",
                foreground_ratio=round(foreground_ratio, 6),
            )
        )

    checkerboard = _dominant_fake_checkerboard(rgb, alpha)
    if checkerboard["suspected"]:
        issues.append(
            _issue(
                "fake_checkerboard_transparency",
                "an opaque gray checkerboard appears to simulate transparency",
                dominant_coverage=checkerboard["dominant_coverage"],
            )
        )

    x_edges = _grid_edges(width)
    y_edges = _grid_edges(height)
    cells: list[dict[str, Any]] = []
    problem_cells: set[int] = set()
    for row in range(3):
        for column in range(3):
            index = row * 3 + column + 1
            x0, x1 = x_edges[column], x_edges[column + 1]
            y0, y1 = y_edges[row], y_edges[row + 1]
            mask = foreground[y0:y1, x0:x1]
            occupancy = float(np.mean(mask)) if mask.size else 0.0
            ys, xs = np.nonzero(mask)
            bbox: list[int] | None = None
            edge_clearance: list[int] | None = None
            if xs.size:
                local_x0, local_x1 = int(xs.min()), int(xs.max()) + 1
                local_y0, local_y1 = int(ys.min()), int(ys.max()) + 1
                bbox = [
                    x0 + local_x0,
                    y0 + local_y0,
                    x0 + local_x1,
                    y0 + local_y1,
                ]
                edge_clearance = [
                    local_x0,
                    local_y0,
                    (x1 - x0) - local_x1,
                    (y1 - y0) - local_y1,
                ]
            minimum_clearance = max(2, round(min(x1 - x0, y1 - y0) * 0.02))
            minimum_extent = max(8, round(min(x1 - x0, y1 - y0) * 0.12))
            if occupancy < MIN_CELL_OCCUPANCY:
                problem_cells.add(index)
                issues.append(
                    _issue(
                        "empty_grid_cell",
                        f"grid cell {index} is empty or nearly empty",
                        cell=index,
                        occupancy=round(occupancy, 6),
                    )
                )
            elif bbox is not None and (
                bbox[2] - bbox[0] < minimum_extent or bbox[3] - bbox[1] < minimum_extent
            ):
                problem_cells.add(index)
                issues.append(
                    _issue(
                        "cell_subject_too_small",
                        f"artwork in grid cell {index} is too small to be a complete sticker",
                        cell=index,
                        bbox=bbox,
                        required_extent=minimum_extent,
                    )
                )
            elif edge_clearance is not None and min(edge_clearance) < minimum_clearance:
                problem_cells.add(index)
                issues.append(
                    _issue(
                        "cell_boundary_contact",
                        f"artwork in grid cell {index} touches a cell boundary",
                        cell=index,
                        clearance=edge_clearance,
                        required=minimum_clearance,
                    )
                )
            cells.append(
                {
                    "index": index,
                    "occupancy": round(occupancy, 6),
                    "bbox": bbox,
                    "edge_clearance": edge_clearance,
                }
            )

    bands: list[dict[str, Any]] = []
    gutter_half_width = max(2, round(min(width, height) * 0.0125))

    def inspect_band(name: str, mask: np.ndarray) -> None:
        clear_ratio = float(np.mean(~mask)) if mask.size else 0.0
        bands.append({"name": name, "transparent_ratio": round(clear_ratio, 6)})
        if clear_ratio < MIN_TRANSPARENT_RATIO:
            issues.append(
                _issue(
                    "nontransparent_gap",
                    f"{name} must remain fully transparent",
                    band=name,
                    transparent_ratio=round(clear_ratio, 6),
                    required=MIN_TRANSPARENT_RATIO,
                )
            )

    for position in x_edges[1:3]:
        inspect_band(
            f"vertical-gutter-{position}",
            nontransparent[:, max(0, position - gutter_half_width) : min(width, position + gutter_half_width)],
        )
    for position in y_edges[1:3]:
        inspect_band(
            f"horizontal-gutter-{position}",
            nontransparent[max(0, position - gutter_half_width) : min(height, position + gutter_half_width), :],
        )
    outer_width = max(2, round(min(width, height) * 0.015))
    inspect_band("outer-left", nontransparent[:, :outer_width])
    inspect_band("outer-right", nontransparent[:, max(0, width - outer_width) :])
    inspect_band("outer-top", nontransparent[:outer_width, :])
    inspect_band("outer-bottom", nontransparent[max(0, height - outer_width) :, :])

    report: dict[str, Any] = {
        "passed": not issues,
        "source": {
            "format": original_format,
            "mode": original_mode,
            "width": width,
            "height": height,
            "frames": frame_count,
        },
        "alpha": {
            "channel_present": has_alpha_channel,
            "transparent_ratio": round(transparent_ratio, 6),
            "foreground_ratio": round(foreground_ratio, 6),
            "minimum": int(alpha.min()) if alpha.size else 255,
            "maximum": int(alpha.max()) if alpha.size else 0,
        },
        "checkerboard": checkerboard,
        "grid": {
            "x_edges": x_edges,
            "y_edges": y_edges,
            "gutter_half_width": gutter_half_width,
            "cells": cells,
            "bands": bands,
        },
        "issues": issues,
        "problem_cells": sorted(problem_cells),
    }
    return report, rgba_image


def render_overlay(image: Image.Image, report: dict[str, Any]) -> Image.Image:
    """Render a checker-composited QA preview with grid, gutters, and cell boxes."""

    rgba = image.convert("RGBA")
    width, height = rgba.size
    tile = max(8, min(width, height) // 32)
    background = Image.new("RGB", rgba.size, (238, 238, 238))
    draw_background = ImageDraw.Draw(background)
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            if (x // tile + y // tile) % 2:
                draw_background.rectangle(
                    [x, y, min(width, x + tile) - 1, min(height, y + tile) - 1],
                    fill=(204, 204, 204),
                )
    background.paste(rgba, mask=rgba.getchannel("A"))
    overlay = background.convert("RGBA")
    draw = ImageDraw.Draw(overlay, "RGBA")
    grid = report["grid"]
    half = int(grid["gutter_half_width"])
    for position in grid["x_edges"][1:3]:
        draw.rectangle(
            [position - half, 0, position + half, height - 1],
            fill=(0, 140, 255, 36),
            outline=(0, 100, 255, 220),
            width=max(1, width // 512),
        )
    for position in grid["y_edges"][1:3]:
        draw.rectangle(
            [0, position - half, width - 1, position + half],
            fill=(0, 140, 255, 36),
            outline=(0, 100, 255, 220),
            width=max(1, width // 512),
        )
    problems = set(report.get("problem_cells", []))
    for cell in grid["cells"]:
        index = int(cell["index"])
        row, column = divmod(index - 1, 3)
        x0, x1 = grid["x_edges"][column], grid["x_edges"][column + 1]
        y0, y1 = grid["y_edges"][row], grid["y_edges"][row + 1]
        color = (255, 45, 45, 240) if index in problems else (30, 190, 90, 220)
        draw.rectangle([x0, y0, x1 - 1, y1 - 1], outline=color, width=max(2, width // 300))
        draw.rectangle([x0 + 3, y0 + 3, x0 + 29, y0 + 23], fill=(0, 0, 0, 165))
        draw.text((x0 + 9, y0 + 6), str(index), fill=(255, 255, 255, 255))
        if cell.get("bbox"):
            draw.rectangle(cell["bbox"], outline=color, width=max(1, width // 450))
    banner_color = (20, 145, 70, 230) if report["passed"] else (205, 35, 35, 235)
    draw.rectangle([0, 0, width, max(26, height // 20)], fill=banner_color)
    label = "PASS" if report["passed"] else f"REVIEW: {len(report['issues'])} issue(s)"
    draw.text((8, 7), label, fill=(255, 255, 255, 255))
    return overlay


def _write_png(path: Path, image: Image.Image, *, overwrite: bool = False) -> Path:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    if overwrite:
        raise ValueError("sheet QA previews never overwrite an existing file")
    return atomic_write_or_adopt_bytes(path, buffer.getvalue())


def inspect_job_sheet(
    job_path: str | Path,
    sheet_path: str | Path,
    *,
    after_review: bool = False,
) -> dict[str, Any]:
    """Validate a candidate sheet, update its job, and return the attempt report."""

    job = load_job(job_path)
    manifest_path = Path(job_path)
    if manifest_path.is_dir():
        manifest_path = manifest_path / "job.json"
    manifest_path = manifest_path.resolve()
    if job.get("status") not in {"awaiting_sheet_generation", "sheet_review_required"}:
        raise JobError("sheet inspection requires awaiting_sheet_generation or sheet_review_required state")
    sheet_qa = job.setdefault("qa", {}).setdefault(
        "sheet", {"passed": None, "attempts": []}
    )
    attempts = sheet_qa.setdefault("attempts", [])
    if sheet_qa.get("passed") or job.get("status") == "sheet_validated":
        raise JobError(
            "this job already has a validated keyed master; refusing an accidental recheck"
        )
    automatic_attempts = sum(
        1 for attempt in attempts if attempt.get("mode", "automatic") == "automatic"
    )
    if automatic_attempts >= 2 and not after_review:
        raise JobError(
            "automatic sheet QA is limited to two attempts; inspect the overlay and retry "
            "an explicitly user-corrected file with --after-review"
        )

    source = Path(sheet_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"sheet does not exist: {source}")
    selected = (job.get("chroma") or {}).get("selected")
    if not isinstance(selected, dict) or not isinstance(selected.get("rgb"), list):
        raise JobError("job does not record the preselected chroma color")
    try:
        with Image.open(source) as candidate_file:
            candidate = ImageOps.exif_transpose(candidate_file).convert("RGBA").copy()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"sheet is not a readable image: {source}") from exc
    if np.any(np.asarray(candidate.getchannel("A"), dtype=np.uint8) < 255):
        normalized = candidate
        chroma_source = composite_chroma(candidate, selected["rgb"])
        _, key_report = key_chroma_image(chroma_source, selected["rgb"])
        key_report["source_had_alpha"] = True
    else:
        chroma_source = candidate
        normalized, key_report = key_chroma_image(candidate, selected["rgb"])
        key_report["source_had_alpha"] = False
    report, normalized = validate_sheet(normalized)
    report["chroma_key"] = key_report
    if key_report["soft_background_ratio"] < 0.10:
        report["issues"].append(
            _issue(
                "insufficient_chroma_background",
                "generated sheet does not contain enough of the selected chroma color",
                selected=selected.get("name"),
                selected_hex=selected.get("hex"),
                soft_background_ratio=key_report["soft_background_ratio"],
            )
        )
        report["passed"] = False
    source_hash = sha256_file(source)
    attempt_number = len(attempts) + 1
    overlay_relative = f"qa/sheet-attempt-{attempt_number:02d}-overlay.png"
    overlay_path = resolve_job_path(manifest_path, overlay_relative)
    _write_png(overlay_path, render_overlay(normalized, report))
    attempt = {
        "attempt": attempt_number,
        "mode": "after_review" if after_review else "automatic",
        "source_sha256": source_hash,
        "passed": bool(report["passed"]),
        "overlay": overlay_relative,
        "report": report,
    }
    attempts.append(attempt)
    sheet_qa["passed"] = bool(report["passed"])
    sheet_qa["latest_overlay"] = overlay_relative
    sheet_qa["latest_source_sha256"] = source_hash

    if report["passed"]:
        transparent_path = resolve_job_path(manifest_path, job["paths"]["transparent_sheet"])
        chroma_path = resolve_job_path(manifest_path, job["paths"]["chroma_sheet"])
        if transparent_path.exists():
            try:
                with Image.open(transparent_path) as existing:
                    same_pixels = np.array_equal(
                        np.asarray(existing.convert("RGBA")), np.asarray(normalized)
                    )
            except (UnidentifiedImageError, OSError) as exc:
                raise FileExistsError(
                    f"existing transparent master is unreadable: {transparent_path}"
                ) from exc
            if not same_pixels:
                raise FileExistsError(
                    f"refusing to replace validated transparent master: {transparent_path}"
                )
        else:
            _write_png(transparent_path, normalized)
        if chroma_path.exists():
            try:
                with Image.open(chroma_path) as existing:
                    same_chroma_pixels = np.array_equal(
                        np.asarray(existing.convert("RGBA")), np.asarray(chroma_source)
                    )
            except (UnidentifiedImageError, OSError) as exc:
                raise FileExistsError(
                    f"existing chroma master is unreadable: {chroma_path}"
                ) from exc
            if not same_chroma_pixels:
                raise FileExistsError(
                    f"refusing to replace validated chroma master: {chroma_path}"
                )
        else:
            _write_png(chroma_path, chroma_source)
        transparent_hash = sha256_file(transparent_path)
        chroma_hash = sha256_file(chroma_path)
        artifact = {
            "path": relative_job_path(manifest_path, transparent_path),
            "sha256": transparent_hash,
        }
        job["artifacts"]["transparent_sheet"] = artifact
        job["artifacts"]["chroma_sheet"] = {
            "path": relative_job_path(manifest_path, chroma_path),
            "sha256": chroma_hash,
        }
        update_status(
            manifest_path,
            job,
            "sheet_validated",
            qa={"sheet": sheet_qa},
        )
    else:
        update_status(
            manifest_path,
            job,
            "sheet_review_required",
            qa={"sheet": sheet_qa},
            error={
                "code": "sheet_qa_failed",
                "message": "transparent master failed automatic QA",
                "attempt": attempt_number,
                "issue_codes": [issue["code"] for issue in report["issues"]],
                "overlay": overlay_relative,
            },
        )
    return attempt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Key and validate a generated 3x3 chroma-screen sticker master."
    )
    parser.add_argument("--job", required=True, help="job.json or its containing directory")
    parser.add_argument("--sheet", required=True, help="candidate chroma-screen master image")
    parser.add_argument(
        "--after-review",
        action="store_true",
        help="allow QA of a user-corrected file after two automatic attempts; QA is not bypassed",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        attempt = inspect_job_sheet(args.job, args.sheet, after_review=args.after_review)
    except (FileNotFoundError, FileExistsError, JobError, ValueError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(attempt, ensure_ascii=False))
    return 0 if attempt["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
