"""Post-ingest helper unit tests."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import polars as pl
from ditto_application.contracts import CheckDataQualityCommand
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitOutcome,
    EvidenceCommitPorts,
    EvidenceCommitRequest,
    IngestionEvidenceCommitter,
    PartitionWriteIntent,
)
from ditto_application.processes.ingestion.list_date_inference import (
    ListDateInferenceService,
)
from ditto_application.processes.ingestion.post_ingest import (
    CatalogWriteContext,
    DataWriteContext,
    PostIngestContext,
    RequestWindow,
    process_fetched_data,
    record_data_catalog_entry,
    run_list_date_inference,
    write_data_safe,
)
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    InMemoryDataCatalog,
)
from ditto_data.catalog.provider_payload import (
    FilesystemProviderPayloadStore,
    ProviderPayloadArtifact,
)
from ditto_data.catalog.source_snapshot import snapshot_identity
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.models.ingestion import IngestionLog
from ditto_platform.foundation import ChecksumCompute, OnDuplicate, WriteResult
from packages.application.tests.unit.process.ingestion import (
    snapshot_evidence_support as _evidence_support,
)


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


class _FailingCatalogWriter:
    def upsert_asset(self, entry: DataCatalogEntry) -> None:
        _ = entry
        raise RuntimeError("catalog unavailable: secret-token")


class _PassingQualityChecker:
    def handle(
        self,
        cmd: CheckDataQualityCommand,
    ) -> tuple[pl.DataFrame, bool]:
        return cmd.df, False


class _IngestionLogRecorder:
    def __init__(self) -> None:
        self.logs: list[IngestionLog] = []

    def get_log(
        self, dataset: str, source: str, trade_date: str
    ) -> IngestionLog | None:
        return next(
            (
                log
                for log in self.logs
                if (log.dataset, log.source, log.trade_date)
                == (dataset, source, trade_date)
            ),
            None,
        )

    def save_log(self, log: IngestionLog) -> IngestionLog:
        existing = self.get_log(log.dataset, log.source, log.trade_date)
        if existing is None:
            self.logs.append(log)
        return log


class _EvidenceCommitRecorder:
    def __init__(self, outcome: EvidenceCommitOutcome) -> None:
        self.outcome = outcome
        self.requests: list[EvidenceCommitRequest] = []

    def prepare_payload_write(self, intent: PartitionWriteIntent) -> None:
        _ = intent

    def commit(self, request: EvidenceCommitRequest) -> EvidenceCommitOutcome:
        self.requests.append(request)
        return self.outcome


def _result_handler(
    logs: _IngestionLogRecorder | None, source_name: str
) -> IngestionResultHandler:
    """IngestionLogStore 是具体类,handler 只消费 get_log/save_log;
    _IngestionLogRecorder 与该表面结构兼容,替身注入经此单点放宽。"""
    return IngestionResultHandler(
        None if logs is None else cast(IngestionLogStore, logs), source_name
    )


def test_index_basic_skips_unbounded_per_instrument_list_date_inference() -> None:
    recorder = _ListDateInferenceRecorder()

    run_list_date_inference(
        cast(ListDateInferenceService, recorder),
        "index_basic",
    )

    assert recorder.asset_classes == []


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

    # #394:数据集级行,partition_keys 恒空;source_snapshot_id 仅作展示。
    asset = DataAssetRef(dataset_id="stock_daily", namespace="market")
    entry = catalog.get_asset(asset)
    assert entry is not None
    assert entry.source == "tushare"
    assert entry.storage_uri == "stock_daily/2024"
    assert entry.schema.row_count == 1
    assert entry.schema.schema_version == "market.stock_daily.v1"
    assert entry.source_snapshot_id == snapshot_identity(
        "stock_daily",
        "tushare",
        "2024-12-27",
        "2024-12-27",
        "market.stock_daily.v1",
        "checksum123",
    )
    assert len(catalog.list_assets()) == 1


def test_dataset_level_catalog_upsert_replaces_the_whole_row() -> None:
    """同一 (namespace, dataset_id) 的重复 upsert 整行替换,不产生分区行。"""
    catalog = InMemoryDataCatalog()

    def _record(checksum: str, rows: int) -> None:
        record_data_catalog_entry(
            CatalogWriteContext(
                dataset="stock_daily",
                trade_date="2024-12-27",
                source_name="tushare",
                write_result=WriteResult(
                    file_path="stock_daily/2024",
                    checksum=checksum,
                    rows_written=rows,
                    rows_total=rows,
                    blocked=False,
                ),
                df=pl.DataFrame(
                    {
                        "source_ticker": ["000001.SZ"],
                        "trade_date": ["2024-12-27"],
                        "close": [10.2],
                    }
                ),
            ),
            catalog_writer=catalog,
        )

    _record("checksum-one", 1)
    _record("checksum-two", 2)

    entries = catalog.list_assets()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.asset.partition_keys == ()
    assert entry.schema.row_count == 2
    assert entry.source_snapshot_id == snapshot_identity(
        "stock_daily",
        "tushare",
        "2024-12-27",
        "2024-12-27",
        "market.stock_daily.v1",
        "checksum-two",
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
        quality_checker=_PassingQualityChecker(),
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
    assert result.quality_evidence is not None
    assert result.quality_evidence.status == "passed"
    assert result.quality_evidence.checksum == "checksum123"
    assert writer.calls == [("stock_daily", "2024-12-27", OnDuplicate.VERIFY_IDENTICAL)]
    assert list_date_inference.asset_classes == []


def test_daily_request_window_keeps_processing_on_trade_date() -> None:
    """A wide daily fetch interval describes coverage, not cursor progress."""
    frame = pl.DataFrame({"trade_date": ["2026-09-25"], "close": [1.0]})
    for advance, expected_date in ((False, "2026-09-25"), (True, "2027-01-31")):
        writer = _WriteDataRecorder(
            WriteResult("unused", "unused", 1, 1, False),
        )
        ctx = PostIngestContext(
            result_handler=IngestionResultHandler(None, "tushare"),
            data_writer=cast(IngestionDataWriter, writer),
            list_date_inference=cast(ListDateInferenceService, None),
            quality_checker=_PassingQualityChecker(),
            source_name="tushare",
        )
        result = process_fetched_data(
            frame,
            "stock_daily",
            "2026-09-25",
            False,
            ctx=ctx,
            request_window=RequestWindow(
                "2026-01-01", "2027-01-31", advance_cursor=advance
            ),
        )
        assert result.status == "success"
        assert writer.calls[0][1] == expected_date


def test_r2_evidence_profile_requires_quality_checker_before_payload_write() -> None:
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="unused",
            checksum="unused",
            rows_written=0,
            rows_total=0,
            blocked=False,
        )
    )
    committer = _EvidenceCommitRecorder(EvidenceCommitOutcome("unused", completed=True))
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
        evidence_committer=cast(IngestionEvidenceCommitter, committer),
    )

    result = process_fetched_data(
        pl.DataFrame({"trade_date": ["2024-12-27"], "close": [10.2]}),
        "stock_daily",
        "2024-12-27",
        False,
        ctx=ctx,
    )

    assert result.status == "failed"
    assert result.error == "INGESTION_QUALITY_CHECK_REQUIRED"
    assert writer.calls == []
    assert committer.requests == []


def test_r2_evidence_failure_never_returns_success(tmp_path: Path) -> None:
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="stock_daily/2024",
            checksum="checksum123",
            rows_written=1,
            rows_total=1,
            blocked=False,
        )
    )
    committer = _EvidenceCommitRecorder(
        EvidenceCommitOutcome(
            "partition:tushare:stock_daily:2024-12-27",
            completed=False,
            error_code="CATALOG_WRITE_FAILED",
        )
    )
    logs = _IngestionLogRecorder()
    ctx = PostIngestContext(
        result_handler=_result_handler(logs, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
        quality_checker=_PassingQualityChecker(),
        evidence_committer=cast(IngestionEvidenceCommitter, committer),
        provider_payload_writer=FilesystemProviderPayloadStore(tmp_path),
    )

    result = process_fetched_data(
        pl.DataFrame({"trade_date": ["2024-12-27"], "close": [10.2]}),
        "stock_daily",
        "2024-12-27",
        False,
        ctx=ctx,
    )

    assert result.status == "failed"
    assert result.error == "CATALOG_WRITE_FAILED"
    assert len(committer.requests) == 1
    assert logs.logs == []


def test_r2_evidence_success_does_not_duplicate_success_log(tmp_path: Path) -> None:
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="stock_daily/2024",
            checksum="checksum123",
            rows_written=1,
            rows_total=1,
            blocked=False,
        )
    )
    committer = _EvidenceCommitRecorder(
        EvidenceCommitOutcome(
            "partition:tushare:stock_daily:2024-12-27",
            completed=True,
        )
    )
    logs = _IngestionLogRecorder()
    ctx = PostIngestContext(
        result_handler=_result_handler(logs, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
        quality_checker=_PassingQualityChecker(),
        evidence_committer=cast(IngestionEvidenceCommitter, committer),
        provider_payload_writer=FilesystemProviderPayloadStore(tmp_path),
    )

    result = process_fetched_data(
        pl.DataFrame({"trade_date": ["2024-12-27"], "close": [10.2]}),
        "stock_daily",
        "2024-12-27",
        False,
        ctx=ctx,
    )

    assert result.status == "success"
    assert len(committer.requests) == 1
    assert logs.logs == []


def test_r2_provider_payload_uri_remains_bound_to_pre_future_response(
    tmp_path: Path,
) -> None:
    """A later same-year response must not change an earlier provider snapshot."""
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="stock_daily/2026",
            checksum="canonical-year-partition",
            rows_written=1,
            rows_total=1,
            blocked=False,
        )
    )
    committer = _EvidenceCommitRecorder(
        EvidenceCommitOutcome("partition:tushare:stock_daily", completed=True)
    )
    payload_store = FilesystemProviderPayloadStore(tmp_path)
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
        quality_checker=_PassingQualityChecker(),
        evidence_committer=cast(IngestionEvidenceCommitter, committer),
        provider_payload_writer=payload_store,
    )
    original = pl.DataFrame({"trade_date": ["2026-08-28"], "close": [10.2]})
    revised = pl.DataFrame(
        {
            "trade_date": ["2026-08-28", "2026-08-31"],
            "close": [10.2, 11.0],
        }
    )

    first = process_fetched_data(
        original,
        "stock_daily",
        "2026-08-28",
        False,
        ctx=ctx,
    )
    second = process_fetched_data(
        revised,
        "stock_daily",
        "2026-08-28",
        True,
        ctx=ctx,
    )

    assert first.status == "success"
    assert second.status == "success"
    first_snapshot = committer.requests[0].provider_snapshot
    second_snapshot = committer.requests[1].provider_snapshot
    first_success_log = committer.requests[0].success_log
    assert first_snapshot.payload_uri != "stock_daily/2026"
    assert second_snapshot.payload_uri != first_snapshot.payload_uri
    assert first_success_log.checksum == "canonical-year-partition"
    assert first_success_log.rows == 1
    assert first_success_log.checksum != first_snapshot.checksum
    payload_uri = first_snapshot.payload_uri
    assert payload_uri is not None
    first_artifact = ProviderPayloadArtifact(
        dataset_id=first_snapshot.dataset_id,
        source=first_snapshot.source,
        checksum=first_snapshot.checksum,
        row_count=first_snapshot.row_count,
        uri=payload_uri,
    )
    assert payload_store.read_payload(first_artifact).to_dicts() == original.to_dicts()


def test_process_fetched_data_rejects_sparse_empty_without_pit_snapshot() -> None:
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

    assert result.status == "failed"
    assert result.error == "PIT_SNAPSHOT_MISSING"
    assert writer.calls == []


def test_sparse_empty_reuses_latest_pit_snapshot_on_or_before_signal_date() -> None:
    """A non-disclosure day must attest the latest known PIT snapshot, not go blank."""
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="unused",
            checksum="unused",
            rows_written=0,
            rows_total=0,
            blocked=False,
        )
    )
    today = datetime.now(UTC).date()
    prior_day = (today - timedelta(days=1)).isoformat()
    older_day = (today - timedelta(days=2)).isoformat()
    future_day = (today + timedelta(days=1)).isoformat()
    with _evidence_support.evidence_stores() as stores:
        older = _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start=older_day,
            request_end=older_day,
            checksum="0" * 32,
            row_count=75,
            schema_version="fundamental.balance_sheet.v1",
            namespace="fundamental",
            observed_at=datetime.now(UTC) - timedelta(days=2),
        )
        prior = _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start=prior_day,
            request_end=prior_day,
            checksum="1" * 32,
            row_count=125,
            schema_version="fundamental.balance_sheet.v1",
            namespace="fundamental",
            observed_at=datetime.now(UTC) - timedelta(days=1),
        )
        # 信号日之后才完成的快照不得伪装成已知事实。
        _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start=future_day,
            request_end=future_day,
            checksum="2" * 32,
            row_count=999,
            schema_version="fundamental.balance_sheet.v1",
            namespace="fundamental",
        )
        ctx = PostIngestContext(
            result_handler=IngestionResultHandler(None, "tushare"),
            data_writer=cast(IngestionDataWriter, writer),
            list_date_inference=cast(ListDateInferenceService, None),
            snapshot_reader=stores.snapshots,
            lifecycle_reader=stores.lifecycle,
            source_name="tushare",
        )

        result = process_fetched_data(
            pl.DataFrame(),
            "balance_sheet",
            today.isoformat(),
            False,
            ctx=ctx,
        )

        assert result.status == "success"
        assert result.trade_date == today.isoformat()
        assert result.checksum is None
        assert result.row_count == 0
        assert result.message == "无新数据, 复用最近 PIT 快照"
        evidence = result.snapshot_evidence
        assert evidence is not None
        assert evidence.kind == "persisted_asof_catalog_snapshot"
        assert evidence.signal_date == today.isoformat()
        assert evidence.effective_partition_date == prior_day
        assert evidence.source_snapshot_id.startswith("snapshot-set:sha256:")
        assert evidence.source_snapshot_ids == tuple(
            sorted({older.snapshot_id, prior.snapshot_id})
        )
        assert evidence.row_count == 200
        assert evidence.freshness_sla_hours == 24 * 45
        datetime.fromisoformat(evidence.checked_at)
        assert writer.calls == []


def test_sparse_nonempty_attests_prior_and_current_pit_snapshots(
    tmp_path: Path,
) -> None:
    """A disclosure-day delta must bind the cumulative persisted PIT snapshot."""
    today = datetime.now(UTC).date().isoformat()
    prior_day = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    frame = pl.DataFrame(
        {
            "report_date": ["2024-12-31", "2024-12-31"],
            "knowledge_date": [prior_day, today],
            "total_assets": [100.0, 200.0],
        }
    )
    from ditto_data.config.dataset_checksum import dataset_sort_keys

    today_checksum = ChecksumCompute.from_dataframe(
        frame,
        dataset_sort_keys("balance_sheet"),
    )
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="balance_sheet/2025",
            checksum=today_checksum,
            rows_written=2,
            rows_total=2,
            blocked=False,
        ),
        expected_columns=["report_date", "knowledge_date", "total_assets"],
    )
    catalog = InMemoryDataCatalog()
    with _evidence_support.evidence_stores() as stores:
        prior = _evidence_support.commit_snapshot(
            stores,
            dataset="balance_sheet",
            request_start=prior_day,
            request_end=prior_day,
            checksum="3" * 32,
            row_count=3,
            schema_version="fundamental.balance_sheet.v1",
            namespace="fundamental",
            observed_at=datetime.now(UTC) - timedelta(days=1),
        )
        logs = _IngestionLogRecorder()
        committer = IngestionEvidenceCommitter(
            ports=EvidenceCommitPorts(
                lifecycle_reader=stores.lifecycle,
                lifecycle_writer=stores.lifecycle,
                snapshot_writer=stores.snapshots,
                snapshot_reader=stores.snapshots,
                catalog_writer=catalog,
                ingestion_log_store=logs,
            )
        )
        ctx = PostIngestContext(
            result_handler=_result_handler(logs, "tushare"),
            data_writer=cast(IngestionDataWriter, writer),
            list_date_inference=cast(ListDateInferenceService, None),
            catalog_reader=catalog,
            catalog_writer=catalog,
            snapshot_reader=stores.snapshots,
            lifecycle_reader=stores.lifecycle,
            quality_checker=_PassingQualityChecker(),
            source_name="tushare",
            evidence_committer=committer,
            provider_payload_writer=FilesystemProviderPayloadStore(tmp_path),
        )

        result = process_fetched_data(
            frame,
            "balance_sheet",
            today,
            False,
            ctx=ctx,
        )

        assert result.status == "success", result
        assert result.checksum is None
        assert result.row_count == 2
        evidence = result.snapshot_evidence
        assert evidence is not None
        assert evidence.effective_partition_date == today
        assert len(evidence.source_snapshot_ids) == 2
        assert prior.snapshot_id in evidence.source_snapshot_ids
        assert evidence.source_snapshot_id.startswith("snapshot-set:sha256:")
        assert evidence.row_count == 5
        quality_evidence = result.quality_evidence
        assert quality_evidence is not None
        assert quality_evidence.kind == "write_time_l1_l2"
        assert quality_evidence.status == "passed"
        assert quality_evidence.checksum == today_checksum
        assert quality_evidence.row_count == 2
        # 数据集级 catalog 行只有一行,携带最后写入的 canonical 展示 id。
        entries = catalog.list_assets()
        assert len(entries) == 1
        assert entries[0].asset.partition_keys == ()


def test_sparse_nonempty_rejects_future_knowledge_date_before_write() -> None:
    """D 日 PIT snapshot 不能包含 D 后才公开的行。"""
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="balance_sheet/2025-01-06",
            checksum="future-checksum",
            rows_written=1,
            rows_total=1,
            blocked=False,
        ),
        expected_columns=["report_date", "knowledge_date", "total_assets"],
    )
    catalog = InMemoryDataCatalog()
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        catalog_reader=catalog,
        catalog_writer=catalog,
        quality_checker=_PassingQualityChecker(),
        source_name="tushare",
    )

    result = process_fetched_data(
        pl.DataFrame(
            {
                "report_date": ["2024-12-31"],
                "knowledge_date": ["2025-01-07"],
                "total_assets": [100.0],
            }
        ),
        "balance_sheet",
        "2025-01-06",
        False,
        ctx=ctx,
    )

    assert result.status == "failed"
    assert result.error == "PIT_KNOWLEDGE_DATE_AFTER_CUTOFF"
    assert writer.calls == []
    assert catalog.list_assets() == ()


def test_sparse_nonempty_requires_knowledge_date() -> None:
    """Sparse PIT delta 缺少行级 knowledge_date 时 fail closed。"""
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="balance_sheet/2025-01-06",
            checksum="missing-checksum",
            rows_written=1,
            rows_total=1,
            blocked=False,
        ),
        expected_columns=["report_date", "knowledge_date", "total_assets"],
    )
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        catalog_reader=InMemoryDataCatalog(),
        catalog_writer=InMemoryDataCatalog(),
        quality_checker=_PassingQualityChecker(),
        source_name="tushare",
    )

    result = process_fetched_data(
        pl.DataFrame({"report_date": ["2024-12-31"], "total_assets": [100.0]}),
        "balance_sheet",
        "2025-01-06",
        False,
        ctx=ctx,
    )

    assert result.status == "failed"
    assert result.error == "PIT_KNOWLEDGE_DATE_MISSING"
    assert writer.calls == []


def test_index_weight_uses_observation_date_as_pit_axis(
    tmp_path: Path,
) -> None:
    """Index weights carry their monthly observation date as the PIT axis."""
    today = datetime.now(UTC).date().isoformat()
    frame = pl.DataFrame(
        {
            "index_code": ["000300.SH"],
            "trade_date": [today],
            "weight": [100.0],
        }
    )
    from ditto_data.config.dataset_checksum import dataset_sort_keys

    checksum = ChecksumCompute.from_dataframe(frame, dataset_sort_keys("index_weight"))
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="index_weight/2025",
            checksum=checksum,
            rows_written=1,
            rows_total=1,
            blocked=False,
        ),
        expected_columns=["index_code", "trade_date", "weight"],
    )
    catalog = InMemoryDataCatalog()
    with _evidence_support.evidence_stores() as stores:
        logs = _IngestionLogRecorder()
        committer = IngestionEvidenceCommitter(
            ports=EvidenceCommitPorts(
                lifecycle_reader=stores.lifecycle,
                lifecycle_writer=stores.lifecycle,
                snapshot_writer=stores.snapshots,
                snapshot_reader=stores.snapshots,
                catalog_writer=catalog,
                ingestion_log_store=logs,
            )
        )
        ctx = PostIngestContext(
            result_handler=_result_handler(logs, "tushare"),
            data_writer=cast(IngestionDataWriter, writer),
            list_date_inference=cast(ListDateInferenceService, None),
            catalog_reader=catalog,
            catalog_writer=catalog,
            snapshot_reader=stores.snapshots,
            lifecycle_reader=stores.lifecycle,
            quality_checker=_PassingQualityChecker(),
            source_name="tushare",
            evidence_committer=committer,
            provider_payload_writer=FilesystemProviderPayloadStore(tmp_path),
        )

        result = process_fetched_data(
            frame,
            "index_weight",
            today,
            False,
            ctx=ctx,
        )

        assert result.status == "success", result
        assert len(writer.calls) == 1


def test_index_weight_rejects_future_observation_date() -> None:
    """A future observation must never leak into an earlier cutoff request."""
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="index_weight/2025",
            checksum="future-index-weight-checksum",
            rows_written=1,
            rows_total=1,
            blocked=False,
        ),
        expected_columns=["index_code", "trade_date", "weight"],
    )
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        catalog_reader=InMemoryDataCatalog(),
        catalog_writer=InMemoryDataCatalog(),
        quality_checker=_PassingQualityChecker(),
        source_name="tushare",
    )

    result = process_fetched_data(
        pl.DataFrame(
            {
                "index_code": ["000300.SH"],
                "trade_date": ["2025-01-07"],
                "weight": [100.0],
            }
        ),
        "index_weight",
        "2025-01-06",
        False,
        ctx=ctx,
    )

    assert result.status == "failed"
    assert result.error == "PIT_KNOWLEDGE_DATE_AFTER_CUTOFF"
    assert writer.calls == []


def test_success_uses_persisted_rows_written_for_result_log_and_quality() -> None:
    """FK 过滤后的实际写入行数是所有持久化证据的权威口径。"""
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="stock_daily/2025",
            checksum="persisted-checksum",
            rows_written=1,
            rows_total=2,
            blocked=False,
        ),
    )
    log_store = _IngestionLogRecorder()
    ctx = PostIngestContext(
        result_handler=_result_handler(log_store, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        catalog_writer=InMemoryDataCatalog(),
        quality_checker=_PassingQualityChecker(),
        source_name="tushare",
    )

    result = process_fetched_data(
        pl.DataFrame(
            {"trade_date": ["2025-01-06", "2025-01-06"], "close": [10.0, 11.0]}
        ),
        "stock_daily",
        "2025-01-06",
        False,
        ctx=ctx,
    )

    assert result.row_count == 1
    assert result.quality_evidence is not None
    assert result.quality_evidence.row_count == 1
    assert log_store.logs[0].rows == 1


def test_sparse_nonempty_fails_closed_when_catalog_evidence_cannot_persist() -> None:
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="balance_sheet/2025-01-06",
            checksum="today-checksum",
            rows_written=1,
            rows_total=1,
            blocked=False,
        ),
        expected_columns=["report_date", "knowledge_date", "total_assets"],
    )
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        catalog_reader=InMemoryDataCatalog(),
        catalog_writer=_FailingCatalogWriter(),
        quality_checker=_PassingQualityChecker(),
        source_name="tushare",
    )

    result = process_fetched_data(
        pl.DataFrame(
            {
                "report_date": ["2024-12-31"],
                "knowledge_date": ["2025-01-06"],
                "total_assets": [100.0],
            }
        ),
        "balance_sheet",
        "2025-01-06",
        False,
        ctx=ctx,
    )

    assert result.status == "failed"
    assert result.error == "CATALOG_EVIDENCE_FAILED"
    assert "secret-token" not in result.message


def test_sparse_range_resolves_pit_snapshot_at_request_end(
    tmp_path: Path,
) -> None:
    """A bounded sparse fetch attests disclosures known by the range end."""
    today = datetime.now(UTC).date()
    range_end = today.isoformat()
    frame = pl.DataFrame(
        {
            "report_date": ["2024-12-31"],
            "knowledge_date": [range_end],
            "total_assets": [100.0],
        }
    )
    from ditto_data.config.dataset_checksum import dataset_sort_keys

    checksum = ChecksumCompute.from_dataframe(
        frame,
        dataset_sort_keys("balance_sheet"),
    )
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="balance_sheet/2025-Q1",
            checksum=checksum,
            rows_written=1,
            rows_total=1,
            blocked=False,
        ),
        expected_columns=["report_date", "knowledge_date", "total_assets"],
    )
    catalog = InMemoryDataCatalog()
    with _evidence_support.evidence_stores() as stores:
        logs = _IngestionLogRecorder()
        committer = IngestionEvidenceCommitter(
            ports=EvidenceCommitPorts(
                lifecycle_reader=stores.lifecycle,
                lifecycle_writer=stores.lifecycle,
                snapshot_writer=stores.snapshots,
                snapshot_reader=stores.snapshots,
                catalog_writer=catalog,
                ingestion_log_store=logs,
            )
        )
        ctx = PostIngestContext(
            result_handler=_result_handler(logs, "tushare"),
            data_writer=cast(IngestionDataWriter, writer),
            list_date_inference=cast(ListDateInferenceService, None),
            catalog_reader=catalog,
            catalog_writer=catalog,
            snapshot_reader=stores.snapshots,
            lifecycle_reader=stores.lifecycle,
            quality_checker=_PassingQualityChecker(),
            source_name="tushare",
            evidence_committer=committer,
            provider_payload_writer=FilesystemProviderPayloadStore(tmp_path),
        )

        result = process_fetched_data(
            frame,
            "balance_sheet",
            (today - timedelta(days=29)).isoformat(),
            False,
            ctx=ctx,
            request_window=RequestWindow(None, range_end),
            chunk_id="chunk:tushare:balance_sheet:2025-Q1",
        )

        assert result.status == "success", result
        assert result.snapshot_evidence is not None
        assert result.snapshot_evidence.signal_date == range_end
        assert result.snapshot_evidence.effective_partition_date == range_end


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


def test_r2_empty_range_commits_no_payload_provider_observation() -> None:
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="unused",
            checksum="unused",
            rows_written=0,
            rows_total=0,
            blocked=False,
        )
    )
    committer = _EvidenceCommitRecorder(
        EvidenceCommitOutcome("chunk:tushare:commodity_daily:2026-01", completed=True)
    )
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
        quality_checker=_PassingQualityChecker(),
        evidence_committer=cast(IngestionEvidenceCommitter, committer),
    )

    result = process_fetched_data(
        pl.DataFrame(schema={"trade_date": pl.Date, "close": pl.Float64}),
        "commodity_daily",
        "2026-01-01",
        False,
        ctx=ctx,
        request_window=RequestWindow(None, "2026-01-31"),
        chunk_id="chunk:tushare:commodity_daily:2026-01",
    )

    assert result.status == "success"
    assert writer.calls == []
    assert len(committer.requests) == 1
    request = committer.requests[0]
    assert request.chunk_id == "chunk:tushare:commodity_daily:2026-01"
    assert request.provider_snapshot.row_count == 0
    assert request.provider_snapshot.payload_retained is False
    assert request.provider_snapshot.payload_uri is None
    assert request.catalog_entry.schema.row_count == 0


def test_basic_catalog_is_recorded_before_list_date_inference() -> None:
    write_result = WriteResult(
        file_path="instrument_reader:stock_basic",
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
    asset = DataAssetRef(dataset_id="stock_basic", namespace="metadata")
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
                "name": ["浦发银行"],
                "exchange": ["SSE"],
                "list_date": [None],
            }
        ),
        "stock_basic",
        "",
        True,
        ctx=ctx,
    )

    assert result.status == "success"
    assert list_date_inference.catalog_present_when_called
