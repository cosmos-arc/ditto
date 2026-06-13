"""Tests for ingestion status query facade."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import ditto_application.queries.ingestion_status as ingestion_status_module
from ditto_application.queries.catalog import CatalogSourceFallbackPolicyEffect
from ditto_application.queries.ingestion_status import (
    DatasetStatus,
    IngestionStatusQueryFacade,
)
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from ditto_data.catalog.promotion import (
    DatasetMaturityPromotion,
    DatasetMaturityPromotionEvent,
    DatasetPromotionEvidence,
)
from ditto_data.models.ingestion import IngestionStatus


def _catalog_entry(
    dataset_id: str,
    *,
    storage_uri: str,
    freshness_at: datetime,
    row_count: int = 17,
) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id=dataset_id,
            namespace="market",
            partition_keys=("trade_date=2026-06-01",),
        ),
        storage_uri=storage_uri,
        schema=DataSchemaFingerprint(
            schema_hash=f"schema:{dataset_id}:v1",
            row_count=row_count,
            created_at=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        ),
        source="tushare",
        freshness_at=freshness_at,
    )


def _log_store() -> MagicMock:
    store = MagicMock()
    store.get_stats.return_value = {"success_count": 1}
    store.get_last_success_date.return_value = "2026-06-01"
    store.list_ingested_dates.return_value = []
    return store


class _PromotionEvidenceReader:
    def __init__(
        self,
        evidence_by_dataset: dict[str, tuple[DatasetPromotionEvidence, ...]]
        | None = None,
    ) -> None:
        self._evidence_by_dataset = evidence_by_dataset or {}

    def list_dataset_evidence(
        self,
        dataset_id: str,
    ) -> tuple[DatasetPromotionEvidence, ...]:
        return self._evidence_by_dataset.get(dataset_id, ())


class _MaturityPromotionReader:
    def __init__(
        self,
        promotions_by_dataset: dict[str, DatasetMaturityPromotion] | None = None,
    ) -> None:
        self._promotions_by_dataset = promotions_by_dataset or {}

    def get_dataset_maturity_promotion(
        self,
        dataset_id: str,
    ) -> DatasetMaturityPromotion | None:
        return self._promotions_by_dataset.get(dataset_id)


class _MaturityPromotionHistoryReader:
    def __init__(
        self,
        events_by_dataset: dict[str, tuple[DatasetMaturityPromotionEvent, ...]]
        | None = None,
    ) -> None:
        self._events_by_dataset = events_by_dataset or {}

    def list_dataset_maturity_promotion_events(
        self,
        dataset_id: str,
    ) -> tuple[DatasetMaturityPromotionEvent, ...]:
        return self._events_by_dataset.get(dataset_id, ())


class TestIngestionStatusCatalogOverlay:
    def test_status_includes_latest_catalog_freshness_storage_schema_and_sla(
        self,
    ) -> None:
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            _catalog_entry(
                "stock_daily",
                storage_uri="stock_daily/older",
                freshness_at=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
                row_count=11,
            )
        )
        catalog.upsert_asset(
            _catalog_entry(
                "stock_daily",
                storage_uri="stock_daily/newer",
                freshness_at=datetime(2026, 6, 1, 10, 1, tzinfo=UTC),
                row_count=23,
            )
        )
        catalog.upsert_asset(
            _catalog_entry(
                "etf_daily",
                storage_uri="etf_daily/newer",
                freshness_at=datetime(2026, 6, 1, 10, 5, tzinfo=UTC),
            )
        )
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=catalog,
            promotion_evidence_reader=_PromotionEvidenceReader(),
            now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        )

        status = facade.get_status(["stock_daily"])[0]

        assert status.catalog_freshness_at == datetime(2026, 6, 1, 10, 1, tzinfo=UTC)
        assert status.catalog_storage_uri == "stock_daily/newer"
        assert status.catalog_schema_hash == "schema:stock_daily:v1"
        assert status.catalog_row_count == 23
        assert status.catalog_freshness_sla_hours == 36
        assert status.catalog_freshness_status == "fresh"
        assert status.dataset_maturity == "experimental"
        assert status.dataset_promotion_criteria
        assert status.dataset_promotion_status == "blocked"
        assert status.dataset_promotion_missing_criteria == (
            status.dataset_promotion_criteria
        )
        assert status.dataset_promotion_satisfied_criteria == ()
        assert status.dataset_promotion_rejected_criteria == ()
        assert "research opt-in" in (status.dataset_maturity_warning or "")

    def test_status_uses_persisted_promotion_evidence_to_mark_ready(self) -> None:
        metadata = ingestion_status_module.default_dataset_metadata()["stock_daily"]
        evidence = tuple(
            DatasetPromotionEvidence(
                criterion=criterion,
                evidence_uri=f"ditto://evidence/stock_daily/{index}",
                approved_by="architecture-review",
            )
            for index, criterion in enumerate(metadata.promotion_criteria, start=1)
        )
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=_PromotionEvidenceReader(
                {"stock_daily": evidence}
            ),
            now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        )

        status = facade.get_status(["stock_daily"])[0]

        assert status.dataset_promotion_status == "ready"
        assert status.dataset_promotion_satisfied_criteria == (
            metadata.promotion_criteria
        )
        assert status.dataset_promotion_missing_criteria == ()
        assert status.dataset_promotion_rejected_criteria == ()

    def test_status_uses_persisted_maturity_promotion_override(self) -> None:
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=_PromotionEvidenceReader(),
            maturity_promotion_reader=_MaturityPromotionReader(
                {
                    "stock_daily": DatasetMaturityPromotion(
                        dataset_id="stock_daily",
                        previous_maturity="experimental",
                        promoted_maturity="initial-focus",
                        promoted_by="architecture-review",
                        promoted_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
                    )
                }
            ),
            now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        )

        status = facade.get_status(["stock_daily"])[0]

        assert status.dataset_maturity == "initial-focus"
        assert status.dataset_maturity_warning is None
        assert status.dataset_promotion_criteria == ()
        assert status.dataset_promotion_status == "not_applicable"
        assert status.dataset_promotion_missing_criteria == ()
        assert status.dataset_promotion_satisfied_criteria == ()
        assert status.dataset_promotion_rejected_criteria == ()

    def test_status_exposes_rejected_promotion_evidence(self) -> None:
        metadata = ingestion_status_module.default_dataset_metadata()["stock_daily"]
        rejected = metadata.promotion_criteria[0]
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=_PromotionEvidenceReader(
                {
                    "stock_daily": (
                        DatasetPromotionEvidence(
                            criterion=rejected,
                            evidence_uri="ditto://evidence/stock_daily/rejected",
                            approved_by="architecture-review",
                            passed=False,
                        ),
                    )
                }
            ),
            now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        )

        status = facade.get_status(["stock_daily"])[0]

        assert status.dataset_promotion_status == "blocked"
        assert status.dataset_promotion_rejected_criteria == (rejected,)
        assert rejected not in status.dataset_promotion_missing_criteria

    def test_status_includes_latest_revocation_context(self) -> None:
        revoked_at = datetime(2026, 6, 2, 9, 30, tzinfo=UTC)
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=_PromotionEvidenceReader(),
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {
                    "stock_daily": (
                        DatasetMaturityPromotionEvent(
                            dataset_id="stock_daily",
                            action="revoked",
                            previous_maturity="initial-focus",
                            next_maturity="experimental",
                            actor="data-governance",
                            action_at=revoked_at,
                            revocation_reason="policy_regression",
                        ),
                    )
                }
            ),
            now=lambda: datetime(2026, 6, 2, 10, 0, tzinfo=UTC),
        )

        status = facade.get_status(["stock_daily"])[0]

        assert status.latest_revocation_reason == "policy_regression"
        assert status.latest_revoked_by == "data-governance"
        assert status.latest_revoked_at == revoked_at

    def test_initial_focus_status_has_no_maturity_warning_or_promotion_criteria(
        self,
    ) -> None:
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=_PromotionEvidenceReader(),
            now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        )

        status = facade.get_status(["etf_daily"])[0]

        assert status.dataset_maturity == "initial-focus"
        assert status.dataset_promotion_criteria == ()
        assert status.dataset_promotion_status == "not_applicable"
        assert status.dataset_promotion_missing_criteria == ()
        assert status.dataset_promotion_satisfied_criteria == ()
        assert status.dataset_promotion_rejected_criteria == ()
        assert status.dataset_maturity_warning is None

    def test_status_marks_catalog_asset_stale_when_freshness_exceeds_sla(
        self,
    ) -> None:
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            _catalog_entry(
                "stock_daily",
                storage_uri="stock_daily/stale",
                freshness_at=datetime(2026, 5, 30, 10, 1, tzinfo=UTC),
            )
        )
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=catalog,
            promotion_evidence_reader=_PromotionEvidenceReader(),
            now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        )

        status = facade.get_status(["stock_daily"])[0]

        assert status.catalog_freshness_status == "stale"
        assert status.catalog_freshness_sla_hours == 36

    def test_status_catalog_fields_are_none_when_dataset_has_no_catalog_asset(
        self,
    ) -> None:
        store = _log_store()
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=store,
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=_PromotionEvidenceReader(),
        )

        status = facade.get_status(["stock_daily"])[0]

        assert status.catalog_freshness_at is None
        assert status.catalog_storage_uri is None
        assert status.catalog_schema_hash is None
        assert status.catalog_row_count is None
        assert status.catalog_freshness_sla_hours == 36
        assert status.catalog_freshness_status == "missing"
        store.list_ingested_dates.assert_called_once_with(
            "stock_daily",
            status=IngestionStatus.FAIL,
        )

    def test_status_marks_dataset_without_runtime_sla_not_applicable(self) -> None:
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=_PromotionEvidenceReader(),
            now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        )

        status = facade.get_status(["index_weight"])[0]

        assert status.catalog_freshness_status == "not_applicable"
        assert status.catalog_freshness_sla_hours is None
        assert status.dataset_maturity == "experimental"


class TestIngestionStatusMaturitySummary:
    def test_groups_dataset_freshness_and_failure_counts_by_maturity(self) -> None:
        statuses = [
            DatasetStatus(
                dataset="stock_daily",
                latest_date="2026-06-01",
                latest_status="success",
                dataset_maturity="experimental",
                dataset_maturity_warning="experimental data requires research opt-in",
                dataset_promotion_status="blocked",
                record_count=1,
                last_attempt=None,
                catalog_freshness_status="fresh",
            ),
            DatasetStatus(
                dataset="etf_daily",
                latest_date="2026-06-01",
                latest_status="failed",
                dataset_maturity="initial-focus",
                record_count=0,
                last_attempt=None,
                catalog_freshness_status="missing",
            ),
            DatasetStatus(
                dataset="macro_indicators",
                latest_date="2026-06-01",
                latest_status="success",
                dataset_maturity="experimental",
                dataset_promotion_status="ready",
                record_count=1,
                last_attempt=None,
                catalog_freshness_status="stale",
            ),
            DatasetStatus(
                dataset="unknown_future",
                latest_date=None,
                latest_status=None,
                dataset_maturity=None,
                record_count=0,
                last_attempt=None,
                catalog_freshness_status="not_applicable",
            ),
        ]

        summary = ingestion_status_module.summarize_status_by_maturity(statuses)

        assert [(item.maturity, item.dataset_count) for item in summary] == [
            ("initial-focus", 1),
            ("experimental", 2),
            ("unknown", 1),
        ]
        initial_focus = summary[0]
        assert initial_focus.fresh_count == 0
        assert initial_focus.missing_count == 1
        assert initial_focus.failed_count == 1
        experimental = summary[1]
        assert experimental.fresh_count == 1
        assert experimental.stale_count == 1
        assert experimental.warning_count == 1
        assert experimental.promotion_blocked_count == 1
        assert experimental.promotion_ready_count == 1
        unknown = summary[2]
        assert unknown.not_applicable_count == 1


class TestPromotionReadinessReport:
    def test_summarizes_source_fallback_policy_effect_counts(self) -> None:
        """Promotion readiness can carry source-policy impact context."""
        source_health = MagicMock()
        source_health.get_source_health_summary.return_value = SimpleNamespace(
            reports=(
                SimpleNamespace(
                    source_fallback_policy_effect=CatalogSourceFallbackPolicyEffect(
                        policy_id="fallback-policy-001",
                        policy_status="active",
                        catalog_selected_source="tushare",
                        effective_selected_source="fred",
                        reason_codes=("selected_source_missing",),
                        recommended_actions=("repair_catalog_source_coverage",),
                    )
                ),
                SimpleNamespace(
                    source_fallback_policy_effect=CatalogSourceFallbackPolicyEffect(
                        policy_id="fallback-policy-001",
                        policy_status="active",
                        catalog_selected_source="tushare",
                        effective_selected_source="fred",
                        reason_codes=("selected_source_missing",),
                        recommended_actions=("repair_catalog_source_coverage",),
                    )
                ),
                SimpleNamespace(source_fallback_policy_effect=None),
            )
        )
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=_PromotionEvidenceReader(),
            source_health_summary_query=source_health,
            now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        )

        report = facade.get_promotion_readiness_report(
            ["stock_daily"],
            trade_dates=("2026-06-01",),
            available_sources=("tushare", "fred"),
        )

        assert [
            (
                item.policy_id,
                item.policy_status,
                item.catalog_selected_source,
                item.effective_selected_source,
                item.count,
            )
            for item in report.source_fallback_policy_effect_counts
        ] == [
            ("fallback-policy-001", "active", "tushare", "fred", 2),
        ]
        source_health.get_source_health_summary.assert_called_once_with(
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("tushare", "fred"),
        )

    def test_reports_latest_revocation_context_for_revoked_promotions(self) -> None:
        """Readiness report composes current readiness with last revoke context."""
        revoked_at = datetime(2026, 6, 2, 9, 30, tzinfo=UTC)
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=_PromotionEvidenceReader(),
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {
                    "stock_daily": (
                        DatasetMaturityPromotionEvent(
                            dataset_id="stock_daily",
                            action="promoted",
                            previous_maturity="experimental",
                            next_maturity="initial-focus",
                            actor="architecture-review",
                            action_at=datetime(2026, 6, 1, 15, 0, tzinfo=UTC),
                        ),
                        DatasetMaturityPromotionEvent(
                            dataset_id="stock_daily",
                            action="revoked",
                            previous_maturity="initial-focus",
                            next_maturity="experimental",
                            actor="data-governance",
                            action_at=revoked_at,
                            revocation_reason="failed_revalidation",
                            notes="PIT regression reopened promotion",
                        ),
                    )
                }
            ),
        )

        report = facade.get_promotion_readiness_report(["stock_daily"])

        item = report.datasets[0]
        assert item.dataset_id == "stock_daily"
        assert item.active_maturity_promotion is False
        assert item.latest_revocation_reason == "failed_revalidation"
        assert item.latest_revoked_by == "data-governance"
        assert item.latest_revoked_at == revoked_at

    def test_reports_dataset_promotion_readiness_and_criteria_counts(self) -> None:
        metadata = ingestion_status_module.default_dataset_metadata()
        stock_criteria = metadata["stock_daily"].promotion_criteria
        macro_criteria = metadata["macro_indicators"].promotion_criteria
        evidence_reader = _PromotionEvidenceReader(
            {
                "stock_daily": (
                    DatasetPromotionEvidence(
                        criterion=stock_criteria[0],
                        evidence_uri="ditto://evidence/stock_daily/pit",
                        approved_by="architecture-review",
                    ),
                    DatasetPromotionEvidence(
                        criterion=stock_criteria[1],
                        evidence_uri="ditto://evidence/stock_daily/failover",
                        approved_by="architecture-review",
                        passed=False,
                    ),
                ),
                "macro_indicators": tuple(
                    DatasetPromotionEvidence(
                        criterion=criterion,
                        evidence_uri=f"ditto://evidence/macro_indicators/{index}",
                        approved_by="architecture-review",
                    )
                    for index, criterion in enumerate(macro_criteria, start=1)
                ),
            }
        )
        maturity_reader = _MaturityPromotionReader(
            {
                "macro_indicators": DatasetMaturityPromotion(
                    dataset_id="macro_indicators",
                    previous_maturity="experimental",
                    promoted_maturity="initial-focus",
                    promoted_by="architecture-review",
                    promoted_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
                    evidence_uri="ditto://evidence/macro_indicators/3",
                )
            }
        )
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=evidence_reader,
            maturity_promotion_reader=maturity_reader,
        )

        report = facade.get_promotion_readiness_report(
            ["stock_daily", "macro_indicators", "etf_daily"]
        )

        assert report.dataset_count == 3
        assert report.promotable_count == 1
        assert report.active_promotion_count == 1
        assert [(item.status, item.count) for item in report.status_counts] == [
            ("ready", 1),
            ("blocked", 1),
            ("not_applicable", 1),
        ]
        assert report.missing_criteria_counts == (
            ingestion_status_module.DatasetPromotionCriterionCount(
                criterion=stock_criteria[2],
                count=1,
            ),
        )
        assert report.rejected_criteria_counts == (
            ingestion_status_module.DatasetPromotionCriterionCount(
                criterion=stock_criteria[1],
                count=1,
            ),
        )
        stock, macro, etf = report.datasets
        assert stock.dataset_id == "stock_daily"
        assert stock.metadata_maturity == "experimental"
        assert stock.current_maturity == "experimental"
        assert stock.promotion_status == "blocked"
        assert stock.active_maturity_promotion is False
        assert stock.satisfied_criteria == (stock_criteria[0],)
        assert stock.rejected_criteria == (stock_criteria[1],)
        assert stock.missing_criteria == (stock_criteria[2],)
        assert macro.dataset_id == "macro_indicators"
        assert macro.metadata_maturity == "experimental"
        assert macro.current_maturity == "initial-focus"
        assert macro.promotion_status == "ready"
        assert macro.active_maturity_promotion is True
        assert macro.required_criteria == macro_criteria
        assert macro.satisfied_criteria == macro_criteria
        assert macro.missing_criteria == ()
        assert etf.dataset_id == "etf_daily"
        assert etf.metadata_maturity == "initial-focus"
        assert etf.current_maturity == "initial-focus"
        assert etf.promotion_status == "not_applicable"
        assert etf.required_criteria == ()


class TestMaturityGovernanceReport:
    def test_summarizes_source_fallback_policy_effect_counts(self) -> None:
        """Maturity governance can carry source-policy impact context."""
        source_health = MagicMock()
        source_health.get_source_health_summary.return_value = SimpleNamespace(
            reports=(
                SimpleNamespace(
                    source_fallback_policy_effect=CatalogSourceFallbackPolicyEffect(
                        policy_id="fallback-policy-001",
                        policy_status="active",
                        catalog_selected_source="tushare",
                        effective_selected_source="fred",
                        reason_codes=("selected_source_missing",),
                        recommended_actions=("repair_catalog_source_coverage",),
                    )
                ),
            )
        )
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=InMemoryDataCatalog(),
            promotion_evidence_reader=_PromotionEvidenceReader(),
            source_health_summary_query=source_health,
            now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        )

        report = facade.get_maturity_governance_report(
            ["stock_daily"],
            trade_dates=("2026-06-01",),
            available_sources=("tushare", "fred"),
        )

        assert [
            (
                item.policy_id,
                item.policy_status,
                item.catalog_selected_source,
                item.effective_selected_source,
                item.count,
            )
            for item in report.source_fallback_policy_effect_counts
        ] == [
            ("fallback-policy-001", "active", "tushare", "fred", 1),
        ]
        source_health.get_source_health_summary.assert_called_once_with(
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("tushare", "fred"),
        )

    def test_unifies_status_readiness_and_revocation_context(self) -> None:
        metadata = ingestion_status_module.default_dataset_metadata()
        stock_criteria = metadata["stock_daily"].promotion_criteria
        macro_criteria = metadata["macro_indicators"].promotion_criteria
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            _catalog_entry(
                "stock_daily",
                storage_uri="stock_daily/fresh",
                freshness_at=datetime(2026, 6, 2, 8, 30, tzinfo=UTC),
            )
        )
        evidence_reader = _PromotionEvidenceReader(
            {
                "stock_daily": (
                    DatasetPromotionEvidence(
                        criterion=stock_criteria[0],
                        evidence_uri="ditto://evidence/stock_daily/pit",
                        approved_by="architecture-review",
                    ),
                    DatasetPromotionEvidence(
                        criterion=stock_criteria[1],
                        evidence_uri="ditto://evidence/stock_daily/failover",
                        approved_by="architecture-review",
                        passed=False,
                    ),
                ),
                "macro_indicators": tuple(
                    DatasetPromotionEvidence(
                        criterion=criterion,
                        evidence_uri=f"ditto://evidence/macro_indicators/{index}",
                        approved_by="architecture-review",
                    )
                    for index, criterion in enumerate(macro_criteria, start=1)
                ),
            }
        )
        maturity_reader = _MaturityPromotionReader(
            {
                "macro_indicators": DatasetMaturityPromotion(
                    dataset_id="macro_indicators",
                    previous_maturity="experimental",
                    promoted_maturity="initial-focus",
                    promoted_by="architecture-review",
                    promoted_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
                    evidence_uri="ditto://evidence/macro_indicators/3",
                )
            }
        )
        revoked_at = datetime(2026, 6, 2, 9, 30, tzinfo=UTC)
        facade = IngestionStatusQueryFacade(
            ingestion_log_store=_log_store(),
            data_catalog_reader=catalog,
            promotion_evidence_reader=evidence_reader,
            maturity_promotion_reader=maturity_reader,
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {
                    "stock_daily": (
                        DatasetMaturityPromotionEvent(
                            dataset_id="stock_daily",
                            action="revoked",
                            previous_maturity="initial-focus",
                            next_maturity="experimental",
                            actor="data-governance",
                            action_at=revoked_at,
                            revocation_reason="failed_revalidation",
                        ),
                    )
                }
            ),
            now=lambda: datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
        )

        report = facade.get_maturity_governance_report(
            ["stock_daily", "macro_indicators", "etf_daily"]
        )

        assert report.dataset_count == 3
        assert report.warning_count == 1
        assert report.promotable_count == 1
        assert report.active_promotion_count == 1
        assert report.revoked_promotion_count == 1
        assert [
            (item.status, item.count) for item in report.promotion_status_counts
        ] == [
            ("ready", 1),
            ("blocked", 1),
            ("not_applicable", 1),
        ]
        assert report.missing_criteria_counts == (
            ingestion_status_module.DatasetPromotionCriterionCount(
                criterion=stock_criteria[2],
                count=1,
            ),
        )
        assert report.rejected_criteria_counts == (
            ingestion_status_module.DatasetPromotionCriterionCount(
                criterion=stock_criteria[1],
                count=1,
            ),
        )
        assert report.attention_reason_counts == (
            ingestion_status_module.DatasetMaturityGovernanceAttentionReasonCount(
                reason="catalog_missing",
                count=2,
            ),
            ingestion_status_module.DatasetMaturityGovernanceAttentionReasonCount(
                reason="maturity_warning",
                count=1,
            ),
            ingestion_status_module.DatasetMaturityGovernanceAttentionReasonCount(
                reason="promotion_blocked",
                count=1,
            ),
            ingestion_status_module.DatasetMaturityGovernanceAttentionReasonCount(
                reason="promotion_revoked",
                count=1,
            ),
        )
        assert report.attention_severity_counts == (
            ingestion_status_module.DatasetMaturityGovernanceAttentionSeverityCount(
                severity="critical",
                count=3,
            ),
            ingestion_status_module.DatasetMaturityGovernanceAttentionSeverityCount(
                severity="warning",
                count=0,
            ),
            ingestion_status_module.DatasetMaturityGovernanceAttentionSeverityCount(
                severity="info",
                count=0,
            ),
        )
        attention_by_dataset = {
            item.dataset_id: item for item in report.attention_required
        }
        assert attention_by_dataset["stock_daily"].attention_reasons == (
            "maturity_warning",
            "promotion_blocked",
            "promotion_revoked",
        )
        assert attention_by_dataset["stock_daily"].attention_severity == "critical"
        assert attention_by_dataset["stock_daily"].dataset.missing_criteria == (
            stock_criteria[2],
        )
        assert attention_by_dataset["macro_indicators"].attention_reasons == (
            "catalog_missing",
        )
        assert attention_by_dataset["macro_indicators"].attention_severity == "critical"
        assert attention_by_dataset["etf_daily"].attention_reasons == (
            "catalog_missing",
        )
        assert attention_by_dataset["etf_daily"].attention_severity == "critical"
        assert [
            (item.maturity, item.dataset_count) for item in report.maturity_summary
        ] == [
            ("initial-focus", 2),
            ("experimental", 1),
        ]
        stock = report.datasets[0]
        assert stock.dataset_id == "stock_daily"
        assert stock.current_maturity == "experimental"
        assert stock.catalog_freshness_status == "fresh"
        assert stock.promotion_status == "blocked"
        assert stock.active_maturity_promotion is False
        assert stock.has_maturity_warning is True
        assert stock.latest_revocation_reason == "failed_revalidation"
        assert stock.latest_revoked_by == "data-governance"
        assert stock.latest_revoked_at == revoked_at
        assert stock.required_criteria == stock_criteria
        assert stock.satisfied_criteria == (stock_criteria[0],)
        assert stock.missing_criteria == (stock_criteria[2],)
        assert stock.rejected_criteria == (stock_criteria[1],)
        macro = report.datasets[1]
        assert macro.current_maturity == "initial-focus"
        assert macro.promotion_status == "ready"
        assert macro.active_maturity_promotion is True
        assert macro.has_maturity_warning is False
        assert macro.required_criteria == macro_criteria
        assert macro.satisfied_criteria == macro_criteria
