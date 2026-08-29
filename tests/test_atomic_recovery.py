from __future__ import annotations

import os
from pathlib import Path

import pytest

import scripts._core as core
from scripts._core import atomic_write_or_adopt_bytes, publish_files_atomically


def _stage(path: Path, payload: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_publish_files_atomically_publishes_complete_staged_set(tmp_path: Path) -> None:
    first = _stage(tmp_path / "stage" / "one.bin", b"one")
    second = _stage(tmp_path / "stage" / "two.bin", b"two")
    destinations = [tmp_path / "final" / "one.bin", tmp_path / "other" / "two.bin"]

    result = publish_files_atomically(zip((first, second), destinations))

    assert result == [path.absolute() for path in destinations]
    assert [path.read_bytes() for path in destinations] == [b"one", b"two"]
    assert first.read_bytes() == b"one"
    assert second.read_bytes() == b"two"


def test_publish_adopts_matching_orphan_and_adds_remaining_file(tmp_path: Path) -> None:
    first = _stage(tmp_path / "stage" / "one.bin", b"same")
    second = _stage(tmp_path / "stage" / "two.bin", b"new")
    orphan = _stage(tmp_path / "final" / "one.bin", b"same")
    new_destination = tmp_path / "final" / "two.bin"
    orphan_identity = orphan.stat()

    publish_files_atomically(((first, orphan), (second, new_destination)))

    assert os.path.samestat(orphan_identity, orphan.stat())
    assert orphan.read_bytes() == b"same"
    assert new_destination.read_bytes() == b"new"


def test_publish_preflights_mismatch_before_creating_any_output(tmp_path: Path) -> None:
    first = _stage(tmp_path / "stage" / "one.bin", b"one")
    second = _stage(tmp_path / "stage" / "two.bin", b"expected")
    first_destination = tmp_path / "final" / "one.bin"
    conflict = _stage(tmp_path / "final" / "two.bin", b"different")

    with pytest.raises(FileExistsError, match="non-identical"):
        publish_files_atomically(
            ((first, first_destination), (second, conflict))
        )

    assert not first_destination.exists()
    assert conflict.read_bytes() == b"different"


def test_publish_rolls_back_only_links_created_by_this_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adopted_stage = _stage(tmp_path / "stage" / "adopted.bin", b"adopted")
    first = _stage(tmp_path / "stage" / "first.bin", b"first")
    second = _stage(tmp_path / "stage" / "second.bin", b"second")
    adopted = _stage(tmp_path / "final" / "adopted.bin", b"adopted")
    first_destination = tmp_path / "final" / "first.bin"
    second_destination = tmp_path / "final" / "second.bin"
    real_link = core.os.link
    link_calls = 0

    def fail_second_new_link(source: Path, destination: Path) -> None:
        nonlocal link_calls
        link_calls += 1
        if link_calls == 2:
            raise OSError("injected publication failure")
        real_link(source, destination)

    monkeypatch.setattr(core.os, "link", fail_second_new_link)

    with pytest.raises(OSError, match="injected"):
        publish_files_atomically(
            (
                (adopted_stage, adopted),
                (first, first_destination),
                (second, second_destination),
            )
        )

    assert adopted.read_bytes() == b"adopted"
    assert not first_destination.exists()
    assert not second_destination.exists()
    assert first.read_bytes() == b"first"


def test_publish_adopts_identical_concurrent_winner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged = _stage(tmp_path / "stage" / "item.bin", b"complete")
    destination = tmp_path / "final" / "item.bin"
    real_link = core.os.link

    def concurrent_link(source: Path, target: Path) -> None:
        real_link(source, target)
        raise FileExistsError("concurrent winner")

    monkeypatch.setattr(core.os, "link", concurrent_link)

    assert publish_files_atomically(((staged, destination),)) == [destination.absolute()]
    assert destination.read_bytes() == b"complete"


def test_publish_rolls_back_prior_link_but_preserves_concurrent_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _stage(tmp_path / "stage" / "first.bin", b"first")
    second = _stage(tmp_path / "stage" / "second.bin", b"second")
    first_destination = tmp_path / "final" / "first.bin"
    second_destination = tmp_path / "final" / "second.bin"
    real_link = core.os.link
    link_calls = 0

    def conflicting_link(source: Path, target: Path) -> None:
        nonlocal link_calls
        link_calls += 1
        if link_calls == 2:
            target.write_bytes(b"someone else's output")
            raise FileExistsError("concurrent mismatch")
        real_link(source, target)

    monkeypatch.setattr(core.os, "link", conflicting_link)

    with pytest.raises(FileExistsError, match="concurrent publication"):
        publish_files_atomically(
            ((first, first_destination), (second, second_destination))
        )

    assert not first_destination.exists()
    assert second_destination.read_bytes() == b"someone else's output"


def test_publish_rejects_duplicate_cross_platform_destination_names(tmp_path: Path) -> None:
    first = _stage(tmp_path / "stage" / "first.bin", b"first")
    second = _stage(tmp_path / "stage" / "second.bin", b"second")

    with pytest.raises(ValueError, match="duplicate transaction destination"):
        publish_files_atomically(
            ((first, tmp_path / "final" / "Result.bin"), (second, tmp_path / "final" / "result.bin"))
        )


def test_publish_rejects_symlink_source_and_destination(tmp_path: Path) -> None:
    staged = _stage(tmp_path / "stage" / "real.bin", b"data")
    staged_link = tmp_path / "stage" / "link.bin"
    destination_link = tmp_path / "final" / "link.bin"
    destination_link.parent.mkdir(parents=True)
    try:
        staged_link.symlink_to(staged)
        destination_link.symlink_to(tmp_path / "missing-target")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable for this test account")

    with pytest.raises(ValueError, match="non-symlink"):
        publish_files_atomically(((staged_link, tmp_path / "final" / "out.bin"),))
    with pytest.raises(FileExistsError, match="non-regular file or symlink"):
        publish_files_atomically(((staged, destination_link),))


def test_atomic_write_or_adopt_bytes_is_idempotent_only_for_exact_bytes(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "result" / "report.json"

    assert atomic_write_or_adopt_bytes(destination, b'{"ok":true}\n') == destination
    identity = destination.stat()
    assert atomic_write_or_adopt_bytes(destination, b'{"ok":true}\n') == destination
    assert os.path.samestat(identity, destination.stat())

    with pytest.raises(FileExistsError, match="non-identical"):
        atomic_write_or_adopt_bytes(destination, b'{"ok":false}\n')
    assert destination.read_bytes() == b'{"ok":true}\n'


def test_atomic_write_or_adopt_bytes_rejects_symlink_and_directory(tmp_path: Path) -> None:
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(FileExistsError, match="non-regular"):
        atomic_write_or_adopt_bytes(directory, b"content")

    link = tmp_path / "dangling-link"
    try:
        link.symlink_to(tmp_path / "does-not-exist")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable for this test account")
    with pytest.raises(FileExistsError, match="non-regular"):
        atomic_write_or_adopt_bytes(link, b"content")

