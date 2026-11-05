"""IO utility functions for file operations."""

import hashlib
import os
import uuid
from pathlib import Path
from typing import Literal

import orjson
import polars as pl

ParquetCompression = Literal["lz4", "uncompressed", "snappy", "gzip", "brotli", "zstd"]


def writer_unique_tmp(path: Path) -> Path:
    """
    写入者唯一的临时路径（#641）.

    旧实现所有写入者共用 ``<file>.tmp``——进程终止/重叠写入期，一方的
    半成品 tmp 可被另一方 rename 到目标路径（#626 实证 parquet 撕裂）。
    pid+随机后缀保证互不相撞；被杀写入者的残留 tmp 因 rename 未发生而
    惰性无害（读取方从不碰 tmp），可安全手工清理——不做自动清扫，
    删除他人进行中的 tmp 会重新引入竞态。``.tmp`` 结尾不匹配 ``*.parquet``
    等读取 glob（#694）.
    """
    return path.with_suffix(f"{path.suffix}.{os.getpid()}-{uuid.uuid4().hex[:8]}.tmp")


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

    # Write to temporary file first (写入者唯一名，见 writer_unique_tmp)
    temp_path = writer_unique_tmp(path)
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

    # Write to temporary file first (写入者唯一名，见 writer_unique_tmp)
    temp_path = writer_unique_tmp(path)
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


def sha256_file(path: Path) -> str:
    """
    Stream-hash one file with SHA-256 without loading it into memory.

    Args:
        path: Path to the file.

    Returns:
        SHA-256 digest as a lowercase hex string.

    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: object) -> bytes:
    """
    Render compact sorted-key JSON bytes for identity hashes and manifests.

    语义规范化（NFC/Decimal/datetime）另属 ditto_agent._canonical；本函数是
    既有证据身份（备份清单回读、状态连续性哈希、签名验证）的权威字节形态，
    改为语义规范化会破坏历史比对，勿合并两者。

    Args:
        value: JSON-serializable object.

    Returns:
        Deterministic compact bytes with sorted keys.

    """
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
