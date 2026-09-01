#!/usr/bin/env python3
"""Create a reviewed source-state map for an explicit Codex pet follow-up."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from _media import inspect_gif, numbered_files, read_json, write_json
from compile_prompts import parse_reactions


PET_STATES = ["idle", "walk", "run", "happy", "sad", "celebrate", "work", "sleep", "alert"]


def preferred_state(reaction: str) -> Optional[str]:
    lowered = reaction.lower()
    groups = [
        ("sleep", ["睡", "困", "晚安", "😴", "💤"]),
        ("sad", ["哭", "伤心", "委屈", "😭", "😢", "🥹"]),
        ("celebrate", ["庆祝", "派对", "🎉", "🥳", "胜利"]),
        ("alert", ["震惊", "警觉", "惊讶", "😱", "🤯", "!"]),
        ("work", ["工作", "思考", "学习", "🤔", "💪", "电脑"]),
        ("run", ["跑", "冲", "开车", "🚗", "🏃"]),
        ("walk", ["走", "骑", "🚲", "散步"]),
        ("happy", ["开心", "喜欢", "大笑", "🤩", "😎", "❤️"]),
    ]
    for state, tokens in groups:
        if any(token.lower() in lowered for token in tokens):
            return state
    return None


def assign_states(reactions: List[str]) -> List[str]:
    assigned: List[Optional[str]] = [None] * 9
    used = set()
    for index, reaction in enumerate(reactions):
        state = preferred_state(reaction)
        if state and state not in used:
            assigned[index] = state
            used.add(state)
    remaining = [state for state in PET_STATES if state not in used]
    for index, value in enumerate(assigned):
        if value is None:
            assigned[index] = remaining.pop(0)
    return [str(value) for value in assigned]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gif-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reactions")
    parser.add_argument("--prompt-plan", type=Path)
    parser.add_argument("--states", help="explicit comma-separated nine-state mapping")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gifs = numbered_files(args.gif_dir, ".gif")
    missing = [path.name for path in gifs if not path.is_file()]
    if missing:
        raise SystemExit("missing GIFs: %s" % missing)
    if args.reactions:
        reactions = parse_reactions(args.reactions)
    elif args.prompt_plan:
        plan = read_json(args.prompt_plan)
        if not isinstance(plan, dict) or not isinstance(plan.get("reactions"), list) or len(plan["reactions"]) != 9:
            raise SystemExit("prompt plan does not contain nine reactions")
        reactions = [str(value) for value in plan["reactions"]]
    else:
        reactions = ["source-%02d" % index for index in range(1, 10)]
    if args.states:
        states = [value.strip() for value in args.states.replace("，", ",").split(",") if value.strip()]
        if len(states) != 9 or set(states) != set(PET_STATES):
            raise SystemExit("--states must contain each standard state exactly once: %s" % PET_STATES)
    else:
        states = assign_states(reactions)

    mappings: List[Dict[str, object]] = []
    for index, path in enumerate(gifs):
        inspection = inspect_gif(path)
        if inspection["frames"] < 2 or not inspection["nonempty"]:
            raise SystemExit("invalid GIF source for pet handoff: %s" % path)
        mappings.append(
            {
                "source_index": index + 1,
                "source_gif": str(path.resolve()),
                "reaction": reactions[index],
                "suggested_state": states[index],
                "inspection": inspection,
            }
        )
    write_json(
        args.output,
        {
            "version": 1,
            "purpose": "hatch-pet-source-handoff",
            "complete_pet": False,
            "requires_skill": "hatch-pet",
            "required_next_work": [
                "review semantic state mapping",
                "build all nine standard animation rows",
                "complete 16 look directions",
                "assemble spriteVersionNumber 2 package",
                "render and visually QA previews",
            ],
            "mappings": mappings,
        },
    )
    print(json.dumps({"output": str(args.output.resolve()), "count": 9, "complete_pet": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
