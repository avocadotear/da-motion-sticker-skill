#!/usr/bin/env python3
"""Validate and package exactly nine GIF stickers plus selected audit artifacts."""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

from _media import alpha_stats, inspect_gif, numbered_files, open_rgba, read_json, sha256_file, write_json


def copy_file(source: Path, destination: Path) -> Path:
    if not source.is_file():
        raise ValueError("required file not found: %s" % source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def validate_gifs(directory: Path) -> List[Dict[str, object]]:
    expected = numbered_files(directory, ".gif")
    missing = [path.name for path in expected if not path.is_file()]
    actual = sorted(path.name for path in directory.glob("*.gif")) if directory.is_dir() else []
    extras = [name for name in actual if name not in {path.name for path in expected}]
    if missing or extras:
        raise ValueError("GIF directory must contain exactly 01.gif–09.gif; missing=%s extras=%s" % (missing, extras))
    reports: List[Dict[str, object]] = []
    sizes = set()
    for path in expected:
        report = inspect_gif(path)
        sizes.add(tuple(report["size"]))
        if report["frames"] < 2:
            raise ValueError("GIF is not animated: %s" % path)
        if report["loop"] != 0:
            raise ValueError("GIF does not declare infinite looping: %s" % path)
        if not report["has_transparency"] or not report["nonempty"]:
            raise ValueError("GIF alpha validation failed: %s" % path)
        reports.append(report)
    if len(sizes) != 1:
        raise ValueError("GIF canvas sizes differ: %s" % sorted(sizes))
    return reports


def validate_static(directory: Path) -> List[Dict[str, object]]:
    expected = numbered_files(directory, ".png")
    missing = [path.name for path in expected if not path.is_file()]
    actual = sorted(path.name for path in directory.glob("*.png")) if directory.is_dir() else []
    extras = [name for name in actual if name not in {path.name for path in expected}]
    if missing or extras:
        raise ValueError("static directory must contain exactly 01.png–09.png; missing=%s extras=%s" % (missing, extras))
    reports: List[Dict[str, object]] = []
    for path in expected:
        stats = alpha_stats(open_rgba(path))
        if stats["transparent_fraction"] <= 0.0 or stats["opaque_fraction"] <= 0.0:
            raise ValueError("static PNG lacks usable foreground/background alpha: %s" % path)
        reports.append({"path": str(path), "alpha": stats, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    return reports


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gif-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--route", choices=["A", "B"], required=True)
    parser.add_argument("--transparent-sheet", type=Path, required=True)
    parser.add_argument("--screen-sheet", type=Path, required=True)
    parser.add_argument("--static-dir", type=Path)
    parser.add_argument("--first-frames-dir", type=Path)
    parser.add_argument("--prompts-dir", type=Path)
    parser.add_argument("--keypose-plan-dir", type=Path, help="route A keypose-plan.json and prompt files")
    parser.add_argument("--sheet-report", type=Path)
    parser.add_argument("--report", type=Path, action="append", default=[])
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gif_inspections = validate_gifs(args.gif_dir)
    static_inspections = validate_static(args.static_dir) if args.static_dir else None
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        if not args.overwrite:
            raise SystemExit("output directory is not empty; use a fresh directory or --overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    delivery_gifs = args.output_dir / "gifs"
    delivery_gifs.mkdir()
    for path in numbered_files(args.gif_dir, ".gif"):
        copy_file(path, delivery_gifs / path.name)
    if args.static_dir:
        delivery_static = args.output_dir / "static"
        delivery_static.mkdir()
        for path in numbered_files(args.static_dir, ".png"):
            copy_file(path, delivery_static / path.name)
    if args.first_frames_dir:
        delivery_first = args.output_dir / "first-frames"
        delivery_first.mkdir()
        for path in numbered_files(args.first_frames_dir, ".png"):
            copy_file(path, delivery_first / path.name)

    copy_file(args.transparent_sheet, args.output_dir / "sheet-transparent.png")
    copy_file(args.screen_sheet, args.output_dir / "sheet-screen.png")

    prompt_plan: Optional[Dict[str, object]] = None
    if args.prompts_dir:
        for name in ("image-prompt.txt", "video-prompt.txt", "video-prompt.template.txt", "prompt-plan.json"):
            source = args.prompts_dir / name
            if source.is_file():
                copy_file(source, args.output_dir / name)
        plan_path = args.prompts_dir / "prompt-plan.json"
        if plan_path.is_file():
            loaded = read_json(plan_path)
            if isinstance(loaded, dict):
                prompt_plan = loaded
    if args.keypose_plan_dir:
        if not args.keypose_plan_dir.is_dir() or not (args.keypose_plan_dir / "keypose-plan.json").is_file():
            raise SystemExit("keypose plan directory must contain keypose-plan.json")
        shutil.copytree(args.keypose_plan_dir, args.output_dir / "keypose-plan")

    screen_report: Optional[Dict[str, object]] = None
    reports_dir = args.output_dir / "reports"
    report_sources = list(args.report)
    if args.sheet_report:
        report_sources.insert(0, args.sheet_report)
        loaded = read_json(args.sheet_report)
        if isinstance(loaded, dict):
            screen_report = loaded
    seen_names = set()
    for source in report_sources:
        if not source.is_file():
            raise SystemExit("report file not found: %s" % source)
        name = source.name
        if name in seen_names:
            name = "%s-%s" % (source.parent.name, source.name)
        seen_names.add(name)
        copy_file(source, reports_dir / name)

    files: List[Dict[str, object]] = []
    for path in sorted(candidate for candidate in args.output_dir.rglob("*") if candidate.is_file()):
        relative = path.relative_to(args.output_dir).as_posix()
        if relative in {"manifest.json", "da-motion-sticker-pack.zip"}:
            continue
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)})

    warnings: List[str] = []
    if args.route == "A":
        warnings.append("路线 A 使用图像模型生成的真实关键姿势并由本地代码确定性往返组帧；未运行光流或生成式插帧。")
    manifest = {
        "version": 1,
        "name": "da-motion-sticker-pack",
        "route": args.route,
        "complete": True,
        "gif_count": 9,
        "static_included": bool(args.static_dir),
        "style": prompt_plan.get("style") if prompt_plan else None,
        "reactions": prompt_plan.get("reactions") if prompt_plan else None,
        "screen": screen_report.get("selected_screen") if screen_report else None,
        "gif_inspections": gif_inspections,
        "static_inspections": static_inspections,
        "files": files,
        "warnings": warnings,
    }
    manifest_path = args.output_dir / "manifest.json"
    write_json(manifest_path, manifest)

    zip_path = args.output_dir / "da-motion-sticker-pack.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(candidate for candidate in args.output_dir.rglob("*") if candidate.is_file()):
            if path == zip_path:
                continue
            relative = path.relative_to(args.output_dir)
            if ".." in relative.parts:
                raise ValueError("unsafe archive path: %s" % relative)
            archive.write(path, relative.as_posix())
    print(json.dumps({"delivery": str(args.output_dir.resolve()), "zip": str(zip_path.resolve()), "gif_count": 9}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
