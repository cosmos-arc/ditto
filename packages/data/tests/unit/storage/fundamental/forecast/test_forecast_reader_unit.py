"""Unit tests for ForecastReader."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl
import pytest
from ditto_data.storage.fundamental.forecast.forecast_reader import (
    ForecastReader,
)
from ditto_data.storage.fundamental.specs import FORECAST_SPEC
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_platform.foundation import SQLitePool

SPEC = FORECAST_SPEC


@pytest.fixture
def in_memory_db(tmp_path: Path) -> SQLitePool:
    """Provide in-memory SQLite database with forecast table."""
    db_path = tmp_path / "test.db"

    pool = SQLitePool(str(db_path))
    pool.get_connection().execute(
        """CREATE TABLE IF NOT EXISTS forecast (
        instrument_id TEXT NOT NULL,
        report_date DATE NOT NULL,
        knowledge_date DATE NOT NULL,
        effective_from DATE NOT NULL,
        effective_to DATE,
        type TEXT,
        profit_range_min REAL,
        profit_range_max REAL,
        PRIMARY KEY (instrument_id, report_date, effective_from)
    )"""
    )
    return pool


@pytest.fixture
def forecast_reader(in_memory_db: SQLitePool) -> ForecastReader:
    """Provide ForecastReader with in-memory database."""
    return ForecastReader(SPEC, SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestForecastReader:
    """Test cases for ForecastReader."""

    def test_get_returns_data(
        self, forecast_reader: ForecastReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns data for valid query."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO forecast
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                600000,
                date(2024, 6, 30),
                date(2024, 4, 20),
                date(2024, 4, 21),
                None,
                "预增",
                1000000.0,
                1200000.0,
            ],
        )
        client.commit()

        # Act
        result = forecast_reader.get(600000, date(2024, 5, 1))

        # Assert
        assert len(result) == 1
        # SQLite TEXT column returns string regardless of insert type
        assert result["instrument_id"][0] == "600000"
        assert result["type"][0] == "预增"
        assert result["profit_range_min"][0] == 1000000.0
        assert result["profit_range_max"][0] == 1200000.0

    def test_get_empty_table(self, forecast_reader: ForecastReader) -> None:
        """Test that get returns empty DataFrame for empty table."""
        # Act
        result = forecast_reader.get(600000, date(2024, 5, 1))

        # Assert
        assert len(result) == 0
        assert isinstance(result, pl.DataFrame)

    def test_get_no_data(
        self, forecast_reader: ForecastReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get returns empty DataFrame for non-existent instrument."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO forecast
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                600001,
                date(2024, 6, 30),
                date(2024, 4, 20),
                date(2024, 4, 21),
                None,
                "预增",
                1000000.0,
                1200000.0,
            ],
        )
        client.commit()

        # Act
        result = forecast_reader.get(600000, date(2024, 5, 1))

        # Assert
        assert len(result) == 0

    def test_get_pit_query(
        self, forecast_reader: ForecastReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query returns correct version based on as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Insert first version (effective 2024-04-21 to 2024-05-01)
        client.execute(
            """INSERT INTO forecast
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                600000,
                date(2024, 6, 30),
                date(2024, 4, 20),
                date(2024, 4, 21),
                date(2024, 5, 1),
                "预增",
                1000000.0,
                1200000.0,
            ],
        )
        # Insert second version (effective from 2024-05-01)
        client.execute(
            """INSERT INTO forecast
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                600000,
                date(2024, 6, 30),
                date(2024, 4, 25),
                date(2024, 5, 1),
                None,
                "预增",
                1100000.0,
                1300000.0,
            ],
        )
        client.commit()

        # Act - Query before second version effective date
        result_old = forecast_reader.get(600000, date(2024, 4, 25))

        # Act - Query after second version effective date
        result_new = forecast_reader.get(600000, date(2024, 5, 5))

        # Assert
        assert len(result_old) == 1
        assert result_old["profit_range_min"][0] == 1000000.0

        assert len(result_new) == 1
        assert result_new["profit_range_min"][0] == 1100000.0

    def test_get_pit_query_excludes_expired_version(
        self, forecast_reader: ForecastReader, in_memory_db: SQLitePool
    ) -> None:
        """Test PIT query excludes version where effective_to == as_of_date."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Version effective from 2024-04-21 to 2024-05-01
        # Note: effective_to = 2024-05-01 means version is NOT valid on 2024-05-01
        client.execute(
            """INSERT INTO forecast
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                600000,
                date(2024, 6, 30),
                date(2024, 4, 20),
                date(2024, 4, 21),
                date(2024, 5, 1),
                "预增",
                1000000.0,
                1200000.0,
            ],
        )
        client.commit()

        # Act - Query on effective_to date (version should be excluded)
        result = forecast_reader.get(600000, date(2024, 5, 1))

        # Assert
        assert len(result) == 0

    def test_get_ordering_by_report_date(
        self, forecast_reader: ForecastReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that results are ordered by report_date DESC."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        # Insert multiple reports
        client.execute(
            """INSERT INTO forecast
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                600000,
                date(2024, 3, 31),
                date(2024, 4, 10),
                date(2024, 4, 11),
                None,
                "预增",
                500000.0,
                600000.0,
            ],
        )
        client.execute(
            """INSERT INTO forecast
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                600000,
                date(2024, 6, 30),
                date(2024, 4, 20),
                date(2024, 4, 21),
                None,
                "预增",
                1000000.0,
                1200000.0,
            ],
        )
        client.commit()

        # Act
        result = forecast_reader.get(600000, date(2024, 5, 1))

        # Assert
        assert len(result) == 2
        # Should be ordered by report_date DESC (2024-06-30 first)
        # Note: SQLite returns dates as strings
        assert result["report_date"][0] == "2024-06-30"
        assert result["report_date"][1] == "2024-03-31"

    def test_get_handles_null_values(
        self, forecast_reader: ForecastReader, in_memory_db: SQLitePool
    ) -> None:
        """Test that get correctly handles NULL profit_range values."""
        # Arrange
        client = SQLiteClient(in_memory_db)
        client.execute(
            """INSERT INTO forecast
            (instrument_id, report_date, knowledge_date,
             effective_from, effective_to, type,
             profit_range_min, profit_range_max)
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)""",
            [
                600000,
                date(2024, 6, 30),
                date(2024, 4, 20),
                date(2024, 4, 21),
                None,
                "预增",
            ],
        )
        client.commit()

        # Act
        result = forecast_reader.get(600000, date(2024, 5, 1))

        # Assert
        assert len(result) == 1
        assert result["profit_range_min"][0] is None
        assert result["profit_range_max"][0] is None
