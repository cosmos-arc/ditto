"""Instrument ingestion context unit tests."""

from typing import cast

import polars as pl
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.instrument_ingestion import (
    InstrumentBackfillContext,
    InstrumentIngestContext,
    InstrumentPostIngestContext,
    _process_fetched_data_by_instrument,
    backfill_adj_factor,
    ingest_by_instrument,
)
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_application.processes.ingestion.types import SourceFetchers
from ditto_data.catalog import DataAssetRef, InMemoryDataCatalog
from ditto_kernel.instrument import InstrumentIngestParams
from ditto_platform.foundation import OnDuplicate, WriteResult


class _WriteDataRecorder:
    def __init__(self, result: WriteResult) -> None:
        self._result = result
        self.calls: list[tuple[str, str, OnDuplicate]] = []

    def write_data(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        self.calls.append((dataset, trade_date, on_duplicate))
        assert df.columns == ["source_ticker", "trade_date", "close"]
        return self._result


class _MetadataService:
    def __init__(self) -> None:
        self.calls: list[tuple[str | None, str]] = []

    def resolve_source_ticker(
        self,
        *,
        ticker: str | None = None,
        standard_ticker: str | None = None,
        instrument_id: int | None = None,
        asset_class: str,
        source: str,
    ) -> str:
        _ = standard_ticker, instrument_id, asset_class
        self.calls.append((ticker, source))
        return "000001.SZ"

    def list_trading_days(self, start: str, end: str) -> list[str]:
        _ = end
        return [start]


class _MarketSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str | None]] = []

    def fetch_stock_daily(
        self,
        *,
        source_ticker: str,
        start_date: str,
        end_date: str | None = None,
    ) -> pl.DataFrame:
        self.calls.append((source_ticker, start_date, end_date))
        return pl.DataFrame(
            {
                "source_ticker": [source_ticker],
                "trade_date": [start_date],
                "close": [10.2],
            }
        )

    def fetch_adj_factor_by_ticker(
        self,
        *,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pl.DataFrame:
        self.calls.append((ts_code, start_date, end_date))
        return pl.DataFrame(
            {
                "source_ticker": [ts_code],
                "trade_date": [start_date],
                "adj_factor": [1.0],
            }
        )


class _MarketQueryService:
    def get_adj_factors(self, start: str, end: str) -> pl.DataFrame:
        _ = start, end
        return pl.DataFrame()


class _AdjFactorWriteRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, OnDuplicate]] = []

    def write_data(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        self.calls.append((dataset, trade_date, on_duplicate))
        return WriteResult(
            file_path=f"{dataset}/{trade_date}",
            checksum="checksum123",
            rows_written=len(df),
            rows_total=len(df),
            blocked=False,
        )


def test_process_fetched_data_by_instrument_accepts_context() -> None:
    write_result = WriteResult(
        file_path="stock_daily/000001/2024",
        checksum="checksum123",
        rows_written=1,
        rows_total=1,
        blocked=False,
    )
    writer = _WriteDataRecorder(write_result)
    catalog = InMemoryDataCatalog()
    ctx = InstrumentPostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        source_name="tushare",
        catalog_writer=catalog,
    )

    result = _process_fetched_data_by_instrument(
        pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": ["2024-01-02"],
                "close": [10.2],
            }
        ),
        "stock_daily",
        "000001.SZ",
        InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        ),
        ctx=ctx,
    )

    assert result.status == "success"
    assert writer.calls == [("stock_daily", "2024-01-01", OnDuplicate.KEEP_LAST)]
    asset = DataAssetRef(
        dataset_id="stock_daily",
        namespace="market",
        partition_keys=(
            "source_ticker=000001.SZ",
            "start_date=2024-01-01",
            "end_date=2024-01-31",
        ),
    )
    assert catalog.get_asset(asset) is not None


def test_ingest_by_instrument_accepts_runtime_context() -> None:
    write_result = WriteResult(
        file_path="stock_daily/000001/2024",
        checksum="checksum123",
        rows_written=1,
        rows_total=1,
        blocked=False,
    )
    writer = _WriteDataRecorder(write_result)
    metadata = _MetadataService()
    market_source = _MarketSource()
    fetchers = SourceFetchers(
        metadata=cast(object, market_source),
        market=cast(object, market_source),
        fundamental=cast(object, market_source),
        capital=cast(object, market_source),
        macro=cast(object, market_source),
    )
    ctx = InstrumentIngestContext(
        fetchers=fetchers,
        metadata_service=cast(object, metadata),
        source_name="tushare",
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
    )

    result = ingest_by_instrument(
        "stock_daily",
        InstrumentIngestParams(
            ticker="000001",
            start_date="2024-01-01",
            end_date="2024-01-31",
        ),
        False,
        ctx=ctx,
    )

    assert result.status == "success"
    assert metadata.calls == [("000001", "tushare")]
    assert market_source.calls == [("000001.SZ", "2024-01-01", "2024-01-31")]
    assert writer.calls == [("stock_daily", "2024-01-01", OnDuplicate.KEEP_LAST)]


def test_backfill_adj_factor_accepts_runtime_context() -> None:
    metadata = _MetadataService()
    market_source = _MarketSource()
    writer = _AdjFactorWriteRecorder()
    fetchers = SourceFetchers(
        metadata=cast(object, market_source),
        market=cast(object, market_source),
        fundamental=cast(object, market_source),
        capital=cast(object, market_source),
        macro=cast(object, market_source),
    )
    ctx = InstrumentBackfillContext(
        metadata_service=cast(object, metadata),
        market_service=cast(object, _MarketQueryService()),
        fetchers=fetchers,
        source_name="tushare",
        data_writer=cast(IngestionDataWriter, writer),
    )

    result = backfill_adj_factor(
        instrument_id=1,
        start="2024-01-02",
        end="2024-01-02",
        ctx=ctx,
    )

    assert result == {"status": "ok", "gap_count": 1, "filled_dates": 1}
    assert market_source.calls == [("000001.SZ", "20240102", "20240102")]
    assert writer.calls == [("adj_factor", "2024-01-02", OnDuplicate.KEEP_LAST)]
