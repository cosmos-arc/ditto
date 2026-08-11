"""Closed-file and no-clobber primitives for indexed artifacts."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from ditto_analysis.research.artifact_measurement import (
    ArtifactMeasurement as _ArtifactMeasurement,
)
from ditto_analysis.research.artifact_measurement import (
    measure_json_bytes as _measure_json_bytes,
)
from ditto_analysis.research.artifact_measurement import (
    measure_parquet_bytes as _measure_parquet_bytes,
)

_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW


@dataclass(frozen=True)
class DirectoryEntryPath:
    """Path-like test surface backed by a stable open directory descriptor."""

    parent_fd: int
    name: str

    @property
    def parent(self) -> int:
        """Expose stable parent identity for publication-order assertions."""
        return self.parent_fd

    @property
    def suffix(self) -> str:
        """Return the leaf suffix without resolving through a process filesystem."""
        return Path(self.name).suffix

    def exists(self) -> bool:
        """Check the anchored directory entry without following symlinks."""
        try:
            os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return True


type ArtifactFilePath = Path | DirectoryEntryPath


def _open_file(path: ArtifactFilePath, flags: int) -> int:
    if isinstance(path, DirectoryEntryPath):
        return os.open(path.name, flags, dir_fd=path.parent_fd)
    return os.open(path, flags)


def write_json_file(path: ArtifactFilePath, payload: bytes) -> None:
    """Write canonical JSON bytes to an already-created safe path."""
    descriptor = _open_file(path, os.O_WRONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()


def write_parquet_file(path: ArtifactFilePath, frame: pl.DataFrame) -> None:
    """Write one frame to an already-created safe path."""
    descriptor = _open_file(path, os.O_WRONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "wb") as stream:
        frame.write_parquet(stream)
        stream.flush()


def _read_path_bytes(path: ArtifactFilePath) -> bytes:
    descriptor = _open_file(path, _READ_FLAGS)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("artifact is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(descriptor)


def measure_json_artifact(path: ArtifactFilePath) -> _ArtifactMeasurement:
    """Measure one closed staged JSON file."""
    return _measure_json_bytes(_read_path_bytes(path))


def measure_parquet_artifact(path: ArtifactFilePath) -> _ArtifactMeasurement:
    """Measure one closed staged Parquet file."""
    return _measure_parquet_bytes(_read_path_bytes(path))


def publish_no_clobber(
    temporary: ArtifactFilePath,
    target: ArtifactFilePath,
) -> bool:
    """Atomically expose one inode without replacing an existing target."""
    try:
        if isinstance(temporary, DirectoryEntryPath):
            if isinstance(target, DirectoryEntryPath):
                os.link(
                    temporary.name,
                    target.name,
                    src_dir_fd=temporary.parent_fd,
                    dst_dir_fd=target.parent_fd,
                    follow_symlinks=False,
                )
            else:
                os.link(
                    temporary.name,
                    target,
                    src_dir_fd=temporary.parent_fd,
                    follow_symlinks=False,
                )
        elif isinstance(target, DirectoryEntryPath):
            os.link(
                temporary,
                target.name,
                dst_dir_fd=target.parent_fd,
                follow_symlinks=False,
            )
        else:
            os.link(temporary, target, follow_symlinks=False)
    except FileExistsError:
        return False
    return True
