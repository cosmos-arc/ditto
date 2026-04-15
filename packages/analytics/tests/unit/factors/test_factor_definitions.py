"""Tests for factor definitions and cycle detection (Phase 3: ENG-E-8, ENG-E-11)."""

from __future__ import annotations

import pytest
from ditto_analytics.expression.compiler import (
    ExpressionCompiler,
    detect_dependency_cycles,
)
from ditto_analytics.factors import ALL_FACTOR_SPECS
from ditto_kernel.specs import DerivedRole, DerivedSpec, MaterializationProfile

# ---------------------------------------------------------------------------
# Task 3A: detect_dependency_cycles
# ---------------------------------------------------------------------------


class TestDetectDependencyCycles:
    """Tests for the Kahn's algorithm cycle detector."""

    def test_no_cycle_dag_passes(self) -> None:
        """A valid DAG should not raise."""
        detect_dependency_cycles({"a": ("b", "c"), "b": (), "c": ()})

    def test_empty_graph_passes(self) -> None:
        """An empty graph should not raise."""
        detect_dependency_cycles({})

    def test_single_node_passes(self) -> None:
        """A single node with no dependencies should not raise."""
        detect_dependency_cycles({"a": ()})

    def test_linear_chain_passes(self) -> None:
        """A linear chain a -> b -> c should not raise."""
        detect_dependency_cycles({"a": ("b",), "b": ("c",), "c": ()})

    def test_self_cycle_raises(self) -> None:
        """A node depending on itself should raise ValueError."""
        with pytest.raises(ValueError, match=r"cycle|circular"):
            detect_dependency_cycles({"a": ("a",)})

    def test_mutual_cycle_raises(self) -> None:
        """A -> B and B -> A should raise ValueError."""
        with pytest.raises(ValueError, match=r"cycle|circular"):
            detect_dependency_cycles({"a": ("b",), "b": ("a",)})

    def test_longer_cycle_raises(self) -> None:
        """A -> B -> C -> A should raise ValueError."""
        with pytest.raises(ValueError, match=r"cycle|circular"):
            detect_dependency_cycles({"a": ("b",), "b": ("c",), "c": ("a",)})

    def test_diamond_dag_passes(self) -> None:
        """Diamond: A -> B, A -> C, B -> D, C -> D is a valid DAG."""
        detect_dependency_cycles({"a": ("b", "c"), "b": ("d",), "c": ("d",), "d": ()})

    def test_cycle_with_independent_nodes_raises(self) -> None:
        """A graph with a cycle among a subset should still raise."""
        with pytest.raises(ValueError, match=r"cycle|circular"):
            detect_dependency_cycles({"a": ("b",), "b": ("a",), "c": ()})

    def test_error_message_contains_node_names(self) -> None:
        """The ValueError message should contain cycle node names."""
        with pytest.raises(ValueError) as exc_info:
            detect_dependency_cycles({"alpha": ("beta",), "beta": ("alpha",)})
        message = str(exc_info.value).lower()
        assert "alpha" in message or "beta" in message


# ---------------------------------------------------------------------------
# Task 3B: Factor definitions
# ---------------------------------------------------------------------------


class TestFactorDefinitionsCompile:
    """Every expression-type factor spec must pass ExpressionCompiler.compile()."""

    def test_all_expression_specs_compile(self) -> None:
        """All expression-type factor specs must compile without error."""
        compiler = ExpressionCompiler()
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            if spec.computation_type == "python":
                continue
            derived_spec = DerivedSpec(
                id=spec_id,
                version=1,
                role=DerivedRole.FACTOR,
                materialization_profile=MaterializationProfile.SERIES,
                expression=spec.expression,
            )
            compiled = compiler.compile(derived_spec)
            assert compiled is not None, f"Failed to compile {spec_id}"

    def test_python_specs_have_empty_expression(self) -> None:
        """Python-type factor specs should have empty expression."""
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            if spec.computation_type == "python":
                assert spec.expression == "", (
                    f"Python factor {spec_id} should have empty expression"
                )

    def test_factor_specs_have_valid_ids(self) -> None:
        """Every spec id should be a non-empty string."""
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            assert isinstance(spec_id, str)
            assert spec_id
            assert spec.id == spec_id

    def test_expression_specs_have_non_empty_expression(self) -> None:
        """Every expression-type spec should have a non-empty expression."""
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            if spec.computation_type == "python":
                continue
            assert spec.expression.strip(), f"Empty expression for {spec_id}"


class TestDependencyDagValid:
    """ALL_FACTOR_SPECS should form a valid DAG (no cycles)."""

    def test_no_cycles_in_factor_specs(self) -> None:
        """The dependency graph of all factor specs must be acyclic."""
        graph = {
            spec_id: spec.dependencies for spec_id, spec in ALL_FACTOR_SPECS.items()
        }
        detect_dependency_cycles(graph)

    def test_dependencies_reference_known_specs_or_data_columns(
        self,
    ) -> None:
        """Dependencies should reference specs or known data column prefixes."""
        valid_refs = set(ALL_FACTOR_SPECS.keys())
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            for dep in spec.dependencies:
                is_internal = dep in valid_refs
                is_market = dep.startswith("market.")
                is_fundamental = dep.startswith("fundamentals.")
                is_capital = dep.startswith("capital.")
                assert is_internal or is_market or is_fundamental or is_capital, (
                    f"{spec_id} references unknown dependency: {dep}"
                )


class TestTopologicalOrder:
    """Dependencies must be defined before dependents."""

    def test_dependencies_precede_dependents(self) -> None:
        """Each dependency must appear in ALL_FACTOR_SPECS."""
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            for dep in spec.dependencies:
                if (
                    dep.startswith("market.")
                    or dep.startswith("fundamentals.")
                    or dep.startswith("capital.")
                ):
                    continue  # external data columns
                assert dep in ALL_FACTOR_SPECS, (
                    f"{spec_id} depends on '{dep}' which is not in ALL_FACTOR_SPECS"
                )

    def test_minimum_spec_count(self) -> None:
        """There should be at least 119 factor specs defined (V1 RC target)."""
        assert len(ALL_FACTOR_SPECS) >= 119, (
            f"Expected >= 119 factor specs, got {len(ALL_FACTOR_SPECS)}"
        )


class TestFactorCategoryCoverage:
    """Verify all factor categories are represented."""

    def test_has_size_factors(self) -> None:
        """Size category should have at least 3 factors."""
        prefixes = ("log_", "size_", "market_cap", "free_float")
        size_ids = [k for k in ALL_FACTOR_SPECS if k.startswith(prefixes)]
        assert len(size_ids) >= 3, f"Expected >= 3 size factors, got {len(size_ids)}"

    def test_has_value_factors(self) -> None:
        """Value category should have at least 5 factors."""
        prefixes = ("value_", "dividend_", "bp_", "ep_", "pcf_", "ev_")
        value_ids = [k for k in ALL_FACTOR_SPECS if k.startswith(prefixes)]
        assert len(value_ids) >= 5, f"Expected >= 5 value factors, got {len(value_ids)}"

    def test_has_momentum_factors(self) -> None:
        """Momentum category should have at least 5 factors."""
        keywords = ("momentum", "reversal", "umd", "sequential")
        momentum_ids = [k for k in ALL_FACTOR_SPECS if any(w in k for w in keywords)]
        assert len(momentum_ids) >= 5, (
            f"Expected >= 5 momentum factors, got {len(momentum_ids)}"
        )

    def test_has_quality_factors(self) -> None:
        """Quality category should have at least 5 factors."""
        prefixes = (
            "roa",
            "accruals",
            "delta_roe",
            "roe_",
            "cash_ratio",
            "gross_margin",
            "operating_leverage",
            "earnings_",
        )
        quality_ids = [k for k in ALL_FACTOR_SPECS if k.startswith(prefixes)]
        assert len(quality_ids) >= 5, (
            f"Expected >= 5 quality factors, got {len(quality_ids)}"
        )

    def test_has_volatility_factors(self) -> None:
        """Volatility category should have at least 10 factors."""
        prefixes = (
            "volatility_",
            "cmra",
            "beta_",
            "idio",
            "downside_",
            "realized_",
            "vol_ratio",
            "parkinson_",
            "garman_",
            "overnight_",
            "intraday_",
        )
        vol_ids = [k for k in ALL_FACTOR_SPECS if k.startswith(prefixes)]
        assert len(vol_ids) >= 10, (
            f"Expected >= 10 volatility factors, got {len(vol_ids)}"
        )

    def test_has_liquidity_factors(self) -> None:
        """Liquidity category should have at least 4 factors."""
        prefixes = ("turnover_", "amihud", "volume_price", "mfi", "obv")
        liq_ids = [k for k in ALL_FACTOR_SPECS if k.startswith(prefixes)]
        assert len(liq_ids) >= 4, f"Expected >= 4 liquidity factors, got {len(liq_ids)}"

    def test_has_growth_factors(self) -> None:
        """Growth category should have at least 3 factors."""
        keywords = ("growth", "sustainable")
        growth_ids = [k for k in ALL_FACTOR_SPECS if any(w in k for w in keywords)]
        assert len(growth_ids) >= 3, (
            f"Expected >= 3 growth factors, got {len(growth_ids)}"
        )

    def test_has_technical_factors(self) -> None:
        """Technical category should have at least 30 factors."""
        prefixes = (
            "ma_",
            "ema_",
            "rsi_",
            "macd",
            "bollinger",
            "atr_",
            "volume_ma",
            "returns_",
            "cci_",
            "williams",
            "vwap_",
            "choppiness",
            "elder_ray",
            "kdj_",
            "supertrend",
            "obv_",
        )
        tech_ids = [k for k in ALL_FACTOR_SPECS if k.startswith(prefixes)]
        assert len(tech_ids) >= 30, (
            f"Expected >= 30 technical factors, got {len(tech_ids)}"
        )

    def test_has_alternative_factors(self) -> None:
        """Alternative category should have at least 2 factors."""
        prefixes = ("margin_", "pledge_", "short_")
        alt_ids = [k for k in ALL_FACTOR_SPECS if k.startswith(prefixes)]
        assert len(alt_ids) >= 2, (
            f"Expected >= 2 alternative factors, got {len(alt_ids)}"
        )


class TestPythonFactors:
    """Verify Python-type factor specs are well-formed."""

    def test_python_factors_have_dependencies(self) -> None:
        """Python factors should declare at least one dependency."""
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            if spec.computation_type == "python":
                assert len(spec.dependencies) > 0, (
                    f"Python factor {spec_id} must declare dependencies"
                )

    def test_python_factors_have_description(self) -> None:
        """Python factors should have a non-empty description."""
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            if spec.computation_type == "python":
                assert spec.description, (
                    f"Python factor {spec_id} must have a description"
                )
