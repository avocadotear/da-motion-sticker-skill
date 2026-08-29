from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.process_video import choose_loop, detect_grid, soft_chroma_key


@pytest.mark.parametrize("key", [(0, 255, 0), (0, 0, 255), (255, 0, 255)])
def test_soft_key_accepts_compressed_color_drift(key: tuple[int, int, int]) -> None:
    array = np.empty((24, 24, 4), dtype=np.uint8)
    drifted = tuple(max(0, min(255, value + delta)) for value, delta in zip(key, (7, -8, 6)))
    array[:] = (*drifted, 255)
    array[8:16, 8:16] = (240, 180, 30, 255)
    output = soft_chroma_key(array, key)
    assert int(output[0, 0, 3]) == 0
    assert int(output[12, 12, 3]) > 245


def test_multiframe_grid_detection_finds_clear_gutters() -> None:
    key = (0, 0, 255)
    arrays = []
    for offset in (0, 2, -2):
        frame = np.zeros((180, 180, 4), dtype=np.uint8)
        frame[:] = (*key, 255)
        for row in range(3):
            for column in range(3):
                cx = column * 60 + 30 + offset
                cy = row * 60 + 30
                frame[cy - 11 : cy + 11, cx - 10 : cx + 10] = (235, 70, 50, 255)
        arrays.append(frame)
    detection = detect_grid(arrays, key)
    assert detection.confidence >= 0.70
    assert all(abs(actual - expected) <= 10 for actual, expected in zip(detection.x_cuts, (60, 120)))
    assert all(abs(actual - expected) <= 10 for actual, expected in zip(detection.y_cuts, (60, 120)))


def test_loop_selection_rejects_single_frame_and_pingpongs_short_motion() -> None:
    one = np.zeros((32, 32, 4), dtype=np.uint8)
    with pytest.raises(ValueError, match="only one"):
        choose_loop([one])
    frames = []
    for offset in (0, 4, 8, 4):
        frame = np.zeros((32, 32, 4), dtype=np.uint8)
        frame[10:20, 5 + offset : 15 + offset] = (230, 60, 40, 255)
        frames.append(frame)
    indices, report = choose_loop(frames, target_frames=12)
    assert len(indices) == 12
    assert report["method"] == "ping_pong"
    assert max(indices) < len(frames)

