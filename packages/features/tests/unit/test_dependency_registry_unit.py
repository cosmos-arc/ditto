"""Tests for materialization dependency registry contracts."""

from __future__ import annotations

import pytest
from ditto_features.materialization.dependency_registry import (
    DependencyContract,
    DependencyRef,
    classify_dependencies,
    contract_for_ref,
    dependency_contracts,
    dependency_refs,
    missing_contract_columns,
    resolve_dependency,
    resolve_etf_dependency,
    resolve_market_dependency,
)


class TestResolveDependency:
    """Single dependency resolution should be package-owned and explicit."""

    def test_market_dependency_resolves_dataset_column_and_persistent_ref(self) -> None:
        resolved = resolve_dependency("market.close")

        assert resolved.source == "market.close"
        assert resolved.kind == "dataset"
        assert resolved.ref == "market.stock_daily"
        assert resolved.column == "close"
        assert resolved.to_ref() == DependencyRef(
            kind="dataset", ref="market.stock_daily"
        )

    def test_etf_dependency_resolves_dataset_column_and_persistent_ref(self) -> None:
        resolved = resolve_dependency("etf.pct_change")

        assert resolved.source == "etf.pct_change"
        assert resolved.kind == "dataset"
        assert resolved.ref == "etf.daily"
        assert resolved.column == "pct_change"

    def test_dotted_derived_dependency_remains_derived_ref(self) -> None:
        resolved = resolve_dependency("factor.alpha_upstream")

        assert resolved.source == "factor.alpha_upstream"
        assert resolved.kind == "derived"
        assert resolved.ref == "factor.alpha_upstream"
        assert resolved.column is None

    def test_plain_identifier_has_no_persistent_ref(self) -> None:
        assert resolve_dependency("close") is None


class TestDatasetResolvers:
    """Runtime input providers need dataset column mapping from the same registry."""

    @pytest.mark.parametrize(
        ("dependency", "expected"),
        [
            ("market.close", ("market.stock_daily", "close")),
            ("market.adj_factor", ("market.adj_factor", "adj_factor")),
            ("market.is_st", ("market.stock_status", "is_st")),
        ],
    )
    def test_resolve_market_dependency(
        self,
        dependency: str,
        expected: tuple[str, str],
    ) -> None:
        assert resolve_market_dependency(dependency) == expected

    def test_resolve_market_dependency_rejects_unknown_columns(self) -> None:
        with pytest.raises(NotImplementedError, match=r"market\.unknown_col"):
            resolve_market_dependency("market.unknown_col")

    @pytest.mark.parametrize(
        ("dependency", "expected"),
        [
            ("etf.close", ("etf.daily", "close")),
            ("etf.volume", ("etf.daily", "volume")),
            ("etf.pct_change", ("etf.daily", "pct_change")),
        ],
    )
    def test_resolve_etf_dependency(
        self,
        dependency: str,
        expected: tuple[str, str],
    ) -> None:
        assert resolve_etf_dependency(dependency) == expected

    def test_resolve_etf_dependency_rejects_unknown_columns(self) -> None:
        with pytest.raises(NotImplementedError, match=r"etf\.unknown_col"):
            resolve_etf_dependency("etf.unknown_col")


class TestDependencyRefs:
    """Persistent dependency refs should be deterministic and deduplicated."""

    def test_dependency_refs_are_deduped_in_first_seen_order(self) -> None:
        result = dependency_refs(
            (
                "market.close",
                "market.volume",
                "etf.close",
                "market.close",
                "factor.alpha",
                "close",
            )
        )

        assert result == (
            DependencyRef(kind="dataset", ref="market.stock_daily"),
            DependencyRef(kind="dataset", ref="etf.daily"),
            DependencyRef(kind="derived", ref="factor.alpha"),
        )


class TestDependencyContracts:
    """Schema and time contracts should live beside dependency resolution."""

    def test_contract_for_ref_exposes_dataset_schema_and_time_semantics(
        self,
    ) -> None:
        contract = contract_for_ref(
            DependencyRef(kind="dataset", ref="market.stock_daily")
        )

        assert contract == DependencyContract(
            ref=DependencyRef(kind="dataset", ref="market.stock_daily"),
            catalog_dataset_id="stock_daily",
            catalog_namespace="market",
            required_columns=(
                "open",
                "high",
                "low",
                "close",
                "pre_close",
                "volume",
                "amount",
            ),
            entity_keys=("instrument_id",),
            time_keys=("trade_date",),
            availability_time_key="trade_date",
            grain="1d",
            schema_version="market.stock_daily.v1",
        )
        assert contract.required_frame_columns == (
            "instrument_id",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "pre_close",
            "volume",
            "amount",
        )

    def test_dependency_contracts_group_requested_columns_by_dataset_ref(
        self,
    ) -> None:
        contracts = dependency_contracts(
            (
                "market.volume",
                "market.close",
                "market.volume",
                "factor.alpha",
                "close",
                "etf.pct_change",
            )
        )

        assert contracts == (
            DependencyContract(
                ref=DependencyRef(kind="dataset", ref="market.stock_daily"),
                catalog_dataset_id="stock_daily",
                catalog_namespace="market",
                required_columns=("volume", "close"),
                entity_keys=("instrument_id",),
                time_keys=("trade_date",),
                availability_time_key="trade_date",
                grain="1d",
                schema_version="market.stock_daily.v1",
            ),
            DependencyContract(
                ref=DependencyRef(kind="dataset", ref="etf.daily"),
                catalog_dataset_id="etf_daily",
                catalog_namespace="etf",
                required_columns=("pct_change",),
                entity_keys=("instrument_id",),
                time_keys=("trade_date",),
                availability_time_key="trade_date",
                grain="1d",
                schema_version="etf.daily.v1",
            ),
        )

    def test_contract_for_non_dataset_ref_is_not_owned_by_dataset_registry(
        self,
    ) -> None:
        assert (
            contract_for_ref(DependencyRef(kind="derived", ref="factor.alpha")) is None
        )

    def test_missing_contract_columns_reports_schema_gap(self) -> None:
        contract = dependency_contracts(("market.volume", "market.close"))[0]

        assert missing_contract_columns(
            contract,
            available_columns=("instrument_id", "trade_date", "close"),
        ) == ("volume",)


class TestClassifyDependencies:
    """Runtime grouping should share the same registry as persistent refs."""

    def test_classify_dependencies_groups_columns_by_dataset_and_derived_ref(
        self,
    ) -> None:
        groups = classify_dependencies(
            (
                "market.close",
                "market.volume",
                "market.adj_factor",
                "etf.pct_change",
                "factor.alpha",
            )
        )

        assert groups.market == {
            "market.stock_daily": frozenset({"close", "volume"}),
            "market.adj_factor": frozenset({"adj_factor"}),
        }
        assert groups.etf == {"etf.daily": frozenset({"pct_change"})}
        assert groups.derived == ("factor.alpha",)
