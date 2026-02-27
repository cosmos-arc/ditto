"""Tushare bond yield integration tests."""

import os

import polars as pl
import pytest
from ditto_datahub.sources.tushare.adapters.bond_yield import (
    CN_BOND_YIELD_INDICATORS,
    BondYieldTushareAdapter,
)


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("TUSHARE_TOKEN"), reason="TUSHARE_TOKEN not set")
class TestTushareBondYieldIngestion:
    """Tushare 中国国债收益率数据摄取集成测试."""

    def test_fetch_cn_bond_yield_10y(self) -> None:
        """测试获取中国10年期国债收益率."""
        adapter = BondYieldTushareAdapter()

        df = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_10Y"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # 验证返回数据结构
        assert df.height > 0, "应该返回至少一条记录"
        assert "indicator_code" in df.columns
        assert "date" in df.columns
        assert "value" in df.columns

        # 验证指标代码正确
        yield_10y_df = df.filter(pl.col("indicator_code") == "CN_BOND_YIELD_10Y")
        assert yield_10y_df.height > 0, "应该包含 CN_BOND_YIELD_10Y 数据"

        # 验证数值范围合理（10年期国债收益率通常在 1.5%-5% 之间）
        values = yield_10y_df["value"].drop_nulls()
        if values.len() > 0:
            assert values.min() > 1.0, "国债收益率应该大于 1%"
            assert values.max() < 6.0, "国债收益率应该小于 6%"

    def test_fetch_multiple_maturities(self) -> None:
        """测试获取多个期限的国债收益率."""
        adapter = BondYieldTushareAdapter()

        codes = ["CN_BOND_YIELD_1Y", "CN_BOND_YIELD_5Y", "CN_BOND_YIELD_10Y"]
        df = adapter.fetch_bond_yield(
            codes=codes,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # 验证所有请求的指标都有数据
        unique_codes = set(df["indicator_code"].unique().to_list())
        assert "CN_BOND_YIELD_1Y" in unique_codes
        assert "CN_BOND_YIELD_5Y" in unique_codes
        assert "CN_BOND_YIELD_10Y" in unique_codes

    def test_bond_yield_schema(self) -> None:
        """测试国债收益率返回的 schema 符合 MACRO_INDICATOR_SOURCE_SCHEMA."""
        adapter = BondYieldTushareAdapter()

        df = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_10Y"],
            start_date="2024-01-01",
            end_date="2024-01-05",
        )

        if df.height == 0:
            pytest.skip("No data returned for the specified period")

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
        assert row["indicator_code"] == "CN_BOND_YIELD_10Y"
        assert row["category"] == "interest_rate"
        assert row["frequency"] == "daily"
        assert row["need_pit"] is False
        assert row["source"] == "tushare"
        assert row["unit"] == "%"

    def test_knowledge_date_equals_date(self) -> None:
        """测试 knowledge_date 等于 date（T+0 发布）."""
        adapter = BondYieldTushareAdapter()

        df = adapter.fetch_bond_yield(
            codes=["CN_BOND_YIELD_10Y"],
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        if df.height == 0:
            pytest.skip("No data returned for the specified period")

        # 验证 knowledge_date = date
        for row in df.iter_rows(named=True):
            assert row["knowledge_date"] == row["date"], (
                f"knowledge_date {row['knowledge_date']} 应等于 date {row['date']}"
            )

    def test_all_defined_indicators_fetchable(self) -> None:
        """测试所有定义的指标都可以获取数据."""
        adapter = BondYieldTushareAdapter()

        # 获取所有定义的指标代码
        all_codes = list(CN_BOND_YIELD_INDICATORS.keys())

        df = adapter.fetch_bond_yield(
            codes=all_codes,
            start_date="2024-01-01",
            end_date="2024-01-31",
        )

        # 验证每个指标都有数据
        returned_codes = set(df["indicator_code"].unique().to_list())
        for code in all_codes:
            assert code in returned_codes, f"指标 {code} 应该有数据返回"
