"""Unit tests for CapitalIngestion service."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_datahub.domains.capital.capital_ingestion import CapitalIngestion
from ditto_datahub.domains.capital.capital_store import CapitalStore
from ditto_datahub.sources.tushare.adapters.capital import CapitalTushareAdapter


@pytest.fixture
def mock_source() -> MagicMock:
    """创建 Mock Source."""
    source = MagicMock(spec=CapitalTushareAdapter)
    return source


@pytest.fixture
def mock_store() -> MagicMock:
    """创建 Mock Store."""
    store = MagicMock(spec=CapitalStore)
    return store


@pytest.fixture
def capital_ingestion(
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> CapitalIngestion:
    """创建 CapitalIngestion 实例."""
    return CapitalIngestion(
        capital_store=mock_store,
        tushare_source=mock_source,
    )


# ============================================================================
# 1. Valuation Metrics 测试
# ============================================================================


def test_ingest_valuation_metrics_success(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试成功摄入估值指标数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "trade_date": [date(2024, 5, 15)],
            "knowledge_date": [date(2024, 5, 15)],
            "effective_from": [date(2024, 5, 16)],
            "effective_to": [None],
            "pe_ratio": [15.5],
            "pb_ratio": [2.3],
            "ps_ratio": [1.8],
            "dividend_yield": [0.03],
            "market_cap": [1000000000.0],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_valuation_metrics.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_valuation_metrics.return_value = 1

    # 执行摄入
    result = capital_ingestion.ingest_valuation_metrics(
        instrument_ids=["600000.SH"],
        trade_date="20240515",
    )

    # 验证
    assert result.success
    assert result.records_written == 1
    assert result.dataset == "valuation_metrics"


def test_ingest_valuation_metrics_empty(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试摄入空估值指标数据."""
    # Mock Source 返回空数据
    mock_source.fetch_valuation_metrics.return_value = pl.DataFrame()

    # 执行摄入
    result = capital_ingestion.ingest_valuation_metrics(
        instrument_ids=["600000.SH"],
        trade_date="20240515",
    )

    # 验证
    assert result.success
    assert result.records_written == 0
    assert result.dataset == "valuation_metrics"

    # 验证未调用写入
    mock_store.write_valuation_metrics.assert_not_called()


# ============================================================================
# 2. Margin Trading 测试
# ============================================================================


def test_ingest_margin_trading_success(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试成功摄入融资融券数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "trade_date": [date(2024, 5, 15)],
            "knowledge_date": [date(2024, 5, 15)],
            "effective_from": [date(2024, 5, 16)],
            "effective_to": [None],
            "margin_buy_balance": [1000000.0],
            "short_sell_balance": [500000.0],
            "margin_buy_volume": [50000000.0],
            "short_sell_volume": [20000000.0],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_margin_trading.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_margin_trading.return_value = 1

    # 执行摄入
    result = capital_ingestion.ingest_margin_trading(
        instrument_ids=["600000.SH"],
        trade_date="20240515",
    )

    # 验证
    assert result.success
    assert result.records_written == 1
    assert result.dataset == "margin_trading"


def test_ingest_margin_trading_empty(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试摄入空融资融券数据."""
    # Mock Source 返回空数据
    mock_source.fetch_margin_trading.return_value = pl.DataFrame()

    # 执行摄入
    result = capital_ingestion.ingest_margin_trading(
        instrument_ids=["600000.SH"],
        trade_date="20240515",
    )

    # 验证
    assert result.success
    assert result.records_written == 0
    assert result.dataset == "margin_trading"

    # 验证未调用写入
    mock_store.write_margin_trading.assert_not_called()


# ============================================================================
# 3. Pledge Ratio 测试
# ============================================================================


def test_ingest_pledge_ratio_success(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试成功摄入股权质押数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1)],
            "effective_to": [None],
            "pledge_ratio": [0.15],
            "pledge_shares": [100000000.0],
            "total_shares": [1000000000.0],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_pledge_ratio.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_pledge_ratio.return_value = 1

    # 执行摄入
    result = capital_ingestion.ingest_pledge_ratio(
        instrument_ids=["600000.SH"],
        report_date="20240331",
    )

    # 验证
    assert result.success
    assert result.records_written == 1
    assert result.dataset == "pledge_ratio"


def test_ingest_pledge_ratio_empty(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试摄入空股权质押数据."""
    # Mock Source 返回空数据
    mock_source.fetch_pledge_ratio.return_value = pl.DataFrame()

    # 执行摄入
    result = capital_ingestion.ingest_pledge_ratio(
        instrument_ids=["600000.SH"],
        report_date="20240331",
    )

    # 验证
    assert result.success
    assert result.records_written == 0
    assert result.dataset == "pledge_ratio"

    # 验证未调用写入
    mock_store.write_pledge_ratio.assert_not_called()


# ============================================================================
# 4. Futures 测试
# ============================================================================


def test_ingest_futures_success(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试成功摄入期货数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["IF2405"],
            "trade_date": [date(2024, 5, 15)],
            "knowledge_date": [date(2024, 5, 15)],
            "effective_from": [date(2024, 5, 16)],
            "effective_to": [None],
            "open_interest": [50000.0],
            "settlement_price": [3500.0],
            "volume": [100000.0],
            "turnover": [350000000.0],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_futures.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_futures.return_value = 1

    # 执行摄入
    result = capital_ingestion.ingest_futures(
        instrument_ids=["IF2405"],
        trade_date="20240515",
    )

    # 验证
    assert result.success
    assert result.records_written == 1
    assert result.dataset == "futures"


def test_ingest_futures_empty(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试摄入空期货数据."""
    # Mock Source 返回空数据
    mock_source.fetch_futures.return_value = pl.DataFrame()

    # 执行摄入
    result = capital_ingestion.ingest_futures(
        instrument_ids=["IF2405"],
        trade_date="20240515",
    )

    # 验证
    assert result.success
    assert result.records_written == 0
    assert result.dataset == "futures"

    # 验证未调用写入
    mock_store.write_futures.assert_not_called()


# ============================================================================
# 5. Index Composition 测试
# ============================================================================


def test_ingest_index_composition_success(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试成功摄入指数成分股数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "index_id": ["000001.SH", "000001.SH"],
            "instrument_id": ["600000.SH", "600001.SH"],
            "weight": [0.15, 0.12],
            "effective_from": [date(2024, 5, 1), date(2024, 5, 1)],
            "effective_to": [None, None],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_index_composition.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_index_composition.return_value = 2

    # 执行摄入
    result = capital_ingestion.ingest_index_composition(
        index_id="000001.SH",
    )

    # 验证
    assert result.success
    assert result.records_written == 2
    assert result.dataset == "index_composition"


def test_ingest_index_composition_empty(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试摄入空指数成分股数据."""
    # Mock Source 返回空数据
    mock_source.fetch_index_composition.return_value = pl.DataFrame()

    # 执行摄入
    result = capital_ingestion.ingest_index_composition(
        index_id="000001.SH",
    )

    # 验证
    assert result.success
    assert result.records_written == 0
    assert result.dataset == "index_composition"

    # 验证未调用写入
    mock_store.write_index_composition.assert_not_called()
