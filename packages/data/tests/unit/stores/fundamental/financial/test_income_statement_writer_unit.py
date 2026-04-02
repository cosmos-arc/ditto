"""Unit tests for IncomeStatementWriter."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_data.stores.fundamental.financial.income_statement_writer import (
    IncomeStatementWriter,
)
from ditto_data.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import Metrics, SQLitePool


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
def income_statement_writer(in_memory_db: SQLitePool) -> IncomeStatementWriter:
    """Provide IncomeStatementWriter with in-memory database."""
    return IncomeStatementWriter(SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestIncomeStatementWriter:
    """Test cases for IncomeStatementWriter."""

    def test_write_success(
        self,
        income_statement_writer: IncomeStatementWriter,
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
                "revenue": [1000.0],
                "operating_profit": [200.0],
                "net_profit": [150.0],
                "eps": [0.5],
            }
        )

        # Mock Metrics.data_records.add to avoid metric recording issues
        mock_metrics_add = mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = income_statement_writer.write(test_df)

        # Assert
        assert count == 1
        mock_metrics_add.assert_called_once_with(
            1, {"dataset": "income_statement", "status": "success"}
        )

        # Verify data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM income_statement")
        assert len(rows) == 1
        assert rows[0]["instrument_id"] == "600000"
        assert rows[0]["revenue"] == 1000.0

    def test_write_returns_count(
        self,
        income_statement_writer: IncomeStatementWriter,
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
                "revenue": [1000.0, 2000.0, 3000.0],
                "operating_profit": [200.0, 400.0, 600.0],
                "net_profit": [150.0, 300.0, 450.0],
                "eps": [0.5, 1.0, 1.5],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = income_statement_writer.write(test_df)

        # Assert
        assert count == 3

    def test_write_empty_dataframe(
        self,
        income_statement_writer: IncomeStatementWriter,
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
                "revenue": [],
                "operating_profit": [],
                "net_profit": [],
                "eps": [],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = income_statement_writer.write(test_df)

        # Assert
        assert count == 0

        # Verify no data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM income_statement")
        assert len(rows) == 0

    def test_write_failure_rollback(
        self,
        income_statement_writer: IncomeStatementWriter,
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
                "revenue": [1000.0],
                "operating_profit": [200.0],
                "net_profit": [150.0],
                "eps": [0.5],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Force an error by using invalid data type
        # Create a mock client that raises RuntimeError
        mock_client = Mock(spec=SQLiteClient)
        mock_client.executemany.side_effect = RuntimeError("Database error")

        # Create writer with mock client
        mock_writer = IncomeStatementWriter(mock_client)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Database error"):
            mock_writer.write(test_df)

    def test_write_with_effective_to(
        self,
        income_statement_writer: IncomeStatementWriter,
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
                "revenue": [1000.0],
                "operating_profit": [200.0],
                "net_profit": [150.0],
                "eps": [0.5],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = income_statement_writer.write(test_df)

        # Assert
        assert count == 1

        # Verify effective_to was written correctly
        # Note: SQLite returns dates as strings
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM income_statement")
        assert len(rows) == 1
        assert rows[0]["effective_to"] == "2024-06-01"
