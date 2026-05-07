"""Unit tests for BalanceSheetReader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_data.storage.fundamental.financial.balance_sheet_reader import (
    BalanceSheetReader,
)
from ditto_data.storage.fundamental.specs import BALANCE_SHEET_SPEC
from ditto_platform.foundation import SQLitePool
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient

SPEC = BALANCE_SHEET_SPEC


@pytest.fixture
def in_memory_db(tmp_path: Path) -> SQLitePool:
    """Provide in-memory SQLite database with balance_sheet table."""
    db_path = tmp_path / "test.db"

    pool = SQLitePool(str(db_path))
    pool.get_connection().execute(
        """CREATE TABLE IF NOT EXISTS balance_sheet (
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
    )"""
    )
    return pool


@pytest.fixture
def balance_sheet_reader(in_memory_db: SQLitePool) -> BalanceSheetReader:
    """Provide BalanceSheetReader with in-memory database."""
    return BalanceSheetReader(SPEC, SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestBalanceSheetReader:
    """Test cases for BalanceSheetReader."""

    def test_get_returns_data(
        self, balance_sheet_reader: BalanceSheetReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns data for valid query."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO balance_sheet
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             total_assets, total_liabilities, net_assets,
             current_assets, current_liabilities)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                None,
                1000.0,
                500.0,
                500.0,
                600.0,
                300.0,
            ],
        )
        client.commit()

        # Act
        result = balance_sheet_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 1
        assert result["instrument_id"][0] == "600000"
        assert result["total_assets"][0] == 1000.0
        assert result["total_liabilities"][0] == 500.0

    def test_get_empty_table(
        self,
        balance_sheet_reader: BalanceSheetReader,
    ) -> None:
        """Test that get returns empty DataFrame for empty table."""
        # Act
        result = balance_sheet_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 0
        assert isinstance(result, pl.DataFrame)

    def test_get_no_data(
        self, balance_sheet_reader: BalanceSheetReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns empty DataFrame for non-existent instrument."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO balance_sheet
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             total_assets, total_liabilities, net_assets,
             current_assets, current_liabilities)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600001",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                None,
                1000.0,
                500.0,
                500.0,
                600.0,
                300.0,
            ],
        )
        client.commit()

        # Act
        result = balance_sheet_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 0

    def test_get_pit_query(
        self, balance_sheet_reader: BalanceSheetReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query returns correct version based on as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Insert first version (effective 2024-05-01 to 2024-06-01)
        client.execute(
            """INSERT INTO balance_sheet
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             total_assets, total_liabilities, net_assets,
             current_assets, current_liabilities)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                date(2024, 6, 1),
                1000.0,
                500.0,
                500.0,
                600.0,
                300.0,
            ],
        )
        # Insert second version (effective from 2024-06-01)
        client.execute(
            """INSERT INTO balance_sheet
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             total_assets, total_liabilities, net_assets,
             current_assets, current_liabilities)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 5, 15),
                date(2024, 6, 1),
                None,
                1200.0,
                600.0,
                600.0,
                700.0,
                350.0,
            ],
        )
        client.commit()

        # Act - Query before second version effective date
        result_old = balance_sheet_reader.get(600000, date(2024, 5, 15))

        # Act - Query after second version effective date
        result_new = balance_sheet_reader.get(600000, date(2024, 6, 15))

        # Assert
        assert len(result_old) == 1
        assert result_old["total_assets"][0] == 1000.0

        assert len(result_new) == 1
        assert result_new["total_assets"][0] == 1200.0

    def test_get_pit_query_excludes_expired_version(
        self, balance_sheet_reader: BalanceSheetReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query excludes version where effective_to == as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Version effective from 2024-05-01 to 2024-06-01
        # Note: effective_to = 2024-06-01 means version is NOT valid on 2024-06-01
        client.execute(
            """INSERT INTO balance_sheet
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             total_assets, total_liabilities, net_assets,
             current_assets, current_liabilities)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                date(2024, 6, 1),
                1000.0,
                500.0,
                500.0,
                600.0,
                300.0,
            ],
        )
        client.commit()

        # Act - Query on effective_to date (version should be excluded)
        result = balance_sheet_reader.get(600000, date(2024, 6, 1))

        # Assert
        assert len(result) == 0
