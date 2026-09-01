#!/usr/bin/env python3
"""Assemble real per-sticker key poses into deterministic transparent GIF loops."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List

from PIL import Image

from _media import (
    encode_gif_images,
    encode_webp_images,
    inspect_gif,
    open_rgba,
    sha256_file,
    write_json,
)


def loop_indices(count: int) -> List[int]:
    if count < 2:
        raise ValueError("each sticker requires at least two key poses")
    return list(range(count)) + list(range(count - 2, 0, -1))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keyposes", type=Path, help="directory containing 01–09 subdirectories")
    parser.add_argument("output", type=Path)
    parser.add_argument("--fps", type=int, default=6)
    parser.add_argument("--hold-frames", type=int, default=1)
    parser.add_argument("--max-colors", type=int, default=192)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.fps < 1 or args.fps > 30:
        raise SystemExit("--fps must be between 1 and 30")
    if args.hold_frames < 1 or args.hold_frames > 6:
        raise SystemExit("--hold-frames must be between 1 and 6")
    if args.max_colors < 2 or args.max_colors > 255:
        raise SystemExit("--max-colors must be between 2 and 255")
    expected_dirs = [args.keyposes / ("%02d" % index) for index in range(1, 10)]
    missing = [path.name for path in expected_dirs if not path.is_dir()]
    extras = sorted(path.name for path in args.keyposes.iterdir() if path.is_dir() and path.name not in {item.name for item in expected_dirs}) if args.keyposes.is_dir() else []
    if missing or extras:
        raise SystemExit("keypose root must contain exactly 01–09 directories; missing=%s extras=%s" % (missing, extras))
    if args.output.exists() and any(args.output.iterdir()):
        if not args.overwrite:
            raise SystemExit("output directory is not empty; use a fresh directory or --overwrite")
        shutil.rmtree(args.output)
    gifs_dir = args.output / "gifs"
    webp_dir = args.output / "webp"
    first_frames_dir = args.output / "first-frames"
    gifs_dir.mkdir(parents=True)
    webp_dir.mkdir()
    first_frames_dir.mkdir()

    cell_reports: List[Dict[str, object]] = []
    warnings: List[str] = [
        "关键姿势按往返顺序确定性组帧；未运行光流或生成式插帧。",
        "本路线不使用整层平移、旋转、缩放、bounce、shake 或 sway。",
    ]
    for index, directory in enumerate(expected_dirs, start=1):
        pose_paths = sorted(directory.glob("*.png"))
        if len(pose_paths) < 3 or len(pose_paths) > 5:
            raise SystemExit("%s requires 3–5 ordered PNG key poses" % directory)
        poses = [open_rgba(path) for path in pose_paths]
        sizes = {pose.size for pose in poses}
        if len(sizes) != 1:
            raise SystemExit("%s pose canvases differ; run prepare_keyposes.py instead of auto-scaling frames" % directory)
        if next(iter(sizes))[0] > 2048 or next(iter(sizes))[1] > 2048:
            raise SystemExit("%s pose canvas exceeds 2048px" % directory)
        indices = loop_indices(len(poses))
        sequence: List[Image.Image] = []
        for pose_index in indices:
            sequence.extend(poses[pose_index].copy() for _ in range(args.hold_frames))

        stem = "%02d" % index
        first_path = first_frames_dir / (stem + ".png")
        gif_path = gifs_dir / (stem + ".gif")
        webp_path = webp_dir / (stem + ".webp")
        poses[0].save(first_path)
        encoder = encode_gif_images(sequence, gif_path, fps=args.fps, max_colors=args.max_colors)
        webp_written = True
        try:
            encode_webp_images(sequence, webp_path, fps=args.fps)
        except (OSError, ValueError) as error:
            webp_written = False
            warnings.append("格子 %s 的动画 WebP 编码失败：%s" % (stem, error))
        inspection = inspect_gif(gif_path)
        if inspection["frames"] < 2 or inspection["loop"] != 0 or not inspection["has_transparency"] or not inspection["nonempty"]:
            raise SystemExit("encoded GIF failed validation: %s" % gif_path)
        if encoder.get("warning"):
            warnings.append("格子 %s：%s" % (stem, encoder["warning"]))
        cell_reports.append(
            {
                "id": stem,
                "source_directory": str(directory.resolve()),
                "keyposes": len(poses),
                "pose_files": [path.name for path in pose_paths],
                "pose_sha256": [sha256_file(path) for path in pose_paths],
                "sequence_zero_based": indices,
                "hold_frames": args.hold_frames,
                "output_frames": len(sequence),
                "gif": str(gif_path.relative_to(args.output)),
                "first_frame": str(first_path.relative_to(args.output)),
                "webp": str(webp_path.relative_to(args.output)) if webp_written else None,
                "gif_encoder": encoder,
                "gif_inspection": inspection,
            }
        )
        for pose in poses + sequence:
            pose.close()

    report_path = args.output / "processing.json"
    write_json(
        report_path,
        {
            "version": 1,
            "mode": "keypose-local",
            "count": 9,
            "output_fps": args.fps,
            "hold_frames": args.hold_frames,
            "gif_max_colors": args.max_colors,
            "loop_strategy": "forward-then-reverse-to-start",
            "interpolation": "none",
            "affine_fallback": False,
            "cells": cell_reports,
            "warnings": warnings,
        },
    )
    print(json.dumps({"report": str(report_path.resolve()), "count": 9, "warnings": warnings}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
