"""Unit tests for DividendReader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_datahub.stores.fundamental.corporate.dividend_reader import (
    DividendReader,
)
from ditto_datahub.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import SQLitePool


@pytest.fixture
def in_memory_db(tmp_path: Path) -> SQLitePool:
    """Provide in-memory SQLite database with dividend table."""
    db_path = tmp_path / "test.db"

    pool = SQLitePool(str(db_path))
    pool.get_connection().execute(
        """CREATE TABLE IF NOT EXISTS dividend (
        instrument_id TEXT NOT NULL,
        ex_dividend_date DATE NOT NULL,
        knowledge_date DATE NOT NULL,
        effective_from DATE NOT NULL,
        effective_to DATE,
        dividend_per_share REAL,
        dividend_yield REAL,
        PRIMARY KEY (instrument_id, ex_dividend_date, effective_from)
    )"""
    )
    return pool


@pytest.fixture
def dividend_reader(in_memory_db: SQLitePool) -> DividendReader:
    """Provide DividendReader with in-memory database."""
    return DividendReader(SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestDividendReader:
    """Test cases for DividendReader."""

    def test_get_returns_data(
        self, dividend_reader: DividendReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns data for valid query."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO dividend
            (instrument_id, ex_dividend_date, knowledge_date,
             effective_from, effective_to,
             dividend_per_share, dividend_yield)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 6, 15),
                date(2024, 6, 10),
                date(2024, 6, 11),
                None,
                0.5,
                2.5,
            ],
        )
        client.commit()

        # Act
        result = dividend_reader.get(600000, date(2024, 6, 20))

        # Assert
        assert len(result) == 1
        assert result["instrument_id"][0] == "600000"
        assert result["dividend_per_share"][0] == 0.5
        assert result["dividend_yield"][0] == 2.5

    def test_get_empty_table(
        self,
        dividend_reader: DividendReader,
    ) -> None:
        """Test that get returns empty DataFrame for empty table."""
        # Act
        result = dividend_reader.get(600000, date(2024, 6, 20))

        # Assert
        assert len(result) == 0
        assert isinstance(result, pl.DataFrame)

    def test_get_no_data(
        self, dividend_reader: DividendReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns empty DataFrame for non-existent instrument."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO dividend
            (instrument_id, ex_dividend_date, knowledge_date,
             effective_from, effective_to,
             dividend_per_share, dividend_yield)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                "600001",
                date(2024, 6, 15),
                date(2024, 6, 10),
                date(2024, 6, 11),
                None,
                0.5,
                2.5,
            ],
        )
        client.commit()

        # Act
        result = dividend_reader.get(600000, date(2024, 6, 20))

        # Assert
        assert len(result) == 0

    def test_get_pit_query(
        self, dividend_reader: DividendReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query returns correct version based on as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Insert first version (effective 2024-06-11 to 2024-07-01)
        client.execute(
            """INSERT INTO dividend
            (instrument_id, ex_dividend_date, knowledge_date,
             effective_from, effective_to,
             dividend_per_share, dividend_yield)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 6, 15),
                date(2024, 6, 10),
                date(2024, 6, 11),
                date(2024, 7, 1),
                0.5,
                2.5,
            ],
        )
        # Insert second version (effective from 2024-07-01)
        client.execute(
            """INSERT INTO dividend
            (instrument_id, ex_dividend_date, knowledge_date,
             effective_from, effective_to,
             dividend_per_share, dividend_yield)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 6, 15),
                date(2024, 6, 25),
                date(2024, 7, 1),
                None,
                0.6,
                3.0,
            ],
        )
        client.commit()

        # Act - Query before second version effective date
        result_old = dividend_reader.get(600000, date(2024, 6, 20))

        # Act - Query after second version effective date
        result_new = dividend_reader.get(600000, date(2024, 7, 5))

        # Assert
        assert len(result_old) == 1
        assert result_old["dividend_per_share"][0] == 0.5

        assert len(result_new) == 1
        assert result_new["dividend_per_share"][0] == 0.6

    def test_get_pit_query_excludes_expired_version(
        self, dividend_reader: DividendReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query excludes version where effective_to == as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Version effective from 2024-06-11 to 2024-07-01
        # Note: effective_to = 2024-07-01 means version is NOT valid on 2024-07-01
        client.execute(
            """INSERT INTO dividend
            (instrument_id, ex_dividend_date, knowledge_date,
             effective_from, effective_to,
             dividend_per_share, dividend_yield)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [
                "600000",
                date(2024, 6, 15),
                date(2024, 6, 10),
                date(2024, 6, 11),
                date(2024, 7, 1),
                0.5,
                2.5,
            ],
        )
        client.commit()

        # Act - Query on effective_to date (version should be excluded)
        result = dividend_reader.get(600000, date(2024, 7, 1))

        # Assert
        assert len(result) == 0
