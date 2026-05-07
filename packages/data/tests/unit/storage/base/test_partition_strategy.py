"""Unit tests for PartitionStrategy."""

from __future__ import annotations

import pytest
from ditto_platform.foundation.storage import PartitionStrategy, YearlyPartition


class TestPartitionStrategy:
    """测试 PartitionStrategy 抽象基类."""

    def test_partition_strategy_is_abstract(self) -> None:
        """测试 PartitionStrategy 不能直接实例化."""
        with pytest.raises(TypeError):
            PartitionStrategy()  # type: ignore[arg-type]


class TestYearlyPartition:
    """测试 YearlyPartition 实现."""

    def test_get_partition_key(self) -> None:
        """测试从日期字符串提取年份."""
        strategy = YearlyPartition()

        assert strategy.get_partition_key("2024-01-01") == "2024"
        assert strategy.get_partition_key("2023-12-31") == "2023"
        assert strategy.get_partition_key("2020-06-15") == "2020"

    def test_get_filename(self) -> None:
        """测试生成分区文件名."""
        strategy = YearlyPartition()

        assert strategy.get_filename("2024") == "2024.parquet"
        assert strategy.get_filename("2023") == "2023.parquet"
        assert strategy.get_filename("2020") == "2020.parquet"

    def test_get_partitions_from_filters_no_filters(self) -> None:
        """测试无过滤条件时返回空列表."""
        strategy = YearlyPartition()

        result = strategy.get_partitions_from_filters(None, None)
        assert result == []

    def test_get_partitions_from_filters_start_only(self) -> None:
        """测试只有起始日期 - 返回空列表让 _collect_paths 扫描所有文件."""
        strategy = YearlyPartition()

        result = strategy.get_partitions_from_filters("2024-01-01", None)
        # 开放式范围返回空列表，依赖 Polars 谓词下推进行日期过滤
        assert result == []

    def test_get_partitions_from_filters_end_only(self) -> None:
        """测试只有结束日期 - 返回空列表让 _collect_paths 扫描所有文件."""
        strategy = YearlyPartition()

        result = strategy.get_partitions_from_filters(None, "2024-12-31")
        # 开放式范围返回空列表，依赖 Polars 谓词下推进行日期过滤
        assert result == []

    def test_get_partitions_from_filters_range_same_year(self) -> None:
        """测试同一年份的范围."""
        strategy = YearlyPartition()

        result = strategy.get_partitions_from_filters("2024-01-01", "2024-12-31")
        assert result == ["2024"]

    def test_get_partitions_from_filters_range_multi_year(self) -> None:
        """测试跨年份的范围."""
        strategy = YearlyPartition()

        result = strategy.get_partitions_from_filters("2023-01-01", "2024-12-31")
        assert result == ["2023", "2024"]

        result = strategy.get_partitions_from_filters("2020-01-01", "2022-12-31")
        assert result == ["2020", "2021", "2022"]

    def test_get_partitions_from_filters_range_decade(self) -> None:
        """测试跨十年的范围."""
        strategy = YearlyPartition()

        result = strategy.get_partitions_from_filters("2020-01-01", "2029-12-31")
        assert result == [
            "2020",
            "2021",
            "2022",
            "2023",
            "2024",
            "2025",
            "2026",
            "2027",
            "2028",
            "2029",
        ]
