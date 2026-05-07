"""
BacktestArtifactReader — 回测产物文件读取服务，封装 parquet/json 文件 I/O.

将文件系统访问从 App 层下沉到 Data 层，遵循分层架构约束。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import orjson
import polars as pl

__all__ = ["BacktestArtifactReader", "BacktestArtifactReaderProtocol"]


@runtime_checkable
class BacktestArtifactReaderProtocol(Protocol):
    """回测产物文件读取协议."""

    def read_json(self, file_path: str) -> dict[str, Any] | None:
        """读取 JSON 文件，不存在返回 None."""
        ...

    def read_parquet(self, file_path: str) -> pl.DataFrame | None:
        """读取 Parquet 文件，不存在返回 None."""
        ...

    def exists(self, file_path: str) -> bool:
        """检查文件是否存在."""
        ...


class BacktestArtifactReader:
    """回测产物文件读取服务 — 封装 JSON/Parquet 文件 I/O."""

    def read_json(self, file_path: str) -> dict[str, Any] | None:
        """
        读取 JSON 文件，文件不存在时返回 None.

        Args:
            file_path: JSON 文件的绝对或相对路径.

        Returns:
            解析后的字典，文件不存在时返回 None.

        """
        path = Path(file_path)
        if not path.exists():
            return None
        return orjson.loads(path.read_bytes())

    def read_parquet(self, file_path: str) -> pl.DataFrame | None:
        """
        读取 Parquet 文件，文件不存在时返回 None.

        Args:
            file_path: Parquet 文件的绝对或相对路径.

        Returns:
            读取到的 DataFrame，文件不存在时返回 None.

        """
        path = Path(file_path)
        if not path.exists():
            return None
        return pl.read_parquet(path)

    def exists(self, file_path: str) -> bool:
        """
        检查文件是否存在.

        Args:
            file_path: 文件路径.

        Returns:
            文件存在返回 True.

        """
        return Path(file_path).exists()
