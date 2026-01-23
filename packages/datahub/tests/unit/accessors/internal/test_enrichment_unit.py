"""Enrichment 纯函数模块单元测试。"""

import polars as pl
from ditto_datahub.accessors.internal.enrichment import (
    enrich_with_sid,
    enrich_with_status,
    enrich_with_symbol,
)


def test_enrich_with_sid_basic():
    """测试 enrich_with_sid 基本功能。"""
    df = pl.DataFrame(
        {
            "ts_code": ["000001.SZ", "000002.SZ"],
            "close": [10.0, 20.0],
        }
    )
    sid_mapping = {
        "000001.SZ": 1,
        "000002.SZ": 2,
    }

    result = enrich_with_sid(df, sid_mapping, source="tushare")

    assert result.columns == ["ts_code", "close", "sid", "source"]
    assert result["sid"].to_list() == [1, 2]
    assert result["source"].to_list() == ["tushare", "tushare"]


def test_enrich_with_sid_custom_column():
    """测试自定义源代码列名。"""
    df = pl.DataFrame(
        {
            "code": ["000001.SZ", "000002.SZ"],
            "close": [10.0, 20.0],
        }
    )
    sid_mapping = {"000001.SZ": 1, "000002.SZ": 2}

    result = enrich_with_sid(df, sid_mapping, src_code_col="code", source="tushare")

    assert result["sid"].to_list() == [1, 2]


def test_enrich_with_sid_empty_dataframe():
    """测试空 DataFrame。"""
    df = pl.DataFrame(schema={"ts_code": pl.String, "close": pl.Float64})
    sid_mapping = {"000001.SZ": 1}

    result = enrich_with_sid(df, sid_mapping)

    assert len(result) == 0


def test_enrich_with_symbol():
    """测试 enrich_with_symbol。"""
    df = pl.DataFrame(
        {
            "sid": [1, 2],
            "close": [10.0, 20.0],
        }
    )
    symbol_map = pl.DataFrame(
        {
            "sid": [1, 2],
            "symbol": ["平安银行", "万科A"],
        }
    )

    result = enrich_with_symbol(df, symbol_map)

    assert "symbol" in result.columns
    assert result["symbol"].to_list() == ["平安银行", "万科A"]


def test_enrich_with_symbol_empty_df():
    """测试空 DataFrame 的 symbol 增强。"""
    df = pl.DataFrame()
    symbol_map = pl.DataFrame({"sid": [1], "symbol": ["平安银行"]})

    result = enrich_with_symbol(df, symbol_map)

    assert len(result) == 0


def test_enrich_with_status():
    """测试 enrich_with_status。"""
    df = pl.DataFrame(
        {
            "sid": [1, 2],
            "trade_date": ["2024-01-02", "2024-01-02"],
            "close": [10.0, 20.0],
        }
    )
    status_df = pl.DataFrame(
        {
            "sid": [1, 2],
            "trade_date": ["2024-01-02", "2024-01-02"],
            "is_suspended": [False, True],
            "is_st": [False, False],
            "st_type": ["", ""],
            "list_status": ["L", "L"],
            "suspend_timing": ["", ""],
        }
    )

    result = enrich_with_status(df, status_df)

    assert "is_suspended" in result.columns
    assert result["is_suspended"].to_list() == [False, True]
    assert result["is_st"].to_list() == [False, False]


def test_enrich_with_status_empty_df():
    """测试空 DataFrame 的状态增强。"""
    df = pl.DataFrame()
    status_df = pl.DataFrame(
        {
            "sid": [1],
            "trade_date": ["2024-01-02"],
            "is_suspended": [False],
        }
    )

    result = enrich_with_status(df, status_df)

    assert len(result) == 0
