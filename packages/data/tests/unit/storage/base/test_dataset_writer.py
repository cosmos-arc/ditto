"""Tests for ParquetDatasetWriter base class."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter
from ditto_platform.foundation.storage.types import OnDuplicate, WriteStoreResult


@pytest.fixture
def mock_store() -> MagicMock:
    store = MagicMock()
    store.data_root = Path("/data")
    return store


@pytest.fixture
def writer(mock_store: MagicMock) -> ParquetDatasetWriter:
    return ParquetDatasetWriter(mock_store, "market/stock/bars")


class TestParquetDatasetWriterInit:
    def test_init_stores_dataset(self, writer: ParquetDatasetWriter) -> None:
        assert writer._dataset == "market/stock/bars"

    def test_init_stores_store(
        self, writer: ParquetDatasetWriter, mock_store: MagicMock
    ) -> None:
        assert writer._store is mock_store

    def test_data_root_delegates_to_store(self, writer: ParquetDatasetWriter) -> None:
        assert writer.data_root == Path("/data")


class TestParquetDatasetWriterWrite:
    def test_write_delegates_to_store(
        self, writer: ParquetDatasetWriter, mock_store: MagicMock
    ) -> None:
        df = pl.DataFrame({"instrument_id": [1], "trade_date": ["2024-01-01"]})
        expected = WriteStoreResult(
            file_path="/data/market/stock/bars/2024.parquet",
            checksum="abc",
            added=1,
            updated=0,
            skipped=0,
            is_merge=False,
        )
        mock_store.write.return_value = expected

        result = writer.write(df, year=2024, on_duplicate=OnDuplicate.ERROR)

        mock_store.write.assert_called_once_with(
            "market/stock/bars", df, OnDuplicate.ERROR.value, year=2024
        )
        assert result is expected

    def test_write_default_on_duplicate(
        self, writer: ParquetDatasetWriter, mock_store: MagicMock
    ) -> None:
        df = pl.DataFrame()
        mock_store.write.return_value = WriteStoreResult("", "", 0, 0, 0, False)

        writer.write(df, year=2024)

        mock_store.write.assert_called_once_with(
            "market/stock/bars", df, OnDuplicate.ERROR.value, year=2024
        )


class TestParquetDatasetWriterDelete:
    def test_delete_delegates_to_store(
        self, writer: ParquetDatasetWriter, mock_store: MagicMock
    ) -> None:
        mock_store.delete.return_value = 5

        result = writer.delete(instrument_ids=[1], start_date="2024-01-01")

        mock_store.delete.assert_called_once()
        args, kwargs = mock_store.delete.call_args
        assert args == ("market/stock/bars",)
        assert kwargs["start_date"] == "2024-01-01"
        assert kwargs["end_date"] is None
        assert len(kwargs["filters"]) == 1
        assert result == 5

    def test_delete_partition_delegates(
        self, writer: ParquetDatasetWriter, mock_store: MagicMock
    ) -> None:
        mock_store.delete_partition.return_value = True

        result = writer.delete_partition("2024")

        mock_store.delete_partition.assert_called_once_with("market/stock/bars", "2024")
        assert result is True


class TestParquetDatasetWriterProtocol:
    def test_satisfies_dataset_writer_protocol(
        self, writer: ParquetDatasetWriter
    ) -> None:
        from ditto_platform.foundation.storage.protocols import DatasetWriter

        _: DatasetWriter = writer
