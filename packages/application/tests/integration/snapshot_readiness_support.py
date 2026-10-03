"""Snapshot readiness against real immutable SQLite evidence ledgers."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from ditto_application.queries.snapshot_readiness import (
    FieldRequirement,
    SnapshotReadinessQuery,
    SnapshotReadinessRequest,
)
from ditto_data.catalog.contracts import DataAssetRef
from ditto_data.catalog.source_snapshot import ProviderSnapshot, ProviderSnapshotDraft
from ditto_data.catalog.source_snapshot_store import SQLiteProviderSnapshotStore
from ditto_data.ingestion.partition_state import (
    PartitionCheckpoint,
    PartitionLifecycleStatus,
)
from ditto_data.ingestion.partition_state_store import SQLitePartitionLifecycleStore
from ditto_platform.foundation import SQLiteClient, SQLitePool

_DAY = date(2026, 9, 18)
_VISIBLE = datetime(2026, 9, 18, 9, tzinfo=UTC)


@contextmanager
def completed_evidence(
    *,
    day=_DAY,
    visible=_VISIBLE,
    complete=True,
    payload_retained=True,
    request_start=None,
    request_end=None,
    dataset_id="stock_daily",
):
    """One retained snapshot with its own ingestion lifecycle evidence."""
    directory = TemporaryDirectory(prefix="ditto-snapshot-readiness-")
    pool = SQLitePool(Path(directory.name) / "evidence.sqlite")
    client = SQLiteClient(pool)
    snapshots = SQLiteProviderSnapshotStore(client)
    snapshot = ProviderSnapshot.create(
        ProviderSnapshotDraft(
            dataset_id=dataset_id,
            source="tushare",
            request_start=(request_start or day).isoformat(),
            request_end=(request_end or day).isoformat(),
            schema_version="market.stock_daily.v1",
            checksum="abc",
            canonical_asset=DataAssetRef(dataset_id, "market"),
            request_parameters_hash="abc",
            response_metadata=(),
            license_record_id="synthetic-license",
            row_count=1,
            payload_uri="evidence://retained/synthetic" if payload_retained else None,
            payload_retained=payload_retained,
            created_at=datetime(2026, 9, 21, tzinfo=UTC),
        )
    )
    snapshots.append_snapshot(snapshot)
    lifecycle = SQLitePartitionLifecycleStore(client)
    lifecycle.plan_partition(
        PartitionCheckpoint(
            chunk_id="synthetic",
            dataset_id=snapshot.dataset_id,
            source=snapshot.source,
            request_start=snapshot.request_start,
            request_end=snapshot.request_end,
            status=PartitionLifecycleStatus.PLANNED,
            last_successful_stage=None,
            attempt=1,
            retry_budget=3,
            payload_id=None,
            complete_evidence_id=None,
            error_code=None,
            updated_at=visible,
        )
    )
    stages = (
        PartitionLifecycleStatus.PAYLOAD_COMMITTED,
        *((PartitionLifecycleStatus.COMPLETE,) if complete else ()),
    )
    for stage in stages:
        lifecycle.advance_partition(
            "synthetic",
            stage,
            occurred_at=visible,
            evidence_id=(
                f"payload:{snapshot.checksum}:synthetic:{snapshot.snapshot_id}"
                if stage is PartitionLifecycleStatus.PAYLOAD_COMMITTED
                else snapshot.snapshot_id
            ),
        )
    request = SnapshotReadinessRequest(
        fields=(
            FieldRequirement(
                dataset_id,
                "amount",
                snapshot.snapshot_id,
                "instruments.average_turnover",
            ),
        ),
        required_from=day,
        required_to=day,
    )
    try:
        yield SnapshotReadinessQuery(snapshots, lifecycle), request, snapshot
    finally:
        pool.close_all()
        directory.cleanup()


_CONSUMER_FIELDS = (
    "universe_snapshot_id",
    "membership_version",
    "market_context_feature_set_id",
    "instruments.instrument_id",
    "instruments.instrument_name",
    "instruments.industry_id",
    "instruments.average_turnover",
    "instruments.is_st",
    "instruments.is_suspended",
    "instruments.listing_days",
    "instruments.limit_state",
    "instruments.tracking_error",
    "industries.industry_id",
    "industries.industry_name",
    "industries.relative_strength_5d",
    "industries.relative_strength_20d",
    "industries.relative_strength_60d",
    "industries.advancing_count",
    "industries.declining_count",
    "industries.member_count",
    "industries.trend_score",
    "industries.fundamental_score",
    "industries.regime_alignment_score",
)


@contextmanager
def ready_selection(request, *, delist_on=None):
    """Bind one completed synthetic snapshot and a real historical pool."""
    with completed_evidence(
        day=request.as_of.date(), visible=request.knowledge_cutoff
    ) as (
        query,
        _,
        snapshot,
    ):
        from packages.application.tests.integration.historical_universe_support import (
            selection_history,
        )

        with selection_history(request, delist_on=delist_on) as (
            history,
            sources,
            universe_id,
        ):
            consumer_fields = (
                *_CONSUMER_FIELDS,
                *(
                    f"instruments.factor_values.{item.name}"
                    for item in request.selection_spec.factor_weights
                ),
            )
            bound = replace(
                request,
                data_fields=tuple(
                    FieldRequirement(
                        "stock_daily", "amount", snapshot.snapshot_id, consumer
                    )
                    for consumer in consumer_fields
                ),
                data_from=request.as_of.date(),
                data_to=request.as_of.date(),
                rotation_source_snapshot_ids=(snapshot.snapshot_id,),
                selection_source_snapshot_ids=(
                    snapshot.snapshot_id,
                    *sources.snapshot_ids,
                ),
                universe_sources=sources,
                universe_snapshot_id=universe_id,
            )
            yield query, bound, history
