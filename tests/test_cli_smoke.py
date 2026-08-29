from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COMMANDS = (
    "create_job.py",
    "inspect_sheet.py",
    "prepare_assets.py",
    "animate_local.py",
    "process_video.py",
    "package_job.py",
)


@pytest.mark.parametrize("script", COMMANDS)
def test_script_help_works_from_a_path_with_spaces(tmp_path: Path, script: str) -> None:
    working = tmp_path / "中文 working directory"
    working.mkdir()
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), "--help"],
        cwd=working,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout.casefold()

