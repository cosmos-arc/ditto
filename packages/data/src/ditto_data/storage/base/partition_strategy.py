"""Partition strategy for Parquet file organization."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PartitionStrategy(Protocol):
    """
    分区策略协议.

    定义如何将数据组织到不同的分区文件中，支持可配置的分区策略。
    使用 Protocol（结构化子类型），实现者无需显式继承。

    Examples:
        >>> strategy = YearlyPartition()
        >>> key = strategy.get_partition_key("2024-01-01")
        >>> assert key == "2024"
        >>> filename = strategy.get_filename(key)
        >>> assert filename == "2024.parquet"

    """

    def get_partition_key(self, date_str: str) -> str:
        """
        从日期字符串提取分区键.

        Args:
            date_str: 日期字符串 (YYYY-MM-DD).

        Returns:
            分区键.

        """
        ...

    def get_filename(self, partition_key: str) -> str:
        """
        生成分区文件名.

        Args:
            partition_key: 分区键.

        Returns:
            文件名.

        """
        ...

    def get_partitions_from_filters(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> list[str]:
        """
        根据日期范围获取需要读取的分区键列表.

        Args:
            start_date: 起始日期 (YYYY-MM-DD)（可选）.
            end_date: 结束日期 (YYYY-MM-DD)（可选）.

        Returns:
            分区键列表.

        """
        ...


class YearlyPartition:
    """
    按年分区策略.

    将数据按年份组织到不同的 Parquet 文件中：
    - 2020.parquet
    - 2021.parquet
    - 2022.parquet
    ...

    Examples:
        >>> strategy = YearlyPartition()
        >>> strategy.get_partition_key("2024-01-15")
        '2024'
        >>> strategy.get_filename("2024")
        '2024.parquet'
        >>> strategy.get_partitions_from_filters("2023-01-01", "2024-12-31")
        ['2023', '2024']

    """

    def get_partition_key(self, date_str: str) -> str:
        """
        从日期字符串提取年份.

        Args:
            date_str: 日期字符串 (YYYY-MM-DD).

        Returns:
            年份字符串.

        """
        return date_str[:4]

    def get_filename(self, partition_key: str) -> str:
        """
        生成分区文件名.

        Args:
            partition_key: 年份字符串.

        Returns:
            文件名 (YYYY.parquet).

        """
        return f"{partition_key}.parquet"

    def get_partitions_from_filters(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> list[str]:
        """
        根据日期范围获取需要读取的年份列表.

        Args:
            start_date: 起始日期 (YYYY-MM-DD)（可选）.
            end_date: 结束日期 (YYYY-MM-DD)（可选）.

        Returns:
            年份字符串列表. 空列表表示扫描所有文件.

        """
        # 无过滤条件，返回空（扫描所有文件）
        if not start_date and not end_date:
            return []

        start_year = int(start_date[:4]) if start_date else None
        end_year = int(end_date[:4]) if end_date else None

        # 同时提供 start_year 和 end_year：返回范围内的年份
        if start_year and end_year:
            return [str(y) for y in range(start_year, end_year + 1)]

        # 只提供 start_year 或 end_year：返回空列表，扫描所有文件
        # 依赖 Polars 谓词下推进行日期过滤，避免遗漏数据
        return []
