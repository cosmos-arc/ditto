"""Tests for ParquetDatasetWriter base class."""

from __future__ import annotations

import threading
from contextlib import AbstractContextManager
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from ditto_data.storage.base.dataset_writer import ParquetDatasetWriter
from ditto_platform.foundation import (
    FileLockManager,
    OnDuplicate,
    ParquetStore,
    WriteStoreResult,
)


@pytest.fixture
def mock_store() -> MagicMock:
    store = MagicMock()
    store.data_root = Path("/data")
    store.date_column = None
    store.file_lock = None
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
        assert result == expected

    def test_write_default_on_duplicate(
        self, writer: ParquetDatasetWriter, mock_store: MagicMock
    ) -> None:
        df = pl.DataFrame()
        mock_store.write.return_value = WriteStoreResult("", "", 0, 0, 0, False)

        writer.write(df, year=2024)

        mock_store.write.assert_called_once_with(
            "market/stock/bars", df, OnDuplicate.ERROR.value, year=2024
        )


class TestParquetDatasetWriterYearSharding:
    """审计 #684 批B #14：跨年分片上移 writer 层，全体 parquet saver 受益."""

    @staticmethod
    def _bars_store(tmp_path: Path) -> ParquetStore:
        return ParquetStore(
            tmp_path,
            key_columns=("instrument_id", "trade_date"),
            date_column="trade_date",
        )

    def test_cross_year_frame_lands_in_own_year_partitions(
        self, tmp_path: Path
    ) -> None:
        """回看窗口跨年：行按 trade_date 年分片落各自分区（#629 E1 语义上移）."""
        store = self._bars_store(tmp_path)
        writer = ParquetDatasetWriter(store, "market/etf/nav")
        df = pl.DataFrame(
            {
                "instrument_id": [4_000_001, 4_000_001],
                "trade_date": [date(2026, 12, 30), date(2027, 1, 3)],
                "close": [7.185, 7.195],
            }
        )

        result = writer.write(df, year=2027, on_duplicate=OnDuplicate.KEEP_FIRST)

        assert (result.added, result.updated) == (2, 0)
        assert (tmp_path / "market/etf/nav/2026.parquet").exists()
        assert (tmp_path / "market/etf/nav/2027.parquet").exists()
        stored = store.read("market/etf/nav")
        assert stored["trade_date"].cast(pl.Date).dt.year().sort().to_list() == [
            2026,
            2027,
        ]

    def test_disclosure_frame_shards_by_report_year(self, tmp_path: Path) -> None:
        """披露锚帧：报告期跨年行落报告期年分区（#627 F1/#3 语义上移）."""
        store = ParquetStore(
            tmp_path,
            key_columns=("instrument_id", "report_date", "knowledge_date"),
            date_column="report_date",
        )
        writer = ParquetDatasetWriter(store, "capital/top10/holders")
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "report_date": [date(2025, 12, 31), date(2026, 3, 31)],
                "knowledge_date": [date(2026, 4, 30), date(2026, 4, 30)],
                "holder_name": ["a", "b"],
            }
        )

        written = writer.write(df, year=2026, on_duplicate=OnDuplicate.KEEP_FIRST)

        assert written.added == 2
        assert (tmp_path / "capital/top10/holders/2025.parquet").exists()
        assert (tmp_path / "capital/top10/holders/2026.parquet").exists()

    def test_null_partition_anchor_fails_closed(self, tmp_path: Path) -> None:
        store = self._bars_store(tmp_path)
        writer = ParquetDatasetWriter(store, "market/stock/bars")
        df = pl.DataFrame(
            {
                "instrument_id": [1],
                "trade_date": [None],
                "close": [1.0],
            },
            schema={
                "instrument_id": pl.Int64,
                "trade_date": pl.Date,
                "close": pl.Float64,
            },
        )

        with pytest.raises(ValueError, match="null"):
            writer.write(df, year=2026)

    def test_declared_date_column_missing_from_frame_fails_closed(
        self, tmp_path: Path
    ) -> None:
        store = self._bars_store(tmp_path)
        writer = ParquetDatasetWriter(store, "market/stock/bars")
        df = pl.DataFrame({"instrument_id": [1], "close": [1.0]})

        with pytest.raises(ValueError, match="missing from frame"):
            writer.write(df, year=2026)


class TestParquetDatasetWriterWriteLock:
    """审计 #684 批B #7：写入锁统一收口 writer 层，锁名 {dataset}_write_{year}."""

    @staticmethod
    def _locked_writer(tmp_path: Path) -> tuple[ParquetDatasetWriter, FileLockManager]:
        lock = FileLockManager(tmp_path / "locks")
        store = ParquetStore(
            tmp_path / "data",
            key_columns=("instrument_id", "trade_date"),
            date_column="trade_date",
            file_lock=lock,
        )
        return ParquetDatasetWriter(store, "market/stock/bars"), lock

    def test_lock_names_cover_each_shard_year_with_sanitized_dataset(
        self, tmp_path: Path
    ) -> None:
        writer, lock = self._locked_writer(tmp_path)
        acquired: list[str] = []
        original_acquire = lock.acquire

        def recording_acquire(
            name: str, timeout: float = 30.0
        ) -> AbstractContextManager[None]:
            acquired.append(name)
            return original_acquire(name, timeout=timeout)

        lock.acquire = recording_acquire  # type: ignore[method-assign]
        df = pl.DataFrame(
            {
                "instrument_id": [1, 1],
                "trade_date": [date(2026, 12, 30), date(2027, 1, 3)],
                "close": [1.0, 2.0],
            }
        )

        writer.write(df, year=2027)

        assert acquired == [
            "market_stock_bars_write_2026",
            "market_stock_bars_write_2027",
        ]

    def test_concurrent_same_year_writes_lose_no_rows(self, tmp_path: Path) -> None:
        """backfill --parallel 并发写同年分区：文件锁下无丢失更新."""
        writers: list[ParquetDatasetWriter] = []
        for _ in range(4):
            store = ParquetStore(
                tmp_path / "data",
                key_columns=("instrument_id", "trade_date"),
                date_column="trade_date",
                file_lock=FileLockManager(tmp_path / "locks"),
            )
            writers.append(ParquetDatasetWriter(store, "market/stock/bars"))

        barrier = threading.Barrier(len(writers))
        errors: list[Exception] = []
        trade_dates = [date(2026, 3, d) for d in range(2, 32)]  # 30 个交易日

        def run(index: int) -> None:
            frame = pl.DataFrame(
                {
                    "instrument_id": [1_000_000 + index] * len(trade_dates),
                    "trade_date": trade_dates,
                    "close": [float(index)] * len(trade_dates),
                }
            )
            barrier.wait()
            try:
                writers[index].write(
                    frame, year=2026, on_duplicate=OnDuplicate.KEEP_LAST
                )
            except Exception as e:  # 线程异常回传主断言
                errors.append(e)

        threads = [threading.Thread(target=run, args=(i,)) for i in range(len(writers))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert errors == []
        stored = writers[0]._store.read("market/stock/bars")
        # 4 标的 × 30 交易日全部可见——无锁竞态会整帧丢失
        assert stored.height == 4 * len(trade_dates)
        per_instrument = stored.group_by("instrument_id").len()
        assert set(per_instrument["len"].to_list()) == {len(trade_dates)}


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
        from ditto_platform.foundation import DatasetWriter

        _: DatasetWriter = writer
