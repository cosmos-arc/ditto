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
    catalog_asof_snapshot,
    catalog_source_snapshot_id,
)
from ditto_application.commands.quality_check import CheckDataQualityHandler
from ditto_application.processes.ingestion.data_writer import IngestionDataWriter
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
from ditto_data.catalog import DataAssetRef, DataCatalogEntry, DataSchemaFingerprint
from ditto_data.catalog.sqlite_store import SQLiteDataCatalog
from ditto_data.config.dataset_checksum import dataset_sort_keys
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.models.ingestion import IngestionLog, IngestionResult, IngestionStatus
from ditto_data.quality import DQSpec, QualityEngine
from ditto_data.storage.runtime.ingestion import IngestionLogReader, IngestionLogWriter
from ditto_platform.foundation import (
    ChecksumCompute,
    OnDuplicate,
    SQLiteClient,
    SQLitePool,
    WriteResult,
)


@dataclass(frozen=True)
class _SQLiteEvidenceRuntime:
    pool: SQLitePool
    catalog: SQLiteDataCatalog
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


def _runtime(db_path: Path) -> _SQLiteEvidenceRuntime:
    pool = SQLitePool(str(db_path))
    client = SQLiteClient(pool)
    catalog = SQLiteDataCatalog(client)
    logs = IngestionLogStore(
        IngestionLogReader(client),
        IngestionLogWriter(client),
    )
    return _SQLiteEvidenceRuntime(
        pool=pool,
        catalog=catalog,
        logs=logs,
        verifier=PersistedIngestionEvidenceVerifier(
            reader=catalog,
            ingestion_logs=logs,
        ),
    )


def _frame(trade_date: str, value: float) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "instrument_id": [1001],
            "trade_date": [date.fromisoformat(trade_date)],
            "knowledge_date": [date.fromisoformat(trade_date)],
            "total_assets": [value],
        }
    )


def _seed_physical_component(
    runtime: _SQLiteEvidenceRuntime,
    root: Path,
    *,
    trade_date: str,
    frame: pl.DataFrame,
    attested: bool,
    with_success_log: bool,
    with_physical_data: bool = True,
) -> str:
    relative_path = Path("balance_sheet") / f"{trade_date}.parquet"
    physical_path = root / relative_path
    if with_physical_data:
        physical_path.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(physical_path)
    checksum = ChecksumCompute.from_dataframe(
        frame,
        dataset_sort_keys("balance_sheet"),
    )
    runtime.catalog.upsert_asset(
        DataCatalogEntry(
            asset=DataAssetRef(
                dataset_id="balance_sheet",
                namespace="fundamental",
                partition_keys=(f"trade_date={trade_date}",),
            ),
            storage_uri=relative_path.as_posix(),
            schema=DataSchemaFingerprint(
                schema_hash="fundamental.balance_sheet.v1",
                row_count=frame.height,
            ),
            source="tushare",
            freshness_at=datetime(2026, 7, 16, tzinfo=UTC),
            source_snapshot_id=catalog_source_snapshot_id(
                dataset="balance_sheet",
                trade_date=trade_date,
                source="tushare",
                checksum=checksum,
                l1_l2_attested=attested,
            ),
        )
    )
    if with_success_log:
        runtime.logs.save_log(
            IngestionLog(
                dataset="balance_sheet",
                source="tushare",
                trade_date=trade_date,
                status=IngestionStatus.SUCCESS,
                checksum=checksum,
                rows=frame.height,
            )
        )
    assert physical_path.is_file() is with_physical_data
    return checksum


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
    )
    port = _PostIngestSparsePort(frames=frames, context=context)
    return (
        SparsePITReattestationProcess(
            ingestion=port,
            catalog=runtime.catalog,
            verifier=runtime.verifier,
        ),
        port,
    )


@pytest.mark.integration
def test_mixed_legacy_history_fails_then_full_recovery_succeeds_idempotently(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path / "runtime.sqlite")
    frames = {
        "2026-06-15": _frame("2026-06-15", 100.0),
        "2026-07-01": _frame("2026-07-01", 120.0),
    }
    try:
        _seed_physical_component(
            runtime,
            tmp_path,
            trade_date="2026-06-15",
            frame=frames["2026-06-15"],
            attested=False,
            with_success_log=True,
        )
        _seed_physical_component(
            runtime,
            tmp_path,
            trade_date="2026-07-01",
            frame=frames["2026-07-01"],
            attested=True,
            with_success_log=True,
        )
        assert (
            catalog_asof_snapshot(
                reader=runtime.catalog,
                dataset="balance_sheet",
                source="tushare",
                signal_date="2026-07-16",
            )
            is None
        )
        process, port = _recovery_process(runtime, tmp_path, frames)
        request = SparsePITReattestationRequest(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-16",
        )

        first = process.run(request)
        second = process.run(request)

        assert first.passed is True
        assert second.passed is True
        assert second.source_snapshot_id == first.source_snapshot_id
        assert first.component_dates == ("2026-06-15", "2026-07-01")
        assert port.calls == [
            ("balance_sheet", "2026-06-15", True),
            ("balance_sheet", "2026-07-01", True),
            ("balance_sheet", "2026-06-15", True),
            ("balance_sheet", "2026-07-01", True),
        ]
        snapshot = catalog_asof_snapshot(
            reader=runtime.catalog,
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-16",
        )
        assert snapshot is not None
        assert runtime.verifier.verify_asof_snapshot(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-16",
            expected_snapshot_ids=snapshot.source_snapshot_ids,
            expected_row_count=snapshot.row_count,
        )
    finally:
        runtime.pool.close()


@pytest.mark.integration
def test_catalog_only_component_without_physical_data_or_log_is_recovered(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path / "runtime.sqlite")
    trade_date = "2026-07-01"
    frame = _frame(trade_date, 120.0)
    try:
        _seed_physical_component(
            runtime,
            tmp_path,
            trade_date=trade_date,
            frame=frame,
            attested=True,
            with_success_log=False,
            with_physical_data=False,
        )
        physical_path = tmp_path / "balance_sheet" / f"{trade_date}.parquet"
        assert not physical_path.exists()
        snapshot = catalog_asof_snapshot(
            reader=runtime.catalog,
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
        process, _ = _recovery_process(
            runtime,
            tmp_path,
            {trade_date: frame},
        )

        result = process.run(
            SparsePITReattestationRequest(
                dataset="balance_sheet",
                source="tushare",
                signal_date="2026-07-16",
            )
        )

        assert result.passed is True
        assert physical_path.is_file()
        assert runtime.logs.get_log("balance_sheet", "tushare", trade_date) is not None
        assert runtime.verifier.verify_asof_snapshot(
            dataset="balance_sheet",
            source="tushare",
            signal_date="2026-07-16",
            expected_snapshot_ids=result.source_snapshot_ids,
            expected_row_count=cast(int, result.row_count),
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
        checksum = _seed_physical_component(
            runtime,
            tmp_path,
            trade_date=trade_date,
            frame=frame,
            attested=True,
            with_success_log=True,
        )
        assert runtime.verifier.verify_exact_date(
            dataset="balance_sheet",
            source="tushare",
            trade_date=trade_date,
            checksum=checksum,
            row_count=1,
        )

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
