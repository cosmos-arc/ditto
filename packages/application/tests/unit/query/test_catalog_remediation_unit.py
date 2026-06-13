"""Tests for catalog remediation backlog query facade."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from ditto_application.queries.catalog import (
    CatalogSourceFallbackPolicyEffect,
    CatalogSourceHealth,
    CatalogSourceHealthAttentionItem,
    CatalogSourceHealthAttentionReasonCount,
    CatalogSourceHealthAttentionSeverityCount,
    CatalogSourceHealthStatusCount,
    CatalogSourceHealthSummaryReport,
)
from ditto_application.queries.ingestion_status import (
    DatasetMaturityGovernanceAttentionItem,
    DatasetMaturityGovernanceAttentionReasonCount,
    DatasetMaturityGovernanceAttentionSeverityCount,
    DatasetMaturityGovernanceItem,
    DatasetMaturityGovernanceReport,
    DatasetMaturitySummary,
    DatasetPromotionStatusCount,
)
from ditto_application.queries.lineage import (
    DataLineageAsset,
    DataLineageCatalogAsset,
    DataLineageCatalogAttentionAsset,
    DataLineageCatalogAttentionReasonCount,
    DataLineageCatalogAttentionSeverityCount,
    DataLineageCatalogFreshnessStatusCount,
    DataLineageCatalogRunReport,
    DataLineageCatalogStatusCount,
)
from ditto_application.queries.remediation import CatalogRemediationQueryFacade


def _source_health_summary(
    *,
    source_fallback_policy_effect: CatalogSourceFallbackPolicyEffect | None = None,
) -> CatalogSourceHealthSummaryReport:
    selected_health = CatalogSourceHealth(
        source="fred",
        supported=True,
        freshness_status="missing",
        freshness_sla_hours=36,
    )
    attention = CatalogSourceHealthAttentionItem(
        dataset_id="stock_daily",
        namespace="market",
        trade_date="2026-06-01",
        default_source="tushare",
        selected_source="fred",
        selected_freshness_status="missing",
        selected_source_health=selected_health,
        attention_reasons=("selected_source_missing", "default_source_failover"),
        attention_severity="critical",
        source_fallback_policy_effect=source_fallback_policy_effect,
        fallback_sources=("fred",),
    )
    return CatalogSourceHealthSummaryReport(
        dataset_ids=("stock_daily",),
        trade_dates=("2026-06-01",),
        available_sources=("tushare",),
        total_reports=1,
        status_counts=(
            CatalogSourceHealthStatusCount(status="fresh", count=0),
            CatalogSourceHealthStatusCount(status="stale", count=0),
            CatalogSourceHealthStatusCount(status="missing", count=1),
            CatalogSourceHealthStatusCount(status="not_applicable", count=0),
        ),
        selected_source_counts=(),
        attention_required=(attention,),
        reports=(),
        attention_reason_counts=(
            CatalogSourceHealthAttentionReasonCount(
                reason="selected_source_missing",
                count=1,
            ),
            CatalogSourceHealthAttentionReasonCount(
                reason="default_source_failover",
                count=1,
            ),
        ),
        attention_severity_counts=(
            CatalogSourceHealthAttentionSeverityCount(severity="critical", count=1),
            CatalogSourceHealthAttentionSeverityCount(severity="warning", count=0),
            CatalogSourceHealthAttentionSeverityCount(severity="info", count=0),
        ),
    )


def _blocked_source_health_summary() -> CatalogSourceHealthSummaryReport:
    selected_health = CatalogSourceHealth(
        source="fred",
        supported=False,
        freshness_status="missing",
        freshness_sla_hours=None,
    )
    attention = CatalogSourceHealthAttentionItem(
        dataset_id="stock_daily",
        namespace="market",
        trade_date="2026-06-01",
        default_source="fred",
        selected_source="fred",
        selected_freshness_status="missing",
        selected_source_health=selected_health,
        attention_reasons=(
            "selected_source_missing",
            "no_fallback_source",
            "unsupported_sources_present",
        ),
        attention_severity="critical",
        source_selection_status="blocked",
        source_selection_blockers=("selected_source_unsupported",),
        unsupported_sources=("fred",),
        fallback_sources=(),
    )
    return CatalogSourceHealthSummaryReport(
        dataset_ids=("stock_daily",),
        trade_dates=("2026-06-01",),
        available_sources=("fred",),
        total_reports=1,
        status_counts=(
            CatalogSourceHealthStatusCount(status="fresh", count=0),
            CatalogSourceHealthStatusCount(status="stale", count=0),
            CatalogSourceHealthStatusCount(status="missing", count=1),
            CatalogSourceHealthStatusCount(status="not_applicable", count=0),
        ),
        selected_source_counts=(),
        attention_required=(attention,),
        reports=(),
        attention_reason_counts=(
            CatalogSourceHealthAttentionReasonCount(
                reason="selected_source_missing",
                count=1,
            ),
            CatalogSourceHealthAttentionReasonCount(
                reason="no_fallback_source",
                count=1,
            ),
            CatalogSourceHealthAttentionReasonCount(
                reason="unsupported_sources_present",
                count=1,
            ),
        ),
        attention_severity_counts=(
            CatalogSourceHealthAttentionSeverityCount(severity="critical", count=1),
            CatalogSourceHealthAttentionSeverityCount(severity="warning", count=0),
            CatalogSourceHealthAttentionSeverityCount(severity="info", count=0),
        ),
    )


def _maturity_governance_report() -> DatasetMaturityGovernanceReport:
    dataset = DatasetMaturityGovernanceItem(
        dataset_id="stock_daily",
        current_maturity="experimental",
        catalog_freshness_status="missing",
        promotion_status="blocked",
        active_maturity_promotion=False,
        has_maturity_warning=True,
        required_criteria=("complete PIT/replay coverage for the dataset",),
        satisfied_criteria=(),
        missing_criteria=("complete PIT/replay coverage for the dataset",),
        rejected_criteria=(),
    )
    attention = DatasetMaturityGovernanceAttentionItem(
        dataset_id="stock_daily",
        attention_reasons=(
            "maturity_warning",
            "catalog_missing",
            "promotion_blocked",
        ),
        attention_severity="critical",
        dataset=dataset,
    )
    return DatasetMaturityGovernanceReport(
        dataset_count=1,
        warning_count=1,
        promotable_count=0,
        active_promotion_count=0,
        revoked_promotion_count=0,
        maturity_summary=(
            DatasetMaturitySummary(
                maturity="experimental",
                dataset_count=1,
                fresh_count=0,
                stale_count=0,
                missing_count=1,
                not_applicable_count=0,
                failed_count=0,
                warning_count=1,
                promotion_ready_count=0,
                promotion_blocked_count=1,
            ),
        ),
        promotion_status_counts=(
            DatasetPromotionStatusCount(status="ready", count=0),
            DatasetPromotionStatusCount(status="blocked", count=1),
            DatasetPromotionStatusCount(status="not_applicable", count=0),
        ),
        missing_criteria_counts=(),
        rejected_criteria_counts=(),
        datasets=(dataset,),
        attention_reason_counts=(
            DatasetMaturityGovernanceAttentionReasonCount(
                reason="catalog_missing",
                count=1,
            ),
            DatasetMaturityGovernanceAttentionReasonCount(
                reason="maturity_warning",
                count=1,
            ),
            DatasetMaturityGovernanceAttentionReasonCount(
                reason="promotion_blocked",
                count=1,
            ),
        ),
        attention_severity_counts=(
            DatasetMaturityGovernanceAttentionSeverityCount(
                severity="critical",
                count=1,
            ),
            DatasetMaturityGovernanceAttentionSeverityCount(
                severity="warning",
                count=0,
            ),
            DatasetMaturityGovernanceAttentionSeverityCount(severity="info", count=0),
        ),
        attention_required=(attention,),
    )


def _empty_maturity_governance_report() -> DatasetMaturityGovernanceReport:
    return DatasetMaturityGovernanceReport(
        dataset_count=0,
        warning_count=0,
        promotable_count=0,
        active_promotion_count=0,
        revoked_promotion_count=0,
        maturity_summary=(),
        promotion_status_counts=(),
        missing_criteria_counts=(),
        rejected_criteria_counts=(),
        datasets=(),
        attention_reason_counts=(),
        attention_severity_counts=(),
        attention_required=(),
    )


def _lineage_catalog_report() -> DataLineageCatalogRunReport:
    asset = DataLineageCatalogAsset(
        asset=DataLineageAsset(
            dataset_id="stock_daily",
            namespace="market",
            partition_keys=("trade_date=2026-06-01",),
        ),
        catalog_status="missing",
        freshness_status="missing",
    )
    return DataLineageCatalogRunReport(
        run_id="run-001",
        events=(),
        input_assets=(asset,),
        output_assets=(),
        catalog_status_counts=(
            DataLineageCatalogStatusCount(status="found", count=0),
            DataLineageCatalogStatusCount(status="missing", count=1),
            DataLineageCatalogStatusCount(status="not_configured", count=0),
        ),
        freshness_status_counts=(
            DataLineageCatalogFreshnessStatusCount(status="fresh", count=0),
            DataLineageCatalogFreshnessStatusCount(status="stale", count=0),
            DataLineageCatalogFreshnessStatusCount(status="missing", count=1),
            DataLineageCatalogFreshnessStatusCount(
                status="not_applicable",
                count=0,
            ),
        ),
        attention_reason_counts=(
            DataLineageCatalogAttentionReasonCount(
                reason="catalog_missing",
                count=1,
            ),
        ),
        attention_severity_counts=(
            DataLineageCatalogAttentionSeverityCount(severity="critical", count=1),
            DataLineageCatalogAttentionSeverityCount(severity="warning", count=0),
            DataLineageCatalogAttentionSeverityCount(severity="info", count=0),
        ),
        attention_required=(
            DataLineageCatalogAttentionAsset(
                side="input",
                asset=asset,
                attention_reasons=("catalog_missing",),
                attention_severity="critical",
            ),
        ),
    )


class TestCatalogRemediationQueryFacade:
    def test_builds_backend_owned_remediation_backlog_across_reports(self) -> None:
        catalog_facade = MagicMock()
        catalog_facade.get_source_health_summary.return_value = _source_health_summary()
        ingestion_facade = MagicMock()
        ingestion_facade.get_maturity_governance_report.return_value = (
            _maturity_governance_report()
        )
        lineage_facade = MagicMock()
        lineage_facade.get_data_lineage_catalog_report_for_run.return_value = (
            _lineage_catalog_report()
        )
        facade = CatalogRemediationQueryFacade(
            catalog_facade=catalog_facade,
            ingestion_status_facade=ingestion_facade,
            lineage_facade=lineage_facade,
            generated_at=lambda: datetime(2026, 6, 9, 9, 30, tzinfo=UTC),
        )

        report = facade.get_remediation_backlog(
            dataset_ids=("stock_daily", "stock_daily"),
            trade_dates=("2026-06-01",),
            available_sources=("tushare",),
            run_id="run-001",
        )

        catalog_facade.get_source_health_summary.assert_called_once_with(
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("tushare",),
        )
        ingestion_facade.get_maturity_governance_report.assert_called_once_with(
            ["stock_daily"],
            trade_dates=("2026-06-01",),
            available_sources=("tushare",),
        )
        lineage_facade.get_data_lineage_catalog_report_for_run.assert_called_once_with(
            "run-001",
            trade_dates=("2026-06-01",),
            available_sources=("tushare",),
        )
        assert report.generated_at == datetime(2026, 6, 9, 9, 30, tzinfo=UTC)
        assert report.dataset_ids == ("stock_daily",)
        assert report.trade_dates == ("2026-06-01",)
        assert report.available_sources == ("tushare",)
        assert report.run_id == "run-001"
        assert report.total_items == 3
        assert [(item.severity, item.count) for item in report.severity_counts] == [
            ("critical", 3),
            ("warning", 0),
            ("info", 0),
        ]
        assert [(item.source, item.count) for item in report.source_counts] == [
            ("source_health", 1),
            ("maturity_governance", 1),
            ("lineage_catalog", 1),
        ]
        assert [
            (item.source, item.reason, item.count) for item in report.reason_counts
        ] == [
            ("source_health", "default_source_failover", 1),
            ("source_health", "selected_source_missing", 1),
            ("maturity_governance", "catalog_missing", 1),
            ("maturity_governance", "maturity_warning", 1),
            ("maturity_governance", "promotion_blocked", 1),
            ("lineage_catalog", "catalog_missing", 1),
        ]
        source_health, maturity, lineage = report.items
        assert source_health.item_id == "source_health:stock_daily:2026-06-01"
        assert source_health.dataset_id == "stock_daily"
        assert source_health.namespace == "market"
        assert source_health.trade_date == "2026-06-01"
        assert source_health.default_source == "tushare"
        assert source_health.selected_source == "fred"
        assert source_health.fallback_sources == ("fred",)
        assert source_health.reasons == (
            "selected_source_missing",
            "default_source_failover",
        )
        assert source_health.suggested_actions == (
            "repair_catalog_source_coverage",
            "review_source_failover",
        )
        assert maturity.item_id == "maturity_governance:stock_daily"
        assert maturity.current_maturity == "experimental"
        assert maturity.promotion_status == "blocked"
        assert maturity.suggested_actions == (
            "review_dataset_maturity",
            "repair_catalog_freshness",
            "submit_or_fix_promotion_evidence",
        )
        assert lineage.item_id == (
            "lineage_catalog:run-001:input:market:stock_daily:trade_date=2026-06-01"
        )
        assert lineage.run_id == "run-001"
        assert lineage.side == "input"
        assert lineage.catalog_status == "missing"
        assert lineage.partition_keys == ("trade_date=2026-06-01",)
        assert lineage.suggested_actions == ("repair_lineage_catalog_asset",)

    def test_preserves_source_fallback_policy_effect_on_source_health_items(
        self,
    ) -> None:
        effect = CatalogSourceFallbackPolicyEffect(
            policy_id="fallback-policy-001",
            policy_status="active",
            catalog_selected_source="tushare",
            effective_selected_source="fred",
            reason_codes=("selected_source_missing",),
            recommended_actions=("repair_catalog_source_coverage",),
        )
        catalog_facade = MagicMock()
        catalog_facade.get_source_health_summary.return_value = _source_health_summary(
            source_fallback_policy_effect=effect,
        )
        ingestion_facade = MagicMock()
        ingestion_facade.get_maturity_governance_report.return_value = (
            _empty_maturity_governance_report()
        )
        facade = CatalogRemediationQueryFacade(
            catalog_facade=catalog_facade,
            ingestion_status_facade=ingestion_facade,
            generated_at=lambda: datetime(2026, 6, 9, 9, 35, tzinfo=UTC),
        )

        report = facade.get_remediation_backlog(
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("tushare", "fred"),
        )

        item = report.items[0]
        assert item.item_id == "source_health:stock_daily:2026-06-01"
        assert item.source_fallback_policy_effect == effect

    def test_summarizes_source_fallback_policy_effect_counts(self) -> None:
        effect = CatalogSourceFallbackPolicyEffect(
            policy_id="fallback-policy-001",
            policy_status="active",
            catalog_selected_source="tushare",
            effective_selected_source="fred",
            reason_codes=("selected_source_missing",),
            recommended_actions=("repair_catalog_source_coverage",),
        )
        catalog_facade = MagicMock()
        catalog_facade.get_source_health_summary.return_value = _source_health_summary(
            source_fallback_policy_effect=effect,
        )
        ingestion_facade = MagicMock()
        ingestion_facade.get_maturity_governance_report.return_value = (
            _empty_maturity_governance_report()
        )
        facade = CatalogRemediationQueryFacade(
            catalog_facade=catalog_facade,
            ingestion_status_facade=ingestion_facade,
            generated_at=lambda: datetime(2026, 6, 9, 9, 36, tzinfo=UTC),
        )

        report = facade.get_remediation_backlog(
            dataset_ids=("stock_daily",),
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

    def test_returns_item_detail_with_evidence_requirements_and_approval_intents(
        self,
    ) -> None:
        catalog_facade = MagicMock()
        catalog_facade.get_source_health_summary.return_value = _source_health_summary()
        ingestion_facade = MagicMock()
        ingestion_facade.get_maturity_governance_report.return_value = (
            _maturity_governance_report()
        )
        facade = CatalogRemediationQueryFacade(
            catalog_facade=catalog_facade,
            ingestion_status_facade=ingestion_facade,
            generated_at=lambda: datetime(2026, 6, 9, 9, 45, tzinfo=UTC),
        )

        detail = facade.get_remediation_item_detail(
            item_id="maturity_governance:stock_daily",
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("tushare",),
        )

        assert detail.generated_at == datetime(2026, 6, 9, 9, 45, tzinfo=UTC)
        assert detail.item.item_id == "maturity_governance:stock_daily"
        assert detail.item.source == "maturity_governance"
        assert detail.summary == (
            "stock_daily requires maturity governance attention "
            "(maturity_warning, catalog_missing, promotion_blocked)."
        )
        assert [
            (
                requirement.requirement_id,
                requirement.source,
                requirement.status,
                requirement.description,
            )
            for requirement in detail.evidence_requirements
        ] == [
            (
                "promotion_criterion:complete PIT/replay coverage for the dataset",
                "promotion_criterion",
                "missing",
                "complete PIT/replay coverage for the dataset",
            ),
        ]
        assert [intent.action for intent in detail.approval_intents] == [
            "review_dataset_maturity",
            "repair_catalog_freshness",
            "submit_or_fix_promotion_evidence",
        ]
        review_intent = detail.approval_intents[0]
        assert review_intent.intent_type == "manual"
        assert review_intent.method is None
        assert review_intent.path is None
        assert review_intent.request_template == {
            "action": "review_dataset_maturity",
            "dataset_id": "stock_daily",
            "namespace": "catalog",
            "current_maturity": "experimental",
            "promotion_status": "blocked",
        }
        assert review_intent.required_operator_inputs == (
            "reviewed_by",
            "decision_notes",
        )
        freshness_intent = detail.approval_intents[1]
        assert freshness_intent.intent_type == "write"
        assert freshness_intent.method == "POST"
        assert freshness_intent.path == "/ingestion/stock_daily/<trade-date>"
        assert freshness_intent.request_template == {
            "dataset_id": "stock_daily",
            "trade_date": "<trade-date>",
            "force": True,
            "source": "auto",
        }
        assert freshness_intent.required_operator_inputs == ("trade_date",)
        evidence_intent = detail.approval_intents[2]
        assert evidence_intent.intent_type == "write"
        assert evidence_intent.method == "POST"
        assert evidence_intent.path == "/ingestion/catalog/promotion/evidence"
        assert evidence_intent.request_template == {
            "dataset_id": "stock_daily",
            "criterion": "complete PIT/replay coverage for the dataset",
            "evidence_uri": "<evidence-uri>",
            "reviewed_by": "<reviewer>",
            "passed": True,
            "notes": None,
        }
        assert evidence_intent.required_operator_inputs == (
            "evidence_uri",
            "reviewed_by",
        )

    def test_returns_source_coverage_repair_approval_intent(self) -> None:
        catalog_facade = MagicMock()
        catalog_facade.get_source_health_summary.return_value = _source_health_summary()
        ingestion_facade = MagicMock()
        ingestion_facade.get_maturity_governance_report.return_value = (
            _maturity_governance_report()
        )
        facade = CatalogRemediationQueryFacade(
            catalog_facade=catalog_facade,
            ingestion_status_facade=ingestion_facade,
            generated_at=lambda: datetime(2026, 6, 9, 9, 50, tzinfo=UTC),
        )

        detail = facade.get_remediation_item_detail(
            item_id="source_health:stock_daily:2026-06-01",
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("tushare", "fred"),
        )

        assert [
            (
                requirement.requirement_id,
                requirement.source,
                requirement.status,
                requirement.description,
            )
            for requirement in detail.evidence_requirements
        ] == [
            (
                "source_health:stock_daily:2026-06-01:selected_source_missing",
                "source_health",
                "attention_required",
                (
                    "Selected source fred is missing catalog freshness evidence "
                    "for stock_daily on 2026-06-01."
                ),
            ),
            (
                "source_health:stock_daily:2026-06-01:default_source_failover",
                "source_health",
                "attention_required",
                (
                    "Selected source fred differs from default source tushare "
                    "for stock_daily on 2026-06-01; review fallback policy before "
                    "changing source preferences."
                ),
            ),
            (
                "source_fallback_candidate:stock_daily:2026-06-01:fred",
                "source_fallback_candidate",
                "attention_required",
                (
                    "Candidate fallback source fred is available for stock_daily "
                    "on 2026-06-01; review suitability before changing fallback policy."
                ),
            ),
        ]
        assert [intent.action for intent in detail.approval_intents] == [
            "repair_catalog_source_coverage",
            "review_source_failover",
        ]
        intent = detail.approval_intents[0]
        assert intent.intent_type == "write"
        assert intent.method == "POST"
        assert intent.path == "/ingestion/stock_daily/2026-06-01"
        assert intent.request_template == {
            "dataset_id": "stock_daily",
            "trade_date": "2026-06-01",
            "force": True,
            "source": "auto",
        }
        assert intent.required_operator_inputs == ()
        manual_intent = detail.approval_intents[1]
        assert manual_intent.intent_type == "manual"
        assert manual_intent.method is None
        assert manual_intent.path is None
        assert manual_intent.request_template == {
            "action": "review_source_failover",
            "dataset_id": "stock_daily",
            "namespace": "market",
            "trade_date": "2026-06-01",
            "default_source": "tushare",
            "selected_source": "fred",
            "fallback_sources": ["fred"],
        }
        assert manual_intent.required_operator_inputs == (
            "reviewed_by",
            "decision_notes",
        )

    def test_source_review_intent_includes_source_fallback_policy_effect(
        self,
    ) -> None:
        effect = CatalogSourceFallbackPolicyEffect(
            policy_id="fallback-policy-001",
            policy_status="active",
            catalog_selected_source="tushare",
            effective_selected_source="fred",
            reason_codes=("selected_source_missing",),
            recommended_actions=("repair_catalog_source_coverage",),
        )
        catalog_facade = MagicMock()
        catalog_facade.get_source_health_summary.return_value = _source_health_summary(
            source_fallback_policy_effect=effect,
        )
        ingestion_facade = MagicMock()
        ingestion_facade.get_maturity_governance_report.return_value = (
            _empty_maturity_governance_report()
        )
        facade = CatalogRemediationQueryFacade(
            catalog_facade=catalog_facade,
            ingestion_status_facade=ingestion_facade,
            generated_at=lambda: datetime(2026, 6, 9, 10, 10, tzinfo=UTC),
        )

        detail = facade.get_remediation_item_detail(
            item_id="source_health:stock_daily:2026-06-01",
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("tushare", "fred"),
        )

        review_intent = detail.approval_intents[1]
        assert review_intent.action == "review_source_failover"
        assert review_intent.request_template["source_fallback_policy_effect"] == {
            "policy_id": "fallback-policy-001",
            "policy_status": "active",
            "catalog_selected_source": "tushare",
            "effective_selected_source": "fred",
            "reason_codes": ["selected_source_missing"],
            "recommended_actions": ["repair_catalog_source_coverage"],
        }

    def test_blocked_source_selection_remediation_requires_manual_review(
        self,
    ) -> None:
        catalog_facade = MagicMock()
        catalog_facade.get_source_health_summary.return_value = (
            _blocked_source_health_summary()
        )
        ingestion_facade = MagicMock()
        ingestion_facade.get_maturity_governance_report.return_value = (
            _empty_maturity_governance_report()
        )
        facade = CatalogRemediationQueryFacade(
            catalog_facade=catalog_facade,
            ingestion_status_facade=ingestion_facade,
            generated_at=lambda: datetime(2026, 6, 9, 10, 5, tzinfo=UTC),
        )

        report = facade.get_remediation_backlog(
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("fred",),
        )

        item = report.items[0]
        assert item.source_selection_status == "blocked"
        assert item.source_selection_blockers == ("selected_source_unsupported",)
        assert item.suggested_actions == (
            "configure_fallback_source",
            "review_source_request",
        )

        detail = facade.get_remediation_item_detail(
            item_id="source_health:stock_daily:2026-06-01",
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("fred",),
        )

        assert [intent.action for intent in detail.approval_intents] == [
            "configure_fallback_source",
            "review_source_request",
        ]
        assert all(intent.intent_type == "manual" for intent in detail.approval_intents)
        assert all(intent.method is None for intent in detail.approval_intents)
        assert all(intent.path is None for intent in detail.approval_intents)
        for intent in detail.approval_intents:
            assert intent.request_template["source_selection_status"] == "blocked"
            assert intent.request_template["source_selection_blockers"] == [
                "selected_source_unsupported"
            ]

    def test_returns_lineage_catalog_asset_repair_approval_intent(self) -> None:
        catalog_facade = MagicMock()
        catalog_facade.get_source_health_summary.return_value = _source_health_summary()
        ingestion_facade = MagicMock()
        ingestion_facade.get_maturity_governance_report.return_value = (
            _maturity_governance_report()
        )
        lineage_facade = MagicMock()
        lineage_facade.get_data_lineage_catalog_report_for_run.return_value = (
            _lineage_catalog_report()
        )
        facade = CatalogRemediationQueryFacade(
            catalog_facade=catalog_facade,
            ingestion_status_facade=ingestion_facade,
            lineage_facade=lineage_facade,
            generated_at=lambda: datetime(2026, 6, 9, 9, 55, tzinfo=UTC),
        )

        detail = facade.get_remediation_item_detail(
            item_id=(
                "lineage_catalog:run-001:input:market:stock_daily:trade_date=2026-06-01"
            ),
            dataset_ids=("stock_daily",),
            trade_dates=("2026-06-01",),
            available_sources=("tushare",),
            run_id="run-001",
        )

        assert [intent.action for intent in detail.approval_intents] == [
            "repair_lineage_catalog_asset",
        ]
        intent = detail.approval_intents[0]
        assert intent.intent_type == "write"
        assert intent.method == "POST"
        assert intent.path == "/ingestion/stock_daily/2026-06-01"
        assert intent.request_template == {
            "dataset_id": "stock_daily",
            "namespace": "market",
            "trade_date": "2026-06-01",
            "run_id": "run-001",
            "side": "input",
            "partition_keys": ["trade_date=2026-06-01"],
            "force": True,
            "source": "auto",
        }
        assert intent.required_operator_inputs == ()
