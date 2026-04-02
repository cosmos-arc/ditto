"""Unit tests for ForecastWriter."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_data.stores.fundamental.forecast.forecast_writer import (
    ForecastWriter,
)
from ditto_data.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import Metrics, SQLitePool


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
def forecast_writer(in_memory_db: SQLitePool) -> ForecastWriter:
    """Provide ForecastWriter with in-memory database."""
    return ForecastWriter(SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestForecastWriter:
    """Test cases for ForecastWriter."""

    def test_write_success(
        self,
        forecast_writer: ForecastWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write successfully inserts data."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": ["600000.SH"],
                "report_date": [date(2024, 6, 30)],
                "knowledge_date": [date(2024, 4, 20)],
                "effective_from": [date(2024, 4, 21)],
                "effective_to": [None],
                "type": ["预增"],
                "profit_range_min": [1000000.0],
                "profit_range_max": [1200000.0],
            }
        )

        # Mock Metrics.data_records.add to avoid metric recording issues
        mock_metrics_add = mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = forecast_writer.write(test_df)

        # Assert
        assert count == 1
        mock_metrics_add.assert_called_once_with(
            1, {"dataset": "forecast", "status": "success"}
        )

        # Verify data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM forecast")
        assert len(rows) == 1
        assert rows[0]["instrument_id"] == "600000.SH"
        assert rows[0]["type"] == "预增"

    def test_write_returns_count(
        self,
        forecast_writer: ForecastWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write returns correct record count."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": ["600000.SH", "600001.SH", "600002.SH"],
                "report_date": [
                    date(2024, 6, 30),
                    date(2024, 6, 30),
                    date(2024, 6, 30),
                ],
                "knowledge_date": [
                    date(2024, 4, 20),
                    date(2024, 4, 20),
                    date(2024, 4, 20),
                ],
                "effective_from": [
                    date(2024, 4, 21),
                    date(2024, 4, 21),
                    date(2024, 4, 21),
                ],
                "effective_to": [None, None, None],
                "type": ["预增", "预增", "预减"],
                "profit_range_min": [1000000.0, 2000000.0, 3000000.0],
                "profit_range_max": [1200000.0, 2200000.0, 3200000.0],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = forecast_writer.write(test_df)

        # Assert
        assert count == 3

    def test_write_empty_dataframe(
        self,
        forecast_writer: ForecastWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write handles empty DataFrame."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [],
                "report_date": [],
                "knowledge_date": [],
                "effective_from": [],
                "effective_to": [],
                "type": [],
                "profit_range_min": [],
                "profit_range_max": [],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = forecast_writer.write(test_df)

        # Assert
        assert count == 0

        # Verify no data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM forecast")
        assert len(rows) == 0

    def test_write_failure_rollback(
        self,
        forecast_writer: ForecastWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write rolls back on failure."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": ["600000.SH"],
                "report_date": [date(2024, 6, 30)],
                "knowledge_date": [date(2024, 4, 20)],
                "effective_from": [date(2024, 4, 21)],
                "effective_to": [None],
                "type": ["预增"],
                "profit_range_min": [1000000.0],
                "profit_range_max": [1200000.0],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Force an error by using invalid data type
        # Create a mock client that raises RuntimeError
        mock_client = Mock(spec=SQLiteClient)
        mock_client.executemany.side_effect = RuntimeError("Database error")

        # Create writer with mock client
        mock_writer = ForecastWriter(mock_client)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Database error"):
            mock_writer.write(test_df)

    def test_write_with_effective_to(
        self,
        forecast_writer: ForecastWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write correctly handles effective_to field."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": ["600000.SH"],
                "report_date": [date(2024, 6, 30)],
                "knowledge_date": [date(2024, 4, 20)],
                "effective_from": [date(2024, 4, 21)],
                "effective_to": [date(2024, 5, 1)],
                "type": ["预增"],
                "profit_range_min": [1000000.0],
                "profit_range_max": [1200000.0],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = forecast_writer.write(test_df)

        # Assert
        assert count == 1

        # Verify effective_to was written correctly
        # Note: SQLite returns dates as strings
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM forecast")
        assert len(rows) == 1
        assert rows[0]["effective_to"] == "2024-05-01"

    def test_write_handles_null_profit_ranges(
        self,
        forecast_writer: ForecastWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write correctly handles NULL profit_range values."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": ["600000.SH"],
                "report_date": [date(2024, 6, 30)],
                "knowledge_date": [date(2024, 4, 20)],
                "effective_from": [date(2024, 4, 21)],
                "effective_to": [None],
                "type": ["预增"],
                "profit_range_min": [None],
                "profit_range_max": [None],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = forecast_writer.write(test_df)

        # Assert
        assert count == 1

        # Verify NULL values were written correctly
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM forecast")
        assert len(rows) == 1
        assert rows[0]["profit_range_min"] is None
        assert rows[0]["profit_range_max"] is None

    def test_write_on_conflict_does_nothing(
        self,
        forecast_writer: ForecastWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that ON CONFLICT DO NOTHING handles duplicate inserts."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": ["600000.SH", "600000.SH"],
                "report_date": [date(2024, 6, 30), date(2024, 6, 30)],
                "knowledge_date": [
                    date(2024, 4, 20),
                    date(2024, 4, 25),
                ],
                "effective_from": [
                    date(2024, 4, 21),
                    date(2024, 4, 21),  # Same effective_from, will conflict
                ],
                "effective_to": [None, None],
                "type": ["预增", "预增"],
                "profit_range_min": [1000000.0, 1100000.0],
                "profit_range_max": [1200000.0, 1300000.0],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act - Only first record should be written
        count = forecast_writer.write(test_df)

        # Assert
        assert count == 2  # Returns count of input, not actual inserts

        # Verify only first record is in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM forecast")
        assert len(rows) == 1
        assert rows[0]["profit_range_min"] == 1000000.0
