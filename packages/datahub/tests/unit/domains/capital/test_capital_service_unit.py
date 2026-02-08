"""Unit tests for CapitalService with PIT query support."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_datahub.services.capital.capital_service import CapitalQuery, CapitalService
from ditto_datahub.stores.capital.capital_store import CapitalStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库用于测试."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)

    # 创建所有 Capital 域的表
    tables = [
        # 1. 估值指标数据 (PIT)
        """
        CREATE TABLE IF NOT EXISTS valuation_metrics (
            instrument_id TEXT NOT NULL,
            trade_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            pe_ratio REAL,
            pb_ratio REAL,
            ps_ratio REAL,
            dividend_yield REAL,
            market_cap REAL,
            PRIMARY KEY (instrument_id, trade_date, effective_from)
        )
        """,
        # 2. 期货数据 (PIT)
        """
        CREATE TABLE IF NOT EXISTS futures (
            instrument_id TEXT NOT NULL,
            trade_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            open_interest REAL,
            settlement_price REAL,
            volume REAL,
            turnover REAL,
            PRIMARY KEY (instrument_id, trade_date, effective_from)
        )
        """,
        # 3. 成分股数据 (PIT)
        """
        CREATE TABLE IF NOT EXISTS index_composition (
            index_id TEXT NOT NULL,
            instrument_id TEXT NOT NULL,
            weight REAL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            PRIMARY KEY (index_id, instrument_id, effective_from)
        )
        """,
        # 4. 融资融券 (PIT)
        """
        CREATE TABLE IF NOT EXISTS margin_trading (
            instrument_id TEXT NOT NULL,
            trade_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            margin_buy_balance REAL,
            short_sell_balance REAL,
            margin_buy_volume REAL,
            short_sell_volume REAL,
            PRIMARY KEY (instrument_id, trade_date, effective_from)
        )
        """,
        # 5. 股权质押 (PIT)
        """
        CREATE TABLE IF NOT EXISTS pledge_ratio (
            instrument_id TEXT NOT NULL,
            report_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            pledge_ratio REAL,
            pledge_shares REAL,
            total_shares REAL,
            PRIMARY KEY (instrument_id, report_date, effective_from)
        )
        """,
    ]

    for table_sql in tables:
        client.execute(table_sql)

    return client


@pytest.fixture
def capital_store(in_memory_db: SQLiteClient) -> CapitalStore:
    """创建 CapitalStore 实例."""
    return CapitalStore(in_memory_db)


@pytest.fixture
def capital_service(capital_store: CapitalStore) -> CapitalService:
    """创建 CapitalService 实例."""
    return CapitalService(capital_store)


def test_query_requires_instrument_id_for_security_dataset(
    capital_service: CapitalService,
) -> None:
    """非指数查询必须提供 instrument_id."""
    with pytest.raises(ValueError, match="instrument_id"):
        capital_service.query(
            CapitalQuery(
                dataset="valuation_metrics",
                as_of_date=date(2024, 5, 20),
            )
        )


def test_query_requires_index_id_for_index_composition(
    capital_service: CapitalService,
) -> None:
    """指数成分查询必须提供 index_id."""
    with pytest.raises(ValueError, match="index_id"):
        capital_service.query(
            CapitalQuery(
                dataset="index_composition",
                as_of_date=date(2024, 5, 20),
            )
        )


# ============================================================================
# 1. Valuation Metrics 测试
# ============================================================================


def test_get_valuation_metrics_pit_query(capital_service: CapitalService) -> None:
    """测试估值指标的 PIT 查询."""
    # 写入测试数据
    test_data = pl.DataFrame(
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

    # 通过 Store 写入数据
    capital_service._store.write_valuation_metrics(test_data)

    # 通过 Service 查询
    result = capital_service.query(
        CapitalQuery(
            dataset="valuation_metrics",
            instrument_id="600000.SH",
            as_of_date=date(2024, 5, 20),
        )
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"
    assert result["pe_ratio"][0] == 15.5
    assert result["pb_ratio"][0] == 2.3


def test_write_returns_result(capital_service: CapitalService) -> None:
    """write() 返回统一结果对象."""
    test_data = pl.DataFrame(
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

    result = capital_service.write(dataset="valuation_metrics", df=test_data)

    assert result.dataset == "valuation_metrics"
    assert result.records_written == 1


def test_get_valuation_metrics_no_data(capital_service: CapitalService) -> None:
    """测试查询不存在的标的."""
    result = capital_service.query(
        CapitalQuery(
            dataset="valuation_metrics",
            instrument_id="999999.SH",
            as_of_date=date(2024, 5, 15),
        )
    )

    assert len(result) == 0
    assert isinstance(result, pl.DataFrame)


def test_get_valuation_metrics_empty_table(capital_service: CapitalService) -> None:
    """测试空表查询."""
    result = capital_service.query(
        CapitalQuery(
            dataset="valuation_metrics",
            instrument_id="600000.SH",
            as_of_date=date(2024, 5, 15),
        )
    )

    assert len(result) == 0


# ============================================================================
# 2. Futures 测试
# ============================================================================


def test_get_futures_pit_query(capital_service: CapitalService) -> None:
    """测试期货数据的 PIT 查询."""
    # 写入测试数据
    test_data = pl.DataFrame(
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

    # 通过 Store 写入数据
    capital_service._store.write_futures(test_data)

    # 通过 Service 查询
    result = capital_service.query(
        CapitalQuery(
            dataset="futures",
            instrument_id="IF2405",
            as_of_date=date(2024, 5, 20),
        )
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "IF2405"
    assert result["settlement_price"][0] == 3500.0
    assert result["volume"][0] == 100000.0


def test_get_futures_no_data(capital_service: CapitalService) -> None:
    """测试查询不存在的期货."""
    result = capital_service.query(
        CapitalQuery(
            dataset="futures",
            instrument_id="IF9999",
            as_of_date=date(2024, 5, 15),
        )
    )

    assert len(result) == 0


# ============================================================================
# 3. Index Composition 测试
# ============================================================================


def test_get_index_composition_pit_query(capital_service: CapitalService) -> None:
    """测试指数成分股的 PIT 查询."""
    # 写入测试数据
    test_data = pl.DataFrame(
        {
            "index_id": ["000001.SH", "000001.SH"],
            "instrument_id": ["600000.SH", "600001.SH"],
            "weight": [0.15, 0.12],
            "effective_from": [date(2024, 5, 1), date(2024, 5, 1)],
            "effective_to": [None, None],
        }
    )

    # 通过 Store 写入数据
    capital_service._store.write_index_composition(test_data)

    # 通过 Service 查询
    result = capital_service.query(
        CapitalQuery(
            dataset="index_composition",
            index_id="000001.SH",
            as_of_date=date(2024, 5, 15),
        )
    )

    assert len(result) == 2
    assert result["index_id"][0] == "000001.SH"
    assert result["instrument_id"][0] == "600000.SH"
    assert result["weight"][0] == 0.15


def test_get_index_composition_no_data(capital_service: CapitalService) -> None:
    """测试查询不存在的指数."""
    result = capital_service.query(
        CapitalQuery(
            dataset="index_composition",
            index_id="999999.SH",
            as_of_date=date(2024, 5, 15),
        )
    )

    assert len(result) == 0


# ============================================================================
# 4. Margin Trading 测试
# ============================================================================


def test_get_margin_trading_pit_query(capital_service: CapitalService) -> None:
    """测试融资融券的 PIT 查询."""
    # 写入测试数据
    test_data = pl.DataFrame(
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

    # 通过 Store 写入数据
    capital_service._store.write_margin_trading(test_data)

    # 通过 Service 查询
    result = capital_service.query(
        CapitalQuery(
            dataset="margin_trading",
            instrument_id="600000.SH",
            as_of_date=date(2024, 5, 20),
        )
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"
    assert result["margin_buy_balance"][0] == 1000000.0
    assert result["short_sell_balance"][0] == 500000.0


def test_get_margin_trading_no_data(capital_service: CapitalService) -> None:
    """测试查询不存在的标的."""
    result = capital_service.query(
        CapitalQuery(
            dataset="margin_trading",
            instrument_id="999999.SH",
            as_of_date=date(2024, 5, 15),
        )
    )

    assert len(result) == 0


# ============================================================================
# 5. Pledge Ratio 测试
# ============================================================================


def test_get_pledge_ratio_pit_query(capital_service: CapitalService) -> None:
    """测试股权质押的 PIT 查询."""
    # 写入测试数据
    test_data = pl.DataFrame(
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

    # 通过 Store 写入数据
    capital_service._store.write_pledge_ratio(test_data)

    # 通过 Service 查询
    result = capital_service.query(
        CapitalQuery(
            dataset="pledge_ratio",
            instrument_id="600000.SH",
            as_of_date=date(2024, 5, 15),
        )
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"
    assert result["pledge_ratio"][0] == 0.15
    assert result["pledge_shares"][0] == 100000000.0


def test_get_pledge_ratio_no_data(capital_service: CapitalService) -> None:
    """测试查询不存在的标的."""
    result = capital_service.query(
        CapitalQuery(
            dataset="pledge_ratio",
            instrument_id="999999.SH",
            as_of_date=date(2024, 5, 15),
        )
    )

    assert len(result) == 0
