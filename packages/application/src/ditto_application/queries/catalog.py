"""DataCatalog query facade."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    default_dataset_metadata,
)
from ditto_data.catalog.source_snapshot import ProviderSnapshotReader
from ditto_data.ingestion.partition_state import PartitionLifecycleReader

from ditto_application.catalog_freshness import (
    dataset_namespace,
    observed_at,
    select_ingestion_source,
    source_coverage_evidence,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.catalog_source_health import (
    CatalogSourceHealth,
    CatalogSourceHealthAttentionItem,
    CatalogSourceHealthAttentionReason,
    CatalogSourceHealthAttentionReasonCount,
    CatalogSourceHealthAttentionSeverity,
    CatalogSourceHealthAttentionSeverityCount,
    CatalogSourceHealthReport,
    CatalogSourceHealthStatusCount,
    CatalogSourceHealthSummaryReport,
    CatalogSourceSelectionBlocker,
    CatalogSourceSelectionCount,
    CatalogSourceSelectionStatus,
    CatalogSourceSelectionStatusCount,
    attention_reason_counts,
    attention_required,
    attention_severity_counts,
    failover_count,
    fallback_source_counts,
    no_fallback_source_count,
    selected_source_counts,
    source_health_attention_reasons,
    source_health_for_source,
    source_health_status_counts,
    source_selection_status_counts,
)
from ditto_application.queries.catalog_source_health import (
    source_selection_blockers as build_source_selection_blockers,
)

__all__ = [
    "CatalogAsset",
    "CatalogAssetRef",
    "CatalogQueryFacade",
    "CatalogSchemaFingerprint",
    "CatalogSourceHealth",
    "CatalogSourceHealthAttentionItem",
    "CatalogSourceHealthAttentionReason",
    "CatalogSourceHealthAttentionReasonCount",
    "CatalogSourceHealthAttentionSeverity",
    "CatalogSourceHealthAttentionSeverityCount",
    "CatalogSourceHealthReport",
    "CatalogSourceHealthStatusCount",
    "CatalogSourceHealthSummaryReport",
    "CatalogSourceSelectionBlocker",
    "CatalogSourceSelectionCount",
    "CatalogSourceSelectionStatus",
    "CatalogSourceSelectionStatusCount",
]


@dataclass(frozen=True)
class CatalogAssetRef:
    """Application-facing catalog asset identity."""

    dataset_id: str
    namespace: str
    partition_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogSchemaFingerprint:
    """Application-facing schema fingerprint metadata."""

    schema_hash: str
    row_count: int | None
    created_at: datetime | None


@dataclass(frozen=True)
class CatalogAsset:
    """Application-facing catalog asset metadata."""

    asset: CatalogAssetRef
    storage_uri: str
    schema: CatalogSchemaFingerprint
    source: str
    freshness_at: datetime


class CatalogQueryFacade:
    """Read-only application facade over the data-owned catalog runtime."""

    def __init__(
        self,
        data_catalog_reader: DataCatalogReader,
        *,
        snapshot_reader: ProviderSnapshotReader | None = None,
        lifecycle_reader: PartitionLifecycleReader | None = None,
    ) -> None:
        self._data_catalog_reader = data_catalog_reader
        self._snapshot_reader = snapshot_reader
        self._lifecycle_reader = lifecycle_reader

    def list_assets(
        self,
        *,
        namespace: str | None = None,
        dataset_id: str | None = None,
    ) -> tuple[CatalogAsset, ...]:
        """Return catalog assets, optionally filtered by namespace and dataset ID."""
        entries = self._data_catalog_reader.list_assets(namespace=namespace)
        if dataset_id is not None:
            entries = tuple(e for e in entries if e.asset.dataset_id == dataset_id)
        assets = tuple(_to_catalog_asset(entry) for entry in entries)
        return tuple(sorted(assets, key=_catalog_asset_sort_key))

    def get_asset(
        self,
        *,
        namespace: str,
        dataset_id: str,
        partition_keys: tuple[str, ...] = (),
    ) -> CatalogAsset | None:
        """Return one catalog asset by exact identity if registered."""
        entry = self._data_catalog_reader.get_asset(
            DataAssetRef(
                dataset_id=dataset_id,
                namespace=namespace,
                partition_keys=partition_keys,
            )
        )
        if entry is None:
            return None
        return _to_catalog_asset(entry)

    def get_source_health_report(
        self,
        *,
        dataset_id: str,
        trade_date: str,
        available_sources: tuple[str, ...],
    ) -> CatalogSourceHealthReport:
        """Return per-source catalog evidence used by automatic source selection."""
        metadata = default_dataset_metadata().get(dataset_id)
        normalized_sources = tuple(
            dict.fromkeys(source.lower() for source in available_sources)
        )
        if not normalized_sources:
            msg = "available_sources must not be empty"
            raise AppQueryError(msg)
        supported_sources = (
            metadata.supported_sources if metadata is not None else normalized_sources
        )
        candidate_sources = tuple(
            source for source in supported_sources if source in normalized_sources
        )
        default_source = (
            metadata.default_source
            if metadata is not None and metadata.default_source in candidate_sources
            else candidate_sources[0]
            if candidate_sources
            else normalized_sources[0]
        )
        selected_source = select_ingestion_source(
            dataset=dataset_id,
            trade_date=trade_date,
            available_sources=normalized_sources,
            snapshots=self._snapshot_reader,
            lifecycle=self._lifecycle_reader,
        )
        source_health = tuple(
            self._to_source_health(
                dataset_id=dataset_id,
                source=source,
                trade_date=trade_date,
            )
            for source in candidate_sources
        )
        fallback_sources = tuple(
            source for source in candidate_sources if source != default_source
        )
        unsupported_sources = tuple(
            source for source in normalized_sources if source not in candidate_sources
        )
        failover_from_default = selected_source != default_source
        selected_source_health = source_health_for_source(
            source_health,
            selected_source,
        )
        selected_freshness_status = selected_source_health.freshness_status
        source_selection_blockers = build_source_selection_blockers(
            selected_source_health
        )
        source_selection_status: CatalogSourceSelectionStatus = (
            "blocked" if source_selection_blockers else "ready"
        )
        attention_reasons = source_health_attention_reasons(
            selected_freshness_status=selected_freshness_status,
            failover_from_default=failover_from_default,
            fallback_sources=fallback_sources,
            unsupported_sources=unsupported_sources,
        )
        return CatalogSourceHealthReport(
            dataset_id=dataset_id,
            namespace=dataset_namespace(dataset_id),
            trade_date=trade_date,
            default_source=default_source,
            selected_source=selected_source,
            selected_freshness_status=selected_freshness_status,
            selected_source_health=selected_source_health,
            source_selection_status=source_selection_status,
            source_selection_blockers=source_selection_blockers,
            attention_reasons=attention_reasons,
            sources=source_health,
            unsupported_sources=unsupported_sources,
            failover_from_default=failover_from_default,
            fallback_sources=fallback_sources,
        )

    def get_source_health_summary(
        self,
        *,
        dataset_ids: tuple[str, ...],
        trade_dates: tuple[str, ...],
        available_sources: tuple[str, ...],
    ) -> CatalogSourceHealthSummaryReport:
        """Return aggregated source-health evidence for datasets and dates."""
        normalized_dataset_ids = _dedupe_tuple(dataset_ids)
        if not normalized_dataset_ids:
            msg = "dataset_ids must not be empty"
            raise AppQueryError(msg)
        normalized_trade_dates = _dedupe_tuple(trade_dates)
        if not normalized_trade_dates:
            msg = "trade_dates must not be empty"
            raise AppQueryError(msg)
        normalized_sources = _dedupe_tuple(
            tuple(source.lower() for source in available_sources)
        )
        if not normalized_sources:
            msg = "available_sources must not be empty"
            raise AppQueryError(msg)

        reports = tuple(
            self.get_source_health_report(
                dataset_id=dataset_id,
                trade_date=trade_date,
                available_sources=normalized_sources,
            )
            for dataset_id in normalized_dataset_ids
            for trade_date in normalized_trade_dates
        )
        status_counts = source_health_status_counts(reports)
        selected_counts = selected_source_counts(reports)
        required_attention = attention_required(reports)
        return CatalogSourceHealthSummaryReport(
            dataset_ids=normalized_dataset_ids,
            trade_dates=normalized_trade_dates,
            available_sources=normalized_sources,
            total_reports=len(reports),
            status_counts=status_counts,
            selected_source_counts=selected_counts,
            attention_required=required_attention,
            reports=reports,
            source_selection_status_counts=source_selection_status_counts(reports),
            failover_count=failover_count(reports),
            no_fallback_source_count=no_fallback_source_count(reports),
            fallback_source_counts=fallback_source_counts(reports),
            attention_reason_counts=attention_reason_counts(reports),
            attention_severity_counts=attention_severity_counts(required_attention),
        )

    def _to_source_health(
        self,
        *,
        dataset_id: str,
        source: str,
        trade_date: str,
    ) -> CatalogSourceHealth:
        """
        Per-source snapshot completion health for one dataset/date.

        #394:证据字段取覆盖该日期的最新 completed snapshot;没有完成事实
        端口时保持保守的 missing 视图。
        """
        if self._snapshot_reader is None or self._lifecycle_reader is None:
            return CatalogSourceHealth(
                source=source,
                supported=True,
                freshness_status="missing",
                freshness_sla_hours=None,
            )
        evidence = source_coverage_evidence(
            self._snapshot_reader,
            self._lifecycle_reader,
            dataset=dataset_id,
            source=source,
            trade_date=trade_date,
        )
        snapshot = evidence.snapshot
        return CatalogSourceHealth(
            source=source,
            supported=True,
            freshness_status=evidence.status,
            freshness_sla_hours=evidence.sla_hours,
            freshness_at=(observed_at(snapshot) if snapshot is not None else None),
            storage_uri=snapshot.payload_uri if snapshot is not None else None,
            schema_hash=(
                snapshot.schema_fingerprint or snapshot.schema_version
                if snapshot is not None
                else None
            ),
            row_count=snapshot.row_count if snapshot is not None else None,
        )


def _to_catalog_asset(entry: DataCatalogEntry) -> CatalogAsset:
    return CatalogAsset(
        asset=CatalogAssetRef(
            dataset_id=entry.asset.dataset_id,
            namespace=entry.asset.namespace,
            partition_keys=entry.asset.partition_keys,
        ),
        storage_uri=entry.storage_uri,
        schema=CatalogSchemaFingerprint(
            schema_hash=entry.schema.schema_hash,
            row_count=entry.schema.row_count,
            created_at=entry.schema.created_at,
        ),
        source=entry.source,
        freshness_at=entry.freshness_at,
    )


def _catalog_asset_sort_key(asset: CatalogAsset) -> tuple[str, str, tuple[str, ...]]:
    return (
        asset.asset.namespace,
        asset.asset.dataset_id,
        asset.asset.partition_keys,
    )


def _dedupe_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))
