from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from _helpers import make_keypose_sheets, make_transparent_sheet, run_script
from _media import inspect_gif


REACTIONS = "🚲🚗🎉😭💪😎🤔🤩🍕"


def test_codex_animation_and_delivery(tmp_path: Path) -> None:
    source = make_transparent_sheet(tmp_path / "sheet.png")
    prepared = tmp_path / "prepared"
    run_script("prepare_sheet.py", [source, prepared, "--cell-size", "128", "--export-static"])

    prompts = tmp_path / "prompts"
    run_script(
        "compile_prompts.py",
        [
            "--style",
            "big-head-chibi",
            "--reactions",
            REACTIONS,
            "--screen-report",
            prepared / "sheet-report.json",
            "--output-dir",
            prompts,
        ],
    )
    keypose_plan = tmp_path / "keypose-plan"
    run_script(
        "compile_keypose_plan.py",
        [
            "--input-dir",
            prepared / "cells",
            "--output-dir",
            keypose_plan,
            "--reactions",
            REACTIONS,
        ],
    )
    plan_payload = json.loads((keypose_plan / "keypose-plan.json").read_text(encoding="utf-8"))
    assert plan_payload["source_background"]["mode"] == "solid-background-first"
    assert plan_payload["source_background"]["hex"] == "#00FF00"
    first_prompt = (keypose_plan / "prompts" / "01.txt").read_text(encoding="utf-8")
    assert "do not ask the generator to reproduce transparency" in first_prompt
    assert "#00FF00" in first_prompt
    assert "RGBA transparent 2×2" not in first_prompt
    assert plan_payload["mode"] == "keypose-local"
    assert "whole-layer-translation" in plan_payload["forbidden_fallbacks"]

    pose_sheets = make_keypose_sheets(prepared / "cells", tmp_path / "keypose-sheets")
    keyposes = tmp_path / "keyposes"
    run_script(
        "prepare_keyposes.py",
        [
            "--source-cells",
            prepared / "cells",
            "--pose-sheets",
            pose_sheets,
            "--output-dir",
            keyposes,
            "--size",
            "128",
        ],
    )
    keypose_output = tmp_path / "keypose-output"
    run_script("render_keypose_pack.py", [keyposes, keypose_output, "--fps", "6"])
    gifs = keypose_output / "gifs"
    processing = json.loads((keypose_output / "processing.json").read_text(encoding="utf-8"))
    assert processing["mode"] == "keypose-local"
    assert processing["affine_fallback"] is False
    assert processing["cells"][0]["sequence_zero_based"] == [0, 1, 2, 3, 2, 1]
    for index in range(1, 10):
        inspection = inspect_gif(gifs / ("%02d.gif" % index))
        assert inspection["frames"] >= 2
        assert inspection["loop"] == 0
        assert inspection["has_transparency"]
    with Image.open(gifs / "01.gif") as gif:
        gif.seek(0)
        first = np.asarray(gif.convert("RGBA"), dtype=np.uint8)
        gif.seek(2)
        peak = np.asarray(gif.convert("RGBA"), dtype=np.uint8)
    assert float(np.abs(first.astype(float) - peak.astype(float)).mean()) > 2.0

    pet_map = tmp_path / "pet-source-map.json"
    run_script(
        "prepare_pet_handoff.py",
        ["--gif-dir", gifs, "--output", pet_map, "--reactions", REACTIONS],
    )
    pet_payload = json.loads(pet_map.read_text(encoding="utf-8"))
    assert pet_payload["complete_pet"] is False
    assert len({item["suggested_state"] for item in pet_payload["mappings"]}) == 9

    delivery = tmp_path / "delivery"
    run_script(
        "package_delivery.py",
        [
            "--gif-dir",
            gifs,
            "--output-dir",
            delivery,
            "--route",
            "A",
            "--transparent-sheet",
            prepared / "sheet-transparent.png",
            "--screen-sheet",
            prepared / "sheet-screen.png",
            "--static-dir",
            prepared / "static",
            "--prompts-dir",
            prompts,
            "--keypose-plan-dir",
            keypose_plan,
            "--sheet-report",
            prepared / "sheet-report.json",
            "--report",
            keyposes / "keypose-preparation.json",
            "--report",
            keypose_output / "processing.json",
            "--first-frames-dir",
            keypose_output / "first-frames",
        ],
    )
    manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is True
    assert manifest["gif_count"] == 9
    assert manifest["static_included"] is True
    archive_path = delivery / "da-motion-sticker-pack.zip"
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert "gifs/01.gif" in names
    assert "gifs/09.gif" in names
    assert "manifest.json" in names
    assert "da-motion-sticker-pack.zip" not in names

    delivery_without_static = tmp_path / "delivery-no-static"
    run_script(
        "package_delivery.py",
        [
            "--gif-dir",
            gifs,
            "--output-dir",
            delivery_without_static,
            "--route",
            "A",
            "--transparent-sheet",
            prepared / "sheet-transparent.png",
            "--screen-sheet",
            prepared / "sheet-screen.png",
            "--prompts-dir",
            prompts,
            "--keypose-plan-dir",
            keypose_plan,
            "--sheet-report",
            prepared / "sheet-report.json",
        ],
    )
    no_static_manifest = json.loads((delivery_without_static / "manifest.json").read_text(encoding="utf-8"))
    assert no_static_manifest["static_included"] is False
    assert not (delivery_without_static / "static").exists()
