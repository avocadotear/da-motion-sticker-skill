#!/usr/bin/env python3
"""Split a 3×3 screen-background video into nine transparent looping GIFs."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

from _media import (
    border_consistency,
    detect_color_grid,
    estimate_background_color,
    fit_rgba,
    grid_cells,
    inspect_gif,
    open_rgba,
    read_json,
    remove_connected_background,
    sha256_file,
    write_json,
)


def require_ffmpeg() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise SystemExit("missing required executable(s): %s" % ", ".join(missing))


def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError("command failed (%s):\n%s" % (" ".join(command), completed.stderr.strip()))
    return completed


def probe_video(path: Path) -> Dict[str, object]:
    completed = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,duration",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    payload = json.loads(completed.stdout)
    streams = payload.get("streams") or []
    if not streams:
        raise ValueError("input contains no video stream")
    stream = streams[0]

    def rate(value: str) -> float:
        numerator, denominator = value.split("/")
        return float(numerator) / float(denominator) if float(denominator) else 0.0

    duration_value = stream.get("duration") or payload.get("format", {}).get("duration")
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "fps": rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"),
        "duration_seconds": float(duration_value) if duration_value else None,
        "declared_frames": int(stream["nb_frames"]) if str(stream.get("nb_frames", "")).isdigit() else None,
    }


def extract_frames(video: Path, directory: Path, fps: int) -> List[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pattern = directory / "frame_%05d.png"
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-i",
            str(video),
            "-vf",
            "fps=%d" % fps,
            "-vsync",
            "0",
            str(pattern),
            "-loglevel",
            "error",
        ]
    )
    frames = sorted(directory.glob("frame_*.png"))
    if len(frames) < 2:
        raise ValueError("video produced fewer than two frames at %d fps" % fps)
    return frames


def sample_paths(paths: Sequence[Path], count: int = 8) -> List[Path]:
    if len(paths) <= count:
        return list(paths)
    indices = np.linspace(0, len(paths) - 1, count, dtype=int)
    return [paths[int(index)] for index in indices]


def expected_screen(report_path: Optional[Path]) -> Optional[Dict[str, object]]:
    if report_path is None:
        return None
    payload = read_json(report_path)
    if not isinstance(payload, dict) or not isinstance(payload.get("selected_screen"), dict):
        raise ValueError("screen report has no selected_screen object")
    selected = payload["selected_screen"]
    rgb = selected.get("rgb")
    if not isinstance(rgb, list) or len(rgb) != 3:
        raise ValueError("screen report selected_screen.rgb is invalid")
    return {"id": selected.get("id"), "rgb": [int(value) for value in rgb], "hex": selected.get("hex")}


def encode_gif(frame_dir: Path, output: Path, fps: int, alpha_threshold: int, max_colors: int) -> None:
    filter_complex = (
        "[0:v]split[a][b];"
        "[a]palettegen=reserve_transparent=1:max_colors=%d[p];"
        "[b][p]paletteuse=alpha_threshold=%d" % (max_colors, alpha_threshold)
    )
    run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_dir / "f_%05d.png"),
            "-filter_complex",
            filter_complex,
            "-loop",
            "0",
            str(output),
            "-loglevel",
            "error",
        ]
    )


def save_grid_debug(image: Image.Image, col_bounds: Sequence[int], row_bounds: Sequence[int], path: Path) -> None:
    preview = image.convert("RGB")
    draw = ImageDraw.Draw(preview)
    width = max(2, preview.width // 400)
    for value in col_bounds[1:-1]:
        draw.line((value, 0, value, preview.height - 1), fill=(255, 40, 70), width=width)
    for value in row_bounds[1:-1]:
        draw.line((0, value, preview.width - 1, value), fill=(255, 40, 70), width=width)
    preview.save(path)


def nearest_valid(index: int, valid_indices: Sequence[int]) -> int:
    return min(valid_indices, key=lambda candidate: abs(candidate - index))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--rows", type=int, default=3)
    parser.add_argument("--cols", type=int, default=3)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--color-threshold", type=float, default=60.0)
    parser.add_argument("--feather", type=float, default=55.0)
    parser.add_argument("--alpha-threshold", type=int, default=112)
    parser.add_argument("--max-colors", type=int, default=255)
    parser.add_argument("--screen-report", type=Path)
    parser.add_argument("--grid-debug", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    require_ffmpeg()
    if not args.input.is_file():
        raise SystemExit("video not found: %s" % args.input)
    if args.rows != 3 or args.cols != 3:
        raise SystemExit("this skill requires a 3×3 video")
    if args.fps < 4 or args.fps > 30:
        raise SystemExit("--fps must be between 4 and 30")
    if args.size < 64:
        raise SystemExit("--size must be at least 64")
    if not 2 <= args.max_colors <= 255:
        raise SystemExit("--max-colors must be between 2 and 255")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        if not args.overwrite:
            raise SystemExit("output directory is not empty; use a fresh directory or --overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    gifs_dir = args.output_dir / "gifs"
    first_frames_dir = args.output_dir / "first-frames"
    gifs_dir.mkdir()
    first_frames_dir.mkdir()
    source_probe = probe_video(args.input)
    warnings: List[str] = []

    with tempfile.TemporaryDirectory(prefix="da-motion-video-") as temporary_name:
        temporary = Path(temporary_name)
        frame_paths = extract_frames(args.input, temporary / "source", args.fps)
        selected_paths = sample_paths(frame_paths)
        sample_images = [open_rgba(path) for path in selected_paths]
        actual_key = estimate_background_color(sample_images)
        consistencies = [border_consistency(image, actual_key, threshold=70.0) for image in sample_images]
        if min(consistencies) < 0.88:
            raise SystemExit(
                "video background is not a stable uniform screen (minimum sampled border consistency %.3f)" % min(consistencies)
            )
        expected = expected_screen(args.screen_report)
        expected_delta = None
        if expected is not None:
            expected_delta = float(
                np.linalg.norm(np.asarray(actual_key, dtype=float) - np.asarray(expected["rgb"], dtype=float))
            )
            if expected_delta > 80.0:
                raise SystemExit(
                    "video screen differs from prepared sheet: expected %s, detected %s" % (expected["rgb"], actual_key)
                )
            if expected_delta > 24.0:
                warnings.append("视频压缩或生成导致幕布色偏移（RGB 距离 %.1f），抠图使用实测色。" % expected_delta)

        col_bounds, row_bounds, grid_confidence, grid_warnings = detect_color_grid(
            sample_images,
            actual_key,
            rows=args.rows,
            cols=args.cols,
            threshold=max(args.color_threshold + 15.0, 72.0),
        )
        warnings.extend(grid_warnings)
        if grid_confidence < 0.75:
            warnings.append("未可靠检测到持续幕布缝，使用固定 3×3 等分网格。")
        if args.grid_debug:
            save_grid_debug(sample_images[0], col_bounds, row_bounds, args.output_dir / "grid-debug.png")

        cell_outputs: List[Dict[str, object]] = []
        for cell_index, cell in enumerate(grid_cells(col_bounds, row_bounds), start=1):
            rgba_frames: List[Image.Image] = []
            coverage: List[float] = []
            border_touch: List[float] = []
            removal_fractions: List[float] = []
            for frame_path in frame_paths:
                frame = open_rgba(frame_path)
                crop = frame.crop(
                    (
                        cell["x"],
                        cell["y"],
                        cell["x"] + cell["width"],
                        cell["y"] + cell["height"],
                    )
                )
                cleaned, removal = remove_connected_background(
                    crop,
                    actual_key,
                    threshold=args.color_threshold,
                    feather=args.feather,
                )
                fitted = fit_rgba(cleaned, size=args.size, trim=False)
                alpha = np.asarray(fitted.getchannel("A"), dtype=np.uint8)
                visible = alpha > 8
                coverage.append(float(visible.mean()))
                edge = np.concatenate((visible[0], visible[-1], visible[1:-1, 0], visible[1:-1, -1]))
                border_touch.append(float(edge.mean()))
                removal_fractions.append(float(removal["fully_removed_fraction"]))
                rgba_frames.append(fitted)

            valid_indices = [index for index, value in enumerate(coverage) if value >= 0.0005]
            if not valid_indices:
                raise SystemExit("cell %02d is empty in every sampled output frame" % cell_index)
            repaired_indices: List[int] = []
            for index, value in enumerate(coverage):
                if value < 0.0005:
                    replacement = nearest_valid(index, valid_indices)
                    rgba_frames[index] = rgba_frames[replacement].copy()
                    coverage[index] = coverage[replacement]
                    border_touch[index] = border_touch[replacement]
                    repaired_indices.append(index)
            if repaired_indices:
                warnings.append("格子 %02d 有 %d 个空帧，已用最近有效帧替换。" % (cell_index, len(repaired_indices)))
            if max(border_touch) > 0.01:
                warnings.append("格子 %02d 的前景在部分帧接触裁切边界。" % cell_index)

            cell_temp = temporary / ("cell-%02d" % cell_index)
            cell_temp.mkdir()
            for frame_index, frame in enumerate(rgba_frames, start=1):
                frame.save(cell_temp / ("f_%05d.png" % frame_index))
            first_path = first_frames_dir / ("%02d.png" % cell_index)
            rgba_frames[0].save(first_path)
            gif_path = gifs_dir / ("%02d.gif" % cell_index)
            encode_gif(cell_temp, gif_path, args.fps, args.alpha_threshold, args.max_colors)
            inspection = inspect_gif(gif_path)
            if inspection["frames"] < 2 or not inspection["has_transparency"] or not inspection["nonempty"]:
                raise SystemExit("encoded GIF failed validation: %s" % gif_path)
            cell_outputs.append(
                {
                    "index": cell_index,
                    "source_box": [cell["x"], cell["y"], cell["width"], cell["height"]],
                    "coverage_min": round(min(coverage), 6),
                    "coverage_max": round(max(coverage), 6),
                    "border_touch_max": round(max(border_touch), 6),
                    "background_removed_mean": round(float(np.mean(removal_fractions)), 6),
                    "repaired_frame_indices_zero_based": repaired_indices,
                    "first_frame": str(first_path.relative_to(args.output_dir)),
                    "gif": str(gif_path.relative_to(args.output_dir)),
                    "inspection": inspection,
                }
            )

    report = {
        "version": 1,
        "route": "external-video-postprocess",
        "source": {
            "path": str(args.input.resolve()),
            "sha256": sha256_file(args.input),
            **source_probe,
        },
        "processing": {
            "output_fps": args.fps,
            "output_size": [args.size, args.size],
            "decoded_frames": len(frame_paths),
            "color_threshold": args.color_threshold,
            "feather": args.feather,
            "gif_alpha_threshold": args.alpha_threshold,
            "gif_max_colors": args.max_colors,
        },
        "screen": {
            "detected_rgb": list(actual_key),
            "sample_border_consistency": [round(value, 6) for value in consistencies],
            "expected": expected,
            "expected_rgb_distance": round(expected_delta, 4) if expected_delta is not None else None,
        },
        "layout": {
            "columns": args.cols,
            "rows": args.rows,
            "count": args.rows * args.cols,
            "column_bounds": col_bounds,
            "row_bounds": row_bounds,
            "confidence": grid_confidence,
        },
        "cells": cell_outputs,
        "warnings": warnings,
    }
    report_path = args.output_dir / "processing.json"
    write_json(report_path, report)
    print(json.dumps({"report": str(report_path.resolve()), "count": len(cell_outputs), "warnings": warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
