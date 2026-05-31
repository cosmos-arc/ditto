"""Unit tests for dataset metadata registry."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import ClassVar

import pytest
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
        )
        with pytest.raises(FrozenInstanceError):
            meta.dataset_id = "changed"  # type: ignore[misc]

    def test_frozen_prevents_attribute_deletion(self) -> None:
        meta = DatasetMetadata(
            dataset_id="test",
            domain="market",
            maturity="experimental",
            schedule="trading_days",
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
        )
        assert meta.quality_profile == "strict"


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


class TestDefaultMetadataMaturityAssignments:
    """Verify maturity assignments match capability-maturity manifest."""

    INITIAL_FOCUS: ClassVar[frozenset[str]] = frozenset(
        {
            "stock_basic",
            "etf_basic",
            "index_basic",
            "calendar",
            "stock_daily",
            "etf_daily",
            "index_daily",
            "stock_status",
            "adj_factor",
            "fund_adj",
        }
    )

    EXPERIMENTAL: ClassVar[frozenset[str]] = frozenset(
        {
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
