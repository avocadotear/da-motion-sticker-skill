#!/usr/bin/env python3
"""Create a portable da-motion-sticker-skill job and its generation prompts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from PIL import Image, UnidentifiedImageError

try:  # Support both ``python scripts/create_job.py`` and package imports.
    from ._core import (
        JOB_SCHEMA_VERSION,
        SKILL_NAME,
        atomic_copy,
        atomic_write_text,
        canonical_sha256,
        numbered_slug,
        relative_job_path,
        save_job_atomic,
        sha256_file,
        slugify,
        unique_job_dir,
        utc_now_iso,
    )
except ImportError:  # pragma: no cover - exercised by CLI integration tests
    from _core import (  # type: ignore
        JOB_SCHEMA_VERSION,
        SKILL_NAME,
        atomic_copy,
        atomic_write_text,
        canonical_sha256,
        numbered_slug,
        relative_job_path,
        save_job_atomic,
        sha256_file,
        slugify,
        unique_job_dir,
        utc_now_iso,
    )


IMAGE_PROMPT_PATH = "prompts/image-prompt.txt"
VIDEO_PROMPT_PATH = "prompts/video-prompt.txt"
VIDEO_PROMPT_TEMPLATE_PATH = "prompts/video-prompt.template.txt"

STYLE_NAMES = (
    "低保真剪纸 Meme", "Q版大头 Chibi", "3D 软陶 / Clay", "3D 毛绒玩偶",
    "搪胶公仔 / Vinyl Toy", "黏土定格", "像素 / Pixel Art", "复古街机",
    "日漫夸张表情", "美式卡通 Meme", "报纸漫画", "复古漫画网点",
    "黑白漫画", "手绘涂鸦", "儿童蜡笔", "油画恶搞",
    "文艺复兴名画 Meme", "浮世绘 Meme", "中国传统年画", "国潮剪纸",
    "水墨 Meme", "刺绣 / 布艺贴章", "毛毡布贴", "纸雕 / Layered Paper",
    "撕纸拼贴 Meme", "Riso 孔版印刷", "丝网印刷", "Y2K 网络表情",
    "VHS / 低清截图", "Windows 95 / 复古电脑 UI", "Mac OS 复古系统图标",
    "Emoji 3D 混合", "表情符号拟人", "Reaction GIF 截帧",
    "夸张真人头 + 卡通小身体", "半写实 3D 大头人物",
)


def resolve_style(style: str, theme: str | None, contents: Sequence[str]) -> str:
    """Resolve a preset number/name/free description and recommend a concrete auto preset."""

    requested = style.strip() or "auto"
    if requested.casefold() != "auto":
        if requested.isdigit() and 1 <= int(requested) <= len(STYLE_NAMES):
            index = int(requested)
            return f"{index} - {STYLE_NAMES[index - 1]}"
        folded = requested.casefold()
        for index, name in enumerate(STYLE_NAMES, 1):
            if folded == name.casefold() or folded in name.casefold():
                return f"{index} - {name}"
        return requested

    context = " ".join([theme or "", *contents]).casefold()
    rules = (
        (("程序", "编程", "codex", "software", "game", "游戏", "ai"), 7),
        (("春节", "新年", "年味", "lunar"), 19),
        (("国风", "传统", "剪纸", "chinese"), 20),
        (("毛绒", "温暖", "plush"), 4),
        (("y2k", "早期互联网"), 28),
        (("抽象", "离谱", "meme", "发疯"), 1),
        (("漫画", "anime", "日漫"), 9),
    )
    selected = 2
    for keywords, candidate in rules:
        if any(keyword in context for keyword in keywords):
            selected = candidate
            break
    return f"{selected} - {STYLE_NAMES[selected - 1]}"


def parse_items(
    *,
    items: str | None = None,
    item_values: Sequence[str] | None = None,
    items_file: str | Path | None = None,
) -> list[str]:
    """Parse exactly nine display labels from one supported input mechanism."""

    supplied = sum(
        [items is not None, bool(item_values), items_file is not None]
    )
    if supplied != 1:
        raise ValueError("provide exactly one of --items, repeated --item, or --items-file")

    values: list[str]
    if item_values:
        values = list(item_values)
    elif items_file is not None:
        path = Path(items_file)
        text = path.read_text(encoding="utf-8-sig")
        if path.suffix.lower() == ".json" or text.lstrip().startswith("["):
            decoded = json.loads(text)
            if not isinstance(decoded, list) or not all(
                isinstance(value, str) for value in decoded
            ):
                raise ValueError("items JSON must be an array of strings")
            values = decoded
        else:
            values = text.splitlines()
    else:
        assert items is not None
        stripped = items.strip()
        if stripped.startswith("["):
            decoded = json.loads(stripped)
            if not isinstance(decoded, list) or not all(
                isinstance(value, str) for value in decoded
            ):
                raise ValueError("--items JSON must be an array of strings")
            values = decoded
        elif "|" in stripped:
            values = stripped.split("|")
        elif "\n" in stripped:
            values = stripped.splitlines()
        else:
            # Comma syntax is convenient for simple labels.  JSON or repeated
            # --item is preferred when a label itself contains punctuation.
            values = stripped.replace("，", ",").split(",")

    cleaned = [value.strip() for value in values if value.strip()]
    if len(cleaned) != 9:
        raise ValueError(f"exactly nine non-empty items are required; received {len(cleaned)}")
    return cleaned


def _validate_reference(path: Path) -> tuple[str, tuple[int, int]]:
    if not path.is_file():
        raise FileNotFoundError(f"reference image does not exist: {path}")
    try:
        with Image.open(path) as image:
            image_format = (image.format or "").upper()
            size = image.size
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"reference is not a readable image: {path}") from exc
    if size[0] < 1 or size[1] < 1:
        raise ValueError("reference image has invalid dimensions")
    return image_format, size


def _reference_suffix(image_format: str, source: Path) -> str:
    by_format = {
        "PNG": ".png",
        "JPEG": ".jpg",
        "WEBP": ".webp",
        "GIF": ".gif",
        "BMP": ".bmp",
        "TIFF": ".tiff",
    }
    return by_format.get(image_format, source.suffix.lower() or ".image")


def build_image_prompt(contents: Sequence[str], style: str) -> str:
    numbered = "\n".join(f"{index}. {label}" for index, label in enumerate(contents, 1))
    style_text = f"Apply this resolved style only to material, line, and shape treatment: {style}."
    return f"""Create one production-ready sticker master sheet from the supplied character reference.

HARD LAYOUT AND ALPHA RULES (these override every style convention):
- Square 1:1 canvas containing an exact 3×3 grid, ordered left-to-right then top-to-bottom.
- Show the same recognizable character exactly nine times, once per cell, performing the nine contents below.
- Leave wide, fully transparent gaps between every cell and around all four canvas edges.
- Output real RGBA transparency (actual Alpha=0 pixels), never a drawn checkerboard or a simulated transparent background.
- No outer sticker outline, border, panel, background, cast shadow, glow, halo, watermark, or UI frame.
- No character or accessory may cross a cell boundary, touch the canvas edge, or overlap another cell.
- Keep every complete character comfortably inside its own cell with animation-safe breathing room.

STYLE:
{style_text}
The transparent/no-outline/no-background rules above always take priority over style traits.
Do not add unrequested text. If an item explicitly requires visible text, render only that exact text inside its own safe cell.

NINE CONTENTS IN FIXED GRID ORDER:
{numbered}

Return a single square PNG with true transparency. Do not return nine separate files.
"""


def build_video_prompt_template(contents: Sequence[str]) -> str:
    numbered = "\n".join(f"{index}. {label}" for index, label in enumerate(contents, 1))
    return f"""Animate the supplied 3×3 sticker master as a locked grid on a solid {{{{CHROMA_NAME}}}} background ({{{{CHROMA_HEX}}}}).

Keep the canvas square, the camera completely static, and all nine grid positions fixed. Animate every character with a small, readable, naturally looping reaction matching its assigned content. Preserve character identity, colors, materials, proportions, and the wide gaps. Do not add text, captions, particles, tears, props, shadows, glow, borders, panels, camera moves, zooms, transitions, or a different background color. Nothing may cross a cell boundary or leave frame. Target about one second with a loop-friendly first and last pose.

Grid order:
{numbered}

The entire background, including gaps and corners, must remain exactly {{{{CHROMA_NAME}}}} ({{{{CHROMA_HEX}}}}) in every frame.
"""


def create_job(
    reference: str | Path,
    contents: Sequence[str],
    *,
    output_root: str | Path = "runs",
    pack_name: str | None = None,
    theme: str | None = None,
    style: str = "auto",
    static: bool = False,
    route: str = "auto",
    pet: bool = False,
) -> Path:
    """Create a unique run directory and return its ``job.json`` path."""

    if len(contents) != 9 or any(not str(value).strip() for value in contents):
        raise ValueError("contents must contain exactly nine non-empty strings")
    if route not in {"auto", "local", "video"}:
        raise ValueError("route must be auto, local, or video")
    reference_path = Path(reference).expanduser().resolve()
    image_format, reference_size = _validate_reference(reference_path)
    reference_hash = sha256_file(reference_path)

    display_name = (pack_name or theme or reference_path.stem or "Sticker Pack").strip()
    if not display_name:
        display_name = "Sticker Pack"
    pack_slug = slugify(display_name, fallback="sticker-pack", max_length=36)
    run_dir = unique_job_dir(output_root, pack_slug)
    job_path = run_dir / "job.json"

    reference_destination = run_dir / "source" / (
        "reference" + _reference_suffix(image_format, reference_path)
    )
    atomic_copy(reference_path, reference_destination)

    clean_contents = [str(value).strip() for value in contents]
    resolved_style = resolve_style(style, theme, clean_contents)
    content_records = [
        {
            "index": index,
            "display_name": label,
            "slug": numbered_slug(index, label),
            "motion_hint": None,
        }
        for index, label in enumerate(clean_contents, 1)
    ]
    created_at = utc_now_iso()
    intake = {
        "reference_sha256": reference_hash,
        "contents": clean_contents,
        "theme": theme,
        "style_requested": style,
        "style_resolved": resolved_style,
        "static_requested": bool(static),
        "route_requested": route,
        "pet_requested": bool(pet),
    }
    paths = {
        "image_prompt": IMAGE_PROMPT_PATH,
        "video_prompt": VIDEO_PROMPT_PATH,
        "video_prompt_template": VIDEO_PROMPT_TEMPLATE_PATH,
        "transparent_sheet": "source/transparent-sheet.png",
        "chroma_sheet": "source/chroma-sheet.png",
        "cells_dir": "work/cells",
        "gifs_dir": "gifs",
        "png_dir": "png",
        "qa_dir": "qa",
        "motion_plan": "motion-plan.json",
        "processing_report": "processing-report.json",
    }
    job: dict[str, object] = {
        "schema_version": JOB_SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "job_id": run_dir.name,
        "status": "awaiting_sheet_generation",
        "created_at": created_at,
        "updated_at": created_at,
        "input_hash": canonical_sha256(intake),
        "intake": intake,
        "pack": {"display_name": display_name, "slug": pack_slug},
        "reference": {
            "path": relative_job_path(job_path, reference_destination),
            "original_name": reference_path.name,
            "sha256": reference_hash,
            "width": reference_size[0],
            "height": reference_size[1],
        },
        "theme": theme,
        "contents": content_records,
        "style": {
            "requested": style,
            "resolved": resolved_style,
        },
        "options": {"static": bool(static), "route": route, "pet": bool(pet)},
        "paths": paths,
        "chroma": {
            "selected": None,
            "scores": {},
            "needs_review": False,
        },
        "artifacts": {
            "cells": [],
            "pngs": [],
            "gifs": [],
            "transparent_sheet": None,
            "chroma_sheet": None,
            "package": None,
        },
        "qa": {"sheet": {"passed": None, "attempts": []}},
        "errors": [],
        "history": [{"status": "awaiting_sheet_generation", "at": created_at}],
    }

    atomic_write_text(
        run_dir / IMAGE_PROMPT_PATH,
        build_image_prompt(clean_contents, resolved_style),
    )
    atomic_write_text(
        run_dir / VIDEO_PROMPT_TEMPLATE_PATH,
        build_video_prompt_template(clean_contents),
    )
    save_job_atomic(job_path, job)  # type: ignore[arg-type]
    return job_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a unique da-motion-sticker-skill run directory and job manifest."
    )
    parser.add_argument("--reference", required=True, help="character reference image")
    parser.add_argument(
        "--items",
        help="nine labels as a JSON array, pipe-separated string, or comma-separated string",
    )
    parser.add_argument(
        "--item",
        action="append",
        dest="item_values",
        help="one label; repeat exactly nine times",
    )
    parser.add_argument("--items-file", help="UTF-8 JSON array or one label per line")
    parser.add_argument("--theme", help="optional theme metadata; nine items are still required")
    parser.add_argument("--pack-name", help="display name for this pack")
    parser.add_argument("--style", default="auto", help="preset number/name or free description")
    parser.add_argument("--static", action="store_true", help="include nine static PNGs")
    parser.add_argument(
        "--route", choices=("auto", "local", "video"), default="auto"
    )
    parser.add_argument("--pet", action="store_true", help="record an explicit pet request")
    parser.add_argument("--output-root", default="runs", help="parent directory for unique jobs")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        contents = parse_items(
            items=args.items,
            item_values=args.item_values,
            items_file=args.items_file,
        )
        job_path = create_job(
            args.reference,
            contents,
            output_root=args.output_root,
            pack_name=args.pack_name,
            theme=args.theme,
            style=args.style,
            static=args.static,
            route=args.route,
            pet=args.pet,
        )
    except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps({"job": str(job_path), "status": "awaiting_sheet_generation"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
