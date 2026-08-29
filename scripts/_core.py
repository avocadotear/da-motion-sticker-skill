#!/usr/bin/env python3
"""Shared, dependency-light helpers for da-motion-sticker scripts.

The helpers in this module deliberately keep job manifests portable: paths written
to ``job.json`` are relative to the job directory and every resolver rejects path
traversal.  Managed-file writes either replace an explicitly owned file or publish
a complete temporary sibling with a hard link, so readers never observe partial
contents and no-overwrite publication remains race safe.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


JOB_SCHEMA_VERSION = "0.1"
SKILL_NAME = "da-motion-sticker"

STATE_TRANSITIONS = {
    "awaiting_sheet_generation": {"sheet_review_required", "sheet_validated"},
    "sheet_review_required": {"sheet_review_required", "sheet_validated"},
    "sheet_validated": {"chroma_review_required", "awaiting_route", "assets_prepared", "waiting_for_video"},
    "chroma_review_required": {"chroma_review_required", "awaiting_route", "assets_prepared", "waiting_for_video"},
    "awaiting_route": {"assets_prepared", "waiting_for_video"},
    "assets_prepared": {"local_animated"},
    "waiting_for_video": {"video_review_required", "video_processed", "video_failed"},
    "video_review_required": {"video_review_required", "video_processed", "video_failed"},
    "local_animated": {"packaged"},
    "video_processed": {"packaged"},
    "video_failed": set(),
    "packaged": set(),
}

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class JobError(RuntimeError):
    """Raised when a job manifest or managed path is invalid."""


def utc_now_iso() -> str:
    """Return an RFC 3339 UTC timestamp without platform-specific formatting."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: os.PathLike[str] | str, chunk_size: int = 1024 * 1024) -> str:
    """Return the lowercase SHA-256 digest of *path*."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    """Hash a JSON-compatible value using a deterministic UTF-8 encoding."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def slugify(value: str, fallback: str = "item", max_length: int = 48) -> str:
    """Create a portable, lowercase ASCII filename slug.

    Transliteration is intentionally conservative.  Text without an ASCII
    representation (for example, an all-Chinese label) receives the stable caller
    supplied fallback instead of a locale-dependent transliteration.
    """

    if max_length < 1:
        raise ValueError("max_length must be positive")
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-. ")
    slug = re.sub(r"-+", "-", slug)
    fallback_slug = re.sub(r"[^a-z0-9]+", "-", fallback.lower()).strip("-. ") or "item"
    slug = (slug or fallback_slug)[:max_length].rstrip("-. ") or fallback_slug[:max_length]
    if slug.upper() in _WINDOWS_RESERVED:
        slug = f"{slug}-file"
    return slug[:max_length].rstrip("-. ")


def numbered_slug(index: int, display_name: str) -> str:
    """Return a stable 1-based media basename such as ``01-happy``."""

    if index < 1 or index > 999:
        raise ValueError("index must be between 1 and 999")
    width = 2 if index < 100 else 3
    label = slugify(display_name, fallback="sticker", max_length=44)
    return f"{index:0{width}d}-{label}"


def _atomic_replace(path: Path, payload: bytes, *, overwrite: bool) -> Path:
    path = path.expanduser()
    if path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # A same-directory hard link provides an atomic CREATE_NEW publish:
            # existing files, symlinks, and dangling symlinks all fail.
            os.link(temporary, path)
            temporary.unlink()
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return path


def atomic_write_bytes(
    path: os.PathLike[str] | str, payload: bytes, *, overwrite: bool = False
) -> Path:
    """Atomically write bytes, refusing replacement unless explicitly allowed."""

    return _atomic_replace(Path(path), payload, overwrite=overwrite)


def _same_file_bytes(path: Path, payload: bytes, chunk_size: int = 1024 * 1024) -> bool:
    """Compare a regular, non-symlink file with *payload* without path races."""

    try:
        before = os.lstat(path)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(before.st_mode):
        raise FileExistsError(
            f"refusing to adopt a non-regular file or symlink: {path}"
        )
    if before.st_size != len(payload):
        return False

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FileExistsError(f"could not safely inspect existing file: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
            raise FileExistsError(f"existing file changed while being inspected: {path}")
        view = memoryview(payload)
        offset = 0
        while offset < len(payload):
            chunk = os.read(descriptor, min(chunk_size, len(payload) - offset))
            if not chunk or chunk != view[offset : offset + len(chunk)]:
                return False
            offset += len(chunk)
        if os.read(descriptor, 1):
            return False
    finally:
        os.close(descriptor)

    try:
        after = os.lstat(path)
    except FileNotFoundError as exc:
        raise FileExistsError(f"existing file disappeared while being inspected: {path}") from exc
    if not os.path.samestat(before, after):
        raise FileExistsError(f"existing file changed while being inspected: {path}")
    return True


def atomic_write_or_adopt_bytes(
    path: os.PathLike[str] | str, payload: bytes
) -> Path:
    """Create *path* atomically or adopt a byte-identical orphaned file.

    An existing destination is accepted only when it is a regular non-symlink file
    whose bytes exactly equal *payload*.  This is intended for deterministic retry
    after a process published an output but crashed before recording it in
    ``job.json``.  Existing mismatches and every special-file type fail closed.
    """

    destination = Path(path).expanduser()
    try:
        return atomic_write_bytes(destination, payload)
    except FileExistsError:
        if _same_file_bytes(destination, payload):
            return destination
        raise FileExistsError(
            f"refusing to overwrite non-identical existing file: {destination}"
        )


def _stable_regular_digest(path: Path) -> tuple[os.stat_result, str]:
    """Return identity and digest for a stable regular non-symlink staging file."""

    try:
        before = os.lstat(path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"staged file does not exist: {path}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"staged path must be a regular non-symlink file: {path}")

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"could not safely open staged file: {path}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
            raise RuntimeError(f"staged file changed before hashing: {path}")
        hasher = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            hasher.update(chunk)
        opened_after = os.fstat(descriptor)
        if (
            not os.path.samestat(opened, opened_after)
            or opened.st_size != opened_after.st_size
            or opened.st_mtime_ns != opened_after.st_mtime_ns
        ):
            raise RuntimeError(f"staged file changed while hashing: {path}")
    finally:
        os.close(descriptor)

    try:
        after = os.lstat(path)
    except FileNotFoundError as exc:
        raise RuntimeError(f"staged file disappeared while hashing: {path}") from exc
    if (
        not os.path.samestat(opened_after, after)
        or opened_after.st_size != after.st_size
        or opened_after.st_mtime_ns != after.st_mtime_ns
    ):
        raise RuntimeError(f"staged file changed while hashing: {path}")
    return after, hasher.hexdigest()


def _existing_digest_matches(path: Path, digest: str, size: int) -> bool:
    """Return whether an existing destination safely matches a staged digest."""

    try:
        identity, actual = _stable_regular_digest(path)
    except FileNotFoundError:
        return False
    except ValueError as exc:
        raise FileExistsError(
            f"refusing to adopt a non-regular file or symlink: {path}"
        ) from exc
    except RuntimeError as exc:
        raise FileExistsError(
            f"existing file changed while being inspected: {path}"
        ) from exc
    if identity.st_size != size:
        return False
    return actual == digest


def publish_files_atomically(
    pairs: Iterable[
        tuple[os.PathLike[str] | str, os.PathLike[str] | str]
    ],
) -> list[Path]:
    """Publish a staged file set with create-new semantics and rollback.

    Each pair is ``(staged_path, final_path)``.  All staged inputs are validated
    before publication begins.  A pre-existing regular non-symlink destination is
    adopted only when its SHA-256 and size match the staged file, supporting a
    deterministic retry after a crash.  New destinations are installed with
    ``os.link``; if any later publication fails, only links created by this call
    are removed and adopted files are left untouched.

    The operation is failure-atomic for its files (not a simultaneous filesystem
    snapshot): another process can briefly observe an early link before rollback.
    Staging and destination paths must therefore reside on filesystems that support
    hard links, as do the other no-overwrite writers in this module.
    """

    entries: list[tuple[Path, Path, os.stat_result, str]] = []
    destination_keys: set[str] = set()
    for staged_value, destination_value in pairs:
        staged = Path(staged_value).expanduser().absolute()
        destination = Path(destination_value).expanduser().absolute()
        destination_key = os.path.normcase(os.fspath(destination)).casefold()
        if destination_key in destination_keys:
            raise ValueError(f"duplicate transaction destination: {destination}")
        destination_keys.add(destination_key)
        staged_identity, digest = _stable_regular_digest(staged)
        entries.append((staged, destination, staged_identity, digest))

    # Preflight every known conflict before exposing even the first new output.
    for _staged, destination, staged_identity, digest in entries:
        if os.path.lexists(destination):
            if not _existing_digest_matches(destination, digest, staged_identity.st_size):
                raise FileExistsError(
                    f"refusing to overwrite non-identical existing file: {destination}"
                )

    created: list[tuple[Path, os.stat_result]] = []
    try:
        for staged, destination, staged_identity, digest in entries:
            if os.path.lexists(destination):
                # Re-check after preflight; another process may have replaced it.
                if not _existing_digest_matches(destination, digest, staged_identity.st_size):
                    raise FileExistsError(
                        f"existing destination changed before publication: {destination}"
                    )
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(staged, destination)
            except FileExistsError:
                # A concurrent publisher won the CREATE_NEW race.  It is safe to
                # adopt only if its complete result is exactly the expected one.
                if _existing_digest_matches(destination, digest, staged_identity.st_size):
                    continue
                raise FileExistsError(
                    f"concurrent publication created different content: {destination}"
                )
            linked_identity = os.lstat(destination)
            current_staged = os.lstat(staged)
            if (
                not stat.S_ISREG(linked_identity.st_mode)
                or not os.path.samestat(linked_identity, current_staged)
                or not os.path.samestat(staged_identity, current_staged)
            ):
                raise RuntimeError(f"staged file changed during publication: {staged}")
            created.append((destination, linked_identity))
    except BaseException:
        for destination, linked_identity in reversed(created):
            try:
                current = os.lstat(destination)
                if os.path.samestat(current, linked_identity):
                    destination.unlink()
            except FileNotFoundError:
                pass
        raise

    return [destination for _staged, destination, _identity, _digest in entries]


def atomic_write_text(
    path: os.PathLike[str] | str,
    text: str,
    *,
    overwrite: bool = False,
    encoding: str = "utf-8",
) -> Path:
    """Atomically write text, refusing replacement unless explicitly allowed."""

    return atomic_write_bytes(path, text.encode(encoding), overwrite=overwrite)


def atomic_write_json(
    path: os.PathLike[str] | str,
    value: Any,
    *,
    overwrite: bool = False,
) -> Path:
    """Atomically write human-readable UTF-8 JSON."""

    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    return atomic_write_text(path, text, overwrite=overwrite)


def atomic_copy(
    source: os.PathLike[str] | str,
    destination: os.PathLike[str] | str,
    *,
    overwrite: bool = False,
) -> Path:
    """Atomically copy a regular file without following a destination overwrite."""

    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(f"source file does not exist: {source_path}")
    destination_path = Path(destination)
    if destination_path.exists() and not overwrite:
        raise FileExistsError(f"refusing to overwrite existing file: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.", suffix=".tmp", dir=str(destination_path.parent)
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source_path, temporary)
        if overwrite:
            os.replace(temporary, destination_path)
        else:
            os.link(temporary, destination_path)
            temporary.unlink()
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return destination_path


def unique_job_dir(output_root: os.PathLike[str] | str, slug: str) -> Path:
    """Create and return a collision-resistant, process-specific job directory."""

    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    safe_slug = slugify(slug, fallback="sticker-pack", max_length=36)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(20):
        suffix = f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        candidate = root / f"{safe_slug}-{timestamp}-{suffix}"
        try:
            candidate.mkdir(mode=0o755)
            return candidate
        except FileExistsError:
            continue
    raise FileExistsError(f"could not allocate a unique job directory under {root}")


def _job_file(job_path: os.PathLike[str] | str) -> Path:
    path = Path(job_path).expanduser()
    if path.is_dir():
        path = path / "job.json"
    return path.resolve()


def resolve_job_path(
    job_path: os.PathLike[str] | str, relative: os.PathLike[str] | str
) -> Path:
    """Resolve a manifest path and reject absolute or escaping paths."""

    manifest = _job_file(job_path)
    raw = Path(relative)
    if raw.is_absolute():
        raise JobError(f"job path must be relative: {relative}")
    root = manifest.parent.resolve()
    # Managed artifacts never traverse user-controlled symlink components. This
    # is stricter than merely checking the resolved destination remains inside
    # the run: it also prevents a later link swap from redirecting a write.
    component = root
    for part in raw.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            raise JobError(f"job path escapes its run directory: {relative}")
        component = component / part
        if component.is_symlink():
            raise JobError(f"job path must not use a symlink: {relative}")
    candidate = (root / raw).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise JobError(f"job path escapes its run directory: {relative}") from exc
    return candidate


def relative_job_path(
    job_path: os.PathLike[str] | str, path: os.PathLike[str] | str
) -> str:
    """Return a POSIX relative path after confirming it belongs to the job."""

    manifest = _job_file(job_path)
    root = manifest.parent.resolve()
    candidate = Path(path).expanduser().resolve(strict=False)
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise JobError(f"path is outside the run directory: {candidate}") from exc
    return relative.as_posix()


def _assert_relative_manifest_paths(job_path: Path, job: dict[str, Any]) -> None:
    paths = job.get("paths", {})
    if not isinstance(paths, dict):
        raise JobError("job.paths must be an object")
    for key, value in paths.items():
        if value is None:
            continue
        if not isinstance(value, str):
            raise JobError(f"job.paths.{key} must be a string")
        resolve_job_path(job_path, value)

    def check_artifact(value: Any, label: str) -> None:
        if value is None:
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                check_artifact(item, f"{label}[{index}]")
            return
        if not isinstance(value, dict):
            raise JobError(f"{label} must be an object, array, or null")
        media_path = value.get("path")
        if media_path is not None:
            if not isinstance(media_path, str):
                raise JobError(f"{label}.path must be a string")
            resolve_job_path(job_path, media_path)

    artifacts = job.get("artifacts", {})
    if not isinstance(artifacts, dict):
        raise JobError("job.artifacts must be an object")
    for key, value in artifacts.items():
        check_artifact(value, f"job.artifacts.{key}")


def validate_input_bindings(
    job_path: os.PathLike[str] | str, job: dict[str, Any]
) -> None:
    """Verify immutable reference/video inputs against their recorded SHA-256.

    This intentionally runs on every resume through :func:`load_job`.  A job may
    therefore never silently continue with a replaced reference or with a video
    uploaded for a different unfinished run.
    """

    manifest = _job_file(job_path)

    def validate_record(record: Any, label: str) -> None:
        if not isinstance(record, dict):
            raise JobError(f"job.{label} must be an object")
        relative = record.get("path")
        expected = record.get("sha256")
        if not isinstance(relative, str):
            raise JobError(f"job.{label}.path must be a relative string")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise JobError(f"job.{label}.sha256 must be a lowercase SHA-256 digest")
        bound_path = resolve_job_path(manifest, relative)
        if not bound_path.is_file():
            raise JobError(f"bound {label} file is missing: {relative}")
        actual = sha256_file(bound_path)
        if actual != expected:
            raise JobError(
                f"bound {label} file hash changed: expected {expected}, received {actual}"
            )

    validate_record(job.get("reference"), "reference")
    if job.get("video_input") is not None:
        validate_record(job["video_input"], "video_input")
    history_records = job.get("video_history", [])
    if not isinstance(history_records, list):
        raise JobError("job.video_history must be an array")
    for index, record in enumerate(history_records):
        validate_record(record, f"video_history[{index}]")

    intake = job.get("intake")
    expected_input_hash = job.get("input_hash")
    if not isinstance(intake, dict):
        raise JobError("job.intake must preserve the immutable intake fields")
    if not isinstance(expected_input_hash, str) or not re.fullmatch(
        r"[0-9a-f]{64}", expected_input_hash
    ):
        raise JobError("job.input_hash must be a lowercase SHA-256 digest")
    actual_input_hash = canonical_sha256(intake)
    if actual_input_hash != expected_input_hash:
        raise JobError(
            "immutable intake hash changed: "
            f"expected {expected_input_hash}, received {actual_input_hash}"
        )

    contents = job.get("contents") or []
    current_labels = [
        item.get("display_name") if isinstance(item, dict) else None for item in contents
    ]
    immutable_checks = {
        "reference_sha256": (job.get("reference") or {}).get("sha256"),
        "contents": current_labels,
        "theme": job.get("theme"),
        "style_requested": (job.get("style") or {}).get("requested"),
        "style_resolved": (job.get("style") or {}).get("resolved"),
        "static_requested": (job.get("options") or {}).get("static"),
        "pet_requested": (job.get("options") or {}).get("pet"),
    }
    for key, current in immutable_checks.items():
        if intake.get(key) != current:
            raise JobError(f"immutable intake field no longer matches job state: {key}")
    requested_route = intake.get("route_requested")
    current_route = (job.get("options") or {}).get("route")
    if requested_route not in {"auto", "local", "video"}:
        raise JobError("job.intake.route_requested is invalid")
    if current_route not in {"auto", "local", "video"}:
        raise JobError("job.options.route is invalid")
    if requested_route != "auto" and current_route != requested_route:
        raise JobError("a preselected motion route cannot change during resume")


def validate_contents(job: dict[str, Any]) -> None:
    """Bind display labels to canonical safe slugs and fixed reading-order indices."""

    contents = job.get("contents")
    if not isinstance(contents, list) or len(contents) != 9:
        raise JobError("job.contents must contain exactly nine entries")
    for expected_index, item in enumerate(contents, 1):
        if not isinstance(item, dict):
            raise JobError(f"job.contents[{expected_index - 1}] must be an object")
        if item.get("index") != expected_index:
            raise JobError("job content indices must be the fixed sequence 1 through 9")
        display_name = item.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            raise JobError(f"job content {expected_index} needs a non-empty display_name")
        expected_slug = numbered_slug(expected_index, display_name)
        if item.get("slug") != expected_slug:
            raise JobError(
                f"job content {expected_index} slug must remain canonical: {expected_slug}"
            )
        motion_hint = item.get("motion_hint")
        if motion_hint is not None and motion_hint not in {
            "bob", "bounce", "shake", "nod", "sway", "pulse", "tilt", "hop"
        }:
            raise JobError(f"job content {expected_index} has an invalid motion_hint")


def verify_artifact_record(
    job_path: os.PathLike[str] | str,
    record: Any,
    label: str,
    *,
    expected_index: int | None = None,
) -> Path:
    """Verify a job-owned regular artifact and its mandatory SHA-256 binding."""

    if not isinstance(record, dict):
        raise JobError(f"{label} artifact must be an object")
    if expected_index is not None and record.get("index") != expected_index:
        raise JobError(f"{label} artifact index must be {expected_index}")
    relative = record.get("path")
    digest = record.get("sha256")
    if not isinstance(relative, str):
        raise JobError(f"{label} artifact path must be a relative string")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise JobError(f"{label} artifact needs a lowercase SHA-256 digest")
    path = resolve_job_path(job_path, relative)
    if path.is_symlink() or not path.is_file():
        raise JobError(f"{label} artifact is missing or is a symlink: {relative}")
    actual = sha256_file(path)
    if actual != digest:
        raise JobError(f"{label} artifact hash changed: {relative}")
    return path


def load_job(job_path: os.PathLike[str] | str) -> dict[str, Any]:
    """Load and minimally validate a da-motion-sticker manifest."""

    path = _job_file(job_path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            job = json.load(handle)
    except json.JSONDecodeError as exc:
        raise JobError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(job, dict):
        raise JobError("job manifest root must be an object")
    if job.get("skill") != SKILL_NAME:
        raise JobError(f"not a {SKILL_NAME} job: {path}")
    if job.get("schema_version") != JOB_SCHEMA_VERSION:
        raise JobError(
            f"unsupported job schema: {job.get('schema_version')!r}; "
            f"expected {JOB_SCHEMA_VERSION!r}"
        )
    validate_contents(job)
    if job.get("status") not in STATE_TRANSITIONS:
        raise JobError(f"unknown job status: {job.get('status')!r}")
    _assert_relative_manifest_paths(path, job)
    validate_input_bindings(path, job)
    return job


def save_job_atomic(
    job_path: os.PathLike[str] | str, job: dict[str, Any]
) -> None:
    """Validate and atomically replace the managed ``job.json`` file."""

    path = _job_file(job_path)
    job["updated_at"] = utc_now_iso()
    validate_contents(job)
    if job.get("status") not in STATE_TRANSITIONS:
        raise JobError(f"unknown job status: {job.get('status')!r}")
    _assert_relative_manifest_paths(path, job)
    validate_input_bindings(path, job)

    lock_path = path.with_name(f".{path.name}.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise JobError(f"job is busy; lock exists: {lock_path.name}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as lock:
            lock.write(f"pid={os.getpid()} at={utc_now_iso()}\n")
            lock.flush()
            os.fsync(lock.fileno())
        expected_revision = int(job.get("revision", 0))
        if path.exists():
            try:
                disk = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise JobError(f"cannot verify current job revision: {path}") from exc
            disk_revision = int(disk.get("revision", 0))
            if disk_revision != expected_revision:
                raise JobError(
                    f"job revision changed concurrently: expected {expected_revision}, received {disk_revision}"
                )
        elif expected_revision != 0:
            raise JobError("job manifest disappeared during an update")
        job["revision"] = expected_revision + 1
        atomic_write_json(path, job, overwrite=path.exists())
    finally:
        lock_path.unlink(missing_ok=True)


def update_status(
    job_path: os.PathLike[str] | str,
    job: dict[str, Any],
    status: str,
    *,
    qa: dict[str, Any] | None = None,
    error: str | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a status transition, optional QA fields, and optional error."""

    current = job.get("status")
    if current not in STATE_TRANSITIONS:
        raise JobError(f"unknown current status: {current!r}")
    if status not in STATE_TRANSITIONS[current]:
        raise JobError(f"invalid status transition: {current} -> {status}")
    timestamp = utc_now_iso()
    job["status"] = status
    history = job.setdefault("history", [])
    history.append({"status": status, "at": timestamp})
    if qa:
        qa_root = job.setdefault("qa", {})
        for key, value in qa.items():
            qa_root[key] = value
    if error is not None:
        entry = dict(error) if isinstance(error, dict) else {"message": str(error)}
        entry.setdefault("at", timestamp)
        entry.setdefault("status", status)
        job.setdefault("errors", []).append(entry)
    save_job_atomic(job_path, job)
    return job


def find_ffmpeg(program: str = "ffmpeg") -> str:
    """Locate ffmpeg/ffprobe and return an executable path."""

    if program not in {"ffmpeg", "ffprobe"}:
        raise ValueError("program must be 'ffmpeg' or 'ffprobe'")
    executable = shutil.which(program)
    if not executable:
        raise FileNotFoundError(
            f"{program} was not found on PATH; install FFmpeg and retry"
        )
    return executable


def ensure_regular_files(paths: Iterable[os.PathLike[str] | str]) -> None:
    """Raise ``FileNotFoundError`` for the first missing regular file."""

    for path in paths:
        if not Path(path).is_file():
            raise FileNotFoundError(str(path))
