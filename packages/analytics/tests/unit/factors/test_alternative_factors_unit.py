"""Tests for alternative factor expression compilation (margin trading and pledge)."""

from __future__ import annotations

from ditto_analytics.expression.compiler import ExpressionCompiler
from ditto_analytics.factors.alternative import ALTERNATIVES
from ditto_kernel.strategy import DerivedRole, DerivedSpec, MaterializationProfile

_EXPECTED_IDS = ("margin_change", "pledge_ratio", "short_interest_ratio")


class TestAlternativeFactorRegistry:
    """Verify the ALTERNATIVES registry is well-formed."""

    def test_expected_factors_present(self) -> None:
        """All three expected alternative factor IDs must exist."""
        for factor_id in _EXPECTED_IDS:
            assert factor_id in ALTERNATIVES, (
                f"Expected factor '{factor_id}' in ALTERNATIVES"
            )

    def test_no_extra_factors(self) -> None:
        """ALTERNATIVES should contain exactly the three expected factors."""
        assert set(ALTERNATIVES.keys()) == set(_EXPECTED_IDS)

    def test_specs_have_non_empty_expression(self) -> None:
        """Every alternative factor should have a non-empty expression string."""
        for factor_id in _EXPECTED_IDS:
            assert ALTERNATIVES[factor_id].expression.strip(), (
                f"Factor '{factor_id}' has empty expression"
            )


class TestAlternativeFactorsCompile:
    """Every alternative factor expression must compile without error."""

    @staticmethod
    def _to_derived_spec(factor_id: str) -> DerivedSpec:
        spec = ALTERNATIVES[factor_id]
        return DerivedSpec(
            id=factor_id,
            version=1,
            role=DerivedRole.FACTOR,
            materialization_profile=MaterializationProfile.SERIES,
            expression=spec.expression,
        )

    def test_margin_change_compiles(self) -> None:
        """margin_change expression should compile without error."""
        compiler = ExpressionCompiler()
        derived_spec = self._to_derived_spec("margin_change")
        compiled = compiler.compile(derived_spec)
        assert compiled is not None

    def test_pledge_ratio_compiles(self) -> None:
        """pledge_ratio expression should compile without error."""
        compiler = ExpressionCompiler()
        derived_spec = self._to_derived_spec("pledge_ratio")
        compiled = compiler.compile(derived_spec)
        assert compiled is not None

    def test_short_interest_ratio_compiles(self) -> None:
        """short_interest_ratio expression should compile without error."""
        compiler = ExpressionCompiler()
        derived_spec = self._to_derived_spec("short_interest_ratio")
        compiled = compiler.compile(derived_spec)
        assert compiled is not None

    def test_all_alternatives_compile(self) -> None:
        """Every factor in ALTERNATIVES should compile without error."""
        compiler = ExpressionCompiler()
        for factor_id in ALTERNATIVES:
            derived_spec = self._to_derived_spec(factor_id)
            compiled = compiler.compile(derived_spec)
            assert compiled is not None, f"Failed to compile '{factor_id}'"
