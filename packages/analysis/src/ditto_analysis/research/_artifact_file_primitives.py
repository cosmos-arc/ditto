"""Closed-file and no-clobber primitives for indexed artifacts."""

from __future__ import annotations

import os
import stat
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


def write_json_file(path: Path, payload: bytes) -> None:
    """Write canonical JSON bytes to an already-created safe path."""
    descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()


def write_parquet_file(path: Path, frame: pl.DataFrame) -> None:
    """Write one frame to an already-created safe path."""
    descriptor = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "wb") as stream:
        frame.write_parquet(stream)
        stream.flush()


def _read_path_bytes(path: Path) -> bytes:
    descriptor = os.open(path, _READ_FLAGS)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("artifact is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(descriptor)


def measure_json_artifact(path: Path) -> _ArtifactMeasurement:
    """Measure one closed staged JSON file."""
    return _measure_json_bytes(_read_path_bytes(path))


def measure_parquet_artifact(path: Path) -> _ArtifactMeasurement:
    """Measure one closed staged Parquet file."""
    return _measure_parquet_bytes(_read_path_bytes(path))


def publish_no_clobber(temporary: Path, target: Path) -> bool:
    """Atomically expose one inode without replacing an existing target."""
    try:
        os.link(temporary, target, follow_symlinks=False)
    except FileExistsError:
        return False
    return True
