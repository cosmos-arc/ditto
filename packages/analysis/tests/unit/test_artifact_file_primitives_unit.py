"""Cross-platform import and no-follow checks for artifact primitives."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from ditto_analysis.research import _artifact_file_primitives as primitives


def test_modules_import_without_posix_only_open_flags() -> None:
    code = """import os
for flag in ("O_NOFOLLOW", "O_DIRECTORY", "O_ACCMODE"):
    if hasattr(os, flag):
        delattr(os, flag)
import ditto_analysis.research._artifact_file_primitives as primitives
import ditto_analysis.research._indexed_artifacts
assert primitives._HAS_ATOMIC_NOFOLLOW is False
assert primitives._windows_access(primitives.READ_FLAGS) != 0
assert (
    primitives._windows_fd_flags(primitives.READ_FLAGS)
    & primitives._WINDOWS_ACCESS_MODE
    == 0
)
"""
    result = subprocess.run(  # noqa: S603 - fixed interpreter and inline literal
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_missing_atomic_nofollow_fails_closed_for_existing_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"safe")
    link = tmp_path / "artifact.json"
    link.symlink_to(outside)
    monkeypatch.setattr(primitives, "_HAS_ATOMIC_NOFOLLOW", False)
    monkeypatch.setattr(primitives, "_IS_WINDOWS", False)

    with pytest.raises(OSError, match="atomic no-follow open unavailable"):
        primitives.open_file(link, os.O_RDONLY)

    assert outside.read_bytes() == b"safe"


def test_missing_atomic_nofollow_fails_closed_for_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "file.json"
    target.write_bytes(b"{}")
    monkeypatch.setattr(primitives, "_HAS_ATOMIC_NOFOLLOW", False)
    monkeypatch.setattr(primitives, "_IS_WINDOWS", False)

    with pytest.raises(OSError, match="atomic no-follow open unavailable"):
        primitives.open_directory(target)


def test_exclusive_create_mode_is_preserved_without_atomic_nofollow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "sidecar.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    monkeypatch.setattr(primitives, "_HAS_ATOMIC_NOFOLLOW", False)
    monkeypatch.setattr(primitives, "_IS_WINDOWS", False)

    descriptor = primitives.open_file(target, flags, 0o600)
    os.close(descriptor)

    if sys.platform != "win32":
        assert target.stat().st_mode & 0o777 == 0o600
    else:
        assert target.is_file()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native behavior")
def test_windows_no_follow_uses_real_reparse_point_entries(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    target.write_bytes(b"safe")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    parent_fd = primitives.open_directory(tmp_path, durable=True)
    try:
        descriptor = primitives.open_file(
            primitives.DirectoryEntryPath(parent_fd, target.name), primitives.READ_FLAGS
        )
        try:
            assert os.read(descriptor, 4) == b"safe"
        finally:
            os.close(descriptor)

        descriptor = primitives.open_file(
            primitives.DirectoryEntryPath(parent_fd, target.name),
            primitives.SYNC_FLAGS,
        )
        try:
            primitives.fsync_entry(descriptor)
        finally:
            os.close(descriptor)

        with pytest.raises(OSError, match="artifact path is a reparse point"):
            primitives.open_file(
                primitives.DirectoryEntryPath(parent_fd, link.name),
                primitives.READ_FLAGS,
            )

        child = tmp_path / "artifacts"
        child.mkdir()
        descriptor = primitives.open_directory(
            primitives.DirectoryEntryPath(parent_fd, child.name), durable=True
        )
        try:
            assert stat.S_ISDIR(os.fstat(descriptor).st_mode)
            primitives.fsync_entry(descriptor)
        finally:
            os.close(descriptor)
    finally:
        os.close(parent_fd)
