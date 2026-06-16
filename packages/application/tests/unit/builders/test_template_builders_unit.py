"""template_builders 单元测试 — StockSelectionTrendConfig 反序列化.

F1-#1: 验证 ``StrategySpec.params`` 预处理开关(winsorize_sigma/zscore/neutralize_by)
正确反序列化到 ``StockSelectionTrendConfig``。
"""

from __future__ import annotations

from ditto_application.builders.template_builders import (
    build_stock_selection_trend_config,
)
from ditto_strategy.alpha.specs import StrategySpec


def _make_spec(**params: object) -> StrategySpec:
    """构造最小合法 stock_selection StrategySpec(预处理字段可选注入)."""
    return StrategySpec(
        strategy_id="test_stock_selection",
        name="test",
        template="stock_selection",
        universe="test_universe",
        asset_class="stock",
        params=params,
    )


class TestBuildStockSelectionTrendConfigPreprocess:
    """F1-#1 params.preprocess → StockSelectionTrendConfig 反序列化."""

    def test_default_no_preprocess(self) -> None:
        """无 params 时,预处理开关全部关闭(向后兼容)."""
        config = build_stock_selection_trend_config(_make_spec())
        assert config.winsorize_sigma is None
        assert config.zscore is False
        assert config.neutralize_by is None

    def test_preprocess_fields_from_params(self) -> None:
        """params 完整预处理字段正确映射到 config."""
        config = build_stock_selection_trend_config(
            _make_spec(
                winsorize_sigma=3.0,
                zscore=True,
                neutralize_by="industry",
            ),
        )
        assert config.winsorize_sigma == 3.0
        assert config.zscore is True
        assert config.neutralize_by == "industry"

    def test_partial_preprocess_only_zscore(self) -> None:
        """仅 zscore 开启时,其余保持默认."""
        config = build_stock_selection_trend_config(_make_spec(zscore=True))
        assert config.winsorize_sigma is None
        assert config.zscore is True
        assert config.neutralize_by is None

    def test_winsorize_sigma_none_when_absent(self) -> None:
        """params 不含 winsorize_sigma 时,config 为 None(非 0)."""
        config = build_stock_selection_trend_config(_make_spec(zscore=True))
        assert config.winsorize_sigma is None
