from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from _helpers import make_video_frames, run_script
from _media import inspect_gif


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg unavailable")
def test_grid_video_to_nine_transparent_gifs(tmp_path: Path) -> None:
    frames = tmp_path / "frames"
    make_video_frames(frames, frame_count=6, size=300)
    video = tmp_path / "grid.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-framerate",
            "6",
            "-i",
            str(frames / "frame_%03d.png"),
            "-c:v",
            "mpeg4",
            "-q:v",
            "2",
            "-pix_fmt",
            "yuv420p",
            str(video),
            "-loglevel",
            "error",
        ],
        check=True,
    )
    output = tmp_path / "processed"
    completed = run_script(
        "process_video.py",
        [
            video,
            output,
            "--fps",
            "6",
            "--size",
            "96",
            "--color-threshold",
            "70",
            "--feather",
            "60",
            "--grid-debug",
        ],
        check=False,
    )
    assert completed.returncode == 0, completed.stderr + "\n" + completed.stdout
    report = json.loads((output / "processing.json").read_text(encoding="utf-8"))
    assert report["layout"]["count"] == 9
    assert len(report["cells"]) == 9
    assert (output / "grid-debug.png").is_file()
    for index in range(1, 10):
        inspection = inspect_gif(output / "gifs" / ("%02d.gif" % index))
        assert inspection["frames"] >= 2
        assert inspection["loop"] == 0
        assert inspection["has_transparency"]
        assert inspection["nonempty"]
