"""IO utility functions for file operations."""

import hashlib
import os
from pathlib import Path
from typing import Literal

import polars as pl

ParquetCompression = Literal["lz4", "uncompressed", "snappy", "gzip", "brotli", "zstd"]


def atomic_write(
    df: pl.DataFrame,
    path: Path,
    *,
    fsync: bool = True,
    compression: ParquetCompression = "zstd",
) -> None:
    """
    Write DataFrame to Parquet file atomically.

    Writes to a temporary file first, then renames to the target path.
    This ensures atomic operation - either the file is fully written or not at all.

    Args:
        df: DataFrame to write.
        path: Target file path.
        fsync: Whether to call fsync to ensure data is persisted to disk.
             Defaults to True for data durability.
        compression: Parquet compression codec. Defaults to ``"zstd"``.

    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file first
    temp_path = path.with_suffix(path.suffix + ".tmp")
    df.write_parquet(temp_path, compression=compression)

    # Call fsync if requested
    if fsync:
        with temp_path.open("r+b") as f:
            os.fsync(f.fileno())

    # Atomic rename
    temp_path.replace(path)


def atomic_bytes_write(
    data: bytes,
    path: Path,
    fsync: bool = True,
) -> None:
    """
    Write raw bytes to a file atomically.

    Writes to a temporary file first, then renames to the target path.
    This ensures atomic operation - either the file is fully written or not at all.

    Args:
        data: Raw bytes to write.
        path: Target file path.
        fsync: Whether to call fsync to ensure data is persisted to disk.
             Defaults to True for data durability.

    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file first
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_bytes(data)

    # Call fsync if requested
    if fsync:
        with temp_path.open("r+b") as f:
            os.fsync(f.fileno())

    # Atomic rename
    temp_path.replace(path)


def file_md5(path: Path) -> str:
    """
    Calculate MD5 checksum of a file.

    Args:
        path: Path to the file.

    Returns:
        MD5 checksum as a 32-character hex string.

    """
    path = Path(path)
    # MD5 用于文件校验，非安全场景，使用 usedforsecurity=False
    md5 = hashlib.md5(usedforsecurity=False)

    with path.open("rb") as f:
        # Read in chunks to handle large files efficiently
        for chunk in iter(lambda: f.read(8192), b""):
            md5.update(chunk)

    return md5.hexdigest()
