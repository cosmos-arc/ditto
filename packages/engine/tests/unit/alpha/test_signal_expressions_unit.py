"""StrategySpec signal_expressions 扩展单元测试."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


class TestStrategySpecSignalExpressions:
    """StrategySpec.signal_expressions / signal_weights 扩展."""

    def test_spec_without_signal_expressions_has_defaults(self) -> None:
        """不含 signal_expressions 的 spec 默认值为空元组."""
        from ditto_engine.alpha.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="test",
            name="Test",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
        )
        assert spec.signal_expressions == ()
        assert spec.signal_weights == ()

    def test_spec_with_signal_expressions(self) -> None:
        """含 signal_expressions 的 spec 正确存储."""
        from ditto_engine.alpha.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="test",
            name="Test",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
            signal_expressions=("close", "volume"),
            signal_weights=(0.6, 0.4),
        )
        assert spec.signal_expressions == ("close", "volume")
        assert spec.signal_weights == (0.6, 0.4)

    def test_signal_expressions_is_frozen(self) -> None:
        """signal_expressions 不可变."""
        from ditto_engine.alpha.specs import StrategySpec

        spec = StrategySpec(
            strategy_id="test",
            name="Test",
            template="etf_rotation",
            universe="csi_etf_broad",
            asset_class="etf",
            signal_expressions=("close",),
            signal_weights=(1.0,),
        )
        with pytest.raises(FrozenInstanceError):
            spec.signal_expressions = ("volume",)  # type: ignore[misc]
