from __future__ import annotations

import json
from pathlib import Path

import pytest

from _helpers import run_script
from compile_prompts import parse_reactions, resolve_style


def test_parse_nine_adjacent_emoji() -> None:
    assert parse_reactions("🚲🚗🎉😭💪😎🤔🤩🍕") == ["🚲", "🚗", "🎉", "😭", "💪", "😎", "🤔", "🤩", "🍕"]


def test_reject_wrong_reaction_count() -> None:
    with pytest.raises(ValueError):
        parse_reactions("开心,难过")


def test_style_library_resolves_all_presets() -> None:
    for index in range(1, 37):
        assert int(resolve_style(str(index))["id"]) == index


def test_compile_screen_aware_prompts(tmp_path: Path) -> None:
    screen_report = tmp_path / "sheet-report.json"
    screen_report.write_text(
        json.dumps({"selected_screen": {"id": "magenta", "rgb": [255, 0, 255], "hex": "#FF00FF"}}),
        encoding="utf-8",
    )
    output = tmp_path / "prompts"
    run_script(
        "compile_prompts.py",
        [
            "--style",
            "2",
            "--reactions",
            "🚲🚗🎉😭💪😎🤔🤩🍕",
            "--screen-report",
            screen_report,
            "--output-dir",
            output,
        ],
    )
    image_prompt = (output / "image-prompt.txt").read_text(encoding="utf-8")
    video_prompt = (output / "video-prompt.txt").read_text(encoding="utf-8")
    assert "纯绿色 #00FF00" in image_prompt
    assert "不要请求或模拟透明背景" in image_prompt
    assert "真正 RGBA 透明 PNG" not in image_prompt
    assert "禁止白色描边" in image_prompt
    assert "#FF00FF" in video_prompt
    assert "纯洋红色" in video_prompt
    assert "{{SCREEN" not in video_prompt
    plan = json.loads((output / "prompt-plan.json").read_text(encoding="utf-8"))
    assert plan["layout"]["count"] == 9
    assert len(plan["reactions"]) == 9
    assert plan["version"] == 2
    assert plan["source_background"] == {
        "mode": "solid-background-first",
        "id": "green",
        "name_zh": "纯绿色",
        "hex": "#00FF00",
        "rgb": [0, 255, 0],
    }
