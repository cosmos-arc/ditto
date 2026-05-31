"""Comprehensive tests for expression/registry.py operator specs.

Tests operator registration, arity validation, suggestion engine,
and P0_OPERATOR_SPECS completeness.
"""

from __future__ import annotations

import pytest
from ditto_features.expression.registry import (
    P0_OPERATOR_SPECS,
    OperatorSpec,
    suggest_operator_names,
)

# ---------------------------------------------------------------------------
# OperatorSpec
# ---------------------------------------------------------------------------


class TestOperatorSpec:
    """Tests for OperatorSpec dataclass."""

    def test_accepts_arity_exact_min_max(self) -> None:
        """accepts_arity returns True when arity in [min, max]."""
        spec = OperatorSpec(name="ts_mean", version="1", min_args=2, max_args=2)
        assert spec.accepts_arity(2) is True

    def test_accepts_arity_below_min(self) -> None:
        """accepts_arity returns False when arity < min."""
        spec = OperatorSpec(name="ts_mean", version="1", min_args=2, max_args=2)
        assert spec.accepts_arity(1) is False

    def test_accepts_arity_above_max(self) -> None:
        """accepts_arity returns False when arity > max."""
        spec = OperatorSpec(name="abs", version="1", min_args=1, max_args=1)
        assert spec.accepts_arity(2) is False

    def test_accepts_arity_variable(self) -> None:
        """accepts_arity handles variable-arity operators."""
        spec = OperatorSpec(name="coalesce", version="1", min_args=1, max_args=10)
        assert spec.accepts_arity(1) is True
        assert spec.accepts_arity(5) is True
        assert spec.accepts_arity(10) is True
        assert spec.accepts_arity(11) is False

    def test_accepts_arity_zero(self) -> None:
        """accepts_arity returns False for zero args."""
        spec = OperatorSpec(name="abs", version="1", min_args=1, max_args=1)
        assert spec.accepts_arity(0) is False

    def test_frozen(self) -> None:
        """OperatorSpec is frozen."""
        spec = OperatorSpec(name="abs", version="1", min_args=1, max_args=1)
        with pytest.raises(AttributeError):
            spec.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# P0_OPERATOR_SPECS completeness
# ---------------------------------------------------------------------------


class TestP0OperatorSpecs:
    """Tests for P0_OPERATOR_SPECS registry completeness."""

    def test_not_empty(self) -> None:
        """Registry is not empty."""
        assert len(P0_OPERATOR_SPECS) > 0

    def test_all_specs_are_operator_spec(self) -> None:
        """All values are OperatorSpec instances."""
        for spec in P0_OPERATOR_SPECS.values():
            assert isinstance(spec, OperatorSpec)

    def test_all_names_match_keys(self) -> None:
        """Each spec name matches its dictionary key."""
        for key, spec in P0_OPERATOR_SPECS.items():
            assert spec.name == key

    @pytest.mark.parametrize(
        "name",
        [
            "abs",
            "ceil",
            "exp",
            "floor",
            "log",
            "log10",
            "sign",
            "sqrt",
            "round",
            "max2",
            "min2",
            "power",
            "clip",
            "if_else",
            "coalesce",
        ],
    )
    def test_scalar_operators_registered(self, name: str) -> None:
        """Scalar operators are registered."""
        assert name in P0_OPERATOR_SPECS

    @pytest.mark.parametrize(
        "name",
        [
            "ts_delay",
            "ts_delta",
            "ts_pct_change",
            "ts_rank",
            "ts_argmax",
            "ts_argmin",
            "ts_corr",
            "ts_cov",
            "ts_ema",
            "ts_decay_linear",
        ],
    )
    def test_ts_special_operators_registered(self, name: str) -> None:
        """Time-series special operators are registered."""
        assert name in P0_OPERATOR_SPECS

    @pytest.mark.parametrize(
        "name",
        [
            "ts_count",
            "ts_max",
            "ts_mean",
            "ts_median",
            "ts_min",
            "ts_std",
            "ts_sum",
            "ts_var",
        ],
    )
    def test_rolling_operators_registered(self, name: str) -> None:
        """Rolling window operators are registered."""
        assert name in P0_OPERATOR_SPECS

    @pytest.mark.parametrize(
        "name",
        [
            "cs_rank",
            "cs_scale",
            "cs_zscore",
            "cs_demean",
            "cs_winsorize",
        ],
    )
    def test_cs_operators_registered(self, name: str) -> None:
        """Cross-section operators are registered."""
        assert name in P0_OPERATOR_SPECS

    @pytest.mark.parametrize(
        "name",
        [
            "group_rank",
            "group_zscore",
        ],
    )
    def test_group_operators_registered(self, name: str) -> None:
        """Grouped operators are registered."""
        assert name in P0_OPERATOR_SPECS

    def test_all_min_args_positive(self) -> None:
        """All operators have positive min_args."""
        for spec in P0_OPERATOR_SPECS.values():
            assert spec.min_args > 0, f"{spec.name} has min_args={spec.min_args}"

    def test_all_max_gte_min(self) -> None:
        """All operators have max_args >= min_args."""
        for spec in P0_OPERATOR_SPECS.values():
            assert spec.max_args >= spec.min_args, (
                f"{spec.name}: max_args={spec.max_args} < min_args={spec.min_args}"
            )


# ---------------------------------------------------------------------------
# suggest_operator_names
# ---------------------------------------------------------------------------


class TestSuggestOperatorNames:
    """Tests for suggest_operator_names."""

    def test_close_match_suggests(self) -> None:
        """Typo of 'abs' suggests 'abs'."""
        suggestions = suggest_operator_names("abx")
        assert "abs" in suggestions

    def test_prefix_match(self) -> None:
        """'ts_' prefix matches time-series operators."""
        suggestions = suggest_operator_names("ts_")
        assert len(suggestions) > 0
        for name in suggestions:
            assert name.startswith("ts_")

    def test_cs_prefix(self) -> None:
        """'cs_' prefix matches cross-section operators."""
        suggestions = suggest_operator_names("cs_")
        assert "cs_rank" in suggestions or "cs_zscore" in suggestions

    def test_unknown_prefix_no_crash(self) -> None:
        """Unknown prefix returns empty without crashing."""
        suggestions = suggest_operator_names("zzzzz_unknown")
        assert isinstance(suggestions, tuple)

    def test_empty_string(self) -> None:
        """Empty string returns suggestions without crashing."""
        suggestions = suggest_operator_names("")
        assert isinstance(suggestions, tuple)

    def test_exact_match_included(self) -> None:
        """Exact match of an operator should include it."""
        suggestions = suggest_operator_names("ts_mean")
        assert "ts_mean" in suggestions

    def test_returns_strings(self) -> None:
        """Return type contains strings."""
        suggestions = suggest_operator_names("abs")
        assert all(isinstance(s, str) for s in suggestions)
