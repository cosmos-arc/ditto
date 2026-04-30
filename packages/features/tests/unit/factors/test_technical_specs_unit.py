"""Tests for technical indicator factor specs (obv_ma20, kdj, supertrend, etc.)."""

from __future__ import annotations

from ditto_features.factors.technical import TECHNICALS


class TestObvMa20Spec:
    """Verify the obv_ma20 FactorSpec definition (obv itself lives in liquidity)."""

    def test_obv_ma20_in_technicals(self) -> None:
        """TECHNICALS dict should expose 'obv_ma20'."""
        assert "obv_ma20" in TECHNICALS

    def test_obv_ma20_dependencies(self) -> None:
        """obv_ma20 should depend on obv."""
        spec = TECHNICALS["obv_ma20"]
        assert spec.dependencies == ("obv",)

    def test_obv_ma20_computation_type(self) -> None:
        """obv_ma20 should use python computation type."""
        spec = TECHNICALS["obv_ma20"]
        assert spec.computation_type == "python"

    def test_obv_ma20_expression_empty(self) -> None:
        """obv_ma20 should have an empty expression (python computation)."""
        spec = TECHNICALS["obv_ma20"]
        assert spec.expression == ""

    def test_obv_ma20_has_description(self) -> None:
        """obv_ma20 should have a non-empty description."""
        spec = TECHNICALS["obv_ma20"]
        assert spec.description

    def test_obv_ma20_id_matches_key(self) -> None:
        """obv_ma20 spec id should match its dict key."""
        assert TECHNICALS["obv_ma20"].id == "obv_ma20"

    def test_obv_not_duplicated_in_technicals(self) -> None:
        """obv should NOT be in TECHNICALS; it lives in LIQUIDITIES."""
        assert "obv" not in TECHNICALS
