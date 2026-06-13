"""摄取状态查询 Facade."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ditto_data.catalog import (
    DataCatalogReader,
    DatasetMetadata,
    default_dataset_metadata,
)
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotion,
    DatasetMaturityPromotionEvent,
    DatasetMaturityPromotionHistoryReader,
    DatasetMaturityPromotionReader,
    DatasetMaturityPromotionRevocationReason,
    DatasetPromotionAssessment,
    DatasetPromotionEvidenceReader,
    DatasetPromotionStatus,
    apply_dataset_maturity_promotion,
    assess_dataset_promotion,
)
from ditto_data.ingestion.ingestion_log_store import IngestionLogStore
from ditto_data.models.ingestion import IngestionStatus

from ditto_application.catalog_freshness import (
    CatalogFreshnessStatus,
    assess_catalog_freshness,
    latest_catalog_entry_for_dataset,
)
from ditto_application.queries import _maturity_governance
from ditto_application.queries.catalog_source_health import (
    CatalogSourceHealthSummaryReport,
)

DatasetMaturityGovernanceAttentionItem = (
    _maturity_governance.DatasetMaturityGovernanceAttentionItem
)
DatasetMaturityGovernanceAttentionReason = (
    _maturity_governance.DatasetMaturityGovernanceAttentionReason
)
DatasetMaturityGovernanceAttentionReasonCount = (
    _maturity_governance.DatasetMaturityGovernanceAttentionReasonCount
)
DatasetMaturityGovernanceAttentionSeverity = (
    _maturity_governance.DatasetMaturityGovernanceAttentionSeverity
)
DatasetMaturityGovernanceAttentionSeverityCount = (
    _maturity_governance.DatasetMaturityGovernanceAttentionSeverityCount
)
DatasetMaturityGovernanceSourceFallbackPolicyEffectCount = (
    _maturity_governance.DatasetMaturityGovernanceSourceFallbackPolicyEffectCount
)
DatasetMaturityGovernanceItem = _maturity_governance.DatasetMaturityGovernanceItem
DatasetMaturityGovernanceReport = _maturity_governance.DatasetMaturityGovernanceReport
build_maturity_governance_report = _maturity_governance.build_maturity_governance_report


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


@dataclass(slots=True)
class _DatasetMaturitySummaryCounts:
    dataset_count: int = 0
    fresh_count: int = 0
    stale_count: int = 0
    missing_count: int = 0
    not_applicable_count: int = 0
    failed_count: int = 0
    warning_count: int = 0
    promotion_ready_count: int = 0
    promotion_blocked_count: int = 0


class _SourceHealthSummaryQuery(Protocol):
    def get_source_health_summary(
        self,
        *,
        dataset_ids: tuple[str, ...],
        trade_dates: tuple[str, ...],
        available_sources: tuple[str, ...],
    ) -> CatalogSourceHealthSummaryReport:
        """Return existing source-health summary without duplicating source policy."""
        ...


@dataclass(frozen=True, slots=True)
class HistoryItem:
    """单条摄取历史记录."""

    dataset: str
    trade_date: str
    status: str
    rows: int | None
    error_message: str | None
    attempts: int
    last_attempt_at: str | None


_MATURITY_SORT_ORDER = {
    "production": 0,
    "initial-focus": 1,
    "experimental": 2,
    "infrastructure": 3,
    "reserved": 4,
    "historical-compat": 5,
    "unknown": 99,
}


def summarize_status_by_maturity(
    statuses: list[DatasetStatus],
) -> list[DatasetMaturitySummary]:
    """Group dataset status rows by capability maturity for reporting."""
    counts_by_maturity: dict[str, _DatasetMaturitySummaryCounts] = {}
    for status in statuses:
        maturity = status.dataset_maturity or "unknown"
        counts = counts_by_maturity.setdefault(
            maturity,
            _DatasetMaturitySummaryCounts(),
        )
        counts.dataset_count += 1
        match status.catalog_freshness_status:
            case "fresh":
                counts.fresh_count += 1
            case "stale":
                counts.stale_count += 1
            case "missing":
                counts.missing_count += 1
            case "not_applicable":
                counts.not_applicable_count += 1
            case _:
                pass
        if status.latest_status == "failed":
            counts.failed_count += 1
        if status.dataset_maturity_warning is not None:
            counts.warning_count += 1
        match status.dataset_promotion_status:
            case "ready":
                counts.promotion_ready_count += 1
            case "blocked":
                counts.promotion_blocked_count += 1
            case _:
                pass

    return [
        DatasetMaturitySummary(
            maturity=maturity,
            dataset_count=counts.dataset_count,
            fresh_count=counts.fresh_count,
            stale_count=counts.stale_count,
            missing_count=counts.missing_count,
            not_applicable_count=counts.not_applicable_count,
            failed_count=counts.failed_count,
            warning_count=counts.warning_count,
            promotion_ready_count=counts.promotion_ready_count,
            promotion_blocked_count=counts.promotion_blocked_count,
        )
        for maturity, counts in sorted(
            counts_by_maturity.items(),
            key=lambda item: (_MATURITY_SORT_ORDER.get(item[0], 98), item[0]),
        )
    ]


class IngestionStatusQueryFacade:
    """摄取状态查询编排."""

    def __init__(
        self,
        ingestion_log_store: IngestionLogStore,
        data_catalog_reader: DataCatalogReader,
        promotion_evidence_reader: DatasetPromotionEvidenceReader,
        maturity_promotion_reader: DatasetMaturityPromotionReader | None = None,
        maturity_promotion_history_reader: DatasetMaturityPromotionHistoryReader
        | None = None,
        *,
        source_health_summary_query: _SourceHealthSummaryQuery | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._log_service = ingestion_log_store
        self._data_catalog_reader = data_catalog_reader
        self._promotion_evidence_reader = promotion_evidence_reader
        self._maturity_promotion_reader = (
            maturity_promotion_reader or _NoDatasetMaturityPromotionReader()
        )
        self._maturity_promotion_history_reader = (
            maturity_promotion_history_reader
            or _NoDatasetMaturityPromotionHistoryReader()
        )
        self._source_health_summary_query = source_health_summary_query
        self._now = now or _utcnow

    def get_status(self, datasets: list[str]) -> list[DatasetStatus]:
        """
        获取各数据集的最新摄取状态.

        Args:
            datasets: 要查询的数据集名称列表

        Returns:
            每个数据集的状态

        """
        results: list[DatasetStatus] = []
        dataset_metadata = default_dataset_metadata()
        for dataset in datasets:
            metadata = dataset_metadata.get(dataset)
            metadata = _apply_persisted_maturity_promotion(
                metadata,
                self._maturity_promotion_reader,
            )
            promotion = _dataset_promotion_assessment(
                metadata,
                self._promotion_evidence_reader,
            )
            stats = self._log_service.get_stats(dataset)
            last_success = self._log_service.get_last_success_date(dataset)

            fail_dates = self._log_service.list_ingested_dates(
                dataset, status=IngestionStatus.FAIL
            )

            # 确定最新状态
            latest_date: str | None = last_success
            latest_status: str | None = "success" if last_success else None
            record_count = stats.get("success_count", 0)

            # 如果有失败记录，需要检查是否比最新成功更晚
            if fail_dates:
                latest_fail = fail_dates[-1] if fail_dates else None
                if latest_fail and (not latest_date or latest_fail > latest_date):
                    latest_date = latest_fail
                    latest_status = "failed"

            catalog_entry = latest_catalog_entry_for_dataset(
                self._data_catalog_reader,
                dataset,
            )
            freshness = assess_catalog_freshness(
                dataset=dataset,
                catalog_entry=catalog_entry,
                now=self._now,
            )
            latest_revocation = _latest_revoked_promotion_event(
                self._maturity_promotion_history_reader.list_dataset_maturity_promotion_events(
                    dataset
                )
            )
            results.append(
                DatasetStatus(
                    dataset=dataset,
                    latest_date=latest_date,
                    latest_status=latest_status,
                    dataset_maturity=(
                        metadata.maturity if metadata is not None else None
                    ),
                    dataset_maturity_warning=_dataset_maturity_warning(metadata),
                    dataset_promotion_criteria=metadata.promotion_criteria
                    if metadata is not None
                    else (),
                    dataset_promotion_status=promotion.status
                    if promotion is not None
                    else None,
                    dataset_promotion_missing_criteria=promotion.missing_criteria
                    if promotion is not None
                    else (),
                    dataset_promotion_satisfied_criteria=promotion.satisfied_criteria
                    if promotion is not None
                    else (),
                    dataset_promotion_rejected_criteria=promotion.rejected_criteria
                    if promotion is not None
                    else (),
                    latest_revocation_reason=latest_revocation.revocation_reason
                    if latest_revocation is not None
                    else None,
                    latest_revoked_by=latest_revocation.actor
                    if latest_revocation is not None
                    else None,
                    latest_revoked_at=latest_revocation.action_at
                    if latest_revocation is not None
                    else None,
                    record_count=record_count,
                    last_attempt=None,
                    catalog_freshness_at=catalog_entry.freshness_at
                    if catalog_entry is not None
                    else None,
                    catalog_storage_uri=catalog_entry.storage_uri
                    if catalog_entry is not None
                    else None,
                    catalog_schema_hash=catalog_entry.schema.schema_hash
                    if catalog_entry is not None
                    else None,
                    catalog_row_count=catalog_entry.schema.row_count
                    if catalog_entry is not None
                    else None,
                    catalog_freshness_status=freshness.status,
                    catalog_freshness_sla_hours=freshness.sla_hours,
                )
            )
        return results

    def get_history(
        self,
        dataset: str,
        limit: int = 20,
    ) -> list[HistoryItem]:
        """
        获取数据集的摄取历史.

        Args:
            dataset: 数据集名称
            limit: 返回条数上限

        Returns:
            摄取历史记录列表

        """
        success_dates = self._log_service.list_ingested_dates(
            dataset, status=IngestionStatus.SUCCESS
        )
        fail_dates = self._log_service.list_ingested_dates(
            dataset, status=IngestionStatus.FAIL
        )

        history: list[HistoryItem] = []
        for date in success_dates[-limit:]:
            log = self._log_service.get_log(dataset, "tushare", date)
            history.append(
                HistoryItem(
                    dataset=dataset,
                    trade_date=date,
                    status="success",
                    rows=log.rows if log else None,
                    error_message=None,
                    attempts=log.attempts if log else 1,
                    last_attempt_at=log.last_attempt_at if log else None,
                )
            )
        for date in fail_dates[-limit:]:
            log = self._log_service.get_log(dataset, "tushare", date)
            history.append(
                HistoryItem(
                    dataset=dataset,
                    trade_date=date,
                    status="failed",
                    rows=None,
                    error_message=log.error_message if log else None,
                    attempts=log.attempts if log else 1,
                    last_attempt_at=log.last_attempt_at if log else None,
                )
            )

        # 按日期降序排序
        history.sort(key=lambda x: x.trade_date, reverse=True)
        return history[:limit]

    def get_promotion_readiness_report(
        self,
        datasets: list[str],
        *,
        trade_dates: tuple[str, ...] = (),
        available_sources: tuple[str, ...] = (),
    ) -> DatasetPromotionReadinessReport:
        """Return promotion readiness governance report for datasets."""
        dataset_ids = list(dict.fromkeys(dataset for dataset in datasets if dataset))
        items = tuple(
            self._promotion_readiness_item(dataset_id) for dataset_id in dataset_ids
        )
        return DatasetPromotionReadinessReport(
            dataset_count=len(items),
            promotable_count=sum(
                1 for item in items if item.promotion_status == "ready"
            ),
            active_promotion_count=sum(
                1 for item in items if item.active_maturity_promotion
            ),
            status_counts=_promotion_status_counts(items),
            missing_criteria_counts=_criterion_counts(
                criterion for item in items for criterion in item.missing_criteria
            ),
            rejected_criteria_counts=_criterion_counts(
                criterion for item in items for criterion in item.rejected_criteria
            ),
            datasets=items,
            source_fallback_policy_effect_counts=(
                self._promotion_source_fallback_policy_effect_counts(
                    dataset_ids=tuple(dataset_ids),
                    trade_dates=trade_dates,
                    available_sources=available_sources,
                )
            ),
        )

    def get_maturity_governance_report(
        self,
        datasets: list[str],
        *,
        trade_dates: tuple[str, ...] = (),
        available_sources: tuple[str, ...] = (),
    ) -> DatasetMaturityGovernanceReport:
        """Return a unified maturity, readiness and revocation report."""
        dataset_ids = list(dict.fromkeys(dataset for dataset in datasets if dataset))
        statuses = self.get_status(dataset_ids)
        readiness_report = self.get_promotion_readiness_report(dataset_ids)
        return build_maturity_governance_report(
            statuses=statuses,
            readiness_report=readiness_report,
            maturity_summary=tuple(summarize_status_by_maturity(statuses)),
            source_fallback_policy_effect_counts=(
                self._maturity_source_fallback_policy_effect_counts(
                    dataset_ids=tuple(dataset_ids),
                    trade_dates=trade_dates,
                    available_sources=available_sources,
                )
            ),
        )

    def _maturity_source_fallback_policy_effect_counts(
        self,
        *,
        dataset_ids: tuple[str, ...],
        trade_dates: tuple[str, ...],
        available_sources: tuple[str, ...],
    ) -> tuple[DatasetMaturityGovernanceSourceFallbackPolicyEffectCount, ...]:
        source_health_query = self._source_health_summary_query
        if (
            source_health_query is None
            or not dataset_ids
            or not trade_dates
            or not available_sources
        ):
            return ()
        source_health = source_health_query.get_source_health_summary(
            dataset_ids=dataset_ids,
            trade_dates=trade_dates,
            available_sources=available_sources,
        )
        return _source_fallback_policy_effect_counts(source_health)

    def _promotion_source_fallback_policy_effect_counts(
        self,
        *,
        dataset_ids: tuple[str, ...],
        trade_dates: tuple[str, ...],
        available_sources: tuple[str, ...],
    ) -> tuple[DatasetPromotionReadinessSourceFallbackPolicyEffectCount, ...]:
        source_health_query = self._source_health_summary_query
        if (
            source_health_query is None
            or not dataset_ids
            or not trade_dates
            or not available_sources
        ):
            return ()
        source_health = source_health_query.get_source_health_summary(
            dataset_ids=dataset_ids,
            trade_dates=trade_dates,
            available_sources=available_sources,
        )
        return _promotion_source_fallback_policy_effect_counts(source_health)

    def _promotion_readiness_item(
        self,
        dataset_id: str,
    ) -> DatasetPromotionReadinessItem:
        metadata = default_dataset_metadata().get(dataset_id)
        if metadata is None:
            return DatasetPromotionReadinessItem(
                dataset_id=dataset_id,
                metadata_maturity=None,
                current_maturity=None,
                promotion_status="not_applicable",
                active_maturity_promotion=False,
                latest_revocation_reason=None,
                latest_revoked_by=None,
                latest_revoked_at=None,
                required_criteria=(),
                satisfied_criteria=(),
                missing_criteria=(),
                rejected_criteria=(),
            )

        evidence = self._promotion_evidence_reader.list_dataset_evidence(dataset_id)
        assessment = assess_dataset_promotion(metadata, evidence)
        maturity_promotion = (
            self._maturity_promotion_reader.get_dataset_maturity_promotion(dataset_id)
        )
        latest_revocation = _latest_revoked_promotion_event(
            self._maturity_promotion_history_reader.list_dataset_maturity_promotion_events(
                dataset_id
            )
        )
        current_metadata = _apply_maturity_promotion(metadata, maturity_promotion)
        return DatasetPromotionReadinessItem(
            dataset_id=dataset_id,
            metadata_maturity=metadata.maturity,
            current_maturity=current_metadata.maturity,
            promotion_status=assessment.status,
            active_maturity_promotion=maturity_promotion is not None,
            latest_revocation_reason=latest_revocation.revocation_reason
            if latest_revocation is not None
            else None,
            latest_revoked_by=latest_revocation.actor
            if latest_revocation is not None
            else None,
            latest_revoked_at=latest_revocation.action_at
            if latest_revocation is not None
            else None,
            required_criteria=assessment.required_criteria,
            satisfied_criteria=assessment.satisfied_criteria,
            missing_criteria=assessment.missing_criteria,
            rejected_criteria=assessment.rejected_criteria,
        )


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _dataset_maturity_warning(metadata: DatasetMetadata | None) -> str | None:
    if metadata is None:
        return None
    if metadata.maturity == "experimental":
        return (
            "experimental data requires explicit research opt-in and promotion "
            "criteria before initial-focus use"
        )
    if metadata.maturity == "reserved":
        return "reserved data is not available for runtime use"
    return None


def _apply_persisted_maturity_promotion(
    metadata: DatasetMetadata | None,
    reader: DatasetMaturityPromotionReader,
) -> DatasetMetadata | None:
    if metadata is None:
        return None
    promotion = reader.get_dataset_maturity_promotion(metadata.dataset_id)
    if promotion is None:
        return metadata
    return _apply_maturity_promotion(metadata, promotion)


def _apply_maturity_promotion(
    metadata: DatasetMetadata,
    promotion: DatasetMaturityPromotion | None,
) -> DatasetMetadata:
    if promotion is None:
        return metadata
    return apply_dataset_maturity_promotion(metadata, promotion)


def _dataset_promotion_assessment(
    metadata: DatasetMetadata | None,
    evidence_reader: DatasetPromotionEvidenceReader,
) -> DatasetPromotionAssessment | None:
    if metadata is None:
        return None
    return assess_dataset_promotion(
        metadata,
        evidence_reader.list_dataset_evidence(metadata.dataset_id),
    )


class _NoDatasetMaturityPromotionReader:
    def get_dataset_maturity_promotion(self, dataset_id: str) -> None:
        return None


class _NoDatasetMaturityPromotionHistoryReader:
    def list_dataset_maturity_promotion_events(
        self,
        dataset_id: str,
    ) -> tuple[DatasetMaturityPromotionEvent, ...]:
        return ()


def _latest_revoked_promotion_event(
    events: tuple[DatasetMaturityPromotionEvent, ...],
) -> DatasetMaturityPromotionEvent | None:
    for event in reversed(events):
        if event.action == "revoked":
            return event
    return None


def _promotion_status_counts(
    items: tuple[DatasetPromotionReadinessItem, ...],
) -> tuple[DatasetPromotionStatusCount, ...]:
    counts: dict[DatasetPromotionStatus, int] = {
        "ready": 0,
        "blocked": 0,
        "not_applicable": 0,
    }
    for item in items:
        counts[item.promotion_status] += 1
    return tuple(
        DatasetPromotionStatusCount(status=status, count=count)
        for status, count in counts.items()
    )


def _criterion_counts(
    criteria: Iterable[str],
) -> tuple[DatasetPromotionCriterionCount, ...]:
    counts: dict[str, int] = {}
    for criterion in criteria:
        counts[criterion] = counts.get(criterion, 0) + 1
    return tuple(
        DatasetPromotionCriterionCount(criterion=criterion, count=counts[criterion])
        for criterion in sorted(counts)
    )


def _source_fallback_policy_effect_counts(
    source_health: CatalogSourceHealthSummaryReport,
) -> tuple[DatasetMaturityGovernanceSourceFallbackPolicyEffectCount, ...]:
    return tuple(
        DatasetMaturityGovernanceSourceFallbackPolicyEffectCount(
            policy_id=policy_id,
            policy_status=policy_status,
            catalog_selected_source=catalog_selected_source,
            effective_selected_source=effective_selected_source,
            count=count,
        )
        for (
            policy_id,
            policy_status,
            catalog_selected_source,
            effective_selected_source,
            count,
        ) in _source_fallback_policy_effect_count_rows(source_health)
    )


def _promotion_source_fallback_policy_effect_counts(
    source_health: CatalogSourceHealthSummaryReport,
) -> tuple[DatasetPromotionReadinessSourceFallbackPolicyEffectCount, ...]:
    return tuple(
        DatasetPromotionReadinessSourceFallbackPolicyEffectCount(
            policy_id=policy_id,
            policy_status=policy_status,
            catalog_selected_source=catalog_selected_source,
            effective_selected_source=effective_selected_source,
            count=count,
        )
        for (
            policy_id,
            policy_status,
            catalog_selected_source,
            effective_selected_source,
            count,
        ) in _source_fallback_policy_effect_count_rows(source_health)
    )


def _source_fallback_policy_effect_count_rows(
    source_health: CatalogSourceHealthSummaryReport,
) -> tuple[tuple[str, str, str, str, int], ...]:
    counts: dict[tuple[str, str, str, str], int] = {}
    for report in source_health.reports:
        effect = report.source_fallback_policy_effect
        if effect is None:
            continue
        key = (
            effect.policy_id,
            effect.policy_status,
            effect.catalog_selected_source,
            effect.effective_selected_source,
        )
        counts[key] = counts.get(key, 0) + 1
    return tuple(
        (
            policy_id,
            policy_status,
            catalog_selected_source,
            effective_selected_source,
            counts[key],
        )
        for key in sorted(counts)
        for (
            policy_id,
            policy_status,
            catalog_selected_source,
            effective_selected_source,
        ) in (key,)
    )
