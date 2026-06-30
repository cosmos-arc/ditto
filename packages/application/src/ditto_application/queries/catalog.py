"""DataCatalog query facade."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataCatalogReader,
    default_dataset_metadata,
)
from ditto_data.catalog.fallback_policy import CatalogSourceFallbackPolicyReader
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotionEvent,
    DatasetMaturityPromotionHistoryReader,
    DatasetMaturityPromotionRevocationReason,
)

from ditto_application.catalog_freshness import (
    assess_catalog_freshness,
    catalog_entry_for_date,
    dataset_namespace,
    select_ingestion_source,
)
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.catalog_source_health import (
    CatalogSourceFallbackPolicyEffect,
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
    revoked_promotion_count,
    selected_source_counts,
    source_health_attention_reasons,
    source_health_for_source,
    source_health_status_counts,
    source_selection_status_counts,
    to_source_fallback_policy_effect,
)
from ditto_application.queries.catalog_source_health import (
    source_selection_blockers as build_source_selection_blockers,
)
from ditto_application.queries.source_fallback_policy import (
    CatalogSourceFallbackPolicyAction,
    CatalogSourceFallbackPolicyActionCount,
    CatalogSourceFallbackPolicyPreview,
    CatalogSourceFallbackPolicyStatusCount,
    CatalogSourceFallbackPolicySummaryReport,
    build_source_fallback_policy_preview,
    build_source_fallback_policy_summary,
)
from ditto_application.source_fallback_policy_effect import (
    resolve_active_source_fallback_policy_effect,
)

__all__ = [
    "CatalogAsset",
    "CatalogAssetRef",
    "CatalogMaturityPromotionHistoryItem",
    "CatalogQueryFacade",
    "CatalogSchemaFingerprint",
    "CatalogSourceFallbackPolicyAction",
    "CatalogSourceFallbackPolicyActionCount",
    "CatalogSourceFallbackPolicyEffect",
    "CatalogSourceFallbackPolicyPreview",
    "CatalogSourceFallbackPolicyStatusCount",
    "CatalogSourceFallbackPolicySummaryReport",
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


class CatalogQueryFacade:
    """Read-only application facade over the data-owned catalog runtime."""

    def __init__(
        self,
        data_catalog_reader: DataCatalogReader,
        maturity_promotion_history_reader: DatasetMaturityPromotionHistoryReader
        | None = None,
        *,
        source_fallback_policy_reader: CatalogSourceFallbackPolicyReader | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._data_catalog_reader = data_catalog_reader
        self._maturity_promotion_history_reader = maturity_promotion_history_reader
        self._source_fallback_policy_reader = source_fallback_policy_reader
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
        catalog_selected_source = select_ingestion_source(
            dataset=dataset_id,
            trade_date=trade_date,
            available_sources=normalized_sources,
            catalog_reader=self._data_catalog_reader,
            now=self._now,
        )
        policy_effect = resolve_active_source_fallback_policy_effect(
            self._source_fallback_policy_reader,
            dataset=dataset_id,
            trade_date=trade_date,
            catalog_selected_source=catalog_selected_source,
        )
        selected_source = (
            policy_effect.effective_source
            if policy_effect is not None
            else catalog_selected_source
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
            selected_source_health=selected_source_health,
            source_selection_status=source_selection_status,
            source_selection_blockers=source_selection_blockers,
            attention_reasons=attention_reasons,
            sources=source_health,
            source_fallback_policy_effect=to_source_fallback_policy_effect(
                policy_effect
            ),
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
            revoked_promotion_count=revoked_promotion_count(reports),
            fallback_source_counts=fallback_source_counts(reports),
            attention_reason_counts=attention_reason_counts(reports),
            attention_severity_counts=attention_severity_counts(required_attention),
        )

    def get_source_fallback_policy_preview(
        self,
        *,
        dataset_id: str,
        trade_date: str,
        available_sources: tuple[str, ...],
    ) -> CatalogSourceFallbackPolicyPreview:
        """Return a read-only backend fallback-policy preview for one dataset/date."""
        report = self.get_source_health_report(
            dataset_id=dataset_id,
            trade_date=trade_date,
            available_sources=available_sources,
        )
        return build_source_fallback_policy_preview(report)

    def get_source_fallback_policy_summary(
        self,
        *,
        dataset_ids: tuple[str, ...],
        trade_dates: tuple[str, ...],
        available_sources: tuple[str, ...],
    ) -> CatalogSourceFallbackPolicySummaryReport:
        """Return aggregated backend fallback-policy previews."""
        source_health = self.get_source_health_summary(
            dataset_ids=dataset_ids,
            trade_dates=trade_dates,
            available_sources=available_sources,
        )
        previews = tuple(
            build_source_fallback_policy_preview(report)
            for report in source_health.reports
        )
        return build_source_fallback_policy_summary(
            dataset_ids=source_health.dataset_ids,
            trade_dates=source_health.trade_dates,
            available_sources=source_health.available_sources,
            previews=previews,
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


def _latest_revoked_promotion_event(
    events: tuple[DatasetMaturityPromotionEvent, ...],
) -> DatasetMaturityPromotionEvent | None:
    for event in reversed(events):
        if event.action == "revoked":
            return event
    return None


def _utcnow() -> datetime:
    return datetime.now(UTC)
