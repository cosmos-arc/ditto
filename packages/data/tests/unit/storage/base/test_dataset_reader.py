"""Tests for ParquetDatasetReader base class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.storage.base.dataset_reader import ParquetDatasetReader


@pytest.fixture
def mock_store() -> MagicMock:
    store = MagicMock()
    store.data_root = Path("/data")
    return store


@pytest.fixture
def reader(mock_store: MagicMock) -> ParquetDatasetReader:
    return ParquetDatasetReader(mock_store, "market/stock/bars")


class TestParquetDatasetReaderInit:
    def test_init_stores_dataset(self, reader: ParquetDatasetReader) -> None:
        assert reader._dataset == "market/stock/bars"

    def test_init_stores_store(
        self, reader: ParquetDatasetReader, mock_store: MagicMock
    ) -> None:
        assert reader._store is mock_store

    def test_data_root_delegates_to_store(self, reader: ParquetDatasetReader) -> None:
        assert reader.data_root == Path("/data")


class TestParquetDatasetReaderRead:
    def test_read_delegates_to_store(
        self, reader: ParquetDatasetReader, mock_store: MagicMock
    ) -> None:
        expected = pl.DataFrame({"instrument_id": [1], "trade_date": ["2024-01-01"]})
        mock_store.read.return_value = expected

        result = reader.read(
            instrument_ids=[1], start_date="2024-01-01", end_date="2024-12-31"
        )

        mock_store.read.assert_called_once()
        args, kwargs = mock_store.read.call_args
        assert args == ("market/stock/bars",)
        assert kwargs["start_date"] == "2024-01-01"
        assert kwargs["end_date"] == "2024-12-31"
        assert len(kwargs["filters"]) == 1
        assert result.equals(expected)

    def test_read_with_no_filters(
        self, reader: ParquetDatasetReader, mock_store: MagicMock
    ) -> None:
        mock_store.read.return_value = pl.DataFrame()

        reader.read()

        mock_store.read.assert_called_once_with(
            "market/stock/bars",
            start_date=None,
            end_date=None,
            filters=[],
        )


class TestParquetDatasetReaderCount:
    def test_count_delegates_to_store(
        self, reader: ParquetDatasetReader, mock_store: MagicMock
    ) -> None:
        mock_store.count.return_value = 42

        result = reader.count(instrument_ids=[1])

        mock_store.count.assert_called_once()
        args, kwargs = mock_store.count.call_args
        assert args == ("market/stock/bars",)
        assert kwargs["start_date"] is None
        assert kwargs["end_date"] is None
        assert len(kwargs["filters"]) == 1
        assert result == 42


class TestParquetDatasetReaderMetadata:
    def test_get_years_delegates(
        self, reader: ParquetDatasetReader, mock_store: MagicMock
    ) -> None:
        mock_store.get_years.return_value = [2022, 2023, 2024]

        result = reader.get_years()

        mock_store.get_years.assert_called_once_with("market/stock/bars")
        assert result == [2022, 2023, 2024]

    def test_get_date_range_delegates(
        self, reader: ParquetDatasetReader, mock_store: MagicMock
    ) -> None:
        mock_store.get_date_range.return_value = ("2022-01-01", "2024-12-31")

        result = reader.get_date_range()

        mock_store.get_date_range.assert_called_once_with("market/stock/bars")
        assert result == ("2022-01-01", "2024-12-31")

    def test_get_checksum_delegates(
        self, reader: ParquetDatasetReader, mock_store: MagicMock
    ) -> None:
        mock_store.get_checksum.return_value = "abc123"

        result = reader.get_checksum("2024")

        mock_store.get_checksum.assert_called_once_with("market/stock/bars", "2024")
        assert result == "abc123"

    def test_list_instrument_ids_delegates(
        self, reader: ParquetDatasetReader, mock_store: MagicMock
    ) -> None:
        mock_store.list_unique_values.return_value = [1, 2, 3]

        result = reader.list_instrument_ids()

        mock_store.list_unique_values.assert_called_once_with(
            "market/stock/bars",
            "instrument_id",
        )
        assert result == [1, 2, 3]


class TestParquetDatasetReaderProtocol:
    def test_satisfies_dataset_reader_protocol(
        self, reader: ParquetDatasetReader
    ) -> None:
        from ditto_platform.foundation.storage.protocols import DatasetReader

        _: DatasetReader = reader
