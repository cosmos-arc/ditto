"""Unit tests for IncomeStatementReader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_data.storage.fundamental.financial.income_statement_reader import (
    IncomeStatementReader,
)
from ditto_data.storage.fundamental.specs import INCOME_STATEMENT_SPEC
from ditto_platform.foundation import SQLitePool
from ditto_platform.foundation.storage.sqlite_client import SQLiteClient

SPEC = INCOME_STATEMENT_SPEC


@pytest.fixture
def in_memory_db(tmp_path: Path) -> SQLitePool:
    """Provide in-memory SQLite database with income_statement table."""
    db_path = tmp_path / "test.db"

    pool = SQLitePool(str(db_path))
    pool.get_connection().execute(
        """CREATE TABLE IF NOT EXISTS income_statement (
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
    )"""
    )
    return pool


@pytest.fixture
def income_statement_reader(in_memory_db: SQLitePool) -> IncomeStatementReader:
    """Provide IncomeStatementReader with in-memory database."""
    return IncomeStatementReader(SPEC, SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestIncomeStatementReader:
    """Test cases for IncomeStatementReader."""

    def test_get_returns_data(
        self, income_statement_reader: IncomeStatementReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns data for valid query."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO income_statement
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             revenue, operating_profit, net_profit, eps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                None,
                1000.0,
                200.0,
                150.0,
                0.5,
            ],
        )
        client.commit()

        # Act
        result = income_statement_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 1
        assert result["instrument_id"][0] == "600000"
        assert result["revenue"][0] == 1000.0
        assert result["operating_profit"][0] == 200.0
        assert result["net_profit"][0] == 150.0
        assert result["eps"][0] == 0.5

    def test_get_empty_table(
        self,
        income_statement_reader: IncomeStatementReader,
    ) -> None:
        """Test that get returns empty DataFrame for empty table."""
        # Act
        result = income_statement_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 0
        assert isinstance(result, pl.DataFrame)

    def test_get_no_data(
        self, income_statement_reader: IncomeStatementReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns empty DataFrame for non-existent instrument."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO income_statement
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             revenue, operating_profit, net_profit, eps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600001",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                None,
                1000.0,
                200.0,
                150.0,
                0.5,
            ],
        )
        client.commit()

        # Act
        result = income_statement_reader.get(600000, date(2024, 5, 15))

        # Assert
        assert len(result) == 0

    def test_get_pit_query(
        self, income_statement_reader: IncomeStatementReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query returns correct version based on as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Insert first version (effective 2024-05-01 to 2024-06-01)
        client.execute(
            """INSERT INTO income_statement
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             revenue, operating_profit, net_profit, eps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                date(2024, 6, 1),
                1000.0,
                200.0,
                150.0,
                0.5,
            ],
        )
        # Insert second version (effective from 2024-06-01)
        client.execute(
            """INSERT INTO income_statement
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             revenue, operating_profit, net_profit, eps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 5, 15),
                date(2024, 6, 1),
                None,
                1200.0,
                250.0,
                180.0,
                0.6,
            ],
        )
        client.commit()

        # Act - Query before second version effective date
        result_old = income_statement_reader.get(600000, date(2024, 5, 15))

        # Act - Query after second version effective date
        result_new = income_statement_reader.get(600000, date(2024, 6, 15))

        # Assert
        assert len(result_old) == 1
        assert result_old["revenue"][0] == 1000.0
        assert result_old["eps"][0] == 0.5

        assert len(result_new) == 1
        assert result_new["revenue"][0] == 1200.0
        assert result_new["eps"][0] == 0.6

    def test_get_pit_query_excludes_expired_version(
        self, income_statement_reader: IncomeStatementReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query excludes version where effective_to == as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Version effective from 2024-05-01 to 2024-06-01
        # Note: effective_to = 2024-06-01 means version is NOT valid on 2024-06-01
        client.execute(
            """INSERT INTO income_statement
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to,
             revenue, operating_profit, net_profit, eps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 3, 31),
                date(2024, 4, 30),
                date(2024, 5, 1),
                date(2024, 6, 1),
                1000.0,
                200.0,
                150.0,
                0.5,
            ],
        )
        client.commit()

        # Act - Query on effective_to date (version should be excluded)
        result = income_statement_reader.get(600000, date(2024, 6, 1))

        # Assert
        assert len(result) == 0
