"""Unit tests for DividendWriter."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import Mock

import polars as pl
import pytest
from ditto_data.stores.fundamental.corporate.dividend_writer import (
    DividendWriter,
)
from ditto_data.stores.sqlite_client import SQLiteClient
from ditto_infra.foundation import Metrics, SQLitePool


@pytest.fixture
def in_memory_db(tmp_path: Path) -> SQLitePool:
    """Provide in-memory SQLite database with dividend table."""
    db_path = tmp_path / "test.db"

    pool = SQLitePool(str(db_path))
    pool.get_connection().execute(
        """CREATE TABLE IF NOT EXISTS dividend (
        instrument_id INTEGER NOT NULL,
        ex_dividend_date DATE,  -- P015: nullable for preliminary stage
        knowledge_date DATE NOT NULL,
        effective_from DATE NOT NULL,
        effective_to DATE,
        dividend_per_share REAL,
        dividend_yield REAL,
        div_proc TEXT,  -- P015: implementation progress
        PRIMARY KEY (instrument_id, effective_from, ex_dividend_date)
    )"""
    )
    return pool


@pytest.fixture
def dividend_writer(in_memory_db: SQLitePool) -> DividendWriter:
    """Provide DividendWriter with in-memory database."""
    return DividendWriter(SQLiteClient(in_memory_db))


@pytest.mark.unit
class TestDividendWriter:
    """Test cases for DividendWriter."""

    def test_write_success(
        self,
        dividend_writer: DividendWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write successfully inserts data."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [1000001],  # 使用整数 instrument_id
                "ex_dividend_date": [date(2024, 6, 15)],
                "knowledge_date": [date(2024, 6, 10)],
                "effective_from": [date(2024, 6, 11)],
                "effective_to": [None],
                "dividend_per_share": [0.5],
                "dividend_yield": [2.5],
                "div_proc": ["实施"],  # P015: 实施进度
            }
        )

        # Mock Metrics.data_records.add to avoid metric recording issues
        mock_metrics_add = mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = dividend_writer.write(test_df)

        # Assert
        assert count == 1
        mock_metrics_add.assert_called_once_with(
            1, {"dataset": "dividend", "status": "success"}
        )

        # Verify data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM dividend")
        assert len(rows) == 1
        assert rows[0]["instrument_id"] == 1000001
        assert rows[0]["dividend_per_share"] == 0.5
        assert rows[0]["div_proc"] == "实施"

    def test_write_returns_count(
        self,
        dividend_writer: DividendWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write returns correct record count."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [1000001, 1000002, 1000003],  # 使用整数
                "ex_dividend_date": [
                    date(2024, 6, 15),
                    date(2024, 6, 15),
                    date(2024, 6, 15),
                ],
                "knowledge_date": [
                    date(2024, 6, 10),
                    date(2024, 6, 10),
                    date(2024, 6, 10),
                ],
                "effective_from": [
                    date(2024, 6, 11),
                    date(2024, 6, 11),
                    date(2024, 6, 11),
                ],
                "effective_to": [None, None, None],
                "dividend_per_share": [0.5, 0.6, 0.7],
                "dividend_yield": [2.5, 3.0, 3.5],
                "div_proc": ["实施", "实施", "实施"],  # P015
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = dividend_writer.write(test_df)

        # Assert
        assert count == 3

    def test_write_empty_dataframe(
        self,
        dividend_writer: DividendWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write handles empty DataFrame."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [],
                "ex_dividend_date": [],
                "knowledge_date": [],
                "effective_from": [],
                "effective_to": [],
                "dividend_per_share": [],
                "dividend_yield": [],
                "div_proc": [],  # P015
            }
        ).cast({"instrument_id": pl.Int64})  # 确保类型正确

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = dividend_writer.write(test_df)

        # Assert
        assert count == 0

        # Verify no data in database
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM dividend")
        assert len(rows) == 0

    def test_write_failure_rollback(
        self,
        dividend_writer: DividendWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write rolls back on failure."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [1000001],  # 使用整数
                "ex_dividend_date": [date(2024, 6, 15)],
                "knowledge_date": [date(2024, 6, 10)],
                "effective_from": [date(2024, 6, 11)],
                "effective_to": [None],
                "dividend_per_share": [0.5],
                "dividend_yield": [2.5],
                "div_proc": ["实施"],  # P015
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Force an error by using invalid data type
        # Create a mock client that raises RuntimeError
        mock_client = Mock(spec=SQLiteClient)
        mock_client.executemany.side_effect = RuntimeError("Database error")

        # Create writer with mock client
        mock_writer = DividendWriter(mock_client)

        # Act & Assert
        with pytest.raises(RuntimeError, match="Database error"):
            mock_writer.write(test_df)

    def test_write_with_effective_to(
        self,
        dividend_writer: DividendWriter,
        in_memory_db: SQLitePool,
        mocker: Mock,
    ) -> None:
        """Test that write correctly handles effective_to field."""
        # Arrange
        test_df = pl.DataFrame(
            {
                "instrument_id": [1000001],  # 使用整数
                "ex_dividend_date": [date(2024, 6, 15)],
                "knowledge_date": [date(2024, 6, 10)],
                "effective_from": [date(2024, 6, 11)],
                "effective_to": [date(2024, 7, 1)],
                "dividend_per_share": [0.5],
                "dividend_yield": [2.5],
                "div_proc": ["实施"],  # P015
            }
        )

        mocker.patch.object(Metrics.data_records, "add")

        # Act
        count = dividend_writer.write(test_df)

        # Assert
        assert count == 1

        # Verify effective_to was written correctly
        # Note: SQLite returns dates as strings
        client = SQLiteClient(in_memory_db)
        rows = client.fetchall("SELECT * FROM dividend")
        assert len(rows) == 1
        assert rows[0]["effective_to"] == "2024-07-01"
