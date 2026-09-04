"""Unit tests for dataset metadata registry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import ClassVar

import pytest
from ditto_data.catalog.dataset_spec import DatasetSpec
from ditto_data.catalog.metadata import (
    DatasetMetadata,
    default_dataset_metadata,
)
from ditto_data.models.common import Dataset


class TestDatasetMetadataFrozen:
    """DatasetMetadata must be frozen (immutable)."""

    def test_frozen_prevents_attribute_assignment(self) -> None:
        meta = DatasetMetadata(
            dataset_id="test",
            domain="market",
            maturity="experimental",
            schedule="trading_days",
            schema_version="market.test.v1",
        )
        with pytest.raises(FrozenInstanceError):
            meta.dataset_id = "changed"  # type: ignore[misc]

    def test_frozen_prevents_attribute_deletion(self) -> None:
        meta = DatasetMetadata(
            dataset_id="test",
            domain="market",
            maturity="experimental",
            schedule="trading_days",
            schema_version="market.test.v1",
        )
        with pytest.raises(FrozenInstanceError):
            del meta.domain  # type: ignore[misc]


class TestMetadataFieldValidation:
    """DatasetMetadata must reject invalid field values."""

    def test_invalid_domain_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid domain"):
            DatasetMetadata(
                dataset_id="test",
                domain="unknown_domain",  # type: ignore[arg-type]
                maturity="experimental",
                schedule="trading_days",
            )

    def test_invalid_maturity_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid maturity"):
            DatasetMetadata(
                dataset_id="test",
                domain="market",
                maturity="production",  # type: ignore[arg-type]
                schedule="trading_days",
            )

    def test_invalid_schedule_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid schedule"):
            DatasetMetadata(
                dataset_id="test",
                domain="market",
                maturity="experimental",
                schedule="hourly",  # type: ignore[arg-type]
            )

    def test_valid_fields_accepted(self) -> None:
        meta = DatasetMetadata(
            dataset_id="stock_daily",
            domain="market",
            maturity="initial-focus",
            schedule="trading_days",
            schema_version="market.stock_daily.v1",
        )
        assert meta.dataset_id == "stock_daily"
        assert meta.domain == "market"
        assert meta.maturity == "initial-focus"
        assert meta.schedule == "trading_days"
        assert meta.quality_profile == "default"

    def test_custom_quality_profile(self) -> None:
        meta = DatasetMetadata(
            dataset_id="test",
            domain="market",
            maturity="experimental",
            schedule="trading_days",
            quality_profile="strict",
            schema_version="market.test.v1",
        )
        assert meta.quality_profile == "strict"

    def test_default_source_must_be_supported(self) -> None:
        with pytest.raises(ValueError, match="default_source"):
            DatasetMetadata(
                dataset_id="test",
                domain="market",
                maturity="experimental",
                schedule="trading_days",
                default_source="fred",
                supported_sources=("tushare",),
            )

    def test_freshness_sla_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="freshness_sla_hours"):
            DatasetMetadata(
                dataset_id="test",
                domain="market",
                maturity="experimental",
                schedule="trading_days",
                freshness_sla_hours=0,
            )

    def test_schema_version_is_required_for_ingestion_datasets(self) -> None:
        with pytest.raises(ValueError, match="schema_version"):
            DatasetMetadata(
                dataset_id="test",
                domain="market",
                maturity="experimental",
                schedule="trading_days",
            )

    def test_schema_version_must_be_normalized(self) -> None:
        with pytest.raises(ValueError, match="Invalid schema_version"):
            DatasetMetadata(
                dataset_id="test",
                domain="market",
                maturity="experimental",
                schedule="trading_days",
                schema_version="Market.Test.V1",
            )

    def test_ingestion_source_helpers_are_case_insensitive(self) -> None:
        meta = DatasetMetadata(
            dataset_id="test",
            domain="market",
            maturity="experimental",
            schedule="trading_days",
            default_source="tushare",
            supported_sources=("tushare",),
            auxiliary_sources=("fred",),
            ingestion_granularities=("date", "instrument"),
            schema_version="market.test.v1",
        )

        assert meta.supports_source("TUSHARE") is True
        assert meta.supports_source("fred") is False
        assert meta.uses_auxiliary_source("FRED") is True
        assert meta.supports_date_ingestion is True
        assert meta.supports_instrument_ingestion is True


class TestDefaultMetadataCoverage:
    """default_dataset_metadata must cover every Dataset enum member."""

    def test_covers_all_datasets(self) -> None:
        registry = default_dataset_metadata()
        for dataset in Dataset:
            assert dataset.value in registry, (
                f"Dataset.{dataset.name} ({dataset.value}) "
                "missing from default_dataset_metadata()"
            )

    def test_no_extra_entries(self) -> None:
        registry = default_dataset_metadata()
        known_ids = {d.value for d in Dataset}
        extra = set(registry) - known_ids
        assert extra == set(), f"Extra dataset IDs in registry: {extra}"

    def test_registry_size_matches_enum(self) -> None:
        registry = default_dataset_metadata()
        assert len(registry) == len(Dataset)


class TestDefaultMetadataScheduleAssignments:
    """Verify schedule assignments match known scheduling requirements."""

    @pytest.mark.parametrize(
        ("dataset_id", "expected_schedule"),
        [
            ("fx_daily", "natural_days"),
            ("dividend", "natural_days"),
            ("macro_indicators", "source_defined"),
            ("commodity_daily", "source_defined"),
            # All others should be trading_days
            ("stock_daily", "trading_days"),
            ("etf_daily", "trading_days"),
            ("calendar", "trading_days"),
            ("stock_basic", "trading_days"),
            ("balance_sheet", "trading_days"),
            ("index_weight", "trading_days"),
        ],
    )
    def test_schedule_assignment(
        self,
        dataset_id: str,
        expected_schedule: str,
    ) -> None:
        registry = default_dataset_metadata()
        assert registry[dataset_id].schedule == expected_schedule

    def test_dividend_schema_versions_exact_announcement_query_semantics(
        self,
    ) -> None:
        registry = default_dataset_metadata()

        assert registry["dividend"].schema_version == "fundamental.dividend.v2"

    def test_corporate_action_schema_versions_announcement_query_semantics(
        self,
    ) -> None:
        registry = default_dataset_metadata()

        assert (
            registry["corporate_actions"].schema_version
            == "fundamental.corporate_actions.v2"
        )


class TestDefaultMetadataMaturityAssignments:
    """Verify maturity assignments match capability-maturity manifest."""

    INITIAL_FOCUS: ClassVar[frozenset[str]] = frozenset(
        {
            "etf_basic",
            "index_basic",
            "calendar",
            "etf_daily",
            "index_daily",
            "adj_factor",
            "fund_adj",
            "global_index_daily",
            "industry_classification",
            "industry_mapping",
        }
    )

    EXPERIMENTAL: ClassVar[frozenset[str]] = frozenset(
        {
            "stock_basic",
            "stock_daily",
            "stock_status",
            "balance_sheet",
            "income_statement",
            "cash_flow",
            "dividend",
            "valuation_metrics",
            "margin_trading",
            "pledge_ratio",
            "corporate_actions",
            "macro_indicators",
            "fx_daily",
            "commodity_daily",
            "index_weight",
        }
    )

    def test_initial_focus_datasets(self) -> None:
        registry = default_dataset_metadata()
        for dataset_id in self.INITIAL_FOCUS:
            assert registry[dataset_id].maturity == "initial-focus", (
                f"{dataset_id} should be initial-focus"
            )

    def test_experimental_datasets(self) -> None:
        registry = default_dataset_metadata()
        for dataset_id in self.EXPERIMENTAL:
            assert registry[dataset_id].maturity == "experimental", (
                f"{dataset_id} should be experimental"
            )

    def test_experimental_datasets_have_promotion_criteria(self) -> None:
        registry = default_dataset_metadata()
        for dataset_id in self.EXPERIMENTAL:
            criteria = registry[dataset_id].promotion_criteria
            assert criteria, f"{dataset_id} should declare promotion criteria"
            assert all(item.strip() for item in criteria)

    def test_initial_focus_datasets_have_no_promotion_criteria(self) -> None:
        registry = default_dataset_metadata()
        for dataset_id in self.INITIAL_FOCUS:
            assert registry[dataset_id].promotion_criteria == ()

    def test_all_datasets_accounted_for(self) -> None:
        registry = default_dataset_metadata()
        all_accounted = self.INITIAL_FOCUS | self.EXPERIMENTAL
        assert set(registry) == all_accounted


class TestDefaultMetadataDomainAssignments:
    """Verify domain assignments are consistent."""

    def test_metadata_domain_datasets(self) -> None:
        registry = default_dataset_metadata()
        for dataset_id in (
            "stock_basic",
            "etf_basic",
            "index_basic",
            "calendar",
            "industry_classification",
            "industry_mapping",
        ):
            assert registry[dataset_id].domain == "metadata", (
                f"{dataset_id} should be in metadata domain"
            )

    def test_market_domain_datasets(self) -> None:
        registry = default_dataset_metadata()
        market_ids = {
            "stock_daily",
            "etf_daily",
            "index_daily",
            "stock_status",
            "adj_factor",
            "fund_adj",
            "index_weight",
            "global_index_daily",
        }
        for dataset_id in market_ids:
            assert registry[dataset_id].domain == "market", (
                f"{dataset_id} should be in market domain"
            )

    def test_fundamental_domain_datasets(self) -> None:
        registry = default_dataset_metadata()
        for dataset_id in (
            "balance_sheet",
            "income_statement",
            "cash_flow",
            "dividend",
        ):
            assert registry[dataset_id].domain == "fundamental", (
                f"{dataset_id} should be in fundamental domain"
            )

    def test_capital_domain_datasets(self) -> None:
        registry = default_dataset_metadata()
        for dataset_id in (
            "valuation_metrics",
            "margin_trading",
            "pledge_ratio",
            "corporate_actions",
        ):
            assert registry[dataset_id].domain == "capital", (
                f"{dataset_id} should be in capital domain"
            )

    def test_macro_domain_datasets(self) -> None:
        registry = default_dataset_metadata()
        for dataset_id in ("macro_indicators", "fx_daily", "commodity_daily"):
            assert registry[dataset_id].domain == "macro", (
                f"{dataset_id} should be in macro domain"
            )

    def test_workstation_context_products_freeze_pit_contracts(self) -> None:
        registry = default_dataset_metadata()

        global_index = registry["global_index_daily"]
        assert global_index.domain == "market"
        assert global_index.schedule == "source_defined"
        assert global_index.asset_class == "index"
        assert global_index.dataset_spec.primary_key == (
            "source_ticker",
            "trade_date",
            "knowledge_date",
        )
        assert global_index.dataset_spec.provider_datasets == ("tushare:index_global",)
        assert global_index.dataset_spec.timezone == "source_defined"
        assert global_index.dataset_spec.currency == "mixed"
        assert global_index.dataset_spec.knowledge_date_field == "knowledge_date"
        assert global_index.dataset_spec.revision_policy == "append_only"

        classification = registry["industry_classification"]
        mapping = registry["industry_mapping"]
        assert classification.domain == mapping.domain == "metadata"
        assert classification.schedule == mapping.schedule == "source_defined"
        assert classification.dataset_spec.provider_datasets == (
            "tushare:index_classify",
        )
        assert mapping.dataset_spec.provider_datasets == ("tushare:index_member_all",)
        assert classification.dataset_spec.knowledge_date_field == "knowledge_date"
        assert mapping.dataset_spec.knowledge_date_field == "knowledge_date"
        assert classification.dataset_spec.revision_policy == "effective_dated"
        assert mapping.dataset_spec.revision_policy == "effective_dated"


class TestDefaultMetadataSourceCapabilities:
    """Verify source capabilities and ingestion granularities are catalog-owned."""

    def test_stock_daily_declares_tushare_date_and_instrument_ingestion(self) -> None:
        meta = default_dataset_metadata()["stock_daily"]

        assert meta.default_source == "tushare"
        assert meta.supported_sources == ("tushare",)
        assert meta.auxiliary_sources == ()
        assert meta.ingestion_granularities == ("date", "instrument")
        assert meta.freshness_sla_hours == 36
        assert meta.schema_version == "market.stock_daily.v1"
        assert meta.supports_source("tushare") is True
        assert meta.supports_source("fred") is False

    def test_macro_indicators_declares_tushare_and_fred_runtime_sources(
        self,
    ) -> None:
        meta = default_dataset_metadata()["macro_indicators"]

        assert meta.default_source == "tushare"
        assert meta.supported_sources == ("tushare", "fred")
        assert meta.freshness_sla_hours == 72
        assert meta.supports_source("tushare") is True
        assert meta.supports_source("fred") is True

    def test_commodity_daily_declares_fred_auxiliary_not_runtime_source(
        self,
    ) -> None:
        meta = default_dataset_metadata()["commodity_daily"]

        assert meta.default_source == "tushare"
        assert meta.supported_sources == ("tushare",)
        assert meta.auxiliary_sources == ("fred",)
        assert meta.supports_source("fred") is False
        assert meta.uses_auxiliary_source("fred") is True

    def test_index_weight_declares_tushare_date_ingestion(self) -> None:
        meta = default_dataset_metadata()["index_weight"]

        assert meta.default_source == "tushare"
        assert meta.supported_sources == ("tushare",)
        assert meta.ingestion_granularities == ("date", "instrument")
        assert meta.freshness_sla_hours is not None


class TestDefaultMetadataAssetClassPolicy:
    """Verify dataset asset-class policy is catalog-owned, not enum-owned."""

    def test_stock_daily_declares_stock_asset_class(self) -> None:
        meta = default_dataset_metadata()["stock_daily"]

        assert meta.asset_class == "stock"

    def test_etf_daily_declares_etf_asset_class(self) -> None:
        meta = default_dataset_metadata()["etf_daily"]

        assert meta.asset_class == "etf"

    def test_metadata_dataset_has_no_asset_class(self) -> None:
        meta = default_dataset_metadata()["stock_basic"]

        assert meta.asset_class is None


class TestDefaultMetadataStorageLocationPolicy:
    """Verify runtime storage location policy is owned by dataset metadata."""

    def test_stock_daily_declares_allowed_storage_prefixes(self) -> None:
        meta = default_dataset_metadata()["stock_daily"]

        assert "stock_daily/" in meta.storage_uri_prefixes
        assert "market/stock_daily/" in meta.storage_uri_prefixes
        assert "lake://market/stock_daily/" in meta.storage_uri_prefixes
        assert "sqlite:///market/stock_daily/" in meta.storage_uri_prefixes

    def test_calendar_declares_calendar_store_prefix(self) -> None:
        meta = default_dataset_metadata()["calendar"]

        assert "calendar_store:" in meta.storage_uri_prefixes

    def test_basic_metadata_declares_instrument_store_prefixes(self) -> None:
        meta = default_dataset_metadata()["stock_basic"]

        assert "instrument_reader:stock_basic" in meta.storage_uri_prefixes
        assert "instrument_store:stock_basic" in meta.storage_uri_prefixes

    def test_storage_prefixes_must_be_normalized(self) -> None:
        with pytest.raises(ValueError, match="storage_uri_prefixes"):
            DatasetMetadata(
                dataset_id="test",
                domain="market",
                maturity="experimental",
                schedule="trading_days",
                schema_version="market.test.v1",
                storage_uri_prefixes=(" lake://market/test/",),
            )


class TestR2DataProductContracts:
    """R2 scope and product semantics must be frozen in the data catalog."""

    HARD_SCOPE: ClassVar[frozenset[str]] = frozenset(
        {
            "calendar",
            "stock_basic",
            "etf_basic",
            "index_basic",
            "stock_daily",
            "etf_daily",
            "index_daily",
            "global_index_daily",
            "adj_factor",
            "fund_adj",
            "stock_status",
            "index_weight",
            "corporate_actions",
            "balance_sheet",
            "income_statement",
            "cash_flow",
            "dividend",
            "valuation_metrics",
            "macro_indicators",
            "commodity_daily",
            "industry_classification",
            "industry_mapping",
        }
    )
    DEFERRED_SCOPE: ClassVar[frozenset[str]] = frozenset(
        {"margin_trading", "pledge_ratio", "fx_daily"}
    )

    def test_freezes_exact_r2_scope(self) -> None:
        registry = default_dataset_metadata()

        hard_scope = {
            dataset_id
            for dataset_id, metadata in registry.items()
            if metadata.dataset_spec.r2_scope == "hard"
        }
        deferred_scope = {
            dataset_id
            for dataset_id, metadata in registry.items()
            if metadata.dataset_spec.r2_scope == "deferred"
        }

        assert hard_scope == self.HARD_SCOPE
        assert deferred_scope == self.DEFERRED_SCOPE

    def test_every_dataset_freezes_operational_product_fields(self) -> None:
        registry = default_dataset_metadata()

        for dataset_id, metadata in registry.items():
            spec = metadata.dataset_spec
            assert isinstance(spec, DatasetSpec)
            assert spec.dataset_id == dataset_id
            assert spec.owner == "data-platform"
            assert spec.primary_key
            assert spec.partition_keys
            assert spec.provider_datasets
            assert spec.schema_version.endswith((".v1", ".v2"))
            assert spec.frequency in {
                "static",
                "trading_daily",
                "monthly",
                "quarterly",
                "event",
                "source_defined",
            }
            assert spec.timezone
            assert spec.currency in {"CNY", "mixed", None}
            assert spec.bootstrap_chunk in {
                "month",
                "quarter",
                "year",
                "source_defined",
            }
            assert spec.coverage_start_rule
            assert spec.fallback_mode in {"automatic", "manual", "none"}
            assert spec.revision_policy in {
                "append_only",
                "effective_dated",
                "not_applicable",
            }
            assert spec.runbook.startswith("docs/operations/")
            assert spec.license_policy == "provider_ledger_required"

    def test_hard_scope_freezes_coverage_targets(self) -> None:
        registry = default_dataset_metadata()

        for dataset_id in self.HARD_SCOPE:
            contract = registry[dataset_id].dataset_spec
            assert contract.raw_target_from is not None
            assert contract.certified_target_from is not None

        assert registry["stock_daily"].dataset_spec.raw_target_from == "2015-01-01"
        assert (
            registry["stock_status"].dataset_spec.certified_target_from == "2016-01-01"
        )
        assert (
            registry["macro_indicators"].dataset_spec.knowledge_date_field
            == "knowledge_date"
        )
        assert (
            registry["index_weight"].dataset_spec.revision_policy == "effective_dated"
        )

    def test_dataset_spec_identity_must_match_metadata(self) -> None:
        stock_spec = default_dataset_metadata()["stock_daily"].dataset_spec

        with pytest.raises(ValueError, match=r"dataset_spec\.dataset_id"):
            DatasetMetadata(
                dataset_id="other",
                domain="market",
                maturity="experimental",
                schedule="trading_days",
                schema_version="market.other.v1",
                dataset_spec=stock_spec,
            )
