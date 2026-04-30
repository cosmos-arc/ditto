"""
文件校验和工具。

提供通用的文件校验和能力，包括文件校验和计算等。
这些工具不依赖任何领域特定逻辑，可用于任何文件的完整性验证。
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def compute_checksum(file_path: Path) -> str:
    """
    计算文件的 SHA-256 checksum。

    该函数提供通用的文件完整性验证能力，使用 SHA-256 算法
    计算文件的加密哈希值。适用于任何需要验证文件完整性的场景。

    Args:
        file_path: 文件路径（可以是绝对路径或相对路径）

    Returns:
        SHA-256 hex string（64 字符）

    Raises:
        FileNotFoundError: 文件不存在
        PermissionError: 文件读取权限不足

    Examples:
        >>> from pathlib import Path
        >>> from ditto_platform.foundation.checksum import compute_checksum
        >>> checksum = compute_checksum(Path("data.parquet"))
        >>> len(checksum)
        64

    Notes:
        - 使用分块读取（8KB 块），避免大文件内存问题
        - SHA-256 是加密哈希算法，适合文件完整性验证
        - 返回的 hex string 固定 64 字符（256 bit = 64 hex chars）

    """
    sha256 = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
