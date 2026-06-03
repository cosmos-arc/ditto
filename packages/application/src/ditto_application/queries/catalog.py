"""DataCatalog query facade."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    default_dataset_metadata,
)
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotionEvent,
    DatasetMaturityPromotionHistoryReader,
    DatasetMaturityPromotionRevocationReason,
)

from ditto_application.catalog_freshness import (
    CatalogFreshnessStatus,
    assess_catalog_freshness,
    catalog_entry_for_date,
    dataset_namespace,
    select_ingestion_source,
)
from ditto_application.exceptions import AppQueryError

__all__ = [
    "CatalogAsset",
    "CatalogAssetRef",
    "CatalogMaturityPromotionHistoryItem",
    "CatalogQueryFacade",
    "CatalogSchemaFingerprint",
    "CatalogSourceHealth",
    "CatalogSourceHealthAttentionItem",
    "CatalogSourceHealthAttentionReason",
    "CatalogSourceHealthAttentionReasonCount",
    "CatalogSourceHealthReport",
    "CatalogSourceHealthStatusCount",
    "CatalogSourceHealthSummaryReport",
    "CatalogSourceSelectionCount",
]

type CatalogSourceHealthAttentionReason = Literal[
    "selected_source_missing",
    "selected_source_stale",
    "selected_source_not_applicable",
    "default_source_failover",
    "no_fallback_source",
    "unsupported_sources_present",
    "latest_maturity_promotion_revoked",
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


@dataclass(frozen=True)
class CatalogMaturityPromotionHistoryItem:
    """Application-facing maturity promotion governance event."""

    dataset_id: str
    action: str
    previous_maturity: str
    next_maturity: str
    actor: str
    action_at: datetime | None
    evidence_uri: str | None = None
    revocation_reason: DatasetMaturityPromotionRevocationReason | None = None
    notes: str | None = None


@dataclass(frozen=True)
class CatalogSourceHealth:
    """Per-source catalog freshness evidence for one dataset/date."""

    source: str
    supported: bool
    freshness_status: CatalogFreshnessStatus
    freshness_sla_hours: int | None
    freshness_at: datetime | None = None
    storage_uri: str | None = None
    schema_hash: str | None = None
    row_count: int | None = None


@dataclass(frozen=True)
class CatalogSourceHealthReport:
    """Application-facing source health report for `source=auto` decisions."""

    dataset_id: str
    namespace: str
    trade_date: str
    default_source: str
    selected_source: str
    selected_freshness_status: CatalogFreshnessStatus
    attention_reasons: tuple[CatalogSourceHealthAttentionReason, ...]
    sources: tuple[CatalogSourceHealth, ...]
    unsupported_sources: tuple[str, ...] = ()
    failover_from_default: bool = False
    fallback_sources: tuple[str, ...] = ()
    latest_revocation_reason: DatasetMaturityPromotionRevocationReason | None = None
    latest_revoked_by: str | None = None
    latest_revoked_at: datetime | None = None


@dataclass(frozen=True)
class CatalogSourceHealthStatusCount:
    """Aggregated freshness status count across source-health reports."""

    status: CatalogFreshnessStatus
    count: int


@dataclass(frozen=True)
class CatalogSourceSelectionCount:
    """Aggregated selected-source count across source-health reports."""

    source: str
    count: int


@dataclass(frozen=True)
class CatalogSourceHealthAttentionReasonCount:
    """Aggregated attention reason count across source-health reports."""

    reason: CatalogSourceHealthAttentionReason
    count: int


@dataclass(frozen=True)
class CatalogSourceHealthAttentionItem:
    """One source-health summary item that needs operator attention."""

    dataset_id: str
    trade_date: str
    selected_source: str
    selected_freshness_status: CatalogFreshnessStatus
    attention_reasons: tuple[CatalogSourceHealthAttentionReason, ...]
    unsupported_sources: tuple[str, ...] = ()
    failover_from_default: bool = False
    fallback_sources: tuple[str, ...] = ()
    latest_revocation_reason: DatasetMaturityPromotionRevocationReason | None = None
    latest_revoked_by: str | None = None
    latest_revoked_at: datetime | None = None


@dataclass(frozen=True)
class CatalogSourceHealthSummaryReport:
    """Aggregated source-health report for backend diagnostics."""

    dataset_ids: tuple[str, ...]
    trade_dates: tuple[str, ...]
    available_sources: tuple[str, ...]
    total_reports: int
    status_counts: tuple[CatalogSourceHealthStatusCount, ...]
    selected_source_counts: tuple[CatalogSourceSelectionCount, ...]
    attention_required: tuple[CatalogSourceHealthAttentionItem, ...]
    reports: tuple[CatalogSourceHealthReport, ...]
    failover_count: int = 0
    no_fallback_source_count: int = 0
    revoked_promotion_count: int = 0
    fallback_source_counts: tuple[CatalogSourceSelectionCount, ...] = ()
    attention_reason_counts: tuple[CatalogSourceHealthAttentionReasonCount, ...] = ()


class CatalogQueryFacade:
    """Read-only application facade over the data-owned catalog runtime."""

    def __init__(
        self,
        data_catalog_reader: DataCatalogReader,
        maturity_promotion_history_reader: DatasetMaturityPromotionHistoryReader
        | None = None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._data_catalog_reader = data_catalog_reader
        self._maturity_promotion_history_reader = maturity_promotion_history_reader
        self._now = now or _utcnow

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

    def list_maturity_promotion_history(
        self,
        dataset_id: str,
    ) -> tuple[CatalogMaturityPromotionHistoryItem, ...]:
        """Return maturity promotion governance history for one dataset."""
        if self._maturity_promotion_history_reader is None:
            return ()
        history_reader = self._maturity_promotion_history_reader
        events = history_reader.list_dataset_maturity_promotion_events(dataset_id)
        return tuple(
            CatalogMaturityPromotionHistoryItem(
                dataset_id=event.dataset_id,
                action=event.action,
                previous_maturity=event.previous_maturity,
                next_maturity=event.next_maturity,
                actor=event.actor,
                action_at=event.action_at,
                evidence_uri=event.evidence_uri,
                revocation_reason=event.revocation_reason,
                notes=event.notes,
            )
            for event in events
        )

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
            catalog_reader=self._data_catalog_reader,
            now=self._now,
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
        latest_revocation = self._latest_revocation(dataset_id)
        unsupported_sources = tuple(
            source for source in normalized_sources if source not in candidate_sources
        )
        failover_from_default = selected_source != default_source
        selected_freshness_status = _source_health_status_for_source(
            source_health,
            selected_source,
        )
        attention_reasons = _source_health_attention_reasons(
            selected_freshness_status=selected_freshness_status,
            failover_from_default=failover_from_default,
            fallback_sources=fallback_sources,
            unsupported_sources=unsupported_sources,
            latest_revocation_reason=latest_revocation.revocation_reason
            if latest_revocation is not None
            else None,
        )
        return CatalogSourceHealthReport(
            dataset_id=dataset_id,
            namespace=dataset_namespace(dataset_id),
            trade_date=trade_date,
            default_source=default_source,
            selected_source=selected_source,
            selected_freshness_status=selected_freshness_status,
            attention_reasons=attention_reasons,
            sources=source_health,
            unsupported_sources=unsupported_sources,
            failover_from_default=failover_from_default,
            fallback_sources=fallback_sources,
            latest_revocation_reason=latest_revocation.revocation_reason
            if latest_revocation is not None
            else None,
            latest_revoked_by=latest_revocation.actor
            if latest_revocation is not None
            else None,
            latest_revoked_at=latest_revocation.action_at
            if latest_revocation is not None
            else None,
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
        status_counts = _source_health_status_counts(reports)
        selected_counts = _selected_source_counts(reports)
        attention_required = _attention_required(reports)
        return CatalogSourceHealthSummaryReport(
            dataset_ids=normalized_dataset_ids,
            trade_dates=normalized_trade_dates,
            available_sources=normalized_sources,
            total_reports=len(reports),
            status_counts=status_counts,
            selected_source_counts=selected_counts,
            attention_required=attention_required,
            reports=reports,
            failover_count=_failover_count(reports),
            no_fallback_source_count=_no_fallback_source_count(reports),
            revoked_promotion_count=_revoked_promotion_count(reports),
            fallback_source_counts=_fallback_source_counts(reports),
            attention_reason_counts=_attention_reason_counts(reports),
        )

    def _to_source_health(
        self,
        *,
        dataset_id: str,
        source: str,
        trade_date: str,
    ) -> CatalogSourceHealth:
        entry = catalog_entry_for_date(
            reader=self._data_catalog_reader,
            dataset=dataset_id,
            source=source,
            trade_date=trade_date,
        )
        freshness = assess_catalog_freshness(
            dataset=dataset_id,
            catalog_entry=entry,
            now=self._now,
        )
        return CatalogSourceHealth(
            source=source,
            supported=True,
            freshness_status=freshness.status,
            freshness_sla_hours=freshness.sla_hours,
            freshness_at=entry.freshness_at if entry is not None else None,
            storage_uri=entry.storage_uri if entry is not None else None,
            schema_hash=entry.schema.schema_hash if entry is not None else None,
            row_count=entry.schema.row_count if entry is not None else None,
        )

    def _latest_revocation(
        self,
        dataset_id: str,
    ) -> DatasetMaturityPromotionEvent | None:
        history_reader = self._maturity_promotion_history_reader
        if history_reader is None:
            return None
        return _latest_revoked_promotion_event(
            history_reader.list_dataset_maturity_promotion_events(dataset_id)
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


def _source_health_status_counts(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceHealthStatusCount, ...]:
    counts: dict[CatalogFreshnessStatus, int] = {
        "fresh": 0,
        "stale": 0,
        "missing": 0,
        "not_applicable": 0,
    }
    for report in reports:
        for source in report.sources:
            counts[source.freshness_status] += 1
    return tuple(
        CatalogSourceHealthStatusCount(status=status, count=count)
        for status, count in counts.items()
    )


def _selected_source_counts(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceSelectionCount, ...]:
    counts: dict[str, int] = {}
    for report in reports:
        counts[report.selected_source] = counts.get(report.selected_source, 0) + 1
    return tuple(
        CatalogSourceSelectionCount(source=source, count=counts[source])
        for source in sorted(counts)
    )


def _attention_required(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceHealthAttentionItem, ...]:
    return tuple(
        CatalogSourceHealthAttentionItem(
            dataset_id=report.dataset_id,
            trade_date=report.trade_date,
            selected_source=report.selected_source,
            selected_freshness_status=status,
            attention_reasons=report.attention_reasons,
            unsupported_sources=report.unsupported_sources,
            failover_from_default=report.failover_from_default,
            fallback_sources=report.fallback_sources,
            latest_revocation_reason=report.latest_revocation_reason,
            latest_revoked_by=report.latest_revoked_by,
            latest_revoked_at=report.latest_revoked_at,
        )
        for report in reports
        for status in (_selected_source_status(report),)
        if report.attention_reasons
    )


def _failover_count(reports: tuple[CatalogSourceHealthReport, ...]) -> int:
    return sum(1 for report in reports if report.failover_from_default)


def _no_fallback_source_count(reports: tuple[CatalogSourceHealthReport, ...]) -> int:
    return sum(1 for report in reports if not report.fallback_sources)


def _revoked_promotion_count(reports: tuple[CatalogSourceHealthReport, ...]) -> int:
    return sum(1 for report in reports if report.latest_revocation_reason is not None)


def _fallback_source_counts(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceSelectionCount, ...]:
    counts: dict[str, int] = {}
    for report in reports:
        for source in report.fallback_sources:
            counts[source] = counts.get(source, 0) + 1
    return tuple(
        CatalogSourceSelectionCount(source=source, count=counts[source])
        for source in sorted(counts)
    )


def _attention_reason_counts(
    reports: tuple[CatalogSourceHealthReport, ...],
) -> tuple[CatalogSourceHealthAttentionReasonCount, ...]:
    counts: dict[CatalogSourceHealthAttentionReason, int] = {}
    for report in reports:
        for reason in report.attention_reasons:
            counts[reason] = counts.get(reason, 0) + 1
    return tuple(
        CatalogSourceHealthAttentionReasonCount(
            reason=reason,
            count=counts[reason],
        )
        for reason in sorted(counts)
    )


def _selected_source_status(
    report: CatalogSourceHealthReport,
) -> CatalogFreshnessStatus:
    return _source_health_status_for_source(report.sources, report.selected_source)


def _source_health_status_for_source(
    sources: tuple[CatalogSourceHealth, ...],
    selected_source: str,
) -> CatalogFreshnessStatus:
    for source in sources:
        if source.source == selected_source:
            return source.freshness_status
    return "missing"


def _source_health_attention_reasons(
    *,
    selected_freshness_status: CatalogFreshnessStatus,
    failover_from_default: bool,
    fallback_sources: tuple[str, ...],
    unsupported_sources: tuple[str, ...],
    latest_revocation_reason: DatasetMaturityPromotionRevocationReason | None,
) -> tuple[CatalogSourceHealthAttentionReason, ...]:
    reasons: list[CatalogSourceHealthAttentionReason] = []
    if selected_freshness_status == "stale":
        reasons.append("selected_source_stale")
    elif selected_freshness_status == "missing":
        reasons.append("selected_source_missing")
    elif selected_freshness_status == "not_applicable":
        reasons.append("selected_source_not_applicable")

    if failover_from_default:
        reasons.append("default_source_failover")
    if selected_freshness_status != "fresh" and not fallback_sources:
        reasons.append("no_fallback_source")
    if unsupported_sources:
        reasons.append("unsupported_sources_present")
    if latest_revocation_reason is not None:
        reasons.append("latest_maturity_promotion_revoked")
    return tuple(reasons)


def _latest_revoked_promotion_event(
    events: tuple[DatasetMaturityPromotionEvent, ...],
) -> DatasetMaturityPromotionEvent | None:
    for event in reversed(events):
        if event.action == "revoked":
            return event
    return None


def _utcnow() -> datetime:
    return datetime.now(UTC)
