"""Post-ingest helper unit tests."""

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import polars as pl
from ditto_application.contracts import CheckDataQualityCommand
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitOutcome,
    IngestionEvidenceCommitter,
)
from ditto_application.processes.ingestion.list_date_inference import (
    ListDateInferenceService,
)
from ditto_application.processes.ingestion.post_ingest import (
    CatalogWriteContext,
    DataWriteContext,
    PostIngestContext,
    process_fetched_data,
    record_data_catalog_entry,
    run_list_date_inference,
    write_data_safe,
)
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from ditto_data.catalog.provider_payload import (
    FilesystemProviderPayloadStore,
    ProviderPayloadArtifact,
)
from ditto_data.ingestion.freeze_store import FreezeStore
from ditto_data.models.ingestion import IngestionLog
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


class _FailingCatalogWriter:
    def upsert_asset(self, entry: DataCatalogEntry) -> None:
        _ = entry
        raise RuntimeError("catalog unavailable: secret-token")


class _PassingQualityChecker:
    def handle(
        self,
        command: CheckDataQualityCommand,
    ) -> tuple[pl.DataFrame, bool]:
        return command.df, False


class _IngestionLogRecorder:
    def __init__(self) -> None:
        self.logs: list[IngestionLog] = []

    def save_log(self, log: IngestionLog) -> IngestionLog:
        self.logs.append(log)
        return log


class _EvidenceCommitRecorder:
    def __init__(self, outcome: EvidenceCommitOutcome) -> None:
        self.outcome = outcome
        self.requests: list[object] = []

    def commit(self, request: object) -> EvidenceCommitOutcome:
        self.requests.append(request)
        return self.outcome


class _FreezeRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[str]]] = []

    def create_freeze(
        self,
        freeze_id: str,
        description: str,
        datasets: list[str],
    ) -> None:
        self.calls.append((freeze_id, description, datasets))


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
    assert writer.calls == [("stock_daily", "2024-12-27", OnDuplicate.ERROR)]
    assert list_date_inference.asset_classes == []


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
        license_record_id="license:tushare:stock_daily:reviewed",
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
        result_handler=IngestionResultHandler(cast(object, logs), "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
        quality_checker=_PassingQualityChecker(),
        evidence_committer=cast(IngestionEvidenceCommitter, committer),
        provider_payload_writer=FilesystemProviderPayloadStore(tmp_path),
        license_record_id="license:tushare:stock_daily:reviewed",
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
    freeze = _FreezeRecorder()
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(cast(object, logs), "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
        quality_checker=_PassingQualityChecker(),
        evidence_committer=cast(IngestionEvidenceCommitter, committer),
        provider_payload_writer=FilesystemProviderPayloadStore(tmp_path),
        license_record_id="license:tushare:stock_daily:reviewed",
        freeze_store=cast(FreezeStore, freeze),
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
    assert freeze.calls == []


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
        license_record_id="license:tushare:stock_daily:reviewed",
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
    first_artifact = ProviderPayloadArtifact(
        dataset_id=first_snapshot.dataset_id,
        source=first_snapshot.source,
        checksum=first_snapshot.checksum,
        row_count=first_snapshot.row_count,
        uri=first_snapshot.payload_uri,
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
    catalog = InMemoryDataCatalog()
    for trade_date, snapshot_id, row_count in (
        (
            "2025-01-02",
            "snapshot:tushare:balance_sheet:older:quality=l1-l2",
            75,
        ),
        (
            "2025-01-03",
            "snapshot:tushare:balance_sheet:prior:quality=l1-l2",
            125,
        ),
        (
            "2025-01-07",
            "snapshot:tushare:balance_sheet:future:quality=l1-l2",
            999,
        ),
    ):
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="balance_sheet",
                    namespace="fundamental",
                    partition_keys=(f"trade_date={trade_date}",),
                ),
                storage_uri=f"balance_sheet/{trade_date}",
                schema=DataSchemaFingerprint(
                    schema_hash="fundamental.balance_sheet.v1",
                    row_count=row_count,
                ),
                source="tushare",
                freshness_at=datetime(2025, 1, 8, tzinfo=UTC),
                source_snapshot_id=snapshot_id,
            )
        )
    ctx = PostIngestContext(
        result_handler=IngestionResultHandler(None, "tushare"),
        data_writer=cast(IngestionDataWriter, writer),
        list_date_inference=cast(ListDateInferenceService, None),
        catalog_reader=catalog,
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
    assert result.trade_date == "2025-01-06"
    assert result.checksum is None
    assert result.row_count == 0
    assert result.message == "无新数据, 复用最近 PIT 快照"
    evidence = result.snapshot_evidence
    assert evidence is not None
    assert evidence.kind == "persisted_asof_catalog_snapshot"
    assert evidence.signal_date == "2025-01-06"
    assert evidence.effective_partition_date == "2025-01-03"
    assert evidence.source_snapshot_id.startswith("snapshot-set:sha256:")
    assert evidence.source_snapshot_ids == (
        "snapshot:tushare:balance_sheet:older:quality=l1-l2",
        "snapshot:tushare:balance_sheet:prior:quality=l1-l2",
    )
    assert evidence.row_count == 200
    assert evidence.freshness_sla_hours == 24 * 45
    datetime.fromisoformat(evidence.checked_at)
    assert writer.calls == []


def test_sparse_nonempty_attests_prior_and_current_pit_catalog_snapshots() -> None:
    """A disclosure-day delta must bind the cumulative persisted PIT snapshot."""
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="balance_sheet/2025-01-06",
            checksum="today-checksum",
            rows_written=2,
            rows_total=2,
            blocked=False,
        ),
        expected_columns=["report_date", "knowledge_date", "total_assets"],
    )
    catalog = InMemoryDataCatalog()
    catalog.upsert_asset(
        DataCatalogEntry(
            asset=DataAssetRef(
                dataset_id="balance_sheet",
                namespace="fundamental",
                partition_keys=("trade_date=2025-01-03",),
            ),
            storage_uri="balance_sheet/2025-01-03",
            schema=DataSchemaFingerprint(
                schema_hash="fundamental.balance_sheet.v1",
                row_count=3,
            ),
            source="tushare",
            freshness_at=datetime(2025, 1, 3, tzinfo=UTC),
            source_snapshot_id=("snapshot:tushare:balance_sheet:prior:quality=l1-l2"),
        )
    )
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
                "report_date": ["2024-12-31", "2024-12-31"],
                "knowledge_date": ["2025-01-03", "2025-01-06"],
                "total_assets": [100.0, 200.0],
            }
        ),
        "balance_sheet",
        "2025-01-06",
        False,
        ctx=ctx,
    )

    assert result.status == "success"
    assert result.checksum is None
    assert result.row_count == 2
    evidence = result.snapshot_evidence
    assert evidence is not None
    assert evidence.effective_partition_date == "2025-01-06"
    assert evidence.source_snapshot_ids == (
        ("snapshot:tushare:balance_sheet:2025-01-06:today-checksum:quality=l1-l2"),
        "snapshot:tushare:balance_sheet:prior:quality=l1-l2",
    )
    assert evidence.source_snapshot_id.startswith("snapshot-set:sha256:")
    assert evidence.row_count == 5
    quality_evidence = result.quality_evidence
    assert quality_evidence is not None
    assert quality_evidence.kind == "write_time_l1_l2"
    assert quality_evidence.status == "passed"
    assert quality_evidence.checksum == "today-checksum"
    assert quality_evidence.row_count == 2


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


def test_index_weight_uses_effective_from_as_pit_knowledge_date() -> None:
    """Index weights are knowable from effective_from, not a synthetic trade date."""
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="index_weight/2025",
            checksum="index-weight-checksum",
            rows_written=1,
            rows_total=1,
            blocked=False,
        ),
        expected_columns=["index_code", "effective_from", "weight"],
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
                "index_code": ["000300.SH"],
                "effective_from": ["2025-01-06"],
                "weight": [100.0],
            }
        ),
        "index_weight",
        "2025-01-06",
        False,
        ctx=ctx,
    )

    assert result.status == "success"
    assert len(writer.calls) == 1


def test_index_weight_rejects_future_effective_from() -> None:
    """A future effective interval must never leak into an earlier as-of snapshot."""
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="index_weight/2025",
            checksum="future-index-weight-checksum",
            rows_written=1,
            rows_total=1,
            blocked=False,
        ),
        expected_columns=["index_code", "effective_from", "weight"],
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
                "effective_from": ["2025-01-07"],
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
        result_handler=IngestionResultHandler(cast(object, log_store), "tushare"),
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
        catalog_writer=cast(object, _FailingCatalogWriter()),
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


def test_sparse_range_resolves_pit_snapshot_at_request_end() -> None:
    """A bounded sparse fetch attests disclosures known by the range end."""
    writer = _WriteDataRecorder(
        WriteResult(
            file_path="balance_sheet/2025-Q1",
            checksum="range-checksum",
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
                "knowledge_date": ["2025-02-15"],
                "total_assets": [100.0],
            }
        ),
        "balance_sheet",
        "2025-01-02",
        False,
        ctx=ctx,
        request_end="2025-03-31",
        chunk_id="chunk:tushare:balance_sheet:2025-Q1",
    )

    assert result.status == "success", result
    assert result.snapshot_evidence is not None
    assert result.snapshot_evidence.signal_date == "2025-03-31"
    assert result.snapshot_evidence.effective_partition_date == "2025-03-31"


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
        license_record_id="license:tushare:commodity_daily:reviewed",
    )

    result = process_fetched_data(
        pl.DataFrame(schema={"trade_date": pl.Date, "close": pl.Float64}),
        "commodity_daily",
        "2026-01-01",
        False,
        ctx=ctx,
        request_end="2026-01-31",
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
    asset = DataAssetRef(
        dataset_id="stock_basic",
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
