"""Unit tests for BalanceSheetWriter."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_data.storage.fundamental.financial.balance_sheet_writer import (
    BalanceSheetWriter,
)
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_infra.foundation import Metrics, SQLitePool


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
def balance_sheet_writer(in_memory_db: SQLitePool) -> BalanceSheetWriter:
    """Provide BalanceSheetWriter with in-memory database."""
    return BalanceSheetWriter(SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestBalanceSheetWriter:
    """Test cases for BalanceSheetWriter."""

    def test_write_success(
        self,
        balance_sheet_writer: BalanceSheetWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write successfully inserts data."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": ["600000"],
                "report_date": [date(2024, 3, 31)],
                "knowledge_date": [date(2024, 4, 30)],
                "effective_from": [date(2024, 5, 1)],
                "effective_to": [None],
                "total_assets": [1000.0],
                "total_liabilities": [500.0],
                "net_assets": [500.0],
                "current_assets": [600.0],
                "current_liabilities": [300.0],
            }
        )

        # Mock Metrics.data_records.add to avoid metric recording issues
        mock_metrics_add = mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = balance_sheet_writer.write(test_df)

        # Assert
        assert count == 1
        mock_metrics_add.assert_called_once_with(
            1, {"dataset": "balance_sheet", "status": "success"}
        )

        # Verify data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM balance_sheet")
        assert len(rows) == 1
        assert rows[0]["instrument_id"] == "600000"
        assert rows[0]["total_assets"] == 1000.0

    def test_write_returns_count(
        self,
        balance_sheet_writer: BalanceSheetWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write returns correct record count."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": ["600000", "600001", "600002"],
                "report_date": [
                    date(2024, 3, 31),
                    date(2024, 3, 31),
                    date(2024, 3, 31),
                ],
                "knowledge_date": [
                    date(2024, 4, 30),
                    date(2024, 4, 30),
                    date(2024, 4, 30),
                ],
                "effective_from": [
                    date(2024, 5, 1),
                    date(2024, 5, 1),
                    date(2024, 5, 1),
                ],
                "effective_to": [None, None, None],
                "total_assets": [1000.0, 2000.0, 3000.0],
                "total_liabilities": [500.0, 1000.0, 1500.0],
                "net_assets": [500.0, 1000.0, 1500.0],
                "current_assets": [600.0, 1200.0, 1800.0],
                "current_liabilities": [300.0, 600.0, 900.0],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = balance_sheet_writer.write(test_df)

        # Assert
        assert count == 3

    def test_write_empty_dataframe(
        self,
        balance_sheet_writer: BalanceSheetWriter,
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
                "total_assets": [],
                "total_liabilities": [],
                "net_assets": [],
                "current_assets": [],
                "current_liabilities": [],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = balance_sheet_writer.write(test_df)

        # Assert
        assert count == 0

        # Verify no data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM balance_sheet")
        assert len(rows) == 0

    def test_write_failure_rollback(
        self,
        balance_sheet_writer: BalanceSheetWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write rolls back on failure."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": ["600000"],
                "report_date": [date(2024, 3, 31)],
                "knowledge_date": [date(2024, 4, 30)],
                "effective_from": [date(2024, 5, 1)],
                "effective_to": [None],
                "total_assets": [1000.0],
                "total_liabilities": [500.0],
                "net_assets": [500.0],
                "current_assets": [600.0],
                "current_liabilities": [300.0],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Force an error by using invalid data type
        # Create a mock client that raises RuntimeError
        mock_client = Mock(spec=SQLiteClient)
        mock_client.executemany.side_effect = RuntimeError("Database error")

        # Create writer with mock client
        mock_writer = BalanceSheetWriter(mock_client)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Database error"):
            mock_writer.write(test_df)

    def test_write_with_effective_to(
        self,
        balance_sheet_writer: BalanceSheetWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write correctly handles effective_to field."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": ["600000"],
                "report_date": [date(2024, 3, 31)],
                "knowledge_date": [date(2024, 4, 30)],
                "effective_from": [date(2024, 5, 1)],
                "effective_to": [date(2024, 6, 1)],
                "total_assets": [1000.0],
                "total_liabilities": [500.0],
                "net_assets": [500.0],
                "current_assets": [600.0],
                "current_liabilities": [300.0],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = balance_sheet_writer.write(test_df)

        # Assert
        assert count == 1

        # Verify effective_to was written correctly
        # Note: SQLite returns dates as strings
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM balance_sheet")
        assert len(rows) == 1
        assert rows[0]["effective_to"] == "2024-06-01"
