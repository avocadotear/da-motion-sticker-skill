#!/usr/bin/env python3
"""Compile the image and screen-aware video prompts for one nine-sticker job."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from _media import SCREEN_COLORS, read_json, write_json


SKILL_ROOT = Path(__file__).resolve().parents[1]
STYLE_LIBRARY = SKILL_ROOT / "assets" / "style-presets.json"
TEMPLATE_VERSION = 2
SOURCE_BACKGROUND = {
    "mode": "solid-background-first",
    "id": "green",
    "name_zh": "纯绿色",
    "hex": "#00FF00",
    "rgb": [0, 255, 0],
}


def _emoji_clusters(value: str) -> List[str]:
    clusters: List[str] = []
    join_next = False
    regional_pending = False
    for char in value:
        code = ord(char)
        if char.isspace():
            continue
        is_variation = 0xFE00 <= code <= 0xFE0F
        is_modifier = 0x1F3FB <= code <= 0x1F3FF
        is_combining = bool(unicodedata.combining(char)) or code == 0x20E3
        is_regional = 0x1F1E6 <= code <= 0x1F1FF
        if not clusters:
            clusters.append(char)
        elif is_variation or is_modifier or is_combining or join_next:
            clusters[-1] += char
        elif char == "\u200d":
            clusters[-1] += char
            join_next = True
            continue
        elif is_regional and regional_pending:
            clusters[-1] += char
            regional_pending = False
            continue
        else:
            clusters.append(char)
        join_next = False
        regional_pending = is_regional
    return clusters


def parse_reactions(value: str) -> List[str]:
    stripped = value.strip()
    if not stripped:
        raise ValueError("reactions cannot be empty")
    if any(separator in stripped for separator in [",", "，", "\n", "|", ";", "；"]):
        parts = [item.strip() for item in re.split(r"[,，\n|;；]+", stripped) if item.strip()]
    else:
        whitespace_parts = [item for item in stripped.split() if item]
        if len(whitespace_parts) == 9:
            parts = whitespace_parts
        else:
            parts = _emoji_clusters(stripped)
    if len(parts) != 9:
        raise ValueError("exactly nine reactions are required; parsed %d: %s" % (len(parts), parts))
    return parts


def load_presets() -> List[Dict[str, object]]:
    payload = read_json(STYLE_LIBRARY)
    if not isinstance(payload, dict) or not isinstance(payload.get("presets"), list):
        raise ValueError("invalid style library")
    return payload["presets"]  # type: ignore[return-value]


def resolve_style(value: str) -> Dict[str, object]:
    needle = value.strip().lower()
    if needle.isdigit():
        numeric = int(needle)
        for preset in load_presets():
            if int(preset["id"]) == numeric:
                return preset
    for preset in load_presets():
        candidates = {str(preset["slug"]).lower(), str(preset["name_zh"]).lower()}
        if needle in candidates:
            return preset
    raise ValueError("unknown style %r; use --list-styles to inspect valid values" % value)


def screen_from_report(path: Optional[Path]) -> Optional[Dict[str, object]]:
    if path is None:
        return None
    report = read_json(path)
    if not isinstance(report, dict):
        raise ValueError("screen report must contain a JSON object")
    selected = report.get("selected_screen")
    if isinstance(selected, str):
        key = selected
    elif isinstance(selected, dict):
        key = str(selected.get("id", ""))
    else:
        raise ValueError("screen report does not contain selected_screen")
    if key not in SCREEN_COLORS:
        raise ValueError("unknown selected screen in report: %s" % key)
    definition = SCREEN_COLORS[key]
    return {
        "id": key,
        "name_zh": definition["name_zh"],
        "rgb": list(definition["rgb"]),
        "hex": definition["hex"],
    }


def build_image_prompt(style: Dict[str, object], reactions: Sequence[str], reference_label: str) -> str:
    cells = "\n".join(
        "%02d（第%d行第%d列）：%s" % (index + 1, index // 3 + 1, index % 3 + 1, reaction)
        for index, reaction in enumerate(reactions)
    )
    return f"""基于{reference_label}创建一套 Meme 贴纸包，内容严格按下面的 3×3 位置排列：
{cells}

风格采用「{style['name_zh']}」：{style['prompt']}。

始终保留参考角色可识别的脸部特征、发型或毛发、肤色或毛色、服装、配饰、标志性道具和整体气质。不要无故改装、换脸、改变身份或新增角色。

人物采用大头小身体的夸张比例，头部约占整体高度的 50%–65%，手臂和双脚非常短。Use exaggerated internet-reaction expressions including crying, confusion, shock, smugness, side-eye, and deadpan disbelief when they match the requested reaction. Make every pose instantly readable and absurdly funny.

创建一张正方形 1:1 的不透明 PNG 贴纸页，包含九个不同贴纸，严格按 3 列 × 3 行排列。整张画布的空白区域和横纵间隔必须使用完全一致的纯绿色 #00FF00（RGB 0,255,0）。贴纸之间留出宽阔的纯绿间隔；人物、道具、眼泪、彩带、速度线和装饰元素都必须完整留在各自格子内，不能越界、重叠或互动。

不要请求或模拟透明背景。纯绿色必须平坦、纯净、无纹理、无渐变、无噪点、无光斑、无阴影，并从画布四边连续延伸到所有格间空白；不要生成棋盘格、场景、地面、卡片或格子底板。每个人物最外缘直接接触纯绿色。禁止白色描边、黑色外描边、彩色描边、贴纸切边、轮廓边框、光晕、投影或半透明外缘。不要模拟实体贴纸的白色切割边缘。人物内部可保留所选画风本来需要的线稿和材质。

固定九个主体，禁止文字、标题、编号、水印、额外人物、额外肢体或格子框线。最终只输出一张干净、单一纯绿背景的九宫格 PNG；后续程序会把与画布边缘连通的纯绿色安全转换为透明 Alpha。"""


def build_video_prompt(reactions: Sequence[str], screen: Optional[Dict[str, object]]) -> str:
    if screen is None:
        screen_name = "{{SCREEN_NAME_ZH}}"
        screen_hex = "{{SCREEN_HEX}}"
        screen_rgb = "{{SCREEN_RGB}}"
    else:
        screen_name = str(screen["name_zh"])
        screen_hex = str(screen["hex"])
        screen_rgb = ",".join(str(value) for value in screen["rgb"])
    actions = "、".join(reactions)
    return f"""将这张 3×3 九宫格中的九个小人视为九个彼此独立的 GIF 表情素材。九格主题依次是：{actions}。

所有小人必须固定在各自原来的格子和位置内，只做轻微、简单、可循环的表情包动作，不得跨出自己的区域，不得互相遮挡，也不得与其他格子中的角色发生互动。

每个小人的单次动作周期约为 1 秒，并可自然循环。根据人物原本的表情分别匹配摇头、摆手、哭泣、耸肩、点头、震惊后退、得意晃动、轻微跳动或左右侧目等动作；动作语义应优先匹配各格的原始主题。

不要改变人物原本的身份、脸部特征、发型、服装、表情主题、道具、身体比例和九宫格位置。不要新增人物、手臂、手指、文字或物体，不要让身体结构变形。

背景始终保持输入图片中的同一种{screen_name}，精确颜色为 {screen_hex}（RGB {screen_rgb}），颜色、亮度和纹理均不得变化；不要生成场景、阴影、光斑、渐变、棋盘格或背景动画。不要在视频生成阶段尝试把背景改成透明。

镜头完全固定，不推拉、不摇移、不旋转，不改变构图。首尾动作尽量衔接，输出适合社交平台使用的短循环动画。

Keep every subject isolated. Animate only the characters. Preserve clean edges and the original grid layout. Keep the exact uniform screen color unchanged in every frame."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", help="1–36, preset slug, or full Chinese preset name")
    parser.add_argument("--reactions", help="exactly nine reactions, separated or nine Emoji")
    parser.add_argument("--reference-label", default="所附图像", help="neutral label used in the image prompt")
    parser.add_argument("--screen-report", type=Path, help="prepare_sheet.py report for final video prompt")
    parser.add_argument("--output-dir", type=Path, help="directory for compiled prompt files")
    parser.add_argument("--list-styles", action="store_true", help="print all style IDs, slugs and names")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_styles:
        for preset in load_presets():
            print("%02d\t%s\t%s" % (preset["id"], preset["slug"], preset["name_zh"]))
        return 0
    if not args.style or not args.reactions or not args.output_dir:
        raise SystemExit("--style, --reactions, and --output-dir are required unless --list-styles is used")
    style = resolve_style(args.style)
    reactions = parse_reactions(args.reactions)
    screen = screen_from_report(args.screen_report)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    image_prompt = build_image_prompt(style, reactions, args.reference_label)
    video_prompt = build_video_prompt(reactions, screen)
    (output_dir / "image-prompt.txt").write_text(image_prompt + "\n", encoding="utf-8")
    video_name = "video-prompt.txt" if screen else "video-prompt.template.txt"
    (output_dir / video_name).write_text(video_prompt + "\n", encoding="utf-8")
    write_json(
        output_dir / "prompt-plan.json",
        {
            "version": TEMPLATE_VERSION,
            "style": style,
            "reactions": reactions,
            "layout": {"columns": 3, "rows": 3, "count": 9, "order": "row-major"},
            "reference_label": args.reference_label,
            "source_background": SOURCE_BACKGROUND,
            "screen": screen,
            "files": {"image_prompt": "image-prompt.txt", "video_prompt": video_name},
        },
    )
    print(json.dumps({"output_dir": str(output_dir.resolve()), "video_prompt": video_name}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
