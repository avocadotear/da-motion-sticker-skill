from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import pytest

from scripts._core import JobError, load_job
from scripts.create_job import create_job
from scripts.inspect_sheet import inspect_job_sheet, validate_sheet
from scripts.prepare_assets import (
    choose_chroma,
    parse_chroma_key,
    prepare_job_assets,
    select_prepared_route,
)

from ._helpers import ITEMS, make_fake_checkerboard, make_master, make_reference, ready_job


def issue_codes(report: dict) -> set[str]:
    return {issue["code"] for issue in report["issues"]}


def test_true_alpha_nine_cell_sheet_passes(tmp_path: Path) -> None:
    report, normalized = validate_sheet(make_master(tmp_path / "valid.png"))
    assert report["passed"]
    assert report["alpha"]["channel_present"]
    assert len(report["grid"]["cells"]) == 9
    assert normalized.mode == "RGBA"


def test_opaque_checkerboard_is_rejected_as_fake_transparency(tmp_path: Path) -> None:
    report, _ = validate_sheet(make_fake_checkerboard(tmp_path / "checker.png"))
    codes = issue_codes(report)
    assert not report["passed"]
    assert "missing_alpha_channel" in codes
    assert "no_real_transparency" in codes
    assert "fake_checkerboard_transparency" in codes


def test_colorful_subject_does_not_hide_opaque_checkerboard(tmp_path: Path) -> None:
    path = make_fake_checkerboard(tmp_path / "checker-with-subject.png", size=360)
    with Image.open(path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    for row in range(3):
        for column in range(3):
            cx, cy = column * 120 + 60, row * 120 + 60
            draw.ellipse((cx - 32, cy - 32, cx + 32, cy + 32), fill=(245, 75, 55))
    image.save(path)
    report, _ = validate_sheet(path)
    assert "fake_checkerboard_transparency" in issue_codes(report)


def test_missing_cell_and_nontransparent_gutter_are_reported(tmp_path: Path) -> None:
    missing, _ = validate_sheet(make_master(tmp_path / "missing.png", missing=5))
    assert "empty_grid_cell" in issue_codes(missing)
    assert 5 in missing["problem_cells"]

    crossing, _ = validate_sheet(
        make_master(tmp_path / "crossing.png", cross_vertical_gutter=True)
    )
    codes = issue_codes(crossing)
    assert "nontransparent_gap" in codes
    assert "cell_boundary_contact" in codes


def test_alpha_fog_and_tiny_noise_are_rejected(tmp_path: Path) -> None:
    fog = Image.new("RGBA", (360, 360), (0, 0, 0, 8))
    fog.putpixel((0, 0), (0, 0, 0, 0))
    draw = ImageDraw.Draw(fog)
    for row in range(3):
        for column in range(3):
            draw.rectangle((column * 120 + 50, row * 120 + 50, column * 120 + 70, row * 120 + 70), fill=(255, 80, 60, 255))
    fog_path = tmp_path / "fog.png"
    fog.save(fog_path)
    fog_report, _ = validate_sheet(fog_path)
    assert not fog_report["passed"]
    assert "nontransparent_gap" in issue_codes(fog_report)

    noise = Image.new("RGBA", (360, 360), (0, 0, 0, 0))
    draw = ImageDraw.Draw(noise)
    for row in range(3):
        for column in range(3):
            draw.rectangle((column * 120 + 56, row * 120 + 56, column * 120 + 64, row * 120 + 64), fill=(255, 80, 60, 255))
    noise_path = tmp_path / "noise.png"
    noise.save(noise_path)
    noise_report, _ = validate_sheet(noise_path)
    assert not noise_report["passed"]
    assert "empty_grid_cell" in issue_codes(noise_report)


def test_chroma_selection_avoids_foreground_collision() -> None:
    image = Image.new("RGBA", (80, 80), (0, 255, 0, 255))
    selected, scores, needs_review = choose_chroma(image)
    assert not needs_review
    assert selected is not None and selected["name"] in {"blue", "magenta"}
    assert scores["green"]["collision_rate"] == 1.0
    assert scores[selected["name"]]["collision_rate"] == 0.0


def test_all_three_collisions_require_explicit_review() -> None:
    array = np.zeros((60, 90, 4), dtype=np.uint8)
    array[:, :30] = (0, 255, 0, 255)
    array[:, 30:60] = (0, 0, 255, 255)
    array[:, 60:] = (255, 0, 255, 255)
    selected, scores, needs_review = choose_chroma(
        Image.fromarray(array, "RGBA"), conflict_threshold=0.25
    )
    assert selected is None
    assert needs_review
    assert all(score["collision_rate"] >= 0.25 for score in scores.values())
    with pytest.raises(ValueError, match="must be"):
        parse_chroma_key("#112233")


def test_static_pngs_exist_only_when_requested(tmp_path: Path) -> None:
    dynamic_job = ready_job(tmp_path / "dynamic", static=False, route="local")
    dynamic = load_job(dynamic_job)
    assert dynamic["artifacts"]["pngs"] == []
    assert not (dynamic_job.parent / "png").exists()

    static_job = ready_job(tmp_path / "static", static=True, route="local")
    static = load_job(static_job)
    assert len(static["artifacts"]["pngs"]) == 9
    assert all((static_job.parent / entry["path"]).is_file() for entry in static["artifacts"]["pngs"])


def test_prepared_prompt_uses_selected_color_not_hardcoded_green(tmp_path: Path) -> None:
    job_path = ready_job(tmp_path, route="video", chroma="magenta")
    job = load_job(job_path)
    prompt = (job_path.parent / job["paths"]["video_prompt"]).read_text(encoding="utf-8")
    assert "magenta" in prompt
    assert "#FF00FF" in prompt
    assert "{{CHROMA_" not in prompt


def test_auto_route_can_enter_video_wait_without_rebuilding_assets(tmp_path: Path) -> None:
    job_path = ready_job(tmp_path, route="auto", chroma="blue")
    before = load_job(job_path)
    cell_hashes = [entry["sha256"] for entry in before["artifacts"]["cells"]]
    assert before["status"] == "awaiting_route"
    result = select_prepared_route(job_path, "video")
    after = load_job(job_path)
    assert result["status"] == "waiting_for_video"
    assert after["options"]["route"] == "video"
    assert [entry["sha256"] for entry in after["artifacts"]["cells"]] == cell_hashes


def test_preselected_route_cannot_be_overridden_during_preparation(tmp_path: Path) -> None:
    reference = make_reference(tmp_path / "reference.png")
    job_path = create_job(reference, ITEMS, output_root=tmp_path / "runs", route="local")
    assert inspect_job_sheet(job_path, make_master(tmp_path / "sheet.png"))["passed"]
    with pytest.raises(JobError, match="preselected route"):
        prepare_job_assets(job_path, route="video")


def test_sheet_auto_retry_stops_after_two_then_accepts_user_correction(tmp_path: Path) -> None:
    reference = make_reference(tmp_path / "reference.png")
    job_path = create_job(reference, ITEMS, output_root=tmp_path / "runs")
    failed = make_master(tmp_path / "failed.png", missing=5)
    assert not inspect_job_sheet(job_path, failed)["passed"]
    assert not inspect_job_sheet(job_path, failed)["passed"]
    corrected = make_master(tmp_path / "corrected.png")
    with pytest.raises(JobError, match="two attempts"):
        inspect_job_sheet(job_path, corrected)
    assert inspect_job_sheet(job_path, corrected, after_review=True)["passed"]
