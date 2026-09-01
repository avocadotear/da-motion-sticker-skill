#!/usr/bin/env python3
"""Convert a uniform-background 3×3 source sheet to Alpha, split it, and add a safe screen."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List

import numpy as np
from PIL import Image, ImageDraw

from _media import (
    SCREEN_COLORS,
    alpha_stats,
    border_consistency,
    choose_screen,
    composite_on_color,
    detect_alpha_grid,
    estimate_background_color,
    grid_cells,
    open_rgba,
    remove_connected_background,
    sha256_file,
    split_sheet,
    write_json,
)


def _border_alpha_stats(image: Image.Image) -> Dict[str, float]:
    alpha = np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, 3]
    border = np.concatenate((alpha[0], alpha[-1], alpha[1:-1, 0], alpha[1:-1, -1]))
    return {
        "transparent_fraction": round(float((border <= 8).mean()), 6),
        "opaque_fraction": round(float((border >= 247).mean()), 6),
        "median": float(np.median(border)),
    }


def normalize_alpha(image: Image.Image) -> tuple[Image.Image, str, Dict[str, object], List[str]]:
    warnings: List[str] = []
    source_stats = alpha_stats(image)
    border_alpha = _border_alpha_stats(image)
    if source_stats["transparent_fraction"] >= 0.05 and border_alpha["transparent_fraction"] >= 0.70:
        return image.convert("RGBA"), "native-alpha", {
            "source_alpha": source_stats,
            "source_border_alpha": border_alpha,
        }, warnings

    if source_stats["transparent_fraction"] > 0.0:
        raise ValueError(
            "image has partial alpha but not a clean transparent outer background; regenerate instead of guessing"
        )

    key_color = estimate_background_color([image])
    consistency = border_consistency(image, key_color, threshold=42.0)
    if consistency < 0.96:
        raise ValueError(
            "opaque image has no uniform edge background (border consistency %.3f); checkerboards, scenes, and gradients are rejected"
            % consistency
        )
    repaired, repair_stats = remove_connected_background(image, key_color, threshold=38.0, feather=44.0)
    repaired_stats = alpha_stats(repaired)
    repaired_border = _border_alpha_stats(repaired)
    if repaired_stats["transparent_fraction"] < 0.05 or repaired_border["transparent_fraction"] < 0.70:
        raise ValueError("uniform-background repair did not produce a clean transparent sheet")
    warnings.append("输入图没有 Alpha；已仅移除与画面边缘连通的均匀背景。")
    return repaired, "uniform-edge-repair", {
        "source_alpha": source_stats,
        "source_border_alpha": border_alpha,
        "detected_background_rgb": list(key_color),
        "border_consistency": round(consistency, 6),
        "repair": repair_stats,
        "repaired_alpha": repaired_stats,
        "repaired_border_alpha": repaired_border,
    }, warnings


def inspect_cells(image: Image.Image, col_bounds: List[int], row_bounds: List[int]) -> tuple[List[Dict[str, object]], List[str]]:
    warnings: List[str] = []
    reports: List[Dict[str, object]] = []
    for index, cell in enumerate(grid_cells(col_bounds, row_bounds), start=1):
        crop = image.crop(
            (
                cell["x"],
                cell["y"],
                cell["x"] + cell["width"],
                cell["y"] + cell["height"],
            )
        )
        alpha = np.asarray(crop.getchannel("A"), dtype=np.uint8)
        coverage = float((alpha > 8).mean())
        border = np.concatenate((alpha[0], alpha[-1], alpha[1:-1, 0], alpha[1:-1, -1]))
        border_touch = float((border > 8).mean())
        if coverage < 0.002:
            raise ValueError("cell %02d is empty" % index)
        if coverage > 0.88:
            warnings.append("格子 %02d 的前景占比过高（%.1f%%），可能缺少安全留白。" % (index, coverage * 100))
        if border_touch > 0.005:
            warnings.append("格子 %02d 的前景接触裁切边界（%.2f%%）。" % (index, border_touch * 100))
        reports.append(
            {
                "index": index,
                "row": cell["row"],
                "col": cell["col"],
                "source_box": [cell["x"], cell["y"], cell["width"], cell["height"]],
                "foreground_fraction": round(coverage, 6),
                "border_touch_fraction": round(border_touch, 6),
            }
        )
    return reports, warnings


def save_overlay(image: Image.Image, col_bounds: List[int], row_bounds: List[int], path: Path) -> None:
    preview = composite_on_color(image, (236, 238, 242)).convert("RGB")
    draw = ImageDraw.Draw(preview)
    for value in col_bounds[1:-1]:
        draw.line((value, 0, value, preview.height - 1), fill=(255, 43, 78), width=max(2, preview.width // 400))
    for value in row_bounds[1:-1]:
        draw.line((0, value, preview.width - 1, value), fill=(255, 43, 78), width=max(2, preview.height // 400))
    preview.save(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="generated square sheet (uniform opaque background expected; native RGBA also accepted)")
    parser.add_argument("output_dir", type=Path, help="new prepared output directory")
    parser.add_argument("--screen", choices=["auto", *SCREEN_COLORS.keys()], default="auto")
    parser.add_argument("--cell-size", type=int, default=512)
    parser.add_argument("--export-static", action="store_true", help="copy cells into a deliverable static/ folder")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.cell_size < 64:
        raise SystemExit("--cell-size must be at least 64")
    if not args.input.is_file():
        raise SystemExit("input image not found: %s" % args.input)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        if not args.overwrite:
            raise SystemExit("output directory is not empty; use a fresh directory or --overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    source = open_rgba(args.input)
    if source.width != source.height:
        raise SystemExit("sticker sheet must be square; got %dx%d" % source.size)
    normalized, alpha_method, alpha_report, warnings = normalize_alpha(source)
    col_bounds, row_bounds, confidence, grid_warnings = detect_alpha_grid(normalized, rows=3, cols=3)
    warnings.extend(grid_warnings)
    if confidence < 0.75:
        raise SystemExit("could not confidently detect two transparent grid gutters; regenerate with wider gaps")
    cell_reports, cell_warnings = inspect_cells(normalized, col_bounds, row_bounds)
    warnings.extend(cell_warnings)

    transparent_path = args.output_dir / "sheet-transparent.png"
    normalized.save(transparent_path)
    cells_dir = args.output_dir / "cells"
    cells_dir.mkdir()
    cells = split_sheet(normalized, col_bounds, row_bounds, size=args.cell_size)
    for index, cell_image in enumerate(cells, start=1):
        cell_image.save(cells_dir / ("%02d.png" % index))
    if args.export_static:
        static_dir = args.output_dir / "static"
        static_dir.mkdir()
        for index, cell_image in enumerate(cells, start=1):
            cell_image.save(static_dir / ("%02d.png" % index))

    screen_id, scores = choose_screen(normalized, requested=args.screen)
    screen_definition = SCREEN_COLORS[screen_id]
    screen_path = args.output_dir / "sheet-screen.png"
    composite_on_color(normalized, screen_definition["rgb"]).save(screen_path)
    overlay_path = args.output_dir / "grid-overlay.png"
    save_overlay(normalized, col_bounds, row_bounds, overlay_path)

    report = {
        "version": 1,
        "source": {
            "path": str(args.input.resolve()),
            "sha256": sha256_file(args.input),
            "size": [source.width, source.height],
        },
        "alpha_method": alpha_method,
        "alpha": alpha_report,
        "normalized_alpha": alpha_stats(normalized),
        "layout": {
            "columns": 3,
            "rows": 3,
            "count": 9,
            "order": "row-major",
            "column_bounds": col_bounds,
            "row_bounds": row_bounds,
            "confidence": confidence,
        },
        "cells": cell_reports,
        "selected_screen": {
            "id": screen_id,
            "name_zh": screen_definition["name_zh"],
            "rgb": list(screen_definition["rgb"]),
            "hex": screen_definition["hex"],
        },
        "screen_scores": scores,
        "static_exported": bool(args.export_static),
        "files": {
            "transparent_sheet": transparent_path.name,
            "screen_sheet": screen_path.name,
            "working_cells": "cells",
            "static": "static" if args.export_static else None,
            "grid_overlay": overlay_path.name,
        },
        "warnings": warnings,
    }
    report_path = args.output_dir / "sheet-report.json"
    write_json(report_path, report)
    print(json.dumps({"report": str(report_path.resolve()), "selected_screen": screen_id, "warnings": warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
