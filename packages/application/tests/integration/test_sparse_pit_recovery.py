"""SQLite/physical-storage integration tests for sparse PIT evidence recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import polars as pl
import pytest
from ditto_application.catalog_freshness import (
    PersistedIngestionEvidenceVerifier,
    snapshot_asof_evidence,
)
from ditto_application.commands.quality_check import CheckDataQualityHandler
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
from ditto_application.processes.ingestion.evidence_commit import (
    EvidenceCommitPorts,
    IngestionEvidenceCommitter,
)
from ditto_application.processes.ingestion.list_date_inference import (
    ListDateInferenceService,
)
from ditto_application.processes.ingestion.post_ingest import (
    PostIngestContext,
    process_fetched_data,
)
from ditto_application.processes.ingestion.result_handler import IngestionResultHandler
from ditto_application.processes.ingestion.sparse_recovery import (
    SparsePITReattestationProcess,
)
from ditto_application.processes.ingestion.sparse_recovery_models import (
    SparsePITReattestationRequest,
)
from ditto_data.catalog.provider_payload import FilesystemProviderPayloadStore
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.catalog.sqlite_store import SQLiteDataCatalog
from ditto_data.config.dataset_checksum import dataset_sort_keys
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_data.models.ingestion import IngestionResult
from ditto_data.quality import DQSpec, QualityEngine
from ditto_data.storage.runtime.ingestion import IngestionLogReader, IngestionLogWriter
from ditto_platform.foundation import (
    ChecksumCompute,
    OnDuplicate,
    SQLiteClient,
    SQLitePool,
    WriteResult,
)

_SCHEMA = "fundamental.balance_sheet.v1"


@dataclass(frozen=True)
class _SQLiteEvidenceRuntime:
    pool: SQLitePool
    catalog: SQLiteDataCatalog
    snapshots: SQLiteProviderSnapshotStore
    lifecycle: SQLitePartitionLifecycleStore
    logs: IngestionLogStore
    verifier: PersistedIngestionEvidenceVerifier


class _PhysicalSparseWriter:
    def __init__(self, root: Path) -> None:
        self._root = root

    def write_data(
        self,
        dataset: str,
        frame: pl.DataFrame,
        trade_date: str,
        on_duplicate: OnDuplicate,
    ) -> WriteResult:
        _ = on_duplicate
        relative_path = Path(dataset) / f"{trade_date}.parquet"
        path = self._root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(path)
        checksum = ChecksumCompute.from_dataframe(
            frame,
            dataset_sort_keys(dataset),
        )
        return WriteResult(
            file_path=relative_path.as_posix(),
            checksum=checksum,
            rows_written=frame.height,
            rows_total=frame.height,
            blocked=False,
        )


class _PostIngestSparsePort:
    def __init__(
        self,
        *,
        frames: dict[str, pl.DataFrame],
        context: PostIngestContext,
    ) -> None:
        self._frames = frames
        self._context = context
        self.calls: list[tuple[str, str, bool]] = []

    def ingest_date(
        self,
        dataset: str,
        trade_date: str,
        force: bool = False,
    ) -> IngestionResult:
        self.calls.append((dataset, trade_date, force))
        return process_fetched_data(
            self._frames[trade_date],
            dataset,
            trade_date,
            force,
            ctx=self._context,
        )


class _MutableClock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now


def _runtime(db_path: Path) -> _SQLiteEvidenceRuntime:
    pool = SQLitePool(str(db_path))
    client = SQLiteClient(pool)
    catalog = SQLiteDataCatalog(client)
    clock = _MutableClock()
    snapshots = SQLiteProviderSnapshotStore(client, now=clock)
    lifecycle = SQLitePartitionLifecycleStore(client)
    logs = IngestionLogStore(
        IngestionLogReader(client),
        IngestionLogWriter(client),
    )
    runtime = _SQLiteEvidenceRuntime(
        pool=pool,
        catalog=catalog,
        snapshots=snapshots,
        lifecycle=lifecycle,
        logs=logs,
        verifier=PersistedIngestionEvidenceVerifier(
            snapshots=snapshots,
            lifecycle=lifecycle,
            ingestion_logs=logs,
        ),
    )
    runtime.__dict__["clock"] = clock
    return runtime


def _frame(trade_date: str, value: float) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1001],
            "trade_date": [date.fromisoformat(trade_date)],
            "knowledge_date": [date.fromisoformat(trade_date)],
            "total_assets": [value],
        }
    )


def _delete_success_logs(runtime: _SQLiteEvidenceRuntime) -> None:
    """模拟 success log 丢失:三方交叉验证必须随之失败。"""
    client = SQLiteClient(runtime.pool)
    client.execute(
        "DELETE FROM ingestion_log WHERE dataset = 'balance_sheet' "
        "AND status = 'SUCCESS'"
    )
    client.commit()


@dataclass(frozen=True)
class _StoresAdapter:
    """Adapt the integration runtime to the shared evidence fixture protocol."""

    _runtime: _SQLiteEvidenceRuntime

    @property
    def snapshots(self):
        return self._runtime.snapshots

    @property
    def lifecycle(self):
        return self._runtime.lifecycle

    @property
    def logs(self):
        return self._runtime.logs

    @property
    def clock(self):
        return self._runtime.__dict__["clock"]


def _recovery_process(
    runtime: _SQLiteEvidenceRuntime,
    root: Path,
    frames: dict[str, pl.DataFrame],
) -> tuple[SparsePITReattestationProcess, _PostIngestSparsePort]:
    quality_checker = CheckDataQualityHandler(QualityEngine(DQSpec()))
    context = PostIngestContext(
        result_handler=IngestionResultHandler(runtime.logs, "tushare"),
        data_writer=cast(IngestionDataWriter, _PhysicalSparseWriter(root)),
        quality_checker=quality_checker,
        list_date_inference=cast(ListDateInferenceService, None),
        source_name="tushare",
        catalog_reader=runtime.catalog,
        catalog_writer=runtime.catalog,
        snapshot_reader=runtime.snapshots,
        lifecycle_reader=runtime.lifecycle,
        evidence_committer=IngestionEvidenceCommitter(
            ports=EvidenceCommitPorts(
                lifecycle_reader=runtime.lifecycle,
                lifecycle_writer=runtime.lifecycle,
                snapshot_writer=runtime.snapshots,
                snapshot_reader=runtime.snapshots,
                catalog_writer=runtime.catalog,
                ingestion_log_store=runtime.logs,
            )
        ),
        provider_payload_writer=FilesystemProviderPayloadStore(root),
    )
    port = _PostIngestSparsePort(frames=frames, context=context)
    return (
        SparsePITReattestationProcess(
            ingestion=port,
            snapshots=runtime.snapshots,
            lifecycle=runtime.lifecycle,
            verifier=runtime.verifier,
        ),
        port,
    )


@pytest.mark.integration
def test_mixed_legacy_history_fails_then_full_recovery_succeeds_idempotently(
    tmp_path: Path,
) -> None:
    """未完成/缺 log 的组件使 asof 失败;全量重放后可复验且幂等。"""
    runtime = _runtime(tmp_path / "runtime.sqlite")
    older_day = "2026-06-15"
    newer_day = "2026-07-01"
    signal = "2026-07-16"
    frames = {
        older_day: _frame(older_day, 100.0),
        newer_day: _frame(newer_day, 120.0),
    }
    try:
        # 先经真实证据路径落两个完整组件。
        process, port = _recovery_process(runtime, tmp_path, frames)
        request = SparsePITReattestationRequest(
            dataset="balance_sheet",
            source="tushare",
            signal_date=signal,
        )
        for day in (older_day, newer_day):
            result = port.ingest_date("balance_sheet", day, force=True)
            assert result.status == "success", result.error
        snapshot = snapshot_asof_evidence(
            snapshots=runtime.snapshots,
            lifecycle=runtime.lifecycle,
            dataset="balance_sheet",
            source="tushare",
            signal_date=signal,
        )
        assert snapshot is not None
        assert runtime.verifier.verify_asof_snapshot(
            dataset="balance_sheet",
            source="tushare",
            signal_date=signal,
            expected_snapshot_ids=snapshot.source_snapshot_ids,
            expected_row_count=snapshot.row_count,
        )
        port.calls.clear()

        # 破坏:success log 丢失 → 三方交叉验证失败。
        _delete_success_logs(runtime)
        assert not runtime.verifier.verify_asof_snapshot(
            dataset="balance_sheet",
            source="tushare",
            signal_date=signal,
            expected_snapshot_ids=snapshot.source_snapshot_ids,
            expected_row_count=snapshot.row_count,
        )

        first = process.run(request)
        second = process.run(request)

        assert first.passed is True, first.error
        assert second.passed is True, second.error
        assert second.source_snapshot_id == first.source_snapshot_id
        assert first.component_dates == (older_day, newer_day)
        assert port.calls == [
            ("balance_sheet", older_day, True),
            ("balance_sheet", newer_day, True),
            ("balance_sheet", older_day, True),
            ("balance_sheet", newer_day, True),
        ]
        snapshot = snapshot_asof_evidence(
            snapshots=runtime.snapshots,
            lifecycle=runtime.lifecycle,
            dataset="balance_sheet",
            source="tushare",
            signal_date=signal,
        )
        assert snapshot is not None
        assert runtime.verifier.verify_asof_snapshot(
            dataset="balance_sheet",
            source="tushare",
            signal_date=signal,
            expected_snapshot_ids=snapshot.source_snapshot_ids,
            expected_row_count=snapshot.row_count,
        )
    finally:
        runtime.pool.close()


@pytest.mark.integration
def test_snapshot_without_success_log_is_rejected_until_replayed(
    tmp_path: Path,
) -> None:
    """完成快照缺 success log 时聚合可成,但三方交叉验证必须拒绝。"""
    runtime = _runtime(tmp_path / "runtime.sqlite")
    trade_date = "2026-07-01"
    frame = _frame(trade_date, 120.0)
    try:
        _process, port = _recovery_process(runtime, tmp_path, {trade_date: frame})
        assert port.ingest_date("balance_sheet", trade_date, force=True).status == (
            "success"
        )
        _delete_success_logs(runtime)
        snapshot = snapshot_asof_evidence(
            snapshots=runtime.snapshots,
            lifecycle=runtime.lifecycle,
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-16",
        )
        assert snapshot is not None
        assert not runtime.verifier.verify_asof_snapshot(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-16",
            expected_snapshot_ids=snapshot.source_snapshot_ids,
            expected_row_count=snapshot.row_count,
        )
    finally:
        runtime.pool.close()


@pytest.mark.integration
def test_sqlite_exact_verifier_accepts_match_and_rejects_log_mismatch(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path / "runtime.sqlite")
    trade_date = "2026-07-01"
    frame = _frame(trade_date, 120.0)
    try:
        _process, port = _recovery_process(runtime, tmp_path, {trade_date: frame})
        assert port.ingest_date("balance_sheet", trade_date, force=True).status == (
            "success"
        )
        log = runtime.logs.get_log("balance_sheet", "tushare", trade_date)
        assert log is not None
        checksum = log.checksum
        assert runtime.verifier.verify_exact_date(
            dataset="balance_sheet",
            source="tushare",
            trade_date=trade_date,
            checksum=checksum,
            row_count=1,
        )

        # 同 run 不同内容:log 校验和漂移后必须拒绝(skip 不再成立)。
        from ditto_data.models.ingestion import IngestionLog, IngestionStatus

        runtime.logs.save_log(
            IngestionLog(
                dataset="balance_sheet",
                source="tushare",
                trade_date=trade_date,
                status=IngestionStatus.SUCCESS,
                checksum="sha256:mismatch",
                rows=1,
            )
        )

        assert not runtime.verifier.verify_exact_date(
            dataset="balance_sheet",
            source="tushare",
            trade_date=trade_date,
            checksum=checksum,
            row_count=1,
        )
    finally:
        runtime.pool.close()
