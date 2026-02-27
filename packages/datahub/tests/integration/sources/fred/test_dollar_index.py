"""FRED dollar index integration tests."""

import os

import polars as pl
import pytest
from ditto_datahub.sources.fred.adapters.macro import MacroFredAdapter


@pytest.mark.skipif(not os.environ.get("FRED_API_KEY"), reason="FRED_API_KEY not set")
class TestFredDollarIndexIngestion:
    """FRED 美元指数数据摄取集成测试."""

    def test_fetch_dollar_index_broad(self) -> None:
        """测试获取贸易加权美元指数(广义)."""
        adapter = MacroFredAdapter()

        try:
            df = adapter.fetch_indicators(
                codes=["US_DOLLAR_INDEX_BROAD"],
                start_date="2024-01-01",
                end_date="2024-01-31",
            )

            # 验证返回数据结构
            assert df.height > 0, "应该返回至少一条记录"
            assert "indicator_code" in df.columns
            assert "date" in df.columns
            assert "value" in df.columns

            # 验证指标代码正确
            dollar_df = df.filter(pl.col("indicator_code") == "US_DOLLAR_INDEX_BROAD")
            assert dollar_df.height > 0, "应该包含 US_DOLLAR_INDEX_BROAD 数据"

            # 验证数值范围合理（美元指数通常在 90-130 之间）
            values = dollar_df["value"].drop_nulls()
            assert values.min() > 80, "美元指数应该大于 80"
            assert values.max() < 150, "美元指数应该小于 150"

        finally:
            adapter.close()

    def test_fetch_dollar_index_schema(self) -> None:
        """测试美元指数返回的 schema 符合 MACRO_INDICATOR_SOURCE_SCHEMA."""
        adapter = MacroFredAdapter()

        try:
            df = adapter.fetch_indicators(
                codes=["US_DOLLAR_INDEX_BROAD"],
                start_date="2024-01-01",
                end_date="2024-01-05",
            )

            # 验证必要的列存在
            required_columns = [
                "indicator_code",
                "indicator_name",
                "category",
                "frequency",
                "need_pit",
                "date",
                "value",
                "knowledge_date",
                "source",
                "unit",
                "description",
            ]
            for col in required_columns:
                assert col in df.columns, f"缺少列: {col}"

            # 验证 metadata 正确
            row = df.row(0, named=True)
            assert row["indicator_code"] == "US_DOLLAR_INDEX_BROAD"
            assert row["category"] == "dollar_index"
            assert row["frequency"] == "daily"
            assert row["need_pit"] is False
            assert row["source"] == "fred"
            assert row["unit"] == "指数"

        finally:
            adapter.close()
