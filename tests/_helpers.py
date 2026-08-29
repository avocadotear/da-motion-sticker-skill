from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from PIL import Image, ImageDraw

from scripts._core import load_job, relative_job_path, save_job_atomic, sha256_file
from scripts.create_job import create_job
from scripts.inspect_sheet import inspect_job_sheet
from scripts.prepare_assets import prepare_job_assets


ITEMS = [
    "开心",
    "生气",
    "疑问",
    "点头",
    "等待",
    "喜欢",
    "跳跃",
    "摇头",
    "再见",
]

CHROMA_RGB = {
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "magenta": (255, 0, 255),
}


def make_reference(path: Path, *, color: tuple[int, int, int, int] = (238, 90, 70, 255)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (72, 72), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((14, 8, 58, 52), fill=color)
    draw.rectangle((23, 45, 49, 65), fill=color)
    image.save(path)
    return path


def make_master(
    path: Path,
    *,
    size: int = 360,
    missing: int | None = None,
    cross_vertical_gutter: bool = False,
) -> Path:
    """Create a copyright-free, true-alpha 3x3 fixture in reading order."""

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cell = size / 3
    colors = (
        (225, 60, 50, 255),
        (255, 190, 20, 255),
        (30, 145, 225, 255),
        (130, 70, 215, 255),
        (240, 110, 170, 255),
        (20, 175, 170, 255),
        (235, 120, 35, 255),
        (65, 105, 220, 255),
        (100, 185, 75, 255),
    )
    radius = max(10, round(cell * 0.22))
    for index in range(9):
        if missing == index + 1:
            continue
        row, column = divmod(index, 3)
        cx = round((column + 0.5) * cell)
        cy = round((row + 0.5) * cell)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=colors[index])
        # An asymmetric mark gives motion/frame comparisons a stable feature.
        draw.rectangle(
            (cx + radius // 4, cy - radius // 2, cx + radius // 2, cy),
            fill=(30, 30, 30, 255),
        )
    if cross_vertical_gutter:
        gutter = round(size / 3)
        draw.rectangle((gutter - 5, 32, gutter + 5, 72), fill=(240, 30, 30, 255))
    image.save(path)
    return path


def make_fake_checkerboard(path: Path, *, size: int = 240) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (size, size), (208, 208, 208))
    draw = ImageDraw.Draw(image)
    tile = 16
    for y in range(0, size, tile):
        for x in range(0, size, tile):
            if (x // tile + y // tile) % 2:
                draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(240, 240, 240))
    image.save(path)
    return path


def ready_job(
    root: Path,
    *,
    static: bool = False,
    route: str = "local",
    chroma: str = "green",
    canvas_size: int = 512,
    content_size: int = 448,
) -> Path:
    reference = make_reference(root / "input" / "角色 参考.png")
    job_path = create_job(
        reference,
        ITEMS,
        output_root=root / "runs",
        pack_name="测试 表情包",
        static=static,
        route=route,
    )
    master = make_master(root / "input" / "透明 九宫格.png")
    attempt = inspect_job_sheet(job_path, master)
    assert attempt["passed"]
    result = prepare_job_assets(
        job_path,
        chroma_key=chroma,
        canvas_size=canvas_size,
        content_size=content_size,
    )
    assert not result["needs_review"]
    return job_path


def make_small_gif(path: Path, *, frames: int = 12) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    images: list[Image.Image] = []
    for index in range(frames):
        frame = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)
        draw.ellipse((150 + index * 3, 160, 350 + index * 3, 360), fill=(240, 80, 60, 255))
        images.append(frame)
    images[0].save(
        path,
        save_all=True,
        append_images=images[1:],
        duration=83,
        loop=0,
        disposal=2,
        transparency=0,
    )
    return path


def attach_partial_gifs(job_path: Path, indices: Sequence[int] = (1, 4)) -> list[Path]:
    job = load_job(job_path)
    outputs: list[Path] = []
    records = []
    for index in indices:
        slug = str(job["contents"][index - 1]["slug"])
        destination = job_path.parent / "gifs" / f"{slug}.gif"
        make_small_gif(destination)
        outputs.append(destination)
        records.append(
            {
                "index": index,
                "path": relative_job_path(job_path, destination),
                "sha256": sha256_file(destination),
            }
        )
    job["artifacts"]["gifs"] = records
    job["status"] = "local_animated"
    save_job_atomic(job_path, job)
    return outputs


def make_chroma_video(
    destination: Path,
    *,
    source_fps: int,
    chroma: str,
    size: int = 180,
    duration_seconds: float = 1.0,
    compressed: bool = False,
) -> Path:
    """Create a lossless synthetic 3x3 video using only Pillow and FFmpeg."""

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for the media fixture")
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame_dir = destination.parent / f".{destination.stem}-frames"
    frame_dir.mkdir()
    key = CHROMA_RGB[chroma]
    object_colors = {
        "green": ((235, 55, 45), (45, 95, 235), (245, 185, 25)),
        "blue": ((235, 55, 45), (35, 190, 70), (245, 185, 25)),
        "magenta": ((30, 185, 75), (30, 160, 220), (245, 185, 25)),
    }[chroma]
    frame_count = round(source_fps * duration_seconds)
    cell = size / 3
    try:
        for frame_index in range(frame_count):
            phase = 2 * math.pi * frame_index / frame_count
            image = Image.new("RGB", (size, size), key)
            draw = ImageDraw.Draw(image)
            for index in range(9):
                row, column = divmod(index, 3)
                cx = round((column + 0.5) * cell + 5 * math.sin(phase + index * 0.13))
                cy = round((row + 0.5) * cell + 3 * math.cos(phase + index * 0.17))
                color = object_colors[index % len(object_colors)]
                draw.ellipse((cx - 10, cy - 11, cx + 10, cy + 11), fill=color)
                draw.rectangle((cx + 2, cy - 5, cx + 7, cy), fill=(20, 20, 20))
            image.save(frame_dir / f"frame-{frame_index:04d}.png")
        codec_args = ["-c:v", "mpeg4", "-q:v", "12", "-pix_fmt", "yuv420p"] if compressed else ["-c:v", "ffv1", "-pix_fmt", "rgb24"]
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-framerate",
            str(source_fps),
            "-i",
            str(frame_dir / "frame-%04d.png"),
            *codec_args,
            str(destination),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
    finally:
        shutil.rmtree(frame_dir, ignore_errors=True)
    return destination


def make_vfr_chroma_video(destination: Path, *, chroma: str = "blue", size: int = 180) -> Path:
    """Create an approximately one-second VFR grid with alternating frame durations."""

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for the media fixture")
    destination.parent.mkdir(parents=True, exist_ok=True)
    frame_dir = destination.parent / f".{destination.stem}-vfr-frames"
    frame_dir.mkdir()
    key = CHROMA_RGB[chroma]
    durations = (0.04, 0.16) * 5
    frame_paths: list[Path] = []
    try:
        for frame_index, _ in enumerate(durations):
            phase = 2 * math.pi * frame_index / len(durations)
            image = Image.new("RGB", (size, size), key)
            draw = ImageDraw.Draw(image)
            for index in range(9):
                row, column = divmod(index, 3)
                cx = round(column * 60 + 30 + 5 * math.sin(phase + index * 0.13))
                cy = round(row * 60 + 30 + 3 * math.cos(phase + index * 0.17))
                draw.ellipse((cx - 10, cy - 11, cx + 10, cy + 11), fill=(235, 70, 40))
                draw.rectangle((cx + 2, cy - 5, cx + 7, cy), fill=(20, 20, 20))
            frame_path = frame_dir / f"frame-{frame_index:03d}.png"
            image.save(frame_path)
            frame_paths.append(frame_path)
        concat_file = frame_dir / "timeline.txt"
        lines: list[str] = []
        for frame_path, duration in zip(frame_paths, durations):
            lines.extend((f"file '{frame_path.as_posix()}'", f"duration {duration:.3f}"))
        lines.append(f"file '{frame_paths[-1].as_posix()}'")
        concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-fps_mode",
            "vfr",
            "-c:v",
            "ffv1",
            "-pix_fmt",
            "rgb24",
            str(destination),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
    finally:
        shutil.rmtree(frame_dir, ignore_errors=True)
    return destination


def make_single_frame_video(destination: Path, *, chroma: str = "green", size: int = 180) -> Path:
    """Create a real video stream containing exactly one grid frame."""

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for the media fixture")
    destination.parent.mkdir(parents=True, exist_ok=True)
    still = destination.with_suffix(".single.png")
    image = Image.new("RGB", (size, size), CHROMA_RGB[chroma])
    draw = ImageDraw.Draw(image)
    for row in range(3):
        for column in range(3):
            cx, cy = column * 60 + 30, row * 60 + 30
            draw.ellipse((cx - 10, cy - 11, cx + 10, cy + 11), fill=(235, 70, 40))
    image.save(still)
    try:
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(still),
            "-frames:v",
            "1",
            "-c:v",
            "ffv1",
            "-pix_fmt",
            "rgb24",
            str(destination),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
    finally:
        still.unlink(missing_ok=True)
    return destination


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
