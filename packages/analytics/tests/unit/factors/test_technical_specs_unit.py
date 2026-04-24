"""Tests for technical indicator factor specs (obv, kdj, supertrend, etc.)."""

from __future__ import annotations

from ditto_analytics.factors.technical import TECHNICALS, _obv_specs


class TestObvSpec:
    """Verify the obv (On-Balance Volume) FactorSpec definition."""

    def test_obv_in_obv_specs_dict(self) -> None:
        """_obv_specs should contain an 'obv' entry."""
        assert "obv" in _obv_specs

    def test_obv_in_technicals(self) -> None:
        """TECHNICALS dict should expose 'obv' via merged specs."""
        assert "obv" in TECHNICALS

    def test_obv_dependencies(self) -> None:
        """obv should depend on market.close and market.volume."""
        spec = _obv_specs["obv"]
        assert spec.dependencies == ("market.close", "market.volume")

    def test_obv_computation_type(self) -> None:
        """obv should use python computation type."""
        spec = _obv_specs["obv"]
        assert spec.computation_type == "python"

    def test_obv_expression_empty(self) -> None:
        """obv should have an empty expression (python computation)."""
        spec = _obv_specs["obv"]
        assert spec.expression == ""

    def test_obv_has_description(self) -> None:
        """obv should have a non-empty description."""
        spec = _obv_specs["obv"]
        assert spec.description

    def test_obv_id_matches_key(self) -> None:
        """obv spec id should match its dict key."""
        assert _obv_specs["obv"].id == "obv"
