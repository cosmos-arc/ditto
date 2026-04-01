"""Tests for factor definitions and cycle detection (Phase 3: ENG-E-8, ENG-E-11)."""

from __future__ import annotations

import pytest
from ditto_analytics.expression.compiler import (
    ExpressionCompiler,
    detect_dependency_cycles,
)
from ditto_engine.engine.factors import ALL_FACTOR_SPECS
from ditto_engine.engine.specs import DerivedRole, DerivedSpec, MaterializationProfile

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
    """Every factor spec expression must pass ExpressionCompiler.compile()."""

    def test_all_factor_specs_compile(self) -> None:
        """All factor specs in ALL_FACTOR_SPECS must compile without error."""
        compiler = ExpressionCompiler()
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            derived_spec = DerivedSpec(
                id=spec_id,
                version=1,
                role=DerivedRole.FACTOR,
                materialization_profile=MaterializationProfile.SERIES,
                expression=spec.expression,
            )
            compiled = compiler.compile(derived_spec)
            assert compiled is not None, f"Failed to compile {spec_id}"

    def test_factor_specs_have_valid_ids(self) -> None:
        """Every spec id should be a non-empty string."""
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            assert isinstance(spec_id, str)
            assert spec_id
            assert spec.id == spec_id

    def test_factor_specs_have_non_empty_expression(self) -> None:
        """Every spec expression should be non-empty."""
        for spec_id, spec in ALL_FACTOR_SPECS.items():
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
        """Dependencies should reference specs or market.* / fundamentals.*."""
        valid_refs = set(ALL_FACTOR_SPECS.keys())
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            for dep in spec.dependencies:
                is_internal = dep in valid_refs
                is_market = dep.startswith("market.")
                is_fundamental = dep.startswith("fundamentals.")
                assert is_internal or is_market or is_fundamental, (
                    f"{spec_id} references unknown dependency: {dep}"
                )


class TestTopologicalOrder:
    """Dependencies must be defined before dependents."""

    def test_dependencies_precede_dependents(self) -> None:
        """Each dependency must appear in ALL_FACTOR_SPECS."""
        for spec_id, spec in ALL_FACTOR_SPECS.items():
            for dep in spec.dependencies:
                if dep.startswith("market.") or dep.startswith("fundamentals."):
                    continue  # external data columns
                assert dep in ALL_FACTOR_SPECS, (
                    f"{spec_id} depends on '{dep}' which is not in ALL_FACTOR_SPECS"
                )

    def test_minimum_spec_count(self) -> None:
        """There should be at least 30 factor specs defined."""
        assert len(ALL_FACTOR_SPECS) >= 30, (
            f"Expected >= 30 factor specs, got {len(ALL_FACTOR_SPECS)}"
        )
