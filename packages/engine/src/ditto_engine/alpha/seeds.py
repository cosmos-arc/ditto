"""
Seed StrategySpecs — 内置策略种子定义.

提供 3 个开箱即用的策略模板实例，覆盖 ETF 轮动、ETF 趋势追踪、个股选股场景。
每个 spec 均通过 StrategySpec.__post_init__ 严格校验。
"""

from __future__ import annotations

from ditto_engine.alpha.specs import (
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)

__all__ = [
    "SEED_STRATEGY_SPECS",
]

# ---------------------------------------------------------------------------
# 1. ETF 行业轮动
# ---------------------------------------------------------------------------
_seed_etf_industry_rotation = StrategySpec(
    strategy_id="seed_etf_industry_rotation",
    name="ETF 行业轮动",
    template="etf_rotation",
    universe="csi_etf_broad",
    asset_class="etf",
    benchmark="000300.SH",
    scorer=ScorerSpec(
        method="rank_then_combine",
    ),
    selector=SelectorSpec(
        method="top_k",
        params={"k": 5},
    ),
    execution=ExecutionSpec(
        frequency="M",
        method="calendar",
        cost_model=CostModelSpec(
            commission_rate=0.0003,
            slippage_bps=5.0,
        ),
    ),
    constraints=(
        ConstraintSpec(
            type="max_weight_per_instrument",
            params={"max_weight": 0.30},
        ),
        ConstraintSpec(
            type="max_turnover",
            params={"max_turnover": 0.50},
        ),
    ),
    params={
        "lookback": 252,
        "vol_window": 60,
    },
    tags=("seed", "etf", "rotation", "industry"),
    signal_expressions=("momentum_1m", "reversal_1w", "volatility_factor"),
    signal_weights=(0.5, 0.3, 0.2),
)

# ---------------------------------------------------------------------------
# 2. ETF 趋势追踪
# ---------------------------------------------------------------------------
_seed_etf_trend_swing = StrategySpec(
    strategy_id="seed_etf_trend_swing",
    name="ETF 趋势追踪",
    template="etf_trend_swing",
    universe="csi_etf_broad",
    asset_class="etf",
    benchmark="000300.SH",
    scorer=ScorerSpec(
        method="rank_then_combine",
    ),
    selector=SelectorSpec(
        method="top_k",
        params={"k": 3},
    ),
    execution=ExecutionSpec(
        frequency="W",
        method="calendar",
        cost_model=CostModelSpec(
            commission_rate=0.0003,
            slippage_bps=3.0,
        ),
    ),
    constraints=(
        ConstraintSpec(
            type="max_weight_per_instrument",
            params={"max_weight": 0.40},
        ),
        ConstraintSpec(
            type="max_turnover",
            params={"max_turnover": 0.60},
        ),
    ),
    params={
        "fast_period": 10,
        "slow_period": 30,
        "atr_period": 14,
    },
    tags=("seed", "etf", "trend", "swing"),
    signal_expressions=("macd_hist", "rsi_14", "atr_14"),
    signal_weights=(0.4, 0.3, 0.3),
)

# ---------------------------------------------------------------------------
# 3. 个股选股轮动
# ---------------------------------------------------------------------------
_seed_stock_selection_rotation = StrategySpec(
    strategy_id="seed_stock_selection_rotation",
    name="个股选股轮动",
    template="stock_selection",
    universe="csi_a_share",
    asset_class="stock",
    benchmark="000300.SH",
    scorer=ScorerSpec(
        method="rank_then_combine",
    ),
    selector=SelectorSpec(
        method="top_k",
        params={"k": 20},
    ),
    execution=ExecutionSpec(
        frequency="M",
        method="calendar",
        cost_model=CostModelSpec(
            commission_rate=0.001,
            slippage_bps=10.0,
        ),
    ),
    constraints=(
        ConstraintSpec(
            type="max_weight_per_instrument",
            params={"max_weight": 0.10},
        ),
        ConstraintSpec(
            type="max_turnover",
            params={"max_turnover": 0.30},
        ),
    ),
    params={
        "lookback": 252,
        "quality_weight": 0.4,
        "value_weight": 0.3,
        "momentum_weight": 0.3,
    },
    tags=("seed", "stock", "selection", "rotation"),
    signal_expressions=("quality_roe", "value_pe", "momentum_1m"),
    signal_weights=(0.4, 0.3, 0.3),
)

# ---------------------------------------------------------------------------
# 公开注册表
# ---------------------------------------------------------------------------
SEED_STRATEGY_SPECS: dict[str, StrategySpec] = {
    spec.strategy_id: spec
    for spec in (
        _seed_etf_industry_rotation,
        _seed_etf_trend_swing,
        _seed_stock_selection_rotation,
    )
}
