from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts._core import (
    JobError,
    load_job,
    resolve_job_path,
    save_job_atomic,
    sha256_file,
    slugify,
    update_status,
)
from scripts.create_job import create_job
from scripts.process_video import process_job

from ._helpers import ITEMS, make_reference, ready_job


def test_slug_is_ascii_stable_and_windows_safe() -> None:
    assert slugify("中文🎉", fallback="sticker") == "sticker"
    assert slugify("COM1") == "com1-file"
    assert slugify("  A / b\\c : d?.  ") == "a-b-c-d"
    assert slugify("a" * 100, max_length=12) == "a" * 12


def test_job_path_rejects_absolute_and_parent_escape(tmp_path: Path) -> None:
    reference = make_reference(tmp_path / "ref.png")
    job_path = create_job(reference, ITEMS, output_root=tmp_path / "runs")
    with pytest.raises(JobError, match="must be relative"):
        resolve_job_path(job_path, tmp_path / "outside.png")
    with pytest.raises(JobError, match="escapes"):
        resolve_job_path(job_path, "../outside.png")
    assert resolve_job_path(job_path, "source/ok.png").parent == job_path.parent / "source"


def test_input_hash_is_content_stable_and_option_sensitive(tmp_path: Path) -> None:
    first = make_reference(tmp_path / "one" / "ref.png")
    second = tmp_path / "two" / "same bytes.png"
    second.parent.mkdir(parents=True)
    second.write_bytes(first.read_bytes())
    job_a = create_job(first, ITEMS, output_root=tmp_path / "a", style="auto")
    job_b = create_job(second, ITEMS, output_root=tmp_path / "b", style="auto")
    job_c = create_job(second, [*ITEMS[:-1], "different"], output_root=tmp_path / "c", style="auto")
    assert load_job(job_a)["input_hash"] == load_job(job_b)["input_hash"]
    assert load_job(job_a)["input_hash"] != load_job(job_c)["input_hash"]


def test_video_resume_rejects_a_different_sha256_before_processing(tmp_path: Path) -> None:
    reference = make_reference(tmp_path / "ref.png")
    job_path = create_job(reference, ITEMS, output_root=tmp_path / "runs", route="video")
    job = load_job(job_path)
    job["status"] = "waiting_for_video"
    recorded = job_path.parent / "source" / "input-video.mp4"
    recorded.write_bytes(b"the video bound to this job")
    job["video_input"] = {"path": "source/input-video.mp4", "sha256": sha256_file(recorded)}
    save_job_atomic(job_path, job)
    uploaded = tmp_path / "different upload.mp4"
    uploaded.write_bytes(b"not the recorded video")
    with pytest.raises(ValueError, match="hash does not match"):
        process_job(job_path, uploaded)


def test_reference_binding_rejects_a_replaced_input(tmp_path: Path) -> None:
    reference = make_reference(tmp_path / "ref.png")
    job_path = create_job(reference, ITEMS, output_root=tmp_path / "runs")
    job = load_job(job_path)
    bound = job_path.parent / job["reference"]["path"]
    bound.write_bytes(bound.read_bytes() + b"changed")
    with pytest.raises(JobError, match="reference file hash changed"):
        load_job(job_path)


def test_manifest_rejects_tampered_slug_before_any_output_can_escape(tmp_path: Path) -> None:
    reference = make_reference(tmp_path / "ref.png")
    job_path = create_job(reference, ITEMS, output_root=tmp_path / "runs")
    payload = job_path.read_text(encoding="utf-8")
    job_path.write_text(
        payload.replace('"slug": "01-sticker"', '"slug": "01-x/../../../outside/pwn"'),
        encoding="utf-8",
    )
    with pytest.raises(JobError, match="slug must remain canonical"):
        load_job(job_path)
    assert not (tmp_path / "outside" / "pwn.gif").exists()


def test_central_state_machine_rejects_invalid_transition(tmp_path: Path) -> None:
    reference = make_reference(tmp_path / "ref.png")
    job_path = create_job(reference, ITEMS, output_root=tmp_path / "runs")
    job = load_job(job_path)
    with pytest.raises(JobError, match="invalid status transition"):
        update_status(job_path, job, "local_animated")


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is required")
def test_invalid_video_is_not_bound_before_probe_and_decode(tmp_path: Path) -> None:
    job_path = ready_job(tmp_path, route="video")
    invalid = tmp_path / "not-video.mp4"
    invalid.write_bytes(b"not a media container")
    with pytest.raises(ValueError):
        process_job(job_path, invalid)
    assert load_job(job_path).get("video_input") is None
