#!/usr/bin/env python3
"""Validate a completed job and atomically build its reproducible delivery ZIP."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

try:
    from ._core import (
        atomic_write_json,
        load_job,
        relative_job_path,
        resolve_job_path,
        sha256_file,
        slugify,
        update_status,
        verify_artifact_record,
    )
    from ._media_qa import inspect_gif, inspect_static_png
except ImportError:  # pragma: no cover - direct CLI execution
    from _core import (  # type: ignore
        atomic_write_json,
        load_job,
        relative_job_path,
        resolve_job_path,
        sha256_file,
        slugify,
        update_status,
        verify_artifact_record,
    )
    from _media_qa import inspect_gif, inspect_static_png  # type: ignore


ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
REDACTED_LOCAL_PATH = "[REDACTED_LOCAL_PATH]"

_SENSITIVE_KEY_NAMES = {
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "authorization",
    "credential",
    "credentials",
    "cookie",
    "password",
    "passwd",
    "private_key",
    "secret",
    "secrets",
}
_SECRET_VALUE_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\b(?:sk|rk|pk|ghp|github_pat|xox[baprs])[-_A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.IGNORECASE),
    re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/:]+:[^\s/@]+@"),
)
_LOCAL_PATH_PATTERNS = (
    # Drive-letter and UNC paths.  The trailing class deliberately excludes
    # JSON punctuation so surrounding prose remains readable after redaction.
    re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/]|\\\\)[^\s\"'<>]+"),
    re.compile(r"(?<![A-Za-z0-9_.:/])~[\\/][^\s\"'<>]+"),
    # A POSIX absolute path with at least two components.  The negative
    # lookbehind avoids treating the path part of https:// URLs as local data.
    re.compile(r"(?<![A-Za-z0-9_.:/])/(?:[^/\s\"'<>]+/)+[^/\s\"'<>]+"),
    re.compile(r"(?<![A-Za-z0-9_.:/])/(?:Users|home|root|tmp|private|var|opt|Volumes)\b"),
)


def _job_root(job_path: Path) -> Path:
    return (job_path / "job.json" if job_path.is_dir() else job_path).resolve().parent


def _assert_no_symlink_components(job_path: Path, relative: str, label: str) -> None:
    """Reject symlinks even when their resolved targets remain inside the run."""

    root = _job_root(job_path)
    raw = Path(relative)
    current = root
    for part in raw.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} must not use a symlink: {relative}")


def _artifact_path(job_path: Path, artifact: Any, label: str) -> Path:
    if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
        raise ValueError(f"missing {label} artifact")
    _assert_no_symlink_components(job_path, artifact["path"], label)
    return verify_artifact_record(job_path, artifact, label)


def _safe_archive_name(name: str) -> str:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 1:
        raise ValueError(f"unsafe archive filename: {name}")
    try:
        name.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError(f"archive filename is not ASCII-safe: {name}") from exc
    return name


def _verify_media_list(
    job_path: Path,
    artifacts: Any,
    label: str,
    contents: list[dict[str, Any]],
    *,
    extension: str,
    minimum: int,
    maximum: int,
) -> list[Path]:
    if not isinstance(artifacts, list) or not (minimum <= len(artifacts) <= maximum):
        raise ValueError(f"{label} artifact count must be between {minimum} and {maximum}")
    indices: set[int] = set()
    resolved_paths: set[str] = set()
    archive_names: set[str] = set()
    paths: list[Path] = []
    seen_order: list[int] = []
    for entry in artifacts:
        if not isinstance(entry, dict) or not isinstance(entry.get("index"), int):
            raise ValueError(f"invalid {label} artifact entry")
        index = entry["index"]
        if index in indices or not 1 <= index <= 9:
            raise ValueError(f"duplicate or invalid {label} index: {index}")
        indices.add(index)
        seen_order.append(index)
        if not isinstance(entry.get("path"), str):
            raise ValueError(f"invalid {label} artifact path at index {index}")
        _assert_no_symlink_components(job_path, entry["path"], f"{label} {index}")
        path = verify_artifact_record(
            job_path,
            entry,
            f"{label} {index}",
            expected_index=index,
        )
        resolved_key = os.path.normcase(str(path.resolve()))
        if resolved_key in resolved_paths:
            raise ValueError(f"duplicate {label} artifact path: {entry['path']}")
        resolved_paths.add(resolved_key)
        expected_name = f"{contents[index - 1]['slug']}{extension}"
        if path.name != expected_name:
            raise ValueError(
                f"{label} index {index} must use canonical filename {expected_name}"
            )
        archive_name = _safe_archive_name(path.name)
        archive_key = archive_name.casefold()
        if archive_key in archive_names:
            raise ValueError(f"duplicate case-insensitive {label} filename: {archive_name}")
        archive_names.add(archive_key)
        entry["media"] = inspect_gif(path) if extension == ".gif" else inspect_static_png(path)
        paths.append(path)
    if seen_order != sorted(seen_order):
        raise ValueError(f"{label} artifacts must remain in ascending index order")
    return paths


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    return (
        normalized in _SENSITIVE_KEY_NAMES
        or normalized.endswith("_secret")
        or normalized.endswith("_password")
        or normalized.endswith("_token")
        or normalized.endswith("_private_key")
    )


def _sanitize_string(value: str, label: str) -> str:
    for pattern in _SECRET_VALUE_PATTERNS:
        if pattern.search(value):
            raise ValueError(f"{label} contains a secret-like value")
    sanitized = value
    for pattern in _LOCAL_PATH_PATTERNS:
        sanitized = pattern.sub(REDACTED_LOCAL_PATH, sanitized)
    return sanitized


def _sanitize_delivery_value(value: Any, label: str) -> Any:
    """Return a portable delivery copy while rejecting likely credentials."""

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key)
            if _sensitive_key(key_text):
                raise ValueError(f"{label} contains forbidden secret-like field: {key_text}")
            sanitized[key_text] = _sanitize_delivery_value(child, f"{label}.{key_text}")
        return sanitized
    if isinstance(value, list):
        return [
            _sanitize_delivery_value(child, f"{label}[{index}]")
            for index, child in enumerate(value)
        ]
    if isinstance(value, str):
        return _sanitize_string(value, label)
    return value


def _manifest(job: dict[str, Any]) -> dict[str, Any]:
    manifest = copy.deepcopy(job)
    # The reproducible ZIP describes inputs and products, not the later ZIP hash itself.
    manifest.get("artifacts", {}).pop("package", None)
    return _sanitize_delivery_value(manifest, "manifest")


def _default_report(job: dict[str, Any], gif_count: int) -> dict[str, Any]:
    return {
        "version": 1,
        "route": (job.get("options") or {}).get("route"),
        "summary": {"succeeded": gif_count, "failed": 9 - gif_count, "partial_delivery": gif_count < 9},
        "qa": job.get("qa") or {},
        "errors": job.get("errors") or [],
    }


def _load_delivery_report(report_path: Path, job: dict[str, Any], gif_count: int) -> dict[str, Any]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"processing report is not valid UTF-8 JSON: {report_path.name}") from exc
    if not isinstance(report, dict):
        raise ValueError("processing report root must be an object")
    # Counts in the delivery report are derived from verified artifacts, never
    # trusted from a stale or manually edited report.
    report["summary"] = {
        "succeeded": gif_count,
        "failed": 9 - gif_count,
        "partial_delivery": gif_count < 9,
    }
    return _sanitize_delivery_value(report, "processing-report")


def _write_reproducible_zip(source_root: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"refusing to overwrite package: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        source_files = sorted(
            (path for path in source_root.rglob("*") if path.is_file()),
            key=lambda item: item.relative_to(source_root).as_posix(),
        )
        expected_names = [path.relative_to(source_root).as_posix() for path in source_files]
        if not expected_names:
            raise ValueError("refusing to create an empty delivery ZIP")
        if len(expected_names) != len(set(name.casefold() for name in expected_names)):
            raise ValueError("delivery ZIP contains duplicate case-insensitive member names")
        # GIF/PNG are already compressed. ZIP_STORED also avoids zlib-version
        # differences, making the archive bytes reproducible across platforms.
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for path in source_files:
                arcname = path.relative_to(source_root).as_posix()
                pure = PurePosixPath(arcname)
                if pure.is_absolute() or ".." in pure.parts:
                    raise ValueError(f"unsafe delivery member: {arcname}")
                info = zipfile.ZipInfo(arcname, date_time=ZIP_TIMESTAMP)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_STORED)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        with zipfile.ZipFile(temporary, "r") as archive:
            actual_names = archive.namelist()
            if actual_names != expected_names or len(actual_names) != len(set(actual_names)):
                raise ValueError("delivery ZIP member validation failed")
            if any(info.create_system != 3 for info in archive.infolist()):
                raise ValueError("delivery ZIP has non-Unix member metadata")
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise ValueError(f"delivery ZIP CRC failed for {corrupt_member}")
            for info, source in zip(archive.infolist(), source_files):
                if info.file_size != source.stat().st_size:
                    raise ValueError(f"delivery ZIP size mismatch for {info.filename}")
        # CREATE_NEW semantics prevent both ordinary files and dangling symlinks
        # from being replaced in a race between validation and publication.
        os.link(temporary, destination)
        temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)


def package_job(job_path: Path) -> Path:
    job_path = (job_path / "job.json" if job_path.is_dir() else job_path).resolve()
    job = load_job(job_path)
    if job.get("status") not in {"local_animated", "video_processed"}:
        raise ValueError("packaging requires local_animated or video_processed state")
    artifacts = job.get("artifacts")
    contents = job.get("contents")
    if not isinstance(artifacts, dict) or not isinstance(contents, list):
        raise ValueError("job artifacts and contents must be objects")
    gif_paths = _verify_media_list(
        job_path,
        artifacts.get("gifs"),
        "GIF",
        contents,
        extension=".gif",
        minimum=1,
        maximum=9,
    )
    include_png = bool((job.get("options") or {}).get("static"))
    png_paths = (
        _verify_media_list(
            job_path,
            artifacts.get("pngs"),
            "PNG",
            contents,
            extension=".png",
            minimum=9,
            maximum=9,
        )
        if include_png
        else []
    )
    transparent = _artifact_path(job_path, artifacts.get("transparent_sheet"), "transparent sheet")
    chroma = _artifact_path(job_path, artifacts.get("chroma_sheet"), "chroma sheet")
    image_prompt = resolve_job_path(job_path, job["paths"]["image_prompt"])
    video_prompt = resolve_job_path(job_path, job["paths"]["video_prompt"])
    for prompt, relative in (
        (image_prompt, job["paths"]["image_prompt"]),
        (video_prompt, job["paths"]["video_prompt"]),
    ):
        _assert_no_symlink_components(job_path, relative, "prompt")
        if not prompt.is_file() or prompt.is_symlink():
            raise FileNotFoundError(f"prompt is missing: {prompt}")

    all_inputs = [*gif_paths, *png_paths, transparent, chroma, image_prompt, video_prompt]
    normalized_inputs = [os.path.normcase(str(path.resolve())) for path in all_inputs]
    if len(normalized_inputs) != len(set(normalized_inputs)):
        raise ValueError("delivery inputs must use unique job-owned paths")

    report_path = resolve_job_path(job_path, job["paths"]["processing_report"])
    _assert_no_symlink_components(job_path, job["paths"]["processing_report"], "processing report")
    if not report_path.exists():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(report_path, _default_report(job, len(gif_paths)), overwrite=False)
    if not report_path.is_file() or report_path.is_symlink():
        raise ValueError("processing report must be a regular file")
    delivery_report = _load_delivery_report(report_path, job, len(gif_paths))

    work_dir = resolve_job_path(job_path, "work")
    _assert_no_symlink_components(job_path, "work", "work directory")
    work_dir.mkdir(parents=True, exist_ok=True)
    pack = job.get("pack") or {}
    pack_slug = slugify(str(pack.get("slug") or pack.get("name") or job.get("job_id") or "motion-stickers"), fallback="motion-stickers")
    destination = resolve_job_path(job_path, f"delivery/{pack_slug}.zip")
    _assert_no_symlink_components(job_path, f"delivery/{pack_slug}.zip", "package destination")
    with tempfile.TemporaryDirectory(prefix="da-package-", dir=work_dir) as staging_name:
        staging = Path(staging_name)
        (staging / "gifs").mkdir(parents=True)
        for path in gif_paths:
            shutil.copyfile(path, staging / "gifs" / _safe_archive_name(path.name))
        if include_png:
            (staging / "png").mkdir()
            for path in png_paths:
                shutil.copyfile(path, staging / "png" / _safe_archive_name(path.name))
        (staging / "source").mkdir()
        shutil.copyfile(transparent, staging / "source" / "transparent-sheet.png")
        shutil.copyfile(chroma, staging / "source" / "chroma-sheet.png")
        (staging / "prompts").mkdir()
        shutil.copyfile(image_prompt, staging / "prompts" / "image-prompt.txt")
        shutil.copyfile(video_prompt, staging / "prompts" / "video-prompt.txt")
        (staging / "manifest.json").write_text(json.dumps(_manifest(job), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (staging / "processing-report.json").write_text(
            json.dumps(delivery_report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_reproducible_zip(staging, destination)

    package_artifact = {"path": relative_job_path(job_path, destination), "sha256": sha256_file(destination)}
    published_identity = destination.stat()
    job["artifacts"]["package"] = package_artifact
    try:
        update_status(
            job_path,
            job,
            "packaged",
            qa={
                "package": {
                    "ok": True,
                    "gif_count": len(gif_paths),
                    "png_count": len(png_paths),
                    "gif_contract": [entry["media"] for entry in artifacts["gifs"]],
                    "png_contract": [entry["media"] for entry in artifacts.get("pngs", [])]
                    if include_png
                    else [],
                }
            },
        )
    except Exception:
        # The link was created by this invocation and has not yet been recorded;
        # removing only that known file keeps the pre-package state retryable.
        try:
            current_identity = destination.stat()
            if os.path.samestat(published_identity, current_identity):
                destination.unlink()
        except FileNotFoundError:
            pass
        raise
    return destination


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True, type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        package = package_job(args.job.resolve())
    except Exception as exc:
        raise SystemExit(f"package_job: {exc}") from exc
    print(json.dumps({"status": "packaged", "package": str(package)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
