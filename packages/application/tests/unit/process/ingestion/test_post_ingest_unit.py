"""Post-ingest helper unit tests."""

from typing import cast

import polars as pl
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.list_date_inference import (
    ListDateInferenceService,
)
from ditto_application.processes.ingestion.post_ingest import (
    CatalogWriteContext,
    DataWriteContext,
    PostIngestContext,
    process_fetched_data,
    record_data_catalog_entry,
    write_data_safe,
)
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_data.catalog import DataAssetRef, InMemoryDataCatalog
from ditto_platform.foundation import OnDuplicate, WriteResult


class _WriteDataRecorder:
    def __init__(
        self, result: WriteResult, expected_columns: list[str] | None = None
    ) -> None:
        self._result = result
        self._expected_columns = expected_columns or ["trade_date", "close"]
        self.calls: list[tuple[str, str, OnDuplicate]] = []

    def write_data(
        self,
        dataset: str,
        df: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        self.calls.append((dataset, trade_date, on_duplicate))
        assert df.columns == self._expected_columns
        return self._result


class _ListDateInferenceRecorder:
    def __init__(self) -> None:
        self.asset_classes: list[str] = []

    def infer_for_asset_class(self, asset_class: str) -> int:
        self.asset_classes.append(asset_class)
        return 0


class _CatalogAwareListDateInferenceRecorder:
    def __init__(self, catalog: InMemoryDataCatalog, asset: DataAssetRef) -> None:
        self._catalog = catalog
        self._asset = asset
        self.catalog_present_when_called = False

    def infer_for_asset_class(self, asset_class: str) -> int:
        _ = asset_class
        self.catalog_present_when_called = (
            self._catalog.get_asset(self._asset) is not None
        )
        return 0


def test_record_data_catalog_entry_accepts_catalog_write_context() -> None:
    catalog = InMemoryDataCatalog()
    write_result = WriteResult(
        file_path="stock_daily/2024",
        checksum="checksum123",
        rows_written=1,
        rows_total=1,
        blocked=False,
    )
    ctx = CatalogWriteContext(
        dataset="stock_daily",
        trade_date="2024-12-27",
        source_name="tushare",
        write_result=write_result,
        df=pl.DataFrame(
            {
                "source_ticker": ["000001.SZ"],
                "trade_date": ["2024-12-27"],
                "close": [10.2],
            }
        ),
    )

    record_data_catalog_entry(ctx, catalog_writer=catalog)

    asset = DataAssetRef(
        dataset_id="stock_daily",
        namespace="market",
        partition_keys=("trade_date=2024-12-27",),
    )
    entry = catalog.get_asset(asset)
    assert entry is not None
    assert entry.source == "tushare"
    assert entry.storage_uri == "stock_daily/2024"
    assert entry.schema.row_count == 1
    assert entry.schema.schema_version == "market.stock_daily.v1"
    assert entry.source_snapshot_id == (
        "snapshot:tushare:stock_daily:2024-12-27:checksum123"
    )


def test_write_data_safe_accepts_data_write_context() -> None:
    write_result = WriteResult(
        file_path="stock_daily/2024",
        checksum="checksum123",
        rows_written=1,
        rows_total=1,
        blocked=False,
    )
    writer = _WriteDataRecorder(write_result)
    ctx = DataWriteContext(
        dataset="stock_daily",
        df=pl.DataFrame({"trade_date": ["2024-12-27"], "close": [10.2]}),
        trade_date="2024-12-27",
        on_duplicate=OnDuplicate.KEEP_LAST,
    )

    result = write_data_safe(
        ctx,
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
    )

    assert result is write_result
    assert writer.calls == [("stock_daily", "2024-12-27", OnDuplicate.KEEP_LAST)]


def test_process_fetched_data_accepts_post_ingest_context() -> None:
    write_result = WriteResult(
        file_path="stock_daily/2024",
        checksum="checksum123",
        rows_written=1,
        rows_total=1,
        blocked=False,
    )
    writer = _WriteDataRecorder(write_result)
    list_date_inference = _ListDateInferenceRecorder()
    catalog = InMemoryDataCatalog()
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, list_date_inference),
        catalog_writer=catalog,
        source_name="tushare",
    )

    result = process_fetched_data(
        pl.DataFrame({"trade_date": ["2024-12-27"], "close": [10.2]}),
        "stock_daily",
        "2024-12-27",
        False,
        ctx=ctx,
    )

    assert result.status == "success"
    assert writer.calls == [("stock_daily", "2024-12-27", OnDuplicate.ERROR)]
    assert list_date_inference.asset_classes == []


def test_process_fetched_data_marks_sparse_fundamental_empty_as_success() -> None:
    write_result = WriteResult(
        file_path="balance_sheet/2025",
        checksum="checksum123",
        rows_written=1,
        rows_total=1,
        blocked=False,
    )
    writer = _WriteDataRecorder(write_result)
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
    )

    result = process_fetched_data(
        pl.DataFrame(),
        "balance_sheet",
        "2025-01-06",
        False,
        ctx=ctx,
    )

    assert result.status == "success"
    assert result.row_count == 0
    assert result.message == "无新数据"
    assert writer.calls == []


def test_process_fetched_data_marks_market_empty_as_failed() -> None:
    write_result = WriteResult(
        file_path="stock_daily/2025",
        checksum="checksum123",
        rows_written=1,
        rows_total=1,
        blocked=False,
    )
    writer = _WriteDataRecorder(write_result)
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
    )

    result = process_fetched_data(
        pl.DataFrame(),
        "stock_daily",
        "2025-01-06",
        False,
        ctx=ctx,
    )

    assert result.status == "failed"
    assert result.error == "EMPTY_DATA"
    assert writer.calls == []


def test_basic_catalog_is_recorded_before_list_date_inference() -> None:
    write_result = WriteResult(
        file_path="instrument_reader:index_basic",
        checksum="checksum123",
        rows_written=1,
        rows_total=1,
        blocked=False,
    )
    writer = _WriteDataRecorder(
        write_result,
        expected_columns=[
            "source_ticker",
            "ticker",
            "name",
            "exchange",
            "list_date",
        ],
    )
    catalog = InMemoryDataCatalog()
    asset = DataAssetRef(
        dataset_id="index_basic",
        namespace="metadata",
        partition_keys=("trade_date=",),
    )
    list_date_inference = _CatalogAwareListDateInferenceRecorder(catalog, asset)
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, list_date_inference),
        catalog_writer=catalog,
        source_name="tushare",
    )

    result = process_fetched_data(
        pl.DataFrame(
            {
                "source_ticker": ["000001.SH"],
                "ticker": ["000001"],
                "name": ["上证指数"],
                "exchange": ["SSE"],
                "list_date": [None],
            }
        ),
        "index_basic",
        "",
        True,
        ctx=ctx,
    )

    assert result.status == "success"
    assert list_date_inference.catalog_present_when_called
