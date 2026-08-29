from __future__ import annotations

import os
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from scripts._core import find_ffmpeg, load_job
from scripts.animate_local import animate_job
from scripts.package_job import package_job
from scripts.process_video import _decode_once, process_job

from ._helpers import make_chroma_video, make_single_frame_video, make_vfr_chroma_video, ready_job


RUN_MEDIA = os.environ.get("DA_RUN_MEDIA_TESTS") == "1"
MEDIA_REASON = "set DA_RUN_MEDIA_TESTS=1 and install ffmpeg/ffprobe to run media tests"


@pytest.mark.skipif(
    not RUN_MEDIA or not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason=MEDIA_REASON,
)
@pytest.mark.parametrize(
    ("source_fps", "chroma"),
    [(24, "green"), (30, "blue"), (60, "magenta")],
)
def test_synthetic_video_end_to_end_across_fps_and_keys(
    tmp_path: Path, source_fps: int, chroma: str
) -> None:
    root = tmp_path / f"中文 空格 {source_fps} {chroma}"
    job_path = ready_job(root, static=False, route="video", chroma=chroma)
    video = make_chroma_video(
        root / "上传 视频" / f"动画 {source_fps}fps.mkv",
        source_fps=source_fps,
        chroma=chroma,
        compressed=source_fps == 30,
    )
    report = process_job(job_path, video, manual_grid="60,120,60,120")
    assert report["summary"] == {
        "succeeded": 9,
        "failed": 0,
        "partial_delivery": False,
    }
    assert report["timeline"]["fps"] == 12
    assert 10 <= report["timeline"]["decoded_frames"] <= 13
    assert report["video"]["avg_frame_rate"] in {
        f"{source_fps}/1",
        str(source_fps),
    }

    job = load_job(job_path)
    assert job["status"] == "video_processed"
    assert len(job["artifacts"]["gifs"]) == 9
    for artifact in job["artifacts"]["gifs"]:
        output_gif = job_path.parent / artifact["path"]
        with Image.open(output_gif) as gif:
            assert gif.size == (512, 512)
            assert gif.info.get("loop") == 0
            assert 10 <= gif.n_frames <= 13
            durations = []
            has_transparency = False
            for frame_index in range(gif.n_frames):
                gif.seek(frame_index)
                durations.append(int(gif.info.get("duration", 0)))
                rgba = np.asarray(gif.convert("RGBA"), dtype=np.uint8)
                has_transparency |= bool(np.any(rgba[..., 3] == 0))
            assert 850 <= sum(durations) <= 1150
            assert has_transparency


@pytest.mark.skipif(
    not RUN_MEDIA or not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason=MEDIA_REASON,
)
def test_local_animation_and_package_end_to_end(tmp_path: Path) -> None:
    job_path = ready_job(tmp_path / "本地 动效", static=True, route="local")
    outputs = animate_job(job_path)
    assert len(outputs) == 9
    job = load_job(job_path)
    assert job["status"] == "local_animated"
    first = job_path.parent / outputs[0]["path"]
    with Image.open(first) as gif:
        assert gif.size == (512, 512)
        assert gif.info.get("loop") == 0
        assert gif.n_frames == 12
        assert 850 <= sum(int((gif.seek(i), gif.info.get("duration", 0))[1]) for i in range(gif.n_frames)) <= 1150
        gif.seek(0)
        assert np.any(np.asarray(gif.convert("RGBA"), dtype=np.uint8)[..., 3] == 0)
    package = package_job(job_path)
    assert package.is_file()
    assert load_job(job_path)["status"] == "packaged"


@pytest.mark.skipif(
    not RUN_MEDIA or not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason=MEDIA_REASON,
)
def test_vfr_and_short_video_timeline_handling(tmp_path: Path) -> None:
    vfr_root = tmp_path / "VFR 中文"
    vfr_job = ready_job(vfr_root, route="video", chroma="blue")
    vfr_video = make_vfr_chroma_video(vfr_root / "输入 VFR.mkv", chroma="blue")
    vfr_report = process_job(vfr_job, vfr_video)
    assert vfr_report["summary"]["succeeded"] == 9
    assert 10 <= vfr_report["timeline"]["decoded_frames"] <= 14
    assert vfr_report["grid"]["confidence"] >= 0.70

    short_root = tmp_path / "短 视频"
    short_job = ready_job(short_root, route="video", chroma="green")
    short_video = make_chroma_video(
        short_root / "short.mkv",
        source_fps=24,
        chroma="green",
        duration_seconds=0.35,
    )
    short_report = process_job(short_job, short_video, manual_grid="60,120,60,120")
    assert short_report["summary"]["succeeded"] == 9
    assert all(item["loop"]["method"] == "ping_pong" for item in short_report["items"])


@pytest.mark.skipif(
    not RUN_MEDIA or not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason=MEDIA_REASON,
)
def test_single_frame_video_decodes_once_without_crashing(tmp_path: Path) -> None:
    video = make_single_frame_video(tmp_path / "单帧 视频.mkv")
    decoded = _decode_once(find_ffmpeg("ffmpeg"), video, tmp_path / "decoded once", 12)
    assert len(decoded) == 1
