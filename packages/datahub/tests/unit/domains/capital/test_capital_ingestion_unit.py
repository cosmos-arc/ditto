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


def test_ingest_balance_sheet_success(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试成功摄入资产负债表数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1)],
            "effective_to": [None],
            "total_assets": [1000000.0],
            "total_liabilities": [600000.0],
            "net_assets": [400000.0],
            "current_assets": [300000.0],
            "current_liabilities": [200000.0],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_balance_sheet.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_balance_sheet.return_value = 1

    # 执行摄入
    result = capital_ingestion.ingest_balance_sheet(
        instrument_ids=["600000.SH"],
        start_date="20240101",
        end_date="20240331",
    )

    # 验证
    assert result.success
    assert result.records_written == 1
    assert result.dataset == "balance_sheet"
    assert result.error is None

    # 验证调用
    mock_source.fetch_balance_sheet.assert_called_once_with(
        ts_code="600000.SH",
        start_date="20240101",
        end_date="20240331",
    )
    mock_store.write_balance_sheet.assert_called_once()


def test_ingest_balance_sheet_empty_data(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试摄入空数据."""
    # Mock Source 返回空数据
    mock_source.fetch_balance_sheet.return_value = pl.DataFrame()

    # 执行摄入
    result = capital_ingestion.ingest_balance_sheet(
        instrument_ids=["600000.SH"],
        start_date="20240101",
        end_date="20240331",
    )

    # 验证
    assert result.success
    assert result.records_written == 0
    assert result.dataset == "balance_sheet"

    # 验证未调用写入
    mock_store.write_balance_sheet.assert_not_called()


def test_ingest_balance_sheet_write_error(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试写入失败的情况."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1)],
            "effective_to": [None],
            "total_assets": [1000000.0],
            "total_liabilities": [600000.0],
            "net_assets": [400000.0],
            "current_assets": [300000.0],
            "current_liabilities": [200000.0],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_balance_sheet.return_value = source_df

    # Mock Store 写入失败
    mock_store.write_balance_sheet.side_effect = Exception("Database error")

    # 执行摄入
    result = capital_ingestion.ingest_balance_sheet(
        instrument_ids=["600000.SH"],
        start_date="20240101",
        end_date="20240331",
    )

    # 验证
    assert not result.success
    assert result.records_written == 0
    assert result.dataset == "balance_sheet"
    assert result.error is not None
    assert "Database error" in result.error


def test_ingest_balance_sheet_fetch_error(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试获取数据失败的情况."""
    # Mock Source 抛出异常
    mock_source.fetch_balance_sheet.side_effect = Exception("API error")

    # 执行摄入
    result = capital_ingestion.ingest_balance_sheet(
        instrument_ids=["600000.SH"],
        start_date="20240101",
        end_date="20240331",
    )

    # 验证
    assert not result.success
    assert result.records_written == 0
    assert result.dataset == "balance_sheet"
    assert result.error is not None
    assert "API error" in result.error

    # 验证未调用写入
    mock_store.write_balance_sheet.assert_not_called()


def test_ingest_balance_sheet_multiple_instruments(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试摄入多个标的的数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH", "600001.SH"],
            "report_date": [date(2024, 3, 31), date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30), date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1), date(2024, 5, 1)],
            "effective_to": [None, None],
            "total_assets": [1000000.0, 2000000.0],
            "total_liabilities": [600000.0, 1200000.0],
            "net_assets": [400000.0, 800000.0],
            "current_assets": [300000.0, 600000.0],
            "current_liabilities": [200000.0, 400000.0],
        }
    )

    # Mock Source 返回数据（针对第一个标的）
    mock_source.fetch_balance_sheet.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_balance_sheet.return_value = 2

    # 执行摄入
    result = capital_ingestion.ingest_balance_sheet(
        instrument_ids=["600000.SH", "600001.SH"],
        start_date="20240101",
        end_date="20240331",
    )

    # 验证
    assert result.success
    assert result.records_written == 2
    assert result.dataset == "balance_sheet"

    # 验证调用次数（多个标的会多次调用 Source）
    assert mock_source.fetch_balance_sheet.call_count == 2
    mock_store.write_balance_sheet.assert_called_once()


def test_ingest_income_statement_success(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试成功摄入利润表数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1)],
            "effective_to": [None],
            "revenue": [500000.0],
            "operating_profit": [100000.0],
            "net_profit": [80000.0],
            "eps": [0.5],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_income_statement.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_income_statement.return_value = 1

    # 执行摄入
    result = capital_ingestion.ingest_income_statement(
        instrument_ids=["600000.SH"],
        start_date="20240101",
        end_date="20240331",
    )

    # 验证
    assert result.success
    assert result.records_written == 1
    assert result.dataset == "income_statement"

    # 验证调用
    mock_source.fetch_income_statement.assert_called_once()
    mock_store.write_income_statement.assert_called_once()


# ============================================================================
# 3. Cash Flow 测试
# ============================================================================


def test_ingest_cash_flow_success(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试成功摄入现金流量表数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 30)],
            "effective_from": [date(2024, 5, 1)],
            "effective_to": [None],
            "operating_cash_flow": [100000.0],
            "investing_cash_flow": [-50000.0],
            "financing_cash_flow": [20000.0],
            "net_cash_flow": [70000.0],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_cash_flow.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_cash_flow.return_value = 1

    # 执行摄入
    result = capital_ingestion.ingest_cash_flow(
        instrument_ids=["600000.SH"],
        start_date="20240101",
        end_date="20240331",
    )

    # 验证
    assert result.success
    assert result.records_written == 1
    assert result.dataset == "cash_flow"


# ============================================================================
# 4. Valuation Metrics 测试
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


# ============================================================================
# 5. Dividend 测试
# ============================================================================


def test_ingest_dividend_success(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试成功摄入股息分红数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "ex_dividend_date": [date(2024, 5, 20)],
            "knowledge_date": [date(2024, 5, 15)],
            "effective_from": [date(2024, 5, 16)],
            "effective_to": [None],
            "dividend_per_share": [0.5],
            "dividend_yield": [0.02],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_dividend.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_dividend.return_value = 1

    # 执行摄入
    result = capital_ingestion.ingest_dividend(
        instrument_ids=["600000.SH"],
        start_date="20240501",
        end_date="20240531",
    )

    # 验证
    assert result.success
    assert result.records_written == 1
    assert result.dataset == "dividend"


# ============================================================================
# 6. Margin Trading 测试
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


# ============================================================================
# 7. Pledge Ratio 测试
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


# ============================================================================
# 8. Futures 测试
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


# ============================================================================
# 9. Index Composition 测试
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


# ============================================================================
# 10. Corporate Actions 测试
# ============================================================================


def test_ingest_corporate_actions_success(
    capital_ingestion: CapitalIngestion,
    mock_source: MagicMock,
    mock_store: MagicMock,
) -> None:
    """测试成功摄入公司行为数据."""
    # 准备测试数据
    source_df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "action_type": ["分红"],
            "announcement_date": [date(2024, 5, 10)],
            "effective_date": [date(2024, 6, 1)],
            "description": ["每10股派5元"],
        }
    )

    # Mock Source 返回数据
    mock_source.fetch_corporate_actions.return_value = source_df

    # Mock Store 写入成功
    mock_store.write_corporate_actions.return_value = 1

    # 执行摄入
    result = capital_ingestion.ingest_corporate_actions(
        instrument_ids=["600000.SH"],
        start_date="20240501",
        end_date="20240531",
    )

    # 验证
    assert result.success
    assert result.records_written == 1
    assert result.dataset == "corporate_actions"
