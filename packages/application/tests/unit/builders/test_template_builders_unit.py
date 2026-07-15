"""template_builders 单元测试 — StockSelectionTrendConfig 反序列化.

F1-#1: 验证 ``StrategySpec.params`` 预处理开关(winsorize_sigma/zscore/neutralize_by)
正确反序列化到 ``StockSelectionTrendConfig``。
"""

from __future__ import annotations

import polars as pl
import pytest
from ditto_application.builders.template_builders import (
    build_portfolio_stages,
    build_stock_selection_trend_config,
)
from ditto_portfolio.rebalancing import AllocationStage, MeanVarianceAllocator
from ditto_strategy.alpha.specs import ConstraintSpec, StrategySpec


def _make_spec(
    *,
    template: str = "stock_selection",
    asset_class: str = "stock",
    constraints: tuple[ConstraintSpec, ...] = (),
    **params: object,
) -> StrategySpec:
    """构造最小合法 stock_selection StrategySpec(预处理字段可选注入)."""
    return StrategySpec(
        strategy_id="test_stock_selection",
        name="test",
        template=template,
        universe="test_universe",
        asset_class=asset_class,
        constraints=constraints,
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


class TestBuildPortfolioStagesLaunchConstraints:
    """Launch portfolio controls are wired from StrategySpec constraints."""

    def test_mean_variance_allocation_method_builds_optimizer_stage(self) -> None:
        spec = _make_spec(
            template="etf_rotation",
            asset_class="etf",
            allocation_method="mean_variance",
            cash_target=0.10,
            max_weight=0.30,
        )

        stages = build_portfolio_stages(spec)

        allocation_stage = stages[0]
        assert isinstance(allocation_stage, AllocationStage)
        assert isinstance(allocation_stage.allocator, MeanVarianceAllocator)
        assert allocation_stage.allocator.cash_target == pytest.approx(0.10)
        assert allocation_stage.allocator.max_weight == pytest.approx(0.30)

    def test_declared_launch_constraints_adjust_target_weights(self) -> None:
        spec = _make_spec(
            allocation_method="equal_weight",
            constraints=(
                ConstraintSpec(
                    type="max_weight_per_instrument",
                    params={"max_weight": 0.20},
                    priority=10,
                ),
                ConstraintSpec(
                    type="max_industry_weight",
                    params={
                        "max_industry_weight": 0.30,
                        "industry_column": "industry",
                    },
                    priority=20,
                ),
                ConstraintSpec(
                    type="min_liquidity",
                    params={
                        "min_liquidity": 5_000_000.0,
                        "liquidity_column": "avg_daily_turnover",
                    },
                    priority=30,
                ),
                ConstraintSpec(
                    type="tradability",
                    params={
                        "st_column": "is_st",
                        "suspended_column": "is_suspended",
                    },
                    priority=40,
                ),
            ),
        )
        frame = pl.DataFrame(
            {
                "instrument_id": [1, 2, 3, 4],
                "industry": ["tech", "tech", "finance", "healthcare"],
                "avg_daily_turnover": [
                    20_000_000.0,
                    30_000_000.0,
                    2_000_000.0,
                    8_000_000.0,
                ],
                "is_st": [False, False, False, False],
                "is_suspended": [False, False, False, True],
            },
        )

        result = _run_portfolio_stages(spec, frame)
        weights = _weights_dict(result)

        assert weights[1] == pytest.approx(0.15)
        assert weights[2] == pytest.approx(0.15)
        assert weights[3] == pytest.approx(0.0)
        assert weights[4] == pytest.approx(0.0)
        reason_text = " ".join(result["reason_codes"][0])
        assert "max_weight_per_instrument" in reason_text
        assert "max_industry_weight" in reason_text
        assert "min_liquidity" in reason_text
        assert "suspended_exclusion" in reason_text

    def test_max_turnover_constraint_uses_supplied_previous_weights(self) -> None:
        spec = _make_spec(
            allocation_method="equal_weight",
            constraints=(
                ConstraintSpec(
                    type="max_turnover",
                    params={
                        "max_turnover": 0.20,
                        "previous_weights": {1: 0.20, 2: 0.80},
                    },
                ),
            ),
        )
        frame = pl.DataFrame({"instrument_id": [1, 2]})

        result = _run_portfolio_stages(spec, frame)
        weights = _weights_dict(result)

        assert weights[1] == pytest.approx(0.30)
        assert weights[2] == pytest.approx(0.70)
        assert "max_turnover" in " ".join(result["reason_codes"][0])


def _run_portfolio_stages(spec: StrategySpec, frame: pl.DataFrame) -> pl.DataFrame:
    result = frame
    for stage in build_portfolio_stages(spec):
        result = stage.process(result, object())
    return result


def _weights_dict(frame: pl.DataFrame) -> dict[int, float]:
    return dict(
        zip(
            frame["instrument_id"].to_list(),
            frame["weight"].to_list(),
            strict=True,
        )
    )
