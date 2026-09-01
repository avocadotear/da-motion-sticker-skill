#!/usr/bin/env python3
"""Compile nine per-sticker prompts for real key-pose image generation."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from _media import numbered_files, sha256_file, write_json
from compile_prompts import SOURCE_BACKGROUND, parse_reactions


def suggested_motion(reaction: str) -> str:
    lowered = reaction.lower()
    rules = [
        (["🚲", "骑", "自行车"], "complete one small pedaling cycle on the existing bicycle, with knees and torso visibly changing pose"),
        (["🚗", "开车", "汽车"], "turn the existing steering pose slightly, react with the face, then settle back; do not create a vehicle if none is visible"),
        (["🎉", "庆祝", "派对", "胜利"], "draw the existing arms inward in anticipation, then lift them in a clear celebration peak, then relax"),
        (["😭", "哭", "伤心", "委屈"], "tense the shoulders, squeeze the eyes and mouth into a stronger crying peak, then recover while preserving existing tears"),
        (["💪", "加油", "力量", "肌肉"], "prepare the existing flex pose, contract into a stronger power pose, then release slightly"),
        (["😎", "酷", "得意", "墨镜"], "shift from neutral confidence into a pronounced chin-and-brow attitude pose, then return; preserve existing eyewear"),
        (["🤔", "思考", "疑惑"], "move eyes and brows into a clear thinking sequence, adjust the existing thinking hand only if already visible, then recover"),
        (["🤩", "兴奋", "惊喜", "崇拜"], "anticipate with a small crouch or facial intake, open into an excited peak with visibly changed expression, then settle"),
        (["🍕", "披萨", "吃", "美食"], "prepare and complete one small bite using the existing food prop if visible; otherwise change only the face into a delighted tasting reaction"),
        (["😴", "睡", "困"], "lower the eyelids and head into a brief dozing peak, then recover to the start pose"),
        (["😱", "🤯", "震惊", "惊讶"], "draw back in anticipation, reach a clear shocked face-and-body peak, then recover"),
    ]
    for tokens, motion in rules:
        if any(token.lower() in lowered for token in tokens):
            return motion
    return "perform one small readable reaction cycle with genuine face and body pose changes that match the visible sticker, then recover"


def load_motion_overrides(path: Optional[Path]) -> Optional[List[str]]:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("motions") or payload.get("tiles")
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            payload = [item.get("motion") for item in payload]
    if not isinstance(payload, list) or len(payload) != 9 or not all(isinstance(item, str) and item.strip() for item in payload):
        raise ValueError("motion override must provide exactly nine non-empty motion strings")
    return [item.strip() for item in payload]


def build_prompt(index: int, reaction: str, motion: str) -> str:
    return f"""Use the attached sticker PNG as the only character and style reference. Its transparent pixels are reference data only; do not ask the generator to reproduce transparency.

Create one square opaque 2×2 key-pose sheet for sticker {index:02d}, whose reaction theme is “{reaction}”. The intended motion is: {motion}.

The four cells, in row-major order, must show the same character at the same scale and fixed camera:
1. START — reproduce the attached sticker's exact identity, outfit, colors, proportions, visible props and starting expression.
2. ANTICIPATION — a small but genuine preparatory pose change in the face and relevant body parts.
3. ACTION PEAK — the clearest readable peak of the action, with real articulation and expression change rather than whole-character displacement.
4. RECOVERY — release from the peak toward the original pose without becoming identical to the peak.

Preserve the exact face, hair or fur, clothing, accessories, prop inventory, art style, lighting and material. Do not add a prop merely because the reaction text mentions one; animate an object only when it already exists in the reference. Do not invent people, limbs, fingers, text or scenery. Do not change camera, character scale or body center. Feet or the lowest body contact point stay on one fixed baseline.

Use a strict 2 columns × 2 rows layout. Fill the entire canvas, every cell background and all wide gutters with one exact flat pure green: #00FF00 (RGB 0,255,0). The green must be uniform, opaque and continuously connected to all four canvas edges, with no gradient, texture, noise, lighting change or enclosed background islands. Keep all body parts, tears, accents and existing props inside their own cells. Do not request transparency. No checkerboard, card, floor, scene, shadow backdrop, white outline, black outer outline, colored sticker border, glow, halo or drop shadow.

The three motion poses must visibly change actual facial features and/or articulated body pose. Never simulate motion by translating, rotating, scaling, bouncing, shaking or swaying the entire unchanged character layer. Output only the single-solid-green-background 2×2 PNG pose sheet. A local processor will later convert only edge-connected green background pixels into real Alpha."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True, help="01.png–09.png source cells")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reactions", required=True)
    parser.add_argument("--motions-file", type=Path, help="vision-reviewed JSON list of nine motion strings")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    sources = numbered_files(args.input_dir, ".png")
    missing = [path.name for path in sources if not path.is_file()]
    if missing:
        raise SystemExit("missing source cells: %s" % missing)
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        if not args.overwrite:
            raise SystemExit("output directory is not empty; use a fresh directory or --overwrite")
        shutil.rmtree(args.output_dir)
    prompts_dir = args.output_dir / "prompts"
    prompts_dir.mkdir(parents=True)
    reactions = parse_reactions(args.reactions)
    overrides = load_motion_overrides(args.motions_file)
    tiles: List[Dict[str, object]] = []
    for index, (source, reaction) in enumerate(zip(sources, reactions), start=1):
        motion = overrides[index - 1] if overrides else suggested_motion(reaction)
        prompt = build_prompt(index, reaction, motion)
        prompt_path = prompts_dir / ("%02d.txt" % index)
        prompt_path.write_text(prompt + "\n", encoding="utf-8")
        tiles.append(
            {
                "id": "%02d" % index,
                "reaction": reaction,
                "source_cell": str(source.resolve()),
                "source_sha256": sha256_file(source),
                "motion": motion,
                "prompt": str(prompt_path.relative_to(args.output_dir)),
                "expected_pose_sheet": "keypose-sheets/%02d.png" % index,
                "layout": {"columns": 2, "rows": 2, "count": 4},
                "poses": ["start", "anticipation", "peak", "recovery"],
            }
        )
    plan_path = args.output_dir / "keypose-plan.json"
    write_json(
        plan_path,
        {
            "version": 1,
            "mode": "keypose-local",
            "source_count": 9,
            "pose_count_per_sticker": 4,
            "motion_source": "vision-reviewed-overrides" if overrides else "reaction-semantic-suggestion-requires-visual-review",
            "source_background": SOURCE_BACKGROUND,
            "tiles": tiles,
            "forbidden_fallbacks": ["whole-layer-translation", "whole-layer-rotation", "whole-layer-scale", "bounce", "shake", "sway"],
        },
    )
    print(json.dumps({"plan": str(plan_path.resolve()), "count": 9}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
