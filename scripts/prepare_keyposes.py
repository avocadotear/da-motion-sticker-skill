#!/usr/bin/env python3
"""Validate nine 2×2 pose sheets and build ordered fixed-canvas key-pose folders."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List, Sequence

import numpy as np
from PIL import Image

from _media import (
    alpha_stats,
    detect_alpha_grid,
    fit_rgba,
    grid_cells,
    numbered_files,
    open_rgba,
    sha256_file,
    write_json,
)
from prepare_sheet import normalize_alpha


POSE_NAMES = ["01-start.png", "02-anticipation.png", "03-peak.png", "04-recovery.png"]


def crop_pose_cells(image: Image.Image, col_bounds: Sequence[int], row_bounds: Sequence[int], size: int) -> List[Image.Image]:
    poses: List[Image.Image] = []
    for cell in grid_cells(col_bounds, row_bounds):
        crop = image.crop(
            (
                cell["x"],
                cell["y"],
                cell["x"] + cell["width"],
                cell["y"] + cell["height"],
            )
        )
        poses.append(fit_rgba(crop, size=size, trim=False))
    return poses


def pose_difference(first: Image.Image, second: Image.Image) -> float:
    left = np.asarray(first.convert("RGBA"), dtype=np.float32) / 255.0
    right = np.asarray(second.convert("RGBA"), dtype=np.float32) / 255.0
    alpha_difference = float(np.abs(left[:, :, 3] - right[:, :, 3]).mean())
    visible = np.maximum(left[:, :, 3], right[:, :, 3])
    rgb_difference = float((np.abs(left[:, :, :3] - right[:, :, :3]).mean(axis=2) * visible).sum() / max(visible.sum(), 1.0))
    return round(0.60 * alpha_difference + 0.40 * rgb_difference, 6)


def foreground_mean_rgb(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32)
    visible = rgba[:, :, 3] >= 64
    if not visible.any():
        raise ValueError("empty key pose")
    return rgba[:, :, :3][visible].mean(axis=0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-cells", type=Path, required=True, help="original 01.png–09.png cells")
    parser.add_argument("--pose-sheets", type=Path, required=True, help="generated 01.png–09.png 2×2 sheets")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.size < 64 or args.size > 2048:
        raise SystemExit("--size must be between 64 and 2048")
    source_paths = numbered_files(args.source_cells, ".png")
    sheet_paths = numbered_files(args.pose_sheets, ".png")
    missing = [str(path) for path in source_paths + sheet_paths if not path.is_file()]
    if missing:
        raise SystemExit("missing required files: %s" % missing)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        if not args.overwrite:
            raise SystemExit("output directory is not empty; use a fresh directory or --overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    cells_report: List[Dict[str, object]] = []
    warnings: List[str] = []
    for index, (source_path, sheet_path) in enumerate(zip(source_paths, sheet_paths), start=1):
        source = fit_rgba(open_rgba(source_path), size=args.size, trim=False)
        raw_sheet = open_rgba(sheet_path)
        if raw_sheet.width != raw_sheet.height:
            raise SystemExit("pose sheet %02d must be square" % index)
        normalized, alpha_method, alpha_report, alpha_warnings = normalize_alpha(raw_sheet)
        warnings.extend("姿势页 %02d：%s" % (index, warning) for warning in alpha_warnings)
        col_bounds, row_bounds, confidence, grid_warnings = detect_alpha_grid(normalized, rows=2, cols=2)
        warnings.extend("姿势页 %02d：%s" % (index, warning) for warning in grid_warnings)
        if confidence < 0.75:
            raise SystemExit("pose sheet %02d has no reliable 2×2 transparent gutters" % index)
        generated = crop_pose_cells(normalized, col_bounds, row_bounds, args.size)
        if len(generated) != 4:
            raise SystemExit("pose sheet %02d did not produce four cells" % index)
        for pose_index, pose in enumerate(generated, start=1):
            stats = alpha_stats(pose)
            if stats["opaque_fraction"] < 0.002:
                raise SystemExit("pose sheet %02d cell %d is empty" % (index, pose_index))

        poses = [source, generated[1], generated[2], generated[3]]
        differences = [pose_difference(source, pose) for pose in poses[1:]]
        if differences[1] < 0.02:
            raise SystemExit(
                "pose sheet %02d action peak is too similar to the original (difference %.4f); regenerate real pose changes"
                % (index, differences[1])
            )
        if max(differences) < 0.025:
            raise SystemExit("pose sheet %02d has no meaningful pose change" % index)

        source_color = foreground_mean_rgb(source)
        color_distances = [round(float(np.linalg.norm(foreground_mean_rgb(pose) - source_color)), 4) for pose in poses[1:]]
        if max(color_distances) > 95.0:
            warnings.append("姿势页 %02d 的前景平均颜色变化较大，需人工确认身份、服装和材质一致性。" % index)
        generated_start_difference = pose_difference(source, generated[0])
        if generated_start_difference > 0.30:
            warnings.append("姿势页 %02d 的生成起始格与原图差异较大；最终循环已强制使用原始 PNG 起始帧。" % index)

        output_cell = args.output_dir / ("%02d" % index)
        output_cell.mkdir()
        for name, pose in zip(POSE_NAMES, poses):
            pose.save(output_cell / name)
        cells_report.append(
            {
                "id": "%02d" % index,
                "source": str(source_path.resolve()),
                "source_sha256": sha256_file(source_path),
                "pose_sheet": str(sheet_path.resolve()),
                "pose_sheet_sha256": sha256_file(sheet_path),
                "alpha_method": alpha_method,
                "alpha": alpha_report,
                "layout": {"columns": 2, "rows": 2, "confidence": confidence, "column_bounds": col_bounds, "row_bounds": row_bounds},
                "generated_start_difference": generated_start_difference,
                "motion_difference_from_start": {
                    "anticipation": differences[0],
                    "peak": differences[1],
                    "recovery": differences[2],
                },
                "foreground_mean_rgb_distance": {
                    "anticipation": color_distances[0],
                    "peak": color_distances[1],
                    "recovery": color_distances[2],
                },
                "outputs": POSE_NAMES,
            }
        )

    report_path = args.output_dir / "keypose-preparation.json"
    write_json(
        report_path,
        {
            "version": 1,
            "mode": "keypose-local-preparation",
            "count": 9,
            "poses_per_sticker": 4,
            "start_frame_policy": "exact-original-static-cell",
            "fixed_canvas": [args.size, args.size],
            "cells": cells_report,
            "warnings": warnings,
        },
    )
    print(json.dumps({"report": str(report_path.resolve()), "count": 9, "warnings": warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
