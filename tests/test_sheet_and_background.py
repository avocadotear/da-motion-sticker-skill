from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from _helpers import make_transparent_sheet, run_script
from _media import choose_screen, open_rgba, remove_connected_background


def test_connected_background_preserves_enclosed_matching_color() -> None:
    image = Image.new("RGB", (100, 100), (0, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 80, 80), fill=(220, 40, 40))
    draw.rectangle((35, 35, 65, 65), fill=(0, 255, 0))
    result, report = remove_connected_background(image, (0, 255, 0), threshold=10, feather=10)
    alpha = np.asarray(result.getchannel("A"), dtype=np.uint8)
    assert alpha[0, 0] == 0
    assert alpha[50, 50] == 255
    assert report["fully_removed_fraction"] > 0.5


def test_screen_selection_avoids_foreground_main_color() -> None:
    image = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((15, 15, 105, 105), fill=(0, 245, 0, 255))
    selected, scores = choose_screen(image)
    assert selected != "green"
    assert scores["green"]["collision_fraction"] > 0.9


def test_prepare_sheet_outputs_nine_cells_and_screen(tmp_path: Path) -> None:
    source = make_transparent_sheet(tmp_path / "sheet.png")
    output = tmp_path / "prepared"
    run_script("prepare_sheet.py", [source, output, "--cell-size", "128", "--export-static"])
    report = json.loads((output / "sheet-report.json").read_text(encoding="utf-8"))
    assert report["layout"]["count"] == 9
    assert report["layout"]["confidence"] >= 0.75
    assert report["selected_screen"]["id"] in {"green", "blue", "magenta", "white"}
    assert len(list((output / "cells").glob("*.png"))) == 9
    assert len(list((output / "static").glob("*.png"))) == 9
    for path in sorted((output / "cells").glob("*.png")):
        image = open_rgba(path)
        assert image.size == (128, 128)
        alpha = np.asarray(image.getchannel("A"), dtype=np.uint8)
        assert alpha.min() == 0
        assert alpha.max() == 255


def test_prepare_sheet_repairs_only_uniform_opaque_background(tmp_path: Path) -> None:
    transparent = Image.open(make_transparent_sheet(tmp_path / "alpha.png", size=300)).convert("RGBA")
    background = Image.new("RGBA", transparent.size, (0, 255, 0, 255))
    opaque = Image.alpha_composite(background, transparent).convert("RGB")
    source = tmp_path / "opaque.png"
    opaque.save(source)
    output = tmp_path / "prepared"
    run_script("prepare_sheet.py", [source, output, "--cell-size", "96"])
    report = json.loads((output / "sheet-report.json").read_text(encoding="utf-8"))
    assert report["alpha_method"] == "uniform-edge-repair"
    assert report["normalized_alpha"]["transparent_fraction"] > 0.1


def test_prepare_sheet_rejects_checkerboard_fake_transparency(tmp_path: Path) -> None:
    image = Image.new("RGB", (300, 300), (230, 230, 230))
    draw = ImageDraw.Draw(image)
    for y in range(0, 300, 20):
        for x in range(0, 300, 20):
            if (x // 20 + y // 20) % 2:
                draw.rectangle((x, y, x + 19, y + 19), fill=(190, 190, 190))
    source = tmp_path / "checkerboard.png"
    image.save(source)
    completed = run_script("prepare_sheet.py", [source, tmp_path / "prepared"], check=False)
    assert completed.returncode != 0
    assert "uniform edge background" in completed.stderr
