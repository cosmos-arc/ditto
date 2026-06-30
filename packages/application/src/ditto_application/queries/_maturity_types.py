"""
Leaf DTOs for dataset maturity & promotion readiness.

Extracted from ``ingestion_status`` to break the ``ingestion_status ->
_maturity_governance`` import cycle. CLAUDE.md forbids runtime-deferred
type-only imports (the typing guard pattern), so both ``ingestion_status``
and ``_maturity_governance`` import these eagerly. ``ingestion_status``
re-exports every name under the same symbol so its internal call sites (and
any existing consumers) need no change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ditto_data.catalog.promotion import (
    DatasetMaturityPromotionRevocationReason,
    DatasetPromotionStatus,
)

from ditto_application.catalog_freshness import CatalogFreshnessStatus

__all__ = [
    "DatasetMaturitySummary",
    "DatasetPromotionCriterionCount",
    "DatasetPromotionReadinessItem",
    "DatasetPromotionReadinessReport",
    "DatasetPromotionReadinessSourceFallbackPolicyEffectCount",
    "DatasetPromotionStatusCount",
    "DatasetStatus",
]


@dataclass(frozen=True, slots=True)
class DatasetStatus:
    """单个数据集的摄取状态."""

    dataset: str
    latest_date: str | None
    latest_status: str | None
    dataset_maturity: str | None
    record_count: int
    last_attempt: str | None
    dataset_maturity_warning: str | None = None
    dataset_promotion_criteria: tuple[str, ...] = ()
    dataset_promotion_status: str | None = None
    dataset_promotion_missing_criteria: tuple[str, ...] = ()
    dataset_promotion_satisfied_criteria: tuple[str, ...] = ()
    dataset_promotion_rejected_criteria: tuple[str, ...] = ()
    latest_revocation_reason: DatasetMaturityPromotionRevocationReason | None = None
    latest_revoked_by: str | None = None
    latest_revoked_at: datetime | None = None
    catalog_freshness_at: datetime | None = None
    catalog_storage_uri: str | None = None
    catalog_schema_hash: str | None = None
    catalog_row_count: int | None = None
    catalog_freshness_status: CatalogFreshnessStatus | None = None
    catalog_freshness_sla_hours: int | None = None


@dataclass(frozen=True, slots=True)
class DatasetMaturitySummary:
    """Maturity-aware operational status summary."""

    maturity: str
    dataset_count: int
    fresh_count: int
    stale_count: int
    missing_count: int
    not_applicable_count: int
    failed_count: int
    warning_count: int
    promotion_ready_count: int
    promotion_blocked_count: int


@dataclass(frozen=True, slots=True)
class DatasetPromotionStatusCount:
    """Promotion readiness status count."""

    status: DatasetPromotionStatus
    count: int


@dataclass(frozen=True, slots=True)
class DatasetPromotionCriterionCount:
    """Promotion criterion occurrence count across datasets."""

    criterion: str
    count: int


@dataclass(frozen=True, slots=True)
class DatasetPromotionReadinessSourceFallbackPolicyEffectCount:
    """Promotion readiness count by active source fallback policy effect."""

    policy_id: str
    policy_status: str
    catalog_selected_source: str
    effective_selected_source: str
    count: int


@dataclass(frozen=True, slots=True)
class DatasetPromotionReadinessItem:
    """Dataset-level promotion readiness assessment."""

    dataset_id: str
    metadata_maturity: str | None
    current_maturity: str | None
    promotion_status: DatasetPromotionStatus
    active_maturity_promotion: bool
    required_criteria: tuple[str, ...]
    satisfied_criteria: tuple[str, ...]
    missing_criteria: tuple[str, ...]
    rejected_criteria: tuple[str, ...]
    latest_revocation_reason: DatasetMaturityPromotionRevocationReason | None = None
    latest_revoked_by: str | None = None
    latest_revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DatasetPromotionReadinessReport:
    """Aggregated promotion readiness report."""

    dataset_count: int
    promotable_count: int
    active_promotion_count: int
    status_counts: tuple[DatasetPromotionStatusCount, ...]
    missing_criteria_counts: tuple[DatasetPromotionCriterionCount, ...]
    rejected_criteria_counts: tuple[DatasetPromotionCriterionCount, ...]
    datasets: tuple[DatasetPromotionReadinessItem, ...]
    source_fallback_policy_effect_counts: tuple[
        DatasetPromotionReadinessSourceFallbackPolicyEffectCount, ...
    ] = ()
