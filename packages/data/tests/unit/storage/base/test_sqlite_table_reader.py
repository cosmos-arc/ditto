"""Tests for SqliteTableSpec and SqliteTableReader."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from unittest.mock import MagicMock

import pytest
from ditto_data.storage.base.sqlite_table_reader import SqliteTableReader
from ditto_data.storage.base.sqlite_table_spec import SqliteTableSpec


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
def valuation_spec() -> SqliteTableSpec:
    return SqliteTableSpec(
        table="valuation_metrics",
        columns=("pe_ratio", "pb_ratio", "ps_ratio", "dividend_yield", "market_cap"),
        id_column="instrument_id",
        date_column="trade_date",
    )


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


class TestSqliteTableSpec:
    def test_frozen(self, balance_sheet_spec: SqliteTableSpec) -> None:
        with pytest.raises(FrozenInstanceError):
            balance_sheet_spec.table = "other"  # type: ignore[misc]

    def test_default_pit_columns(self, balance_sheet_spec: SqliteTableSpec) -> None:
        assert balance_sheet_spec.pit_columns == (
            "knowledge_date",
            "effective_from",
            "effective_to",
        )

    def test_custom_pit_columns(self) -> None:
        spec = SqliteTableSpec(
            table="test",
            columns=("a",),
            id_column="id",
            date_column="date",
            pit_columns=("effective_from", "effective_to"),
        )
        assert spec.pit_columns == ("effective_from", "effective_to")

    def test_nullable_columns_default(
        self, balance_sheet_spec: SqliteTableSpec
    ) -> None:
        assert balance_sheet_spec.nullable_columns == frozenset()

    def test_nullable_columns_custom(self) -> None:
        spec = SqliteTableSpec(
            table="test",
            columns=("a", "b"),
            id_column="id",
            date_column="date",
            nullable_columns=frozenset({"b"}),
        )
        assert spec.nullable_columns == frozenset({"b"})

    def test_all_columns_includes_id_date_and_pit(
        self, balance_sheet_spec: SqliteTableSpec
    ) -> None:
        all_cols = balance_sheet_spec.all_columns
        assert "instrument_id" in all_cols
        assert "report_date" in all_cols
        assert "knowledge_date" in all_cols
        assert "effective_from" in all_cols
        assert "effective_to" in all_cols
        assert "total_assets" in all_cols

    def test_optional_date_column(self) -> None:
        spec = SqliteTableSpec(
            table="index_composition",
            columns=("instrument_id", "weight"),
            id_column="index_id",
            date_column=None,
            pit_columns=("effective_from", "effective_to"),
        )
        assert spec.date_column is None
        assert "index_id" in spec.all_columns
        assert "weight" in spec.all_columns

    def test_order_by_column(self) -> None:
        spec = SqliteTableSpec(
            table="index_composition",
            columns=("instrument_id", "weight"),
            id_column="index_id",
            order_by_column="instrument_id",
            pit_columns=("effective_from", "effective_to"),
        )
        assert spec.order_by_column == "instrument_id"

    def test_order_by_column_defaults_to_date_column(self) -> None:
        spec = SqliteTableSpec(
            table="test",
            columns=("a",),
            id_column="id",
            date_column="report_date",
        )
        assert spec.order_by_column is None


class TestSqliteTableReader:
    def test_get_delegates_with_report_date(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = [
            {
                "instrument_id": 1,
                "report_date": "2024-03-31",
                "knowledge_date": "2024-04-25",
                "effective_from": "2024-04-25",
                "effective_to": None,
                "total_assets": 1000,
                "total_liabilities": 500,
                "net_assets": 500,
                "current_assets": 200,
                "current_liabilities": 100,
            }
        ]

        result = reader.get(1, date(2024, 6, 1))

        assert len(result) == 1
        mock_client.fetchall.assert_called_once()
        sql = mock_client.fetchall.call_args[0][0]
        params = mock_client.fetchall.call_args[0][1]

        assert "balance_sheet" in sql
        assert "effective_from <= ?" in sql
        assert "effective_to IS NULL OR effective_to > ?" in sql
        assert "report_date DESC" in sql
        assert "total_assets" in sql
        assert "knowledge_date" in sql
        assert params == [1, date(2024, 6, 1), date(2024, 6, 1)]

    def test_get_delegates_with_trade_date(
        self, valuation_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(valuation_spec, mock_client)
        mock_client.fetchall.return_value = []

        reader.get(1, date(2024, 6, 1))

        sql = mock_client.fetchall.call_args[0][0]
        assert "trade_date DESC" in sql
        assert "pe_ratio" in sql

    def test_get_returns_empty_dataframe_when_no_rows(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = []

        result = reader.get(1, date(2024, 6, 1))

        assert result.is_empty()

    def test_get_returns_dataframe_with_rows(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = [
            {
                "instrument_id": 1,
                "report_date": "2024-03-31",
                "knowledge_date": "2024-04-25",
                "effective_from": "2024-04-25",
                "effective_to": None,
                "total_assets": 1000,
                "total_liabilities": 500,
                "net_assets": 500,
                "current_assets": 200,
                "current_liabilities": 100,
            }
        ]

        result = reader.get(1, date(2024, 6, 1))

        assert not result.is_empty()
        assert result["instrument_id"][0] == 1
        assert result["total_assets"][0] == 1000

    def test_satisfies_sqlite_reader_protocol(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        from ditto_data.storage.base.protocols import SqliteReader

        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        _: SqliteReader = reader

    def test_get_range_with_date_range_only(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = [
            {
                "instrument_id": 1,
                "report_date": "2024-03-31",
                "knowledge_date": "2024-04-25",
                "effective_from": "2024-04-25",
                "effective_to": None,
                "total_assets": 1000,
                "total_liabilities": 500,
                "net_assets": 500,
                "current_assets": 200,
                "current_liabilities": 100,
            }
        ]

        result = reader.get_range(
            1, start_date=date(2024, 1, 1), end_date=date(2024, 6, 30)
        )

        assert len(result) == 1
        sql = mock_client.fetchall.call_args[0][0]
        params = mock_client.fetchall.call_args[0][1]

        assert "report_date >= ?" in sql
        assert "report_date <= ?" in sql
        assert "effective_from <= ?" not in sql
        assert params[0] == 1
        assert params[1] == date(2024, 1, 1)
        assert params[2] == date(2024, 6, 30)

    def test_get_range_with_pit_only(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = []

        reader.get_range(1, as_of_date=date(2024, 6, 1))

        sql = mock_client.fetchall.call_args[0][0]
        params = mock_client.fetchall.call_args[0][1]

        assert "effective_from <= ?" in sql
        assert "effective_to IS NULL OR effective_to > ?" in sql
        assert "report_date >=" not in sql
        assert "report_date <=" not in sql
        assert params == [1, date(2024, 6, 1), date(2024, 6, 1)]

    def test_get_range_with_all_params(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = []

        reader.get_range(
            1,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 6, 30),
            as_of_date=date(2024, 6, 1),
        )

        sql = mock_client.fetchall.call_args[0][0]
        params = mock_client.fetchall.call_args[0][1]

        assert "report_date >= ?" in sql
        assert "report_date <= ?" in sql
        assert "effective_from <= ?" in sql
        assert "effective_to IS NULL OR effective_to > ?" in sql
        assert len(params) == 5

    def test_get_range_with_no_filters(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = []

        reader.get_range(1)

        sql = mock_client.fetchall.call_args[0][0]
        params = mock_client.fetchall.call_args[0][1]

        assert "effective_from <= ?" not in sql
        assert "report_date >=" not in sql
        assert params == [1]

    def test_get_range_returns_empty_when_no_rows(
        self, balance_sheet_spec: SqliteTableSpec, mock_client: MagicMock
    ) -> None:
        reader = SqliteTableReader(balance_sheet_spec, mock_client)
        mock_client.fetchall.return_value = []

        result = reader.get_range(1, start_date=date(2024, 1, 1))

        assert result.is_empty()

    def test_order_by_uses_spec_column(self, mock_client: MagicMock) -> None:
        spec = SqliteTableSpec(
            table="index_composition",
            columns=("instrument_id", "weight"),
            id_column="index_id",
            order_by_column="instrument_id",
            pit_columns=("effective_from", "effective_to"),
        )
        reader = SqliteTableReader(spec, mock_client)
        mock_client.fetchall.return_value = []

        reader.get(1, date(2024, 6, 1))

        sql = mock_client.fetchall.call_args[0][0]
        assert "ORDER BY instrument_id DESC" in sql

    def test_get_with_str_id_value(self, mock_client: MagicMock) -> None:
        spec = SqliteTableSpec(
            table="index_composition",
            columns=("instrument_id", "weight"),
            id_column="index_id",
            order_by_column="instrument_id",
            pit_columns=("effective_from", "effective_to"),
        )
        reader = SqliteTableReader(spec, mock_client)
        mock_client.fetchall.return_value = [
            {
                "index_id": "000300",
                "instrument_id": 1,
                "weight": 0.05,
                "effective_from": "2024-01-01",
                "effective_to": None,
            }
        ]

        result = reader.get("000300", date(2024, 6, 1))

        assert len(result) == 1
        params = mock_client.fetchall.call_args[0][1]
        assert params[0] == "000300"
