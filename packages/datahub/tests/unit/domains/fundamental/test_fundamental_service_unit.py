"""Unit tests for FundamentalService."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest
from ditto_datahub.domains.fundamental.fundamental_service import (
    FundamentalQuery,
    FundamentalService,
)
from ditto_datahub.domains.fundamental.fundamental_store import FundamentalStore
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_foundation import SQLitePool


@pytest.fixture
def in_memory_db() -> SQLiteClient:
    """创建内存数据库用于测试."""
    pool = SQLitePool(":memory:")
    client = SQLiteClient(pool)
    return client


@pytest.fixture
def store(in_memory_db: SQLiteClient) -> FundamentalStore:
    """创建 FundamentalStore 实例."""
    return FundamentalStore(sqlite_client=in_memory_db)


@pytest.fixture
def service(store: FundamentalStore) -> FundamentalService:
    """创建 FundamentalService 实例."""
    return FundamentalService(store)


def test_fundamental_service_init(service: FundamentalService) -> None:
    """测试 FundamentalService 初始化."""
    assert service is not None
    assert service._store is not None


def test_query_requires_as_of_date_for_pit_dataset(
    service: FundamentalService,
) -> None:
    """PIT 数据集必须提供 as_of_date."""
    with pytest.raises(ValueError, match="as_of_date"):
        service.query(
            FundamentalQuery(
                dataset="balance_sheet",
                instrument_id="600000.SH",
            )
        )


@pytest.fixture
def balance_sheet_table(in_memory_db: SQLiteClient) -> None:
    """创建 balance_sheet 表."""
    in_memory_db.execute("""
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
    """)
    in_memory_db.commit()


def test_write_balance_sheet(
    balance_sheet_table: None, store: FundamentalStore
) -> None:
    """测试写入资产负债表数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "total_assets": [1000000.0],
            "total_liabilities": [500000.0],
            "net_assets": [500000.0],
            "current_assets": [300000.0],
            "current_liabilities": [200000.0],
        }
    )

    count = store.write_balance_sheet(df)
    assert count == 1


def test_service_write_returns_result(
    balance_sheet_table: None, service: FundamentalService
) -> None:
    """write() 返回统一结果对象."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "total_assets": [1000000.0],
            "total_liabilities": [500000.0],
            "net_assets": [500000.0],
            "current_assets": [300000.0],
            "current_liabilities": [200000.0],
        }
    )
    result = service.write(dataset="balance_sheet", df=df)
    assert result.dataset == "balance_sheet"
    assert result.records_written == 1


def test_get_balance_sheet_pit(
    balance_sheet_table: None, service: FundamentalService
) -> None:
    """测试 PIT 查询资产负债表."""
    # 先写入数据（通过 Store）
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "total_assets": [1000000.0],
            "total_liabilities": [500000.0],
            "net_assets": [500000.0],
            "current_assets": [300000.0],
            "current_liabilities": [200000.0],
        }
    )
    service._store.write_balance_sheet(df)

    # 通过 Service 查询
    result = service.query(
        FundamentalQuery(
            dataset="balance_sheet",
            instrument_id="600000.SH",
            as_of_date=date(2024, 5, 1),
        )
    )
    assert len(result) == 1
    assert result["total_assets"][0] == 1000000.0


@pytest.fixture
def income_statement_table(in_memory_db: SQLiteClient) -> None:
    """创建 income_statement 表."""
    in_memory_db.execute("""
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
    """)
    in_memory_db.commit()


def test_write_income_statement(
    income_statement_table: None, store: FundamentalStore
) -> None:
    """测试写入利润表数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "revenue": [500000.0],
            "operating_profit": [100000.0],
            "net_profit": [80000.0],
            "eps": [0.5],
        }
    )

    count = store.write_income_statement(df)
    assert count == 1


def test_get_income_statement_pit(
    income_statement_table: None, service: FundamentalService
) -> None:
    """测试 PIT 查询利润表."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "revenue": [500000.0],
            "operating_profit": [100000.0],
            "net_profit": [80000.0],
            "eps": [0.5],
        }
    )
    service._store.write_income_statement(df)

    # 通过 Service 查询
    result = service.query(
        FundamentalQuery(
            dataset="income_statement",
            instrument_id="600000.SH",
            as_of_date=date(2024, 5, 1),
        )
    )
    assert len(result) == 1
    assert result["revenue"][0] == 500000.0


@pytest.fixture
def cash_flow_table(in_memory_db: SQLiteClient) -> None:
    """创建 cash_flow 表."""
    in_memory_db.execute("""
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
    """)
    in_memory_db.commit()


def test_write_cash_flow(cash_flow_table: None, store: FundamentalStore) -> None:
    """测试写入现金流量表数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "operating_cash_flow": [90000.0],
            "investing_cash_flow": [-20000.0],
            "financing_cash_flow": [-10000.0],
            "net_cash_flow": [60000.0],
        }
    )

    count = store.write_cash_flow(df)
    assert count == 1


def test_get_cash_flow_pit(cash_flow_table: None, service: FundamentalService) -> None:
    """测试 PIT 查询现金流量表."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "report_date": [date(2024, 3, 31)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "operating_cash_flow": [90000.0],
            "investing_cash_flow": [-20000.0],
            "financing_cash_flow": [-10000.0],
            "net_cash_flow": [60000.0],
        }
    )
    service._store.write_cash_flow(df)

    # 通过 Service 查询
    result = service.query(
        FundamentalQuery(
            dataset="cash_flow",
            instrument_id="600000.SH",
            as_of_date=date(2024, 5, 1),
        )
    )
    assert len(result) == 1
    assert result["operating_cash_flow"][0] == 90000.0


@pytest.fixture
def dividend_table(in_memory_db: SQLiteClient) -> None:
    """创建 dividend 表."""
    in_memory_db.execute("""
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
    """)
    in_memory_db.commit()


def test_write_dividend(dividend_table: None, store: FundamentalStore) -> None:
    """测试写入分红数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "ex_dividend_date": [date(2024, 5, 1)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "dividend_per_share": [0.5],
            "dividend_yield": [0.02],
        }
    )

    count = store.write_dividend(df)
    assert count == 1


def test_get_dividend_pit(dividend_table: None, service: FundamentalService) -> None:
    """测试 PIT 查询分红数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "ex_dividend_date": [date(2024, 5, 1)],
            "knowledge_date": [date(2024, 4, 25)],
            "effective_from": [date(2024, 4, 26)],
            "effective_to": [None],
            "dividend_per_share": [0.5],
            "dividend_yield": [0.02],
        }
    )
    service._store.write_dividend(df)

    # 通过 Service 查询
    result = service.query(
        FundamentalQuery(
            dataset="dividend",
            instrument_id="600000.SH",
            as_of_date=date(2024, 5, 2),
        )
    )
    assert len(result) == 1
    assert result["dividend_per_share"][0] == 0.5


@pytest.fixture
def corporate_actions_table(in_memory_db: SQLiteClient) -> None:
    """创建 corporate_actions 表."""
    in_memory_db.execute("""
        CREATE TABLE IF NOT EXISTS corporate_actions (
            instrument_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            announcement_date DATE NOT NULL,
            effective_date DATE,
            description TEXT,
            PRIMARY KEY (instrument_id, action_type, announcement_date)
        )
    """)
    in_memory_db.commit()


def test_write_corporate_actions(
    corporate_actions_table: None, store: FundamentalStore
) -> None:
    """测试写入公司行为数据."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "action_type": ["分红"],
            "announcement_date": [date(2024, 4, 25)],
            "effective_date": [date(2024, 5, 1)],
            "description": ["2023年度分红派息"],
        }
    )

    count = store.write_corporate_actions(df)
    assert count == 1


def test_get_corporate_actions(
    corporate_actions_table: None, service: FundamentalService
) -> None:
    """测试查询公司行为数据（非 PIT）."""
    df = pl.DataFrame(
        {
            "instrument_id": ["600000.SH"],
            "action_type": ["分红"],
            "announcement_date": [date(2024, 4, 25)],
            "effective_date": [date(2024, 5, 1)],
            "description": ["2023年度分红派息"],
        }
    )
    service._store.write_corporate_actions(df)

    # 查询全部（通过 Service）
    result = service.query(
        FundamentalQuery(
            dataset="corporate_actions",
            instrument_id="600000.SH",
        )
    )
    assert len(result) == 1
    assert result["action_type"][0] == "分红"

    # 按日期范围查询
    result = service.query(
        FundamentalQuery(
            dataset="corporate_actions",
            instrument_id="600000.SH",
            start_date=date(2024, 4, 1),
            end_date=date(2024, 4, 30),
        )
    )
    assert len(result) == 1
