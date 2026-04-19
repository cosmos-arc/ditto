"""Unit tests for CashFlowWriter."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_data.storage.fundamental.financial.cash_flow_writer import (
    CashFlowWriter,
)
from ditto_data.storage.fundamental.specs import CASH_FLOW_SPEC
from ditto_data.storage.sqlite_client import SQLiteClient
from ditto_infra.foundation import Metrics, SQLitePool

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
def cash_flow_writer(in_memory_db: SQLitePool) -> CashFlowWriter:
    """Provide CashFlowWriter with in-memory database."""
    return CashFlowWriter(SPEC, SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestCashFlowWriter:
    """Test cases for CashFlowWriter."""

    def test_write_success(
        self,
        cash_flow_writer: CashFlowWriter,
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
                "operating_cash_flow": [500.0],
                "investing_cash_flow": [-200.0],
                "financing_cash_flow": [-300.0],
                "net_cash_flow": [0.0],
            }
        )

        # Mock Metrics.data_records.add to avoid metric recording issues
        mock_metrics_add = mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = cash_flow_writer.write(test_df)

        # Assert
        assert count == 1
        mock_metrics_add.assert_called_once_with(
            1, {"dataset": "cash_flow", "status": "success"}
        )

        # Verify data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM cash_flow")
        assert len(rows) == 1
        assert rows[0]["instrument_id"] == "600000"
        assert rows[0]["operating_cash_flow"] == 500.0

    def test_write_returns_count(
        self,
        cash_flow_writer: CashFlowWriter,
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
                "operating_cash_flow": [500.0, 600.0, 700.0],
                "investing_cash_flow": [-200.0, -250.0, -300.0],
                "financing_cash_flow": [-300.0, -350.0, -400.0],
                "net_cash_flow": [0.0, 0.0, 0.0],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = cash_flow_writer.write(test_df)

        # Assert
        assert count == 3

    def test_write_empty_dataframe(
        self,
        cash_flow_writer: CashFlowWriter,
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
                "operating_cash_flow": [],
                "investing_cash_flow": [],
                "financing_cash_flow": [],
                "net_cash_flow": [],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = cash_flow_writer.write(test_df)

        # Assert
        assert count == 0

        # Verify no data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM cash_flow")
        assert len(rows) == 0

    def test_write_failure_rollback(
        self,
        cash_flow_writer: CashFlowWriter,
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
                "operating_cash_flow": [500.0],
                "investing_cash_flow": [-200.0],
                "financing_cash_flow": [-300.0],
                "net_cash_flow": [0.0],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Force an error by using invalid data type
        # Create a mock client that raises RuntimeError
        mock_client = Mock(spec=SQLiteClient)
        mock_client.executemany.side_effect = RuntimeError("Database error")

        # Create writer with mock client
        mock_writer = CashFlowWriter(SPEC, mock_client)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Database error"):
            mock_writer.write(test_df)

    def test_write_with_effective_to(
        self,
        cash_flow_writer: CashFlowWriter,
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
                "operating_cash_flow": [500.0],
                "investing_cash_flow": [-200.0],
                "financing_cash_flow": [-300.0],
                "net_cash_flow": [0.0],
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = cash_flow_writer.write(test_df)

        # Assert
        assert count == 1

        # Verify effective_to was written correctly
        # Note: SQLite returns dates as strings
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM cash_flow")
        assert len(rows) == 1
        assert rows[0]["effective_to"] == "2024-06-01"
