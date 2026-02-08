"""BaseStore abstract base class for data storage implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ditto_datahub.models.storage import WriteResultStore


class BaseStore(ABC):
    """
    数据存储抽象基类.

    定义所有存储实现必须遵循的接口，提供统一的数据访问模式。
    所有具体存储实现（ParquetStore、DuckDBStore 等）都必须继承此类。

    Attributes:
        data_root: 数据根目录路径.

    """

    def __init__(self, data_root: Path) -> None:
        """
        初始化 BaseStore.

        Args:
            data_root: 数据根目录路径.

        """
        self._data_root = Path(data_root)

    @property
    def data_root(self) -> Path:
        """获取数据根目录路径."""
        return self._data_root

    @abstractmethod
    def read(
        self,
        dataset: str,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> object:
        """
        读取数据.

        Args:
            dataset: 数据集名称.
            instrument_ids: 证券 ID 列表（可选）.
            start_date: 起始日期 (YYYY-MM-DD)（可选）.
            end_date: 结束日期 (YYYY-MM-DD)（可选）.
            **kwargs: 其他实现特定的参数.

        Returns:
            数据对象（具体类型由实现决定）.

        """
        ...

    @abstractmethod
    def write(
        self,
        dataset: str,
        data: object,
        on_duplicate: str = "error",
        **kwargs: object,
    ) -> WriteResultStore:
        """
        写入数据.

        Args:
            dataset: 数据集名称.
            data: 要写入的数据对象.
            on_duplicate: 重复数据处理策略 ("error"|"keep_first"|"keep_last").
            **kwargs: 其他实现特定的参数.

        Returns:
            写入结果统计.

        """
        ...

    @abstractmethod
    def delete(
        self,
        dataset: str,
        instrument_ids: list[int] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        **kwargs: object,
    ) -> int:
        """
        删除数据.

        Args:
            dataset: 数据集名称.
            instrument_ids: 证券 ID 列表（可选）.
            start_date: 起始日期 (YYYY-MM-DD)（可选）.
            end_date: 结束日期 (YYYY-MM-DD)（可选）.
            **kwargs: 其他实现特定的参数.

        Returns:
            删除的记录数.

        """
        ...
