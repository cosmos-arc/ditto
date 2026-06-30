"""Tests for application-level DataCatalog query facade."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ditto_application.exceptions import AppQueryError
from ditto_application.queries.catalog import (
    CatalogQueryFacade,
    CatalogSourceHealthAttentionItem,
    CatalogSourceHealthSummaryReport,
)
from ditto_data.catalog import (
    DataAssetRef,
    DataCatalogEntry,
    DataSchemaFingerprint,
    InMemoryDataCatalog,
)
from ditto_data.catalog.fallback_policy import (
    CatalogSourceFallbackPolicy,
    CatalogSourceFallbackPolicyEvent,
    CatalogSourceFallbackPolicyStatus,
)
from ditto_data.catalog.promotion import DatasetMaturityPromotionEvent


def _entry(
    dataset_id: str,
    namespace: str,
    partition_keys: tuple[str, ...],
    *,
    storage_uri: str,
    freshness_at: datetime,
) -> DataCatalogEntry:
    return DataCatalogEntry(
        asset=DataAssetRef(
            dataset_id=dataset_id,
            namespace=namespace,
            partition_keys=partition_keys,
        ),
        storage_uri=storage_uri,
        schema=DataSchemaFingerprint(
            schema_hash=f"schema:{dataset_id}:v1",
            row_count=17,
            created_at=datetime(2026, 6, 1, 9, 30, tzinfo=UTC),
        ),
        source="tushare",
        freshness_at=freshness_at,
    )


class TestCatalogQueryFacadeListAssets:
    def test_lists_catalog_assets_with_schema_storage_and_freshness(self) -> None:
        catalog = InMemoryDataCatalog()
        target = _entry(
            "stock_daily",
            "market",
            ("trade_date=2026-06-01",),
            storage_uri="stock_daily/2026",
            freshness_at=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        )
        catalog.upsert_asset(target)
        catalog.upsert_asset(
            _entry(
                "etf_daily",
                "market",
                ("trade_date=2026-06-01",),
                storage_uri="etf_daily/2026",
                freshness_at=datetime(2026, 6, 1, 9, 32, tzinfo=UTC),
            )
        )
        facade = CatalogQueryFacade(catalog)

        result = facade.list_assets(namespace="market", dataset_id="stock_daily")

        assert len(result) == 1
        item = result[0]
        assert item.asset.dataset_id == "stock_daily"
        assert item.asset.namespace == "market"
        assert item.asset.partition_keys == ("trade_date=2026-06-01",)
        assert item.storage_uri == "stock_daily/2026"
        assert item.schema.schema_hash == "schema:stock_daily:v1"
        assert item.schema.row_count == 17
        assert item.source == "tushare"
        assert item.freshness_at == datetime(2026, 6, 1, 9, 31, tzinfo=UTC)

    def test_orders_assets_by_identity_for_stable_api_results(self) -> None:
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            _entry(
                "stock_daily",
                "market",
                ("trade_date=2026-06-02",),
                storage_uri="stock_daily/2026/02",
                freshness_at=datetime(2026, 6, 2, tzinfo=UTC),
            )
        )
        catalog.upsert_asset(
            _entry(
                "stock_daily",
                "market",
                ("trade_date=2026-06-01",),
                storage_uri="stock_daily/2026/01",
                freshness_at=datetime(2026, 6, 1, tzinfo=UTC),
            )
        )
        facade = CatalogQueryFacade(catalog)

        result = facade.list_assets(namespace="market")

        assert [item.asset.partition_keys for item in result] == [
            ("trade_date=2026-06-01",),
            ("trade_date=2026-06-02",),
        ]


class TestCatalogQueryFacadeGetAsset:
    def test_gets_exact_catalog_asset(self) -> None:
        catalog = InMemoryDataCatalog()
        entry = _entry(
            "stock_daily",
            "market",
            ("trade_date=2026-06-01",),
            storage_uri="stock_daily/2026",
            freshness_at=datetime(2026, 6, 1, 9, 31, tzinfo=UTC),
        )
        catalog.upsert_asset(entry)
        facade = CatalogQueryFacade(catalog)

        result = facade.get_asset(
            namespace="market",
            dataset_id="stock_daily",
            partition_keys=("trade_date=2026-06-01",),
        )

        assert result is not None
        assert result.storage_uri == "stock_daily/2026"
        assert result.schema.created_at == datetime(2026, 6, 1, 9, 30, tzinfo=UTC)

    def test_returns_none_for_missing_asset(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        result = facade.get_asset(
            namespace="market",
            dataset_id="stock_daily",
            partition_keys=("trade_date=2026-06-01",),
        )

        assert result is None


class _MaturityPromotionHistoryReader:
    def __init__(
        self,
        events_by_dataset: dict[str, tuple[DatasetMaturityPromotionEvent, ...]],
    ) -> None:
        self._events_by_dataset = events_by_dataset

    def list_dataset_maturity_promotion_events(
        self,
        dataset_id: str,
    ) -> tuple[DatasetMaturityPromotionEvent, ...]:
        return self._events_by_dataset.get(dataset_id, ())


class _SourceFallbackPolicyReader:
    def __init__(
        self,
        policies: tuple[CatalogSourceFallbackPolicy, ...],
    ) -> None:
        self._policies = policies

    def get_source_fallback_policy(
        self,
        policy_id: str,
    ) -> CatalogSourceFallbackPolicy | None:
        return next(
            (policy for policy in self._policies if policy.policy_id == policy_id),
            None,
        )

    def list_source_fallback_policies(
        self,
        *,
        dataset_id: str | None = None,
        status: CatalogSourceFallbackPolicyStatus | None = None,
    ) -> tuple[CatalogSourceFallbackPolicy, ...]:
        return tuple(
            policy
            for policy in self._policies
            if (dataset_id is None or policy.dataset_id == dataset_id)
            and (status is None or policy.status == status)
        )

    def list_source_fallback_policy_events(
        self,
        policy_id: str,
    ) -> tuple[CatalogSourceFallbackPolicyEvent, ...]:
        return ()


def _active_source_fallback_policy(
    *,
    recommended_source: str,
) -> CatalogSourceFallbackPolicy:
    return CatalogSourceFallbackPolicy(
        policy_id="fallback-policy-001",
        dataset_id="macro_indicators",
        namespace="macro",
        trade_date="2024-12-27",
        default_source="tushare",
        selected_source="tushare",
        recommended_source=recommended_source,
        status="active",
        created_by="data-governance",
        created_at=datetime(2026, 6, 1, 10, tzinfo=UTC),
        recommended_actions=("review_source_failover",),
        reason_codes=("manual_source_override",),
        fallback_sources=(recommended_source,),
        unsupported_sources=(),
        source_selection_status="ready",
        source_selection_blockers=(),
        approval_required=False,
        execution_allowed=True,
        decided_by="data-governance",
        decided_at=datetime(2026, 6, 1, 11, tzinfo=UTC),
        decision_notes="approved active fallback for this dataset/date",
    )


class TestCatalogQueryFacadePromotionHistory:
    def test_lists_dataset_maturity_promotion_history(self) -> None:
        promoted = DatasetMaturityPromotionEvent(
            dataset_id="stock_daily",
            action="promoted",
            previous_maturity="experimental",
            next_maturity="initial-focus",
            actor="architecture-review",
            action_at=datetime(2026, 6, 1, 13, 0, tzinfo=UTC),
            evidence_uri="ditto://evidence/stock_daily/runtime-tests",
            notes="all criteria approved",
        )
        revoked = DatasetMaturityPromotionEvent(
            dataset_id="stock_daily",
            action="revoked",
            previous_maturity="initial-focus",
            next_maturity="experimental",
            actor="architecture-review",
            action_at=datetime(2026, 6, 2, 9, 0, tzinfo=UTC),
            evidence_uri="ditto://evidence/stock_daily/runtime-tests",
            revocation_reason="failed_revalidation",
            notes="PIT regression reopened promotion",
        )
        facade = CatalogQueryFacade(
            InMemoryDataCatalog(),
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {"stock_daily": (promoted, revoked)}
            ),
        )

        result = facade.list_maturity_promotion_history("stock_daily")

        assert len(result) == 2
        assert result[0].dataset_id == "stock_daily"
        assert result[0].action == "promoted"
        assert result[0].previous_maturity == "experimental"
        assert result[0].next_maturity == "initial-focus"
        assert result[0].actor == "architecture-review"
        assert result[0].evidence_uri == "ditto://evidence/stock_daily/runtime-tests"
        assert result[1].action == "revoked"
        assert result[1].revocation_reason == "failed_revalidation"


class TestCatalogQueryFacadeSourceHealth:
    def test_reports_source_freshness_and_selected_auto_source(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="macro_indicators",
                    namespace="macro",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="macro/macro_indicators/2024-12-27",
                schema=DataSchemaFingerprint(schema_hash="stale", row_count=1),
                source="tushare",
                freshness_at=now - timedelta(hours=100),
            )
        )
        facade = CatalogQueryFacade(catalog, now=lambda: now)

        report = facade.get_source_health_report(
            dataset_id="macro_indicators",
            trade_date="2024-12-27",
            available_sources=("tushare", "fred"),
        )

        assert report.dataset_id == "macro_indicators"
        assert report.namespace == "macro"
        assert report.trade_date == "2024-12-27"
        assert report.default_source == "tushare"
        assert report.selected_source == "fred"
        assert report.selected_freshness_status == "missing"
        assert report.attention_reasons == (
            "selected_source_missing",
            "default_source_failover",
        )
        assert [source.source for source in report.sources] == ["tushare", "fred"]
        tushare, fred = report.sources
        assert tushare.supported is True
        assert tushare.freshness_status == "stale"
        assert tushare.storage_uri == "macro/macro_indicators/2024-12-27"
        assert tushare.schema_hash == "stale"
        assert tushare.row_count == 1
        assert tushare.freshness_at == now - timedelta(hours=100)
        assert fred.supported is True
        assert fred.freshness_status == "missing"
        assert fred.storage_uri is None
        assert fred.schema_hash is None
        assert report.unsupported_sources == ()
        assert report.selected_source_health.source == "fred"
        assert report.selected_source_health.supported is True
        assert report.selected_source_health.freshness_status == "missing"
        assert report.source_selection_status == "ready"
        assert report.source_selection_blockers == ()

    def test_reports_active_source_fallback_policy_effect(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="macro_indicators",
                    namespace="macro",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="macro/macro_indicators/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:macro:v1",
                    row_count=1,
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=1),
            )
        )
        facade = CatalogQueryFacade(
            catalog,
            source_fallback_policy_reader=_SourceFallbackPolicyReader(
                (_active_source_fallback_policy(recommended_source="fred"),)
            ),
            now=lambda: now,
        )

        report = facade.get_source_health_report(
            dataset_id="macro_indicators",
            trade_date="2024-12-27",
            available_sources=("tushare", "fred"),
        )

        assert report.selected_source == "fred"
        assert report.selected_freshness_status == "missing"
        assert report.failover_from_default is True
        assert report.source_fallback_policy_effect is not None
        assert report.source_fallback_policy_effect.policy_id == "fallback-policy-001"
        assert report.source_fallback_policy_effect.policy_status == "active"
        assert report.source_fallback_policy_effect.catalog_selected_source == "tushare"
        assert report.source_fallback_policy_effect.effective_selected_source == "fred"
        assert report.source_fallback_policy_effect.reason_codes == (
            "manual_source_override",
        )
        assert report.source_fallback_policy_effect.recommended_actions == (
            "review_source_failover",
        )

    def test_reports_latest_revocation_context_with_source_health(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        facade = CatalogQueryFacade(
            InMemoryDataCatalog(),
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {
                    "macro_indicators": (
                        DatasetMaturityPromotionEvent(
                            dataset_id="macro_indicators",
                            action="revoked",
                            previous_maturity="initial-focus",
                            next_maturity="experimental",
                            actor="data-governance",
                            action_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
                            evidence_uri="ditto://evidence/macro/pit",
                            revocation_reason="policy_regression",
                            notes="source health must surface maturity reversal",
                        ),
                    )
                }
            ),
            now=lambda: now,
        )

        report = facade.get_source_health_report(
            dataset_id="macro_indicators",
            trade_date="2024-12-27",
            available_sources=("tushare", "fred"),
        )

        assert report.latest_revocation_reason == "policy_regression"
        assert report.latest_revoked_by == "data-governance"
        assert report.latest_revoked_at == datetime(2026, 6, 2, 9, 30, tzinfo=UTC)

    def test_reports_unsupported_source_attention_when_selected_source_is_fresh(
        self,
    ) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="market/stock_daily/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:stock_daily:v1",
                    row_count=2300,
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=1),
            )
        )
        facade = CatalogQueryFacade(catalog, now=lambda: now)

        report = facade.get_source_health_report(
            dataset_id="stock_daily",
            trade_date="2024-12-27",
            available_sources=("tushare", "fred"),
        )

        assert report.selected_source == "tushare"
        assert report.selected_freshness_status == "fresh"
        assert report.unsupported_sources == ("fred",)
        assert report.attention_reasons == ("unsupported_sources_present",)

    def test_reports_revocation_attention_when_selected_source_is_fresh(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="market/stock_daily/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:stock_daily:v1",
                    row_count=2300,
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=1),
            )
        )
        facade = CatalogQueryFacade(
            catalog,
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {
                    "stock_daily": (
                        DatasetMaturityPromotionEvent(
                            dataset_id="stock_daily",
                            action="revoked",
                            previous_maturity="initial-focus",
                            next_maturity="experimental",
                            actor="data-governance",
                            action_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
                            evidence_uri="ditto://evidence/stock_daily/pit",
                            revocation_reason="failed_revalidation",
                            notes="fresh source data still carries promotion reversal",
                        ),
                    )
                }
            ),
            now=lambda: now,
        )

        report = facade.get_source_health_report(
            dataset_id="stock_daily",
            trade_date="2024-12-27",
            available_sources=("tushare",),
        )

        assert report.selected_source == "tushare"
        assert report.selected_freshness_status == "fresh"
        assert report.latest_revocation_reason == "failed_revalidation"
        assert report.attention_reasons == ("latest_maturity_promotion_revoked",)

    def test_reports_single_source_dataset_without_cross_source_fallback(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        facade = CatalogQueryFacade(InMemoryDataCatalog(), now=lambda: now)

        report = facade.get_source_health_report(
            dataset_id="stock_daily",
            trade_date="2024-12-27",
            available_sources=("tushare", "fred"),
        )

        assert report.default_source == "tushare"
        assert report.selected_source == "tushare"
        assert [source.source for source in report.sources] == ["tushare"]
        assert report.sources[0].freshness_status == "missing"
        assert report.unsupported_sources == ("fred",)

    def test_marks_selected_source_blocked_when_no_supported_source_is_available(
        self,
    ) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        report = facade.get_source_health_report(
            dataset_id="stock_daily",
            trade_date="2024-12-27",
            available_sources=("fred",),
        )

        assert report.selected_source == "fred"
        assert report.sources == ()
        assert report.selected_source_health.source == "fred"
        assert report.selected_source_health.supported is False
        assert report.selected_source_health.freshness_status == "missing"
        assert report.source_selection_status == "blocked"
        assert report.source_selection_blockers == ("selected_source_unsupported",)

    def test_rejects_empty_available_sources(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        with pytest.raises(AppQueryError, match="available_sources"):
            facade.get_source_health_report(
                dataset_id="stock_daily",
                trade_date="2024-12-27",
                available_sources=(),
            )


class TestCatalogQueryFacadeSourceFallbackPolicyPreview:
    def test_previews_review_required_policy_for_failover_with_missing_selected_source(
        self,
    ) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="macro_indicators",
                    namespace="macro",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="macro/macro_indicators/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:macro:v1",
                    row_count=1,
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=100),
            )
        )
        facade = CatalogQueryFacade(catalog, now=lambda: now)

        preview = facade.get_source_fallback_policy_preview(
            dataset_id="macro_indicators",
            trade_date="2024-12-27",
            available_sources=("tushare", "fred"),
        )

        assert preview.dataset_id == "macro_indicators"
        assert preview.namespace == "macro"
        assert preview.trade_date == "2024-12-27"
        assert preview.default_source == "tushare"
        assert preview.selected_source == "fred"
        assert preview.recommended_source == "fred"
        assert preview.policy_status == "review_required"
        assert preview.recommended_actions == (
            "repair_catalog_source_coverage",
            "review_source_failover",
        )
        assert preview.approval_required is True
        assert preview.execution_allowed is True
        assert preview.reason_codes == (
            "selected_source_missing",
            "default_source_failover",
        )
        assert preview.fallback_sources == ("fred",)
        assert preview.source_selection_status == "ready"
        assert preview.source_selection_blockers == ()

    def test_previews_blocked_policy_when_selected_source_is_unsupported(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        preview = facade.get_source_fallback_policy_preview(
            dataset_id="stock_daily",
            trade_date="2024-12-27",
            available_sources=("fred",),
        )

        assert preview.policy_status == "blocked"
        assert preview.recommended_source is None
        assert preview.recommended_actions == (
            "configure_fallback_source",
            "review_source_request",
        )
        assert preview.approval_required is True
        assert preview.execution_allowed is False
        assert preview.source_selection_status == "blocked"
        assert preview.source_selection_blockers == ("selected_source_unsupported",)
        assert "selected_source_unsupported" in preview.reason_codes


class TestCatalogQueryFacadeSourceFallbackPolicySummary:
    def test_summarizes_fallback_policy_previews_across_datasets_and_dates(
        self,
    ) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="macro_indicators",
                    namespace="macro",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="macro/macro_indicators/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:macro:v1",
                    row_count=1,
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=100),
            )
        )
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="market/stock_daily/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:stock_daily:v1",
                    row_count=2300,
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=1),
            )
        )
        facade = CatalogQueryFacade(catalog, now=lambda: now)

        summary = facade.get_source_fallback_policy_summary(
            dataset_ids=("macro_indicators", "stock_daily"),
            trade_dates=("2024-12-27",),
            available_sources=("tushare", "fred"),
        )

        assert summary.dataset_ids == ("macro_indicators", "stock_daily")
        assert summary.trade_dates == ("2024-12-27",)
        assert summary.available_sources == ("tushare", "fred")
        assert summary.total_previews == 2
        assert summary.approval_required_count == 2
        assert summary.execution_allowed_count == 2
        assert [(item.status, item.count) for item in summary.policy_status_counts] == [
            ("ready", 0),
            ("review_required", 2),
            ("blocked", 0),
        ]
        assert [
            (item.action, item.count) for item in summary.recommended_action_counts
        ] == [
            ("repair_catalog_source_coverage", 1),
            ("review_source_failover", 1),
            ("review_source_request", 1),
        ]
        assert [preview.dataset_id for preview in summary.previews] == [
            "macro_indicators",
            "stock_daily",
        ]
        assert summary.previews[0].policy_status == "review_required"
        assert summary.previews[1].recommended_actions == ("review_source_request",)

    def test_rejects_empty_fallback_policy_summary_inputs(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        with pytest.raises(AppQueryError, match="dataset_ids"):
            facade.get_source_fallback_policy_summary(
                dataset_ids=(),
                trade_dates=("2024-12-27",),
                available_sources=("tushare",),
            )

        with pytest.raises(AppQueryError, match="trade_dates"):
            facade.get_source_fallback_policy_summary(
                dataset_ids=("stock_daily",),
                trade_dates=(),
                available_sources=("tushare",),
            )


def _assert_source_health_summary_rollups(
    summary: CatalogSourceHealthSummaryReport,
) -> None:
    assert summary.dataset_ids == ("macro_indicators", "stock_daily")
    assert summary.trade_dates == ("2024-12-27",)
    assert summary.available_sources == ("tushare", "fred")
    assert summary.total_reports == 2
    assert summary.failover_count == 1
    assert summary.no_fallback_source_count == 1
    assert [(item.source, item.count) for item in summary.fallback_source_counts] == [
        ("fred", 1),
    ]
    assert [(item.status, item.count) for item in summary.status_counts] == [
        ("fresh", 1),
        ("stale", 1),
        ("missing", 1),
        ("not_applicable", 0),
    ]
    assert [(item.source, item.count) for item in summary.selected_source_counts] == [
        ("fred", 1),
        ("tushare", 1),
    ]
    assert [(item.reason, item.count) for item in summary.attention_reason_counts] == [
        ("default_source_failover", 1),
        ("selected_source_missing", 1),
        ("unsupported_sources_present", 1),
    ]
    assert [
        (item.severity, item.count) for item in summary.attention_severity_counts
    ] == [
        ("critical", 1),
        ("warning", 0),
        ("info", 1),
    ]


def _assert_macro_missing_attention(
    attention: CatalogSourceHealthAttentionItem,
) -> None:
    assert attention.dataset_id == "macro_indicators"
    assert attention.namespace == "macro"
    assert attention.trade_date == "2024-12-27"
    assert attention.default_source == "tushare"
    assert attention.selected_source == "fred"
    assert attention.selected_freshness_status == "missing"
    assert attention.selected_source_health.source == "fred"
    assert attention.selected_source_health.freshness_status == "missing"
    assert attention.selected_source_health.freshness_sla_hours == 72
    assert attention.selected_source_health.storage_uri is None
    assert attention.attention_reasons == (
        "selected_source_missing",
        "default_source_failover",
    )
    assert attention.attention_severity == "critical"
    assert attention.failover_from_default is True
    assert attention.fallback_sources == ("fred",)
    assert attention.latest_revocation_reason is None


def _assert_stock_unsupported_attention(
    attention: CatalogSourceHealthAttentionItem,
) -> None:
    assert attention.dataset_id == "stock_daily"
    assert attention.namespace == "market"
    assert attention.trade_date == "2024-12-27"
    assert attention.default_source == "tushare"
    assert attention.selected_source == "tushare"
    assert attention.selected_freshness_status == "fresh"
    assert attention.selected_source_health.source == "tushare"
    assert attention.selected_source_health.freshness_status == "fresh"
    assert attention.selected_source_health.storage_uri == (
        "market/stock_daily/2024-12-27"
    )
    assert attention.selected_source_health.schema_hash == "schema:stock_daily:v1"
    assert attention.selected_source_health.row_count == 2300
    assert attention.attention_reasons == ("unsupported_sources_present",)
    assert attention.attention_severity == "info"
    assert attention.unsupported_sources == ("fred",)


class TestCatalogQueryFacadeSourceHealthSummary:
    def test_summarizes_source_health_across_datasets_and_dates(self) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        catalog = InMemoryDataCatalog()
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="macro_indicators",
                    namespace="macro",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="macro/macro_indicators/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:macro:v1", row_count=1
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=100),
            )
        )
        catalog.upsert_asset(
            DataCatalogEntry(
                asset=DataAssetRef(
                    dataset_id="stock_daily",
                    namespace="market",
                    partition_keys=("trade_date=2024-12-27",),
                ),
                storage_uri="market/stock_daily/2024-12-27",
                schema=DataSchemaFingerprint(
                    schema_hash="schema:stock_daily:v1",
                    row_count=2300,
                ),
                source="tushare",
                freshness_at=now - timedelta(hours=1),
            )
        )
        facade = CatalogQueryFacade(catalog, now=lambda: now)

        summary = facade.get_source_health_summary(
            dataset_ids=("macro_indicators", "stock_daily"),
            trade_dates=("2024-12-27",),
            available_sources=("tushare", "fred"),
        )

        _assert_source_health_summary_rollups(summary)
        assert len(summary.attention_required) == 2
        _assert_macro_missing_attention(summary.attention_required[0])
        _assert_stock_unsupported_attention(summary.attention_required[1])
        assert summary.reports[0].failover_from_default is True
        assert summary.reports[0].fallback_sources == ("fred",)
        assert summary.reports[1].failover_from_default is False
        assert summary.reports[1].fallback_sources == ()

    def test_summary_surfaces_blocked_source_selection_context(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        summary = facade.get_source_health_summary(
            dataset_ids=("stock_daily",),
            trade_dates=("2024-12-27",),
            available_sources=("fred",),
        )

        assert [
            (item.status, item.count) for item in summary.source_selection_status_counts
        ] == [
            ("ready", 0),
            ("blocked", 1),
        ]
        assert len(summary.attention_required) == 1
        attention = summary.attention_required[0]
        assert attention.source_selection_status == "blocked"
        assert attention.source_selection_blockers == ("selected_source_unsupported",)

    def test_summary_carries_latest_revocation_context_for_attention_items(
        self,
    ) -> None:
        now = datetime(2026, 6, 1, 12, tzinfo=UTC)
        facade = CatalogQueryFacade(
            InMemoryDataCatalog(),
            maturity_promotion_history_reader=_MaturityPromotionHistoryReader(
                {
                    "macro_indicators": (
                        DatasetMaturityPromotionEvent(
                            dataset_id="macro_indicators",
                            action="revoked",
                            previous_maturity="initial-focus",
                            next_maturity="experimental",
                            actor="data-governance",
                            action_at=datetime(2026, 6, 2, 9, 30, tzinfo=UTC),
                            evidence_uri="ditto://evidence/macro/pit",
                            revocation_reason="policy_regression",
                            notes="source health must surface maturity reversal",
                        ),
                    )
                }
            ),
            now=lambda: now,
        )

        summary = facade.get_source_health_summary(
            dataset_ids=("macro_indicators",),
            trade_dates=("2024-12-27",),
            available_sources=("tushare", "fred"),
        )

        assert summary.revoked_promotion_count == 1
        assert summary.reports[0].latest_revocation_reason == "policy_regression"
        attention = summary.attention_required[0]
        assert attention.latest_revocation_reason == "policy_regression"
        assert attention.latest_revoked_by == "data-governance"
        assert attention.latest_revoked_at == datetime(2026, 6, 2, 9, 30, tzinfo=UTC)

    def test_rejects_empty_summary_inputs(self) -> None:
        facade = CatalogQueryFacade(InMemoryDataCatalog())

        with pytest.raises(AppQueryError, match="dataset_ids"):
            facade.get_source_health_summary(
                dataset_ids=(),
                trade_dates=("2024-12-27",),
                available_sources=("tushare",),
            )

        with pytest.raises(AppQueryError, match="trade_dates"):
            facade.get_source_health_summary(
                dataset_ids=("stock_daily",),
                trade_dates=(),
                available_sources=("tushare",),
            )
