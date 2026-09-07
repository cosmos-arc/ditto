"""Cross-platform import and no-follow checks for artifact primitives."""

from __future__ import annotations

import importlib
import os
import stat
from pathlib import Path

import pytest
from ditto_analysis.research import _artifact_file_primitives as primitives


def test_modules_import_without_posix_only_open_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(os, "O_NOFOLLOW")
    monkeypatch.delattr(os, "O_DIRECTORY")

    indexed = importlib.import_module("ditto_analysis.research._indexed_artifacts")
    importlib.reload(primitives)
    importlib.reload(indexed)

    assert primitives._HAS_ATOMIC_NOFOLLOW is False

    monkeypatch.undo()
    importlib.reload(primitives)
    importlib.reload(indexed)


def test_fallback_open_rejects_final_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"safe")
    link = tmp_path / "artifact.json"
    link.symlink_to(outside)
    monkeypatch.setattr(primitives, "_HAS_ATOMIC_NOFOLLOW", False)

    with pytest.raises(OSError, match="artifact path changed while opening"):
        primitives.open_file(link, os.O_RDONLY)

    assert outside.read_bytes() == b"safe"


def test_fallback_directory_open_rejects_non_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "file.json"
    target.write_bytes(b"{}")
    monkeypatch.setattr(primitives, "_HAS_ATOMIC_NOFOLLOW", False)
    monkeypatch.setattr(
        primitives, "_DIRECTORY_FLAGS", os.O_RDONLY | getattr(os, "O_BINARY", 0)
    )

    with pytest.raises(OSError, match="artifact path is not a directory"):
        primitives.open_directory(target)

    descriptor = primitives.open_directory(tmp_path)
    try:
        assert stat.S_ISDIR(os.fstat(descriptor).st_mode)
    finally:
        os.close(descriptor)


def test_exclusive_create_mode_is_preserved_without_atomic_nofollow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "sidecar.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    monkeypatch.setattr(primitives, "_HAS_ATOMIC_NOFOLLOW", False)

    descriptor = primitives.open_file(target, flags, 0o600)
    os.close(descriptor)

    assert target.stat().st_mode & 0o777 == 0o600
