"""Failure-safety tests for immutable payload tree backup and restore."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from ditto_platform.foundation.storage import payload_backup
from ditto_platform.foundation.storage.payload_backup import (
    PayloadBackupError,
    PayloadTreeReport,
    backup_payload_tree,
    inspect_payload_tree,
)


def _source_tree(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload.json").write_text('{"value": 1}\n')
    return source


def test_inspection_rejects_file_and_root_directory_symlinks(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    outside_file = tmp_path / "outside.json"
    outside_file.write_text("outside")
    (source / "linked.json").symlink_to(outside_file)

    with pytest.raises(PayloadBackupError, match="cannot contain symbolic links"):
        inspect_payload_tree(source)

    source_link = tmp_path / "source-link"
    source_link.symlink_to(source, target_is_directory=True)
    with pytest.raises(
        PayloadBackupError,
        match="source payload directory cannot be a symbolic link",
    ):
        inspect_payload_tree(source_link)


def test_backup_rejects_existing_or_nested_destinations(tmp_path: Path) -> None:
    source = _source_tree(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()

    with pytest.raises(PayloadBackupError, match="destination already exists"):
        backup_payload_tree(source, existing)
    with pytest.raises(PayloadBackupError, match="outside the source tree"):
        backup_payload_tree(source, source / "nested-backup")


def test_backup_detects_verification_mismatch_and_removes_partial_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_tree(tmp_path)
    destination = tmp_path / "backup"
    monkeypatch.setattr(payload_backup, "_copy_payload_files", lambda *_args: None)

    with pytest.raises(PayloadBackupError, match="verification failed"):
        backup_payload_tree(source, destination)

    assert not destination.exists()


def test_backup_rechecks_for_a_symlink_inserted_after_source_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_tree(tmp_path)
    destination = tmp_path / "backup"
    outside = tmp_path / "outside"
    outside.mkdir()
    original_inspect = inspect_payload_tree

    def inspect_then_inject_symlink(directory: Path) -> PayloadTreeReport:
        report = original_inspect(directory)
        if directory.resolve() == source.resolve():
            (source / "late-link").symlink_to(outside, target_is_directory=True)
        return report

    monkeypatch.setattr(
        payload_backup,
        "inspect_payload_tree",
        inspect_then_inject_symlink,
    )

    with pytest.raises(PayloadBackupError, match="cannot contain symbolic links"):
        backup_payload_tree(source, destination)

    assert not destination.exists()


def test_backup_wraps_copy_os_error_and_removes_partial_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source_tree(tmp_path)
    destination = tmp_path / "backup"

    def fail_copy(*_args: object) -> None:
        raise OSError("simulated copy failure")

    monkeypatch.setattr(payload_backup, "_copy_payload_files", fail_copy)

    with pytest.raises(PayloadBackupError, match="payload tree copy failed"):
        backup_payload_tree(source, destination)

    assert not destination.exists()


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (PayloadBackupError("simulated guarded failure"), "guarded failure"),
        (OSError("simulated mkdir failure"), "payload tree copy failed"),
    ],
)
def test_backup_does_not_remove_destination_when_creation_never_succeeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    message: str,
) -> None:
    source = _source_tree(tmp_path)
    destination = tmp_path / "backup"
    original_mkdir: Callable[..., None] = Path.mkdir

    def fail_destination_mkdir(
        path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        if path == destination:
            raise failure
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)

    monkeypatch.setattr(Path, "mkdir", fail_destination_mkdir)

    with pytest.raises(PayloadBackupError, match=message):
        backup_payload_tree(source, destination)

    assert not destination.exists()
