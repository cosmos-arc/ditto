"""Unit tests for CashFlowReader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_data.storage.fundamental.financial.cash_flow_reader import (
    CashFlowReader,
)
from ditto_data.storage.fundamental.specs import CASH_FLOW_SPEC
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_platform.foundation import SQLitePool

SPEC = CASH_FLOW_SPEC


@pytest.fixture
def in_memory_db(tmp_path: Path) -> SQLitePool:
    """Provide in-memory SQLite database with cash_flow table."""
    db_path = tmp_path / "test.db"

    pool = SQLitePool(str(db_path))
    pool.get_connection().execute(
        """CREATE TABLE IF NOT EXISTS cash_flow (
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
    )"""
    )
    return pool


@pytest.fixture
def cash_flow_reader(in_memory_db: SQLitePool) -> CashFlowReader:
    """Provide CashFlowReader with in-memory database."""
    return CashFlowReader(SPEC, SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestCashFlowReader:
    """Test cases for CashFlowReader."""

    def test_get_returns_data(
        self, cash_flow_reader: CashFlowReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns data for valid query."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO cash_flow
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             operating_cash_flow, investing_cash_flow,
             financing_cash_flow, net_cash_flow)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                None,
                500.0,
                -200.0,
                -300.0,
                0.0,
            ],
        )
        client.commit()

        # Act
        result = cash_flow_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 1
        assert result["instrument_id"][0] == "600000"
        assert result["operating_cash_flow"][0] == 500.0
        assert result["investing_cash_flow"][0] == -200.0
        assert result["financing_cash_flow"][0] == -300.0
        assert result["net_cash_flow"][0] == 0.0

    def test_get_empty_table(
        self,
        cash_flow_reader: CashFlowReader,
    ) -> None:
        """Test that get returns empty DataFrame for empty table."""
        # Act
        result = cash_flow_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 0
        assert isinstance(result, pl.DataFrame)

    def test_get_no_data(
        self, cash_flow_reader: CashFlowReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns empty DataFrame for non-existent instrument."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO cash_flow
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             operating_cash_flow, investing_cash_flow,
             financing_cash_flow, net_cash_flow)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600001",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                None,
                500.0,
                -200.0,
                -300.0,
                0.0,
            ],
        )
        client.commit()

        # Act
        result = cash_flow_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 0

    def test_get_pit_query(
        self, cash_flow_reader: CashFlowReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query returns correct version based on as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Insert first version (effective 2024-05-01 to 2024-06-01)
        client.execute(
            """INSERT INTO cash_flow
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             operating_cash_flow, investing_cash_flow,
             financing_cash_flow, net_cash_flow)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                date(2024, 6, 1),
                500.0,
                -200.0,
                -300.0,
                0.0,
            ],
        )
        # Insert second version (effective from 2024-06-01)
        client.execute(
            """INSERT INTO cash_flow
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             operating_cash_flow, investing_cash_flow,
             financing_cash_flow, net_cash_flow)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 5, 15),
                date(2024, 6, 1),
                None,
                600.0,
                -250.0,
                -350.0,
                0.0,
            ],
        )
        client.commit()

        # Act - Query before second version effective date
        result_old = cash_flow_reader.get(600000, date(2024, 5, 15))

        # Act - Query after second version effective date
        result_new = cash_flow_reader.get(600000, date(2024, 6, 15))

        # Assert
        assert len(result_old) == 1
        assert result_old["operating_cash_flow"][0] == 500.0

        assert len(result_new) == 1
        assert result_new["operating_cash_flow"][0] == 600.0

    def test_get_pit_query_excludes_expired_version(
        self, cash_flow_reader: CashFlowReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query excludes version where effective_to == as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Version effective from 2024-05-01 to 2024-06-01
        # Note: effective_to = 2024-06-01 means version is NOT valid on 2024-06-01
        client.execute(
            """INSERT INTO cash_flow
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             operating_cash_flow, investing_cash_flow,
             financing_cash_flow, net_cash_flow)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                date(2024, 6, 1),
                500.0,
                -200.0,
                -300.0,
                0.0,
            ],
        )
        client.commit()

        # Act - Query on effective_to date (version should be excluded)
        result = cash_flow_reader.get(600000, date(2024, 6, 1))

        # Assert
        assert len(result) == 0
