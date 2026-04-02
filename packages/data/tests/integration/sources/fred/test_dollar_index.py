"""FRED dollar index integration tests."""

import os

import keyring
import polars as pl
import pytest
from ditto_data.sources.fred.adapters.macro import MacroFredAdapter


def _get_fred_api_key() -> str | None:
    """获取 FRED API key（优先环境变量，其次 keyring）."""
    if api_key := os.environ.get("FRED_API_KEY"):
        return api_key
    return keyring.get_password("fred", "api_key")


def _has_fred_api_key() -> bool:
    """检查 FRED API key 是否可用（环境变量或 keyring）."""
    return bool(_get_fred_api_key())


@pytest.fixture
def fred_adapter() -> MacroFredAdapter:
    """创建配置好的 MacroFredAdapter 实例."""
    api_key = _get_fred_api_key()
    if not api_key:
        pytest.skip("FRED_API_KEY not set (env or keyring)")
    return MacroFredAdapter(api_key=api_key)


@pytest.mark.integration
@pytest.mark.skipif(
    not _has_fred_api_key(), reason="FRED_API_KEY not set (env or keyring)"
)
class TestFredDollarIndexIngestion:
    """FRED 美元指数数据摄取集成测试."""

    def test_fetch_dollar_index_broad(self, fred_adapter: MacroFredAdapter) -> None:
        """测试获取贸易加权美元指数(广义)."""
        df = fred_adapter.fetch_indicators(
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

    def test_fetch_dollar_index_schema(self, fred_adapter: MacroFredAdapter) -> None:
        """测试美元指数返回的 schema 符合 MACRO_INDICATOR_SOURCE_SCHEMA."""
        df = fred_adapter.fetch_indicators(
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
