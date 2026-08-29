from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts._core import load_job, save_job_atomic
from scripts.animate_local import ALLOWED_MOTIONS, motion_parameters
from scripts.package_job import package_job

from ._helpers import attach_partial_gifs, ready_job


@pytest.mark.parametrize("template", ALLOWED_MOTIONS)
def test_motion_parameters_are_periodic_at_loop_boundary(template: str) -> None:
    start = motion_parameters(template, 0.0)
    end = motion_parameters(template, 1.0)
    assert start.keys() == end.keys()
    for key in start:
        assert start[key] == pytest.approx(end[key], abs=1e-12)


def test_partial_delivery_packages_successes_and_report(tmp_path: Path) -> None:
    job_path = ready_job(tmp_path, static=False, route="local")
    attach_partial_gifs(job_path, (1, 4))
    package = package_job(job_path)
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        gif_names = sorted(name for name in names if name.startswith("gifs/"))
        assert gif_names == ["gifs/01-sticker.gif", "gifs/04-sticker.gif"]
        assert not any(name.startswith("png/") for name in names)
        report = json.loads(archive.read("processing-report.json"))
        assert report["summary"] == {
            "succeeded": 2,
            "failed": 7,
            "partial_delivery": True,
        }
        assert {
            "source/transparent-sheet.png",
            "source/chroma-sheet.png",
            "prompts/image-prompt.txt",
            "prompts/video-prompt.txt",
            "manifest.json",
        }.issubset(names)


def test_static_delivery_contains_exactly_nine_pngs(tmp_path: Path) -> None:
    job_path = ready_job(tmp_path, static=True, route="local")
    attach_partial_gifs(job_path, (2,))
    package = package_job(job_path)
    with zipfile.ZipFile(package) as archive:
        assert len([name for name in archive.namelist() if name.startswith("png/")]) == 9


def test_package_rejects_missing_hash_and_duplicate_artifact_path(tmp_path: Path) -> None:
    missing_hash_job = ready_job(tmp_path / "missing", static=False, route="local")
    attach_partial_gifs(missing_hash_job, (1,))
    job = load_job(missing_hash_job)
    job["artifacts"]["gifs"][0].pop("sha256")
    save_job_atomic(missing_hash_job, job)
    with pytest.raises(Exception, match="SHA-256"):
        package_job(missing_hash_job)

    duplicate_job = ready_job(tmp_path / "duplicate", static=False, route="local")
    attach_partial_gifs(duplicate_job, (1,))
    job = load_job(duplicate_job)
    duplicate = dict(job["artifacts"]["gifs"][0])
    duplicate["index"] = 2
    job["artifacts"]["gifs"].append(duplicate)
    save_job_atomic(duplicate_job, job)
    with pytest.raises(ValueError, match="duplicate GIF artifact path"):
        package_job(duplicate_job)
