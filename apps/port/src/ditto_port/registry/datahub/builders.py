"""
Provider 样板代码工厂函数。

此模块提供工厂函数来减少 Provider 中的重复代码，
同时保持显式的 provider 名称以便于 DI 追踪。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ditto_datahub.stores.sqlite_client import SQLiteClient

__all__ = [
    "parquet_store_pair",
    "sqlite_store_pair",
]


def sqlite_store_pair[R, W](
    reader_cls: Callable[[SQLiteClient], R],
    writer_cls: Callable[[SQLiteClient], W],
) -> tuple[Callable[[SQLiteClient], R], Callable[[SQLiteClient], W]]:
    """
    创建 SQLite reader/writer 工厂函数。

    Args:
        reader_cls: Reader 类（接受 SQLiteClient 作为第一个参数）
        writer_cls: Writer 类（接受 SQLiteClient 作为第一个参数）

    Returns:
        元组 (make_reader, make_writer)，每个都是工厂函数

    Example:
        >>> _balance_r, _balance_w = sqlite_store_pair(
        ...     BalanceSheetReader, BalanceSheetWriter
        ... )
        >>> reader = _balance_r(sqlite_client)
        >>> writer = _balance_w(sqlite_client)

    """
    # 注意：使用 reader_cls.__name__ 作为函数名便于调试
    # __name__ 属性在类对象上存在，但 Callable 类型不保证，需要运行时访问
    reader_name = f"make_{getattr(reader_cls, '__name__', 'reader')}"
    writer_name = f"make_{getattr(writer_cls, '__name__', 'writer')}"

    def make_reader(client: SQLiteClient) -> R:
        return reader_cls(client)

    def make_writer(client: SQLiteClient) -> W:
        return writer_cls(client)

    # 设置函数名便于调试
    make_reader.__name__ = reader_name
    make_writer.__name__ = writer_name

    return make_reader, make_writer


def parquet_store_pair[R, W](
    reader_cls: Callable[..., R],
    writer_cls: Callable[..., W],
    subdir: str | None = None,
) -> tuple[Callable[[Path], R], Callable[[Path], W]]:
    """
    创建 Parquet reader/writer 工厂函数。

    Args:
        reader_cls: Reader 类（接受 data_root: Path 作为关键字参数）
        writer_cls: Writer 类（接受 data_root: Path 作为关键字参数）
        subdir: 可选的子目录路径，会自动拼接到 data_root

    Returns:
        元组 (make_reader, make_writer)，每个都是工厂函数

    Example:
        >>> # 无子目录
        >>> _stock_bars_r, _stock_bars_w = parquet_store_pair(
        ...     StockBarsReader, StockBarsWriter
        ... )
        >>> reader = _stock_bars_r(data_root)
        >>>
        >>> # 有子目录
        >>> _nav_r, _nav_w = parquet_store_pair(
        ...     EtfNavReader, EtfNavWriter, subdir="market/etf/nav"
        ... )
        >>> reader = _nav_r(data_root)  # 路径自动变为 data_root / "market/etf/nav"

    """
    reader_name = f"make_{getattr(reader_cls, '__name__', 'reader')}"
    writer_name = f"make_{getattr(writer_cls, '__name__', 'writer')}"

    if subdir is not None:

        def make_reader(data_root: Path) -> R:
            return reader_cls(data_root=data_root / subdir)

        def make_writer(data_root: Path) -> W:
            return writer_cls(data_root=data_root / subdir)
    else:

        def make_reader(data_root: Path) -> R:
            return reader_cls(data_root=data_root)

        def make_writer(data_root: Path) -> W:
            return writer_cls(data_root=data_root)

    make_reader.__name__ = reader_name
    make_writer.__name__ = writer_name

    return make_reader, make_writer
