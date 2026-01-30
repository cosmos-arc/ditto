"""Unit tests for CapitalStore with PIT query support."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_datahub.domains.capital.capital_store import CapitalStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库用于测试."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)

    # 创建所有 Capital 域的表
    tables = [
        # 1. 财务报表数据 (PIT)
        """
        CREATE TABLE IF NOT EXISTS balance_sheet (
            instrument_id TEXT NOT NULL,
            report_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            total_assets REAL,
            total_liabilities REAL,
            net_assets REAL,
            current_assets REAL,
            current_liabilities REAL,
            PRIMARY KEY (instrument_id, report_date, effective_from)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS income_statement (
            instrument_id TEXT NOT NULL,
            report_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            revenue REAL,
            operating_profit REAL,
            net_profit REAL,
            eps REAL,
            PRIMARY KEY (instrument_id, report_date, effective_from)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cash_flow (
            instrument_id TEXT NOT NULL,
            report_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            operating_cash_flow REAL,
            investing_cash_flow REAL,
            financing_cash_flow REAL,
            net_cash_flow REAL,
            PRIMARY KEY (instrument_id, report_date, effective_from)
        )
        """,
        # 2. 估值指标数据 (PIT)
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
        # 3. 衍生品数据 (PIT)
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
        # 4. 成分股数据 (PIT)
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
        # 5. 股息分红 (PIT)
        """
        CREATE TABLE IF NOT EXISTS dividend (
            instrument_id TEXT NOT NULL,
            ex_dividend_date DATE NOT NULL,
            knowledge_date DATE NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE,
            dividend_per_share REAL,
            dividend_yield REAL,
            PRIMARY KEY (instrument_id, ex_dividend_date, effective_from)
        )
        """,
        # 6. 融资融券 (PIT)
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
        # 7. 股权质押 (PIT)
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
        # 8. 公司行为 (非 PIT)
        """
        CREATE TABLE IF NOT EXISTS corporate_actions (
            instrument_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            announcement_date DATE NOT NULL,
            effective_date DATE,
            description TEXT,
            PRIMARY KEY (instrument_id, action_type, announcement_date)
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


def test_get_balance_sheet_pit_query(capital_store: CapitalStore) -> None:
    """测试资产负债表的 PIT 查询 - 基本功能."""
    # 准备测试数据
    test_data = [
        {
            "instrument_id": "600000.SH",
            "report_date": date(2024, 3, 31),
            "knowledge_date": date(2024, 4, 30),
            "effective_from": date(2024, 5, 1),
            "effective_to": None,  # 当前有效
            "total_assets": 1000000.0,
            "total_liabilities": 600000.0,
            "net_assets": 400000.0,
            "current_assets": 300000.0,
            "current_liabilities": 200000.0,
        },
        {
            "instrument_id": "600000.SH",
            "report_date": date(2024, 3, 31),
            "knowledge_date": date(2024, 4, 25),
            "effective_from": date(2024, 4, 26),
            "effective_to": date(2024, 5, 1),  # 已被新数据替代
            "total_assets": 950000.0,
            "total_liabilities": 580000.0,
            "net_assets": 370000.0,
            "current_assets": 280000.0,
            "current_liabilities": 190000.0,
        },
    ]

    # 写入测试数据
    for row in test_data:
        capital_store._client.execute(
            """
            INSERT INTO balance_sheet (
                instrument_id, report_date, knowledge_date,
                effective_from, effective_to,
                total_assets, total_liabilities, net_assets,
                current_assets, current_liabilities
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [
                row["instrument_id"],
                row["report_date"],
                row["knowledge_date"],
                row["effective_from"],
                row["effective_to"],
                row["total_assets"],
                row["total_liabilities"],
                row["net_assets"],
                row["current_assets"],
                row["current_liabilities"],
            ],
        )
    capital_store._client.commit()

    # 测试 1: 查询当前数据（应该返回 effective_to IS NULL 的记录）
    result = capital_store.get_balance_sheet(
        instrument_id="600000.SH",
        as_of_date=date(2024, 5, 15),
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"
    assert result["total_assets"][0] == 1000000.0  # 当前有效数据
    assert result["effective_to"][0] is None

    # 测试 2: 查询历史数据（应该返回 effective_from <= as_of
    # AND (effective_to IS NULL OR effective_to > as_of) 的记录）
    result_historical = capital_store.get_balance_sheet(
        instrument_id="600000.SH",
        as_of_date=date(2024, 4, 28),
    )

    assert len(result_historical) == 1
    assert result_historical["instrument_id"][0] == "600000.SH"
    assert result_historical["total_assets"][0] == 950000.0  # 历史数据


def test_get_balance_sheet_no_data(capital_store: CapitalStore) -> None:
    """测试查询不存在的标的."""
    result = capital_store.get_balance_sheet(
        instrument_id="999999.SH",
        as_of_date=date(2024, 5, 15),
    )

    assert len(result) == 0
    assert isinstance(result, pl.DataFrame)


def test_get_balance_sheet_empty_table(capital_store: CapitalStore) -> None:
    """测试空表查询."""
    result = capital_store.get_balance_sheet(
        instrument_id="600000.SH",
        as_of_date=date(2024, 5, 15),
    )

    assert len(result) == 0


def test_get_balance_sheet_multiple_instruments(capital_store: CapitalStore) -> None:
    """测试多个标的的 PIT 查询."""
    # 写入多个标的数据
    instruments = ["600000.SH", "600001.SH", "600002.SH"]
    for i, instrument_id in enumerate(instruments):
        capital_store._client.execute(
            """
            INSERT INTO balance_sheet (
                instrument_id, report_date, knowledge_date,
                effective_from, effective_to,
                total_assets, total_liabilities, net_assets,
                current_assets, current_liabilities
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            [
                instrument_id,
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                None,
                (i + 1) * 1000000.0,
                (i + 1) * 600000.0,
                (i + 1) * 400000.0,
                (i + 1) * 300000.0,
                (i + 1) * 200000.0,
            ],
        )
    capital_store._client.commit()

    # 查询每个标的
    for i, instrument_id in enumerate(instruments):
        result = capital_store.get_balance_sheet(
            instrument_id=instrument_id,
            as_of_date=date(2024, 5, 15),
        )

        assert len(result) == 1
        assert result["instrument_id"][0] == instrument_id
        assert result["total_assets"][0] == (i + 1) * 1000000.0


def test_get_balance_sheet_pit_boundary(capital_store: CapitalStore) -> None:
    """测试 PIT 查询的边界情况."""
    # 创建数据：effective_from = 2024-05-01, effective_to = 2024-06-01
    capital_store._client.execute(
        """
        INSERT INTO balance_sheet (
            instrument_id, report_date, knowledge_date,
            effective_from, effective_to,
            total_assets, total_liabilities, net_assets,
            current_assets, current_liabilities
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        [
            "600000.SH",
            date(2024, 3, 31),
            date(2024, 4, 30),
            date(2024, 5, 1),
            date(2024, 6, 1),
            1000000.0,
            600000.0,
            400000.0,
            300000.0,
            200000.0,
        ],
    )
    capital_store._client.commit()

    # 测试边界前（应该查不到）
    result_before = capital_store.get_balance_sheet(
        instrument_id="600000.SH",
        as_of_date=date(2024, 4, 30),
    )
    assert len(result_before) == 0

    # 测试生效当天（应该查到）
    result_on = capital_store.get_balance_sheet(
        instrument_id="600000.SH",
        as_of_date=date(2024, 5, 1),
    )
    assert len(result_on) == 1

    # 测试失效当天（应该查不到，因为 effective_to > as_of_date 不满足）
    result_off = capital_store.get_balance_sheet(
        instrument_id="600000.SH",
        as_of_date=date(2024, 6, 1),
    )
    assert len(result_off) == 0


# ============================================================================
# 2. Income Statement 测试
# ============================================================================


def test_get_income_statement_pit_query(capital_store: CapitalStore) -> None:
    """测试利润表的 PIT 查询."""
    # 写入测试数据
    test_data = pl.DataFrame(
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

    capital_store.write_income_statement(test_data)

    # 查询
    result = capital_store.get_income_statement(
        instrument_id="600000.SH",
        as_of_date=date(2024, 5, 15),
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"
    assert result["revenue"][0] == 500000.0
    assert result["eps"][0] == 0.5


# ============================================================================
# 3. Cash Flow 测试
# ============================================================================


def test_get_cash_flow_pit_query(capital_store: CapitalStore) -> None:
    """测试现金流量表的 PIT 查询."""
    # 写入测试数据
    test_data = pl.DataFrame(
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

    capital_store.write_cash_flow(test_data)

    # 查询
    result = capital_store.get_cash_flow(
        instrument_id="600000.SH",
        as_of_date=date(2024, 5, 15),
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"
    assert result["operating_cash_flow"][0] == 100000.0
    assert result["net_cash_flow"][0] == 70000.0


# ============================================================================
# 4. Valuation Metrics 测试
# ============================================================================


def test_get_valuation_metrics_pit_query(capital_store: CapitalStore) -> None:
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

    capital_store.write_valuation_metrics(test_data)

    # 查询
    result = capital_store.get_valuation_metrics(
        instrument_id="600000.SH",
        as_of_date=date(2024, 5, 20),
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"
    assert result["pe_ratio"][0] == 15.5
    assert result["pb_ratio"][0] == 2.3


# ============================================================================
# 5. Futures 测试
# ============================================================================


def test_get_futures_pit_query(capital_store: CapitalStore) -> None:
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

    capital_store.write_futures(test_data)

    # 查询
    result = capital_store.get_futures(
        instrument_id="IF2405",
        as_of_date=date(2024, 5, 20),
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "IF2405"
    assert result["settlement_price"][0] == 3500.0
    assert result["volume"][0] == 100000.0


# ============================================================================
# 6. Index Composition 测试
# ============================================================================


def test_get_index_composition_pit_query(capital_store: CapitalStore) -> None:
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

    capital_store.write_index_composition(test_data)

    # 查询
    result = capital_store.get_index_composition(
        index_id="000001.SH",
        as_of_date=date(2024, 5, 15),
    )

    assert len(result) == 2
    assert result["index_id"][0] == "000001.SH"
    assert result["instrument_id"][0] == "600000.SH"
    assert result["weight"][0] == 0.15


# ============================================================================
# 7. Dividend 测试
# ============================================================================


def test_get_dividend_pit_query(capital_store: CapitalStore) -> None:
    """测试股息分红的 PIT 查询."""
    # 写入测试数据
    test_data = pl.DataFrame(
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

    capital_store.write_dividend(test_data)

    # 查询
    result = capital_store.get_dividend(
        instrument_id="600000.SH",
        as_of_date=date(2024, 5, 25),
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"
    assert result["dividend_per_share"][0] == 0.5
    assert result["dividend_yield"][0] == 0.02


# ============================================================================
# 8. Margin Trading 测试
# ============================================================================


def test_get_margin_trading_pit_query(capital_store: CapitalStore) -> None:
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

    capital_store.write_margin_trading(test_data)

    # 查询
    result = capital_store.get_margin_trading(
        instrument_id="600000.SH",
        as_of_date=date(2024, 5, 20),
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"
    assert result["margin_buy_balance"][0] == 1000000.0
    assert result["short_sell_balance"][0] == 500000.0


# ============================================================================
# 9. Pledge Ratio 测试
# ============================================================================


def test_get_pledge_ratio_pit_query(capital_store: CapitalStore) -> None:
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

    capital_store.write_pledge_ratio(test_data)

    # 查询
    result = capital_store.get_pledge_ratio(
        instrument_id="600000.SH",
        as_of_date=date(2024, 5, 15),
    )

    assert len(result) == 1
    assert result["instrument_id"][0] == "600000.SH"
    assert result["pledge_ratio"][0] == 0.15
    assert result["pledge_shares"][0] == 100000000.0


# ============================================================================
# 10. Corporate Actions 测试（非 PIT）
# ============================================================================


def test_get_corporate_actions(capital_store: CapitalStore) -> None:
    """测试公司行为的查询（非 PIT）."""
    # 写入测试数据
    test_data = pl.DataFrame(
        {
            "instrument_id": ["600000.SH", "600000.SH"],
            "action_type": ["分红", "配股"],
            "announcement_date": [date(2024, 5, 10), date(2024, 5, 20)],
            "effective_date": [date(2024, 6, 1), date(2024, 6, 15)],
            "description": ["每10股派5元", "每10股配3股"],
        }
    )

    capital_store.write_corporate_actions(test_data)

    # 查询
    result = capital_store.get_corporate_actions(
        instrument_id="600000.SH",
        start_date=date(2024, 5, 1),
        end_date=date(2024, 5, 31),
    )

    assert len(result) == 2
    assert result["instrument_id"][0] == "600000.SH"
    # 结果按 announcement_date DESC 排序，所以应该是 "配股"（5月20日）
    assert result["action_type"][0] == "配股"


def test_get_corporate_actions_no_filter(capital_store: CapitalStore) -> None:
    """测试公司行为的无过滤查询."""
    # 写入测试数据
    test_data = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "action_type": ["分红"],
            "announcement_date": [date(2024, 5, 10)],
            "effective_date": [date(2024, 6, 1)],
            "description": ["每10股派5元"],
        }
    )

    capital_store.write_corporate_actions(test_data)

    # 无过滤查询
    result = capital_store.get_corporate_actions(instrument_id="600000.SH")

    assert len(result) == 1
    assert result["action_type"][0] == "分红"
