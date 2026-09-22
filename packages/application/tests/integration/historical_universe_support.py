"""Recorded synthetic universe evidence in real SQLite and retained Parquet."""

from contextlib import contextmanager
from datetime import UTC, date, datetime

import polars as pl
from ditto_application.queries.historical_universe import HistoricalUniverseSources
from ditto_data.catalog.certification import (
    CertificationEvidence,
    DatasetCertificationReport,
    EvidenceCheck,
)
from ditto_data.catalog.certification_store import SQLiteCertificationStore
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.coverage import DatasetCoverage
from ditto_data.catalog.field_evidence import CertifiedField
from ditto_data.catalog.license import DatasetLicenseDraft, DatasetLicenseRecord
from ditto_data.catalog.license_store import SQLiteDatasetLicenseStore
from ditto_data.catalog.provider_payload import (
    FilesystemProviderPayloadStore,
    schema_fingerprint,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore

VISIBLE = datetime(2026, 1, 1, tzinfo=UTC)
START = date(2026, 1, 1)
END = date(2026, 12, 31)


def retain_history(
    client,
    root,
    dataset_id,
    frame,
    *,
    complete=True,
    observed=VISIBLE,
    certify=True,
):
    payload = FilesystemProviderPayloadStore(root).retain_payload(
        dataset_id=dataset_id,
        source="recorded",
        payload=frame,
    )
    license_record = DatasetLicenseRecord.create(
        DatasetLicenseDraft(
            dataset_id=dataset_id,
            source="recorded",
            terms_version="synthetic-v1",
            effective_from=date(2020, 1, 1),
            effective_to=None,
            local_cache="allowed",
            display="allowed",
            derivative_compute="allowed",
            redistribution="prohibited",
            notes="synthetic only",
            reviewed_by="test",
            reviewed_at=VISIBLE,
        )
    )
    SQLiteDatasetLicenseStore(client).append_license(license_record)
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset_id,
            source="recorded",
            request_start=START.isoformat(),
            request_end=END.isoformat(),
            schema_version=f"{dataset_id}.history.v1",
            checksum=payload.checksum,
            canonical_asset=DataAssetRef(dataset_id, "metadata"),
            request_parameters_hash="recorded",
            response_metadata=(),
            license_record_id=license_record.record_id,
            row_count=frame.height,
            payload_uri=payload.uri,
            payload_retained=True,
            created_at=VISIBLE,
            schema_fingerprint=schema_fingerprint(frame),
        )
    )
    SQLiteProviderSnapshotStore(client, now=lambda: observed).append_snapshot(snapshot)
    lifecycle = SQLitePartitionLifecycleStore(client)
    chunk = snapshot.snapshot_id
    if lifecycle.get_checkpoint(chunk) is None:
        lifecycle.plan_partition(
            PartitionCheckpoint(
                chunk_id=chunk,
                dataset_id=dataset_id,
                source="recorded",
                request_start=START.isoformat(),
                request_end=END.isoformat(),
                status=PartitionLifecycleStatus.PLANNED,
                last_successful_stage=None,
                attempt=1,
                retry_budget=3,
                payload_id=None,
                catalog_asset_id=None,
                lineage_run_id=None,
                ingestion_log_id=None,
                error_code=None,
                updated_at=VISIBLE,
            )
        )
        for stage in (
            PartitionLifecycleStatus.FETCHED,
            PartitionLifecycleStatus.NORMALIZED,
            PartitionLifecycleStatus.PIT_PASSED,
            PartitionLifecycleStatus.DQ_PASSED,
            PartitionLifecycleStatus.PAYLOAD_COMMITTED,
            PartitionLifecycleStatus.CATALOG_ATTESTED,
            PartitionLifecycleStatus.LINEAGE_RECORDED,
            PartitionLifecycleStatus.SUCCESS_RECORDED,
            *((PartitionLifecycleStatus.COMPLETE,) if complete else ()),
        ):
            lifecycle.advance_partition(
                chunk,
                stage,
                occurred_at=VISIBLE,
                evidence_id=(
                    f"payload:{snapshot.checksum}:synthetic:{chunk}"
                    if stage is PartitionLifecycleStatus.PAYLOAD_COMMITTED
                    else chunk
                ),
            )
    if not complete:
        return snapshot
    if certify:
        certify_snapshots(client, dataset_id, ((snapshot, frame, observed),))
    return snapshot


def certify_snapshots(client, dataset_id, members):
    """One active report covering every retained chain member of a dataset."""
    check = (EvidenceCheck("recorded", "evidence://synthetic", True),)
    fields: list[CertifiedField] = []
    for snapshot, frame, observed in members:
        fields.extend(
            CertifiedField(
                field=field,
                snapshot_id=snapshot.snapshot_id,
                instrument_ids=tuple(sorted(set(frame["instrument_id"].to_list()))),
                covered_from=START,
                covered_to=END,
                available_at=VISIBLE,
                publication_at=VISIBLE,
                time_precision="timestamp",
                observed_at=observed,
                evidence_uri="evidence://synthetic",
            )
            for field in frame.columns
        )
    report = DatasetCertificationReport.create(
        dataset_id=dataset_id,
        profile="selection-fields-v1",
        coverage=DatasetCoverage(
            dataset_id=dataset_id,
            schedule="trading_days",
            target_from=START,
            target_to=END,
            native_from=START,
            native_to=END,
            actual_from=START,
            actual_to=END,
            raw_from=START,
            complete_from=START,
            expected_partitions=len(members),
            actual_partitions=len(members),
            gaps=(),
            exceptions=(),
            collected_at=VISIBLE,
        ),
        evidence=CertificationEvidence(
            source_ids=("recorded",),
            schema_versions=tuple(
                dict.fromkeys(snapshot.schema_version for snapshot, _, _ in members)
            ),
            snapshot_ids=tuple(snapshot.snapshot_id for snapshot, _, _ in members),
            dq_rule_version="test-v1",
            dq_results=check,
            pit_replay_results=check,
            fallback_history=("none",),
            override_history=(),
            freshness_results=check,
            recovery_results=check,
            license_record_ids=tuple(
                dict.fromkeys(snapshot.license_record_id for snapshot, _, _ in members)
            ),
            consumer_results=check,
            certified_fields=tuple(fields),
        ),
        generated_at=VISIBLE,
    )
    reports = SQLiteCertificationStore(client)
    reports.append_report(report)
    reports.approve_report(report.report_id, reviewer="test", reviewed_at=VISIBLE)
    return report


def history_frames(ids=(1,), *, asset_kind="stock"):
    common = {
        "instrument_id": list(ids),
        "effective_from": [date(2020, 1, 1)] * len(ids),
        "effective_to": [None] * len(ids),
        "available_at": [VISIBLE] * len(ids),
        "publication_at": [VISIBLE] * len(ids),
    }
    master = pl.DataFrame(
        {
            **common,
            "list_date": [date(2020, 1, 1)] * len(ids),
            "delist_date": [None] * len(ids),
        },
        schema_overrides={"effective_to": pl.Date, "delist_date": pl.Date},
    )
    if asset_kind == "etf":
        master = master.with_columns(pl.lit("csi300").alias("tracking_index"))
    status = pl.DataFrame(
        {**common, "is_suspended": [False] * len(ids)},
        schema_overrides={"effective_to": pl.Date},
    )
    return master, status


def seed_history(
    client,
    root,
    *,
    asset_kind="stock",
    ids=(1,),
    universe_id="universe.cn.all",
    delist_on=None,
):
    master, status = history_frames(ids, asset_kind=asset_kind)
    if delist_on is not None:
        master = master.with_columns(pl.lit(delist_on).alias("delist_date"))
    primary = retain_history(client, root, f"{asset_kind}_basic", master)
    trading = retain_history(
        client, root, "stock_status" if asset_kind == "stock" else "etf_daily", status
    )
    return HistoricalUniverseSources(
        universe_id,
        asset_kind,
        (primary.snapshot_id,),
        (trading.snapshot_id,),
    )


@contextmanager
def selection_history(request, *, delist_on=None):
    """Provide a real historical pool matching the declared synthetic instruments."""
    from pathlib import Path
    from tempfile import TemporaryDirectory

    from ditto_application.processes.selection.facade import EtfSelectionSpecDraft
    from ditto_application.queries.field_admission import FieldAdmissionQuery
    from ditto_application.queries.historical_universe import HistoricalUniverseQuery
    from ditto_data.catalog.snapshot_reader import SnapshotReadService
    from ditto_platform.foundation import SQLiteClient, SQLitePool

    with TemporaryDirectory() as directory:
        root = Path(directory)
        pool = SQLitePool(root / "history.sqlite")
        try:
            client = SQLiteClient(pool)
            kind = (
                "etf"
                if isinstance(request.selection_spec, EtfSelectionSpecDraft)
                else "stock"
            )
            sources = seed_history(
                client,
                root,
                asset_kind=kind,
                delist_on=delist_on,
                ids=tuple(int(x.instrument_id) for x in request.instruments),
            )
            snapshots = SQLiteProviderSnapshotStore(client)
            lifecycle = SQLitePartitionLifecycleStore(client)
            query = HistoricalUniverseQuery(
                SnapshotReadService(
                    snapshots, FilesystemProviderPayloadStore(root), lifecycle
                ),
                FieldAdmissionQuery(
                    snapshots,
                    SQLiteDatasetLicenseStore(client),
                    SQLiteCertificationStore(client),
                    lifecycle,
                ),
            )
            result = query.resolve(
                sources,
                as_of=request.as_of.date(),
                knowledge_cutoff=request.knowledge_cutoff,
                publication_cutoff=request.publication_cutoff,
            )
            yield query, sources, result.snapshot_id
        finally:
            pool.close_all()
