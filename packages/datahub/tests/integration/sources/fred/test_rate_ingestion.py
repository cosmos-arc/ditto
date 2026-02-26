"""FRED rate data ingestion integration tests."""

import os

import polars as pl
import pytest
from ditto_datahub.sources.fred.adapters.macro import MacroFredAdapter


@pytest.mark.skipif(not os.environ.get("FRED_API_KEY"), reason="FRED_API_KEY not set")
class TestFredRateIngestion:
    """FRED 利率数据摄取集成测试."""

    def test_fetch_us_bond_yield_10y(self) -> None:
        """测试获取美国10年期国债收益率."""
        adapter = MacroFredAdapter()

        try:
            df = adapter.fetch_indicators(
                codes=["US_BOND_YIELD_10Y"],
                start_date="2024-01-01",
                end_date="2024-01-31",
            )

            # 验证返回数据结构
            assert df.height > 0, "应该返回至少一条记录"
            assert "indicator_code" in df.columns
            assert "date" in df.columns
            assert "value" in df.columns

            # 验证指标代码正确
            bond_10y_df = df.filter(pl.col("indicator_code") == "US_BOND_YIELD_10Y")
            assert bond_10y_df.height > 0, "应该包含 US_BOND_YIELD_10Y 数据"

        finally:
            adapter.close()

    def test_fetch_fed_funds_rate(self) -> None:
        """测试获取联邦基金利率."""
        adapter = MacroFredAdapter()

        try:
            df = adapter.fetch_indicators(
                codes=["US_FEDFUNDS_D"],
                start_date="2024-01-01",
                end_date="2024-01-31",
            )

            assert df.height > 0

        finally:
            adapter.close()

    def test_fetch_commodity_gold(self) -> None:
        """测试获取黄金价格."""
        adapter = MacroFredAdapter()

        try:
            df = adapter.fetch_indicators(
                codes=["COMMOD_GOLD"],
                start_date="2024-01-01",
                end_date="2024-01-31",
            )

            assert df.height > 0

        finally:
            adapter.close()

    def test_fetch_vix(self) -> None:
        """测试获取 VIX 指数."""
        adapter = MacroFredAdapter()

        try:
            df = adapter.fetch_indicators(
                codes=["VIX_30D"],
                start_date="2024-01-01",
                end_date="2024-01-31",
            )

            assert df.height > 0

        finally:
            adapter.close()
