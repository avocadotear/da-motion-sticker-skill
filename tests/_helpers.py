from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def run_script(name: str, arguments: Sequence[object], check: bool = True) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(SCRIPTS / name)] + [str(value) for value in arguments]
    return subprocess.run(command, capture_output=True, text=True, check=check)


def make_transparent_sheet(path: Path, size: int = 600) -> Path:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cell = size // 3
    colors: List[Tuple[int, int, int, int]] = [
        (240, 70, 60, 255),
        (244, 154, 45, 255),
        (245, 214, 66, 255),
        (52, 125, 210, 255),
        (90, 72, 190, 255),
        (235, 76, 172, 255),
        (65, 190, 180, 255),
        (88, 91, 105, 255),
        (170, 108, 58, 255),
    ]
    for index, color in enumerate(colors):
        row, col = divmod(index, 3)
        left = col * cell + round(cell * 0.22)
        top = row * cell + round(cell * 0.16)
        right = (col + 1) * cell - round(cell * 0.22)
        bottom = (row + 1) * cell - round(cell * 0.16)
        draw.ellipse((left, top, right, bottom), fill=color)
        draw.ellipse((left + 35, top + 45, left + 48, top + 58), fill=(20, 20, 20, 255))
        draw.ellipse((right - 48, top + 45, right - 35, top + 58), fill=(20, 20, 20, 255))
    image.save(path)
    return path


def make_video_frames(directory: Path, frame_count: int = 6, size: int = 300) -> List[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    cell = size // 3
    colors = [
        (230, 50, 45),
        (245, 150, 35),
        (245, 220, 55),
        (20, 100, 230),
        (100, 55, 190),
        (235, 60, 170),
        (20, 180, 190),
        (70, 70, 80),
        (170, 100, 50),
    ]
    for frame_index in range(frame_count):
        image = Image.new("RGB", (size, size), (0, 255, 0))
        draw = ImageDraw.Draw(image)
        shift = round(3 * __import__("math").sin(frame_index * 2 * __import__("math").pi / frame_count))
        for index, color in enumerate(colors):
            row, col = divmod(index, 3)
            center_x = col * cell + cell // 2 + shift
            center_y = row * cell + cell // 2 - shift
            radius = 25
            draw.ellipse(
                (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                fill=color,
            )
            draw.ellipse((center_x - 9, center_y - 6, center_x - 4, center_y - 1), fill=(15, 15, 15))
            draw.ellipse((center_x + 4, center_y - 6, center_x + 9, center_y - 1), fill=(15, 15, 15))
        path = directory / ("frame_%03d.png" % (frame_index + 1))
        image.save(path)
        paths.append(path)
    return paths


def make_keypose_sheets(source_cells: Path, output_dir: Path, size: int = 256) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cell = size // 2
    for sticker_index in range(1, 10):
        with Image.open(source_cells / ("%02d.png" % sticker_index)) as source:
            rgba = source.convert("RGBA")
            pixels = list(rgba.getdata())
            visible = [pixel for pixel in pixels if pixel[3] > 128]
            color = visible[len(visible) // 2][:3] if visible else (220, 70, 70)
        sheet = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(sheet)
        for pose_index in range(4):
            row, col = divmod(pose_index, 2)
            center_x = col * cell + cell // 2
            center_y = row * cell + cell // 2
            if pose_index == 0:
                draw.ellipse((center_x - 30, center_y - 42, center_x + 30, center_y + 42), fill=(*color, 255))
            elif pose_index == 1:
                draw.ellipse((center_x - 36, center_y - 30, center_x + 36, center_y + 36), fill=(*color, 255))
                draw.line((center_x - 30, center_y, center_x - 45, center_y + 15), fill=(*color, 255), width=10)
            elif pose_index == 2:
                draw.ellipse((center_x - 28, center_y - 44, center_x + 28, center_y + 38), fill=(*color, 255))
                draw.line((center_x - 20, center_y - 10, center_x - 42, center_y - 40), fill=(*color, 255), width=11)
                draw.line((center_x + 20, center_y - 10, center_x + 42, center_y - 40), fill=(*color, 255), width=11)
            else:
                draw.ellipse((center_x - 32, center_y - 38, center_x + 32, center_y + 40), fill=(*color, 255))
                draw.line((center_x + 24, center_y, center_x + 40, center_y - 12), fill=(*color, 255), width=9)
            draw.ellipse((center_x - 12, center_y - 12, center_x - 6, center_y - 6), fill=(15, 15, 15, 255))
            draw.ellipse((center_x + 6, center_y - 12, center_x + 12, center_y - 6), fill=(15, 15, 15, 255))
        sheet.save(output_dir / ("%02d.png" % sticker_index))
    return output_dir
