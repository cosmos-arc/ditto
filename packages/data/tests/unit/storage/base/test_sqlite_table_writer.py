"""Tests for SqliteTableWriter."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec
from ditto_data.storage.base.sqlite_table_writer import SqliteTableWriter


@pytest.fixture
def balance_sheet_spec() -> SqliteTableSpec:
    return SqliteTableSpec(
        table="balance_sheet",
        columns=(
            "total_assets",
            "total_liabilities",
            "net_assets",
            "current_assets",
            "current_liabilities",
        ),
        id_column="instrument_id",
        date_column="report_date",
    )


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


class TestSqliteTableWriterWrite:
    def test_write_generates_correct_sql(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        writer = SqliteTableWriter(balance_sheet_spec, mock_client)
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "report_date": [date(2024, 3, 31)],
                "knowledge_date": [date(2024, 4, 25)],
                "effective_from": [date(2024, 4, 25)],
                "effective_to": [None],
                "total_assets": [1000],
                "total_liabilities": [500],
                "net_assets": [500],
                "current_assets": [200],
                "current_liabilities": [100],
            }
        )

        result = writer.write(df)

        assert result == 1
        mock_client.executemany.assert_called_once()
        mock_client.commit.assert_called_once()

        sql = mock_client.executemany.call_args[0][0]
        params_list = mock_client.executemany.call_args[0][1]

        assert "INSERT INTO balance_sheet" in sql
        assert "instrument_id" in sql
        assert "report_date" in sql
        assert "knowledge_date" in sql
        assert "effective_from" in sql
        assert "effective_to" in sql
        assert "total_assets" in sql
        assert "ON CONFLICT DO NOTHING" in sql

        assert len(params_list) == 1
        row = params_list[0]
        assert row[0] == 1  # instrument_id
        assert row[4] is None  # effective_to (nullable)

    def test_write_commits_and_returns_count(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        writer = SqliteTableWriter(balance_sheet_spec, mock_client)
        df = pl.DataFrame(
            {
                "instrument_id": [1, 2],
                "report_date": [date(2024, 3, 31), date(2024, 6, 30)],
                "knowledge_date": [date(2024, 4, 25), date(2024, 7, 20)],
                "effective_from": [date(2024, 4, 25), date(2024, 7, 20)],
                "effective_to": [None, None],
                "total_assets": [1000, 2000],
                "total_liabilities": [500, 1000],
                "net_assets": [500, 1000],
                "current_assets": [200, 400],
                "current_liabilities": [100, 200],
            }
        )

        result = writer.write(df)

        assert result == 2
        mock_client.commit.assert_called_once()

    def test_write_rollbacks_on_error(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        writer = SqliteTableWriter(balance_sheet_spec, mock_client)
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "report_date": [date(2024, 3, 31)],
                "knowledge_date": [date(2024, 4, 25)],
                "effective_from": [date(2024, 4, 25)],
                "effective_to": [None],
                "total_assets": [1000],
                "total_liabilities": [500],
                "net_assets": [500],
                "current_assets": [200],
                "current_liabilities": [100],
            }
        )
        mock_client.executemany.side_effect = RuntimeError("DB error")

        with pytest.raises(RuntimeError, match="DB error"):
            writer.write(df)

        mock_client.rollback.assert_called_once()
        mock_client.commit.assert_not_called()

    def test_write_with_trade_date_spec(self, mock_client: MagicMock) -> None:
        spec = SqliteTableSpec(
            table="valuation_metrics",
            columns=("pe_ratio", "pb_ratio"),
            id_column="instrument_id",
            date_column="trade_date",
        )
        writer = SqliteTableWriter(spec, mock_client)
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [date(2024, 1, 15)],
                "knowledge_date": [date(2024, 1, 16)],
                "effective_from": [date(2024, 1, 16)],
                "effective_to": [None],
                "pe_ratio": [15.5],
                "pb_ratio": [2.1],
            }
        )

        writer.write(df)

        sql = mock_client.executemany.call_args[0][0]
        assert "INSERT INTO valuation_metrics" in sql
        assert "trade_date" in sql

    def test_satisfies_sqlite_writer_protocol(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        from ditto_platform.foundation import SqliteWriter

        writer = SqliteTableWriter(balance_sheet_spec, mock_client)
        _: SqliteWriter = writer
