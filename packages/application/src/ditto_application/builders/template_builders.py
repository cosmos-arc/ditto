"""模板配置构建函数 — 从 StrategySpec 构造各模板 Pipeline Config + Portfolio stages."""

from __future__ import annotations

from ditto_portfolio.rebalancing import (
    AllocationStage,
    ConstraintChecker,
    ConstraintStage,
    EqualWeightAllocator,
    InverseVolAllocator,
    MaxPositionsConstraint,
    MaxWeightConstraint,
    ScoreWeightAllocator,
)
from ditto_strategy.alpha.builtins.scoring import ScoringMethod
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.alpha.templates import (
    ETFRotationConfig,
    ETFTrendSwingConfig,
    StockSectorRotationConfig,
    StockSelectionTrendConfig,
    build_etf_rotation_pipeline,
    build_etf_trend_swing_pipeline,
    build_stock_sector_rotation_pipeline,
    build_stock_selection_trend_pipeline,
    validate_sector_rotation_config,
)
from ditto_strategy.alpha.templates import (
    validate_config as validate_stock_selection_config,
)

from ditto_application.builders._spec_deserializer import (
    as_float_tuple,
    as_str_tuple,
    deserialize_regime_config,
    read_bool,
    read_float,
    read_int,
    read_optional_float,
    read_optional_int,
    read_optional_str,
    read_str_value,
)
from ditto_application.builders.deserialization import (
    _DEFAULT_MAX_WEIGHT,
    _DEFAULT_TOP_K,
    _DEFAULT_TRAILING_STOP_PCT,
)
from ditto_application.exceptions import AppBuilderError

__all__ = [
    "build_alpha_stages",
    "build_etf_rotation_config",
    "build_etf_trend_swing_config",
    "build_portfolio_stages",
    "build_stock_sector_rotation_config",
    "build_stock_selection_trend_config",
    "resolve_rebalance_frequency",
    "resolve_scoring_method",
    "resolve_top_k",
]


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def resolve_top_k(spec: StrategySpec, *, default: int) -> int:
    """优先使用 params.top_k，否则回落到 selector.params.k。"""
    params = spec.params
    if "top_k" in params:
        return read_int(
            params["top_k"],
            field_name="params.top_k",
        )
    selector_k = spec.selector.params.get("k")
    if selector_k is None:
        return default
    return read_int(
        selector_k,
        field_name="selector.params.k",
    )


def resolve_scoring_method(
    spec: StrategySpec,
    *,
    default: str,
) -> ScoringMethod:
    """优先使用 params.scoring_method，否则回落到 scorer.method。"""
    raw_method = spec.params.get("scoring_method")
    if raw_method is None:
        raw_method = spec.scorer.method or default
    method = read_str_value(
        raw_method,
        field_name="scoring_method",
    )
    try:
        return ScoringMethod(method)
    except ValueError as exc:
        msg = f"不支持的 scoring_method: {method}"
        raise AppBuilderError(msg) from exc


def resolve_rebalance_frequency(frequency: str) -> str:
    """将执行层频率映射为模板 rebalance_freq。"""
    mapping = {
        "D": "daily",
        "W": "weekly",
        "M": "monthly",
    }
    return mapping.get(frequency, "daily")


# ---------------------------------------------------------------------------
# Alpha pipeline construction
# ---------------------------------------------------------------------------


def build_alpha_stages(spec: StrategySpec) -> list[DecisionStage]:
    """根据模板类型构建 alpha pipeline stages。"""
    if spec.template == "etf_rotation":
        return build_etf_rotation_pipeline(build_etf_rotation_config(spec))
    if spec.template == "etf_trend_swing":
        return build_etf_trend_swing_pipeline(
            build_etf_trend_swing_config(spec),
        )
    if spec.template == "stock_selection_trend":
        config = build_stock_selection_trend_config(spec)
        validate_stock_selection_config(config)
        return build_stock_selection_trend_pipeline(config)
    if spec.template == "stock_sector_rotation":
        config = build_stock_sector_rotation_config(spec)
        validate_sector_rotation_config(config)
        return build_stock_sector_rotation_pipeline(config)

    msg = f"不支持的策略模板: {spec.template}"
    raise AppBuilderError(msg)


# ---------------------------------------------------------------------------
# Portfolio stage construction
# ---------------------------------------------------------------------------


def build_portfolio_stages(spec: StrategySpec) -> list[DecisionStage]:
    """从 StrategySpec 构建 allocation + constraint stages。"""
    params = spec.params
    stages: list[DecisionStage] = []

    # Allocation — stock_sector_rotation 使用内置 SectorWeightStage，跳过
    if spec.template != "stock_sector_rotation":
        method = read_optional_str(params.get("allocation_method")) or "equal_weight"
        cash_target = read_float(
            params.get("cash_target", 0.0),
            field_name="params.cash_target",
        )
        if method == "score_weight":
            allocator = ScoreWeightAllocator(cash_target=cash_target)
        elif method == "inverse_vol":
            allocator = InverseVolAllocator(cash_target=cash_target)
        else:
            allocator = EqualWeightAllocator(cash_target=cash_target)
        stages.append(AllocationStage(allocator=allocator))

    # Constraints
    constraint_list: list[MaxWeightConstraint | MaxPositionsConstraint] = []
    max_weight = read_optional_float(
        params.get("max_weight"),
        field_name="params.max_weight",
    )
    if max_weight is not None:
        constraint_list.append(MaxWeightConstraint(max_weight=max_weight))
    max_positions = read_optional_int(
        params.get("max_positions"),
        field_name="params.max_positions",
    )
    if max_positions is not None:
        constraint_list.append(
            MaxPositionsConstraint(max_positions=max_positions),
        )
    if constraint_list:
        stages.append(ConstraintStage(checker=ConstraintChecker(constraint_list)))

    return stages


# ---------------------------------------------------------------------------
# Template config builders
# ---------------------------------------------------------------------------


def build_etf_rotation_config(spec: StrategySpec) -> ETFRotationConfig:
    """从 StrategySpec 构造 ETFRotationConfig。"""
    params = spec.params
    return ETFRotationConfig(
        top_k=resolve_top_k(spec, default=_DEFAULT_TOP_K),
        scoring_method=resolve_scoring_method(spec, default="rank"),
        scoring_ascending=read_bool(
            params.get("scoring_ascending", True),
            field_name="params.scoring_ascending",
        ),
        allocation_method=read_optional_str(
            params.get("allocation_method"),
        )
        or "equal_weight",
        cash_target=read_float(
            params.get("cash_target", 0.0),
            field_name="params.cash_target",
        ),
        signal_column=read_optional_str(params.get("signal_column")) or "signal_value",
        max_weight=read_optional_float(
            params.get("max_weight"),
            field_name="params.max_weight",
        ),
        max_positions=read_optional_int(
            params.get("max_positions"),
            field_name="params.max_positions",
        ),
        regime_config=deserialize_regime_config(params.get("regime_config")),
    )


def build_etf_trend_swing_config(
    spec: StrategySpec,
) -> ETFTrendSwingConfig:
    """从 StrategySpec 构造 ETFTrendSwingConfig。"""
    params = spec.params
    return ETFTrendSwingConfig(
        lookback_window=read_int(
            params.get("lookback_window", 20),
            field_name="params.lookback_window",
        ),
        trend_threshold=read_float(
            params.get("trend_threshold", 0.0),
            field_name="params.trend_threshold",
        ),
        trailing_stop_pct=read_float(
            params.get("trailing_stop_pct", _DEFAULT_TRAILING_STOP_PCT),
            field_name="params.trailing_stop_pct",
        ),
        max_positions=read_int(
            params.get(
                "max_positions",
                resolve_top_k(spec, default=_DEFAULT_TOP_K),
            ),
            field_name="params.max_positions",
        ),
        scoring_method=resolve_scoring_method(spec, default="rank"),
        scoring_ascending=read_bool(
            params.get("scoring_ascending", True),
            field_name="params.scoring_ascending",
        ),
        allocation_method=read_optional_str(
            params.get("allocation_method"),
        )
        or "equal_weight",
        cash_target=read_float(
            params.get("cash_target", 0.0),
            field_name="params.cash_target",
        ),
        signal_column=read_optional_str(params.get("signal_column")) or "signal_value",
        regime_config=deserialize_regime_config(params.get("regime_config")),
    )


def build_stock_selection_trend_config(
    spec: StrategySpec,
) -> StockSelectionTrendConfig:
    """从 StrategySpec 构造 StockSelectionTrendConfig。"""
    params = spec.params
    return StockSelectionTrendConfig(
        universe_filter=(read_optional_str(params.get("universe_filter")) or ""),
        signal_factors=_as_str_tuple_from_params(
            params,
            "signal_factors",
            default=("signal_value",),
        ),
        signal_weights=_as_float_tuple_from_params(
            params,
            "signal_weights",
            default=(1.0,),
        ),
        top_k=resolve_top_k(spec, default=_DEFAULT_TOP_K),
        max_weight=read_float(
            params.get("max_weight", _DEFAULT_MAX_WEIGHT),
            field_name="params.max_weight",
        ),
        allocation_method=read_optional_str(
            params.get("allocation_method"),
        )
        or "equal_weight",
        cash_target=read_float(
            params.get("cash_target", 0.0),
            field_name="params.cash_target",
        ),
        trend_threshold=read_float(
            params.get("trend_threshold", 0.0),
            field_name="params.trend_threshold",
        ),
        rebalance_freq=read_optional_str(params.get("rebalance_freq"))
        or resolve_rebalance_frequency(spec.execution.frequency),
        regime_config=deserialize_regime_config(params.get("regime_config")),
    )


def build_stock_sector_rotation_config(
    spec: StrategySpec,
) -> StockSectorRotationConfig:
    """从 StrategySpec 构造 StockSectorRotationConfig。"""
    params = spec.params
    return StockSectorRotationConfig(
        sector_signal=read_optional_str(params.get("sector_signal")) or "signal_value",
        stock_signal=read_optional_str(params.get("stock_signal")) or "signal_value",
        top_sectors=read_int(
            params.get("top_sectors", 3),
            field_name="params.top_sectors",
        ),
        stocks_per_sector=read_int(
            params.get("stocks_per_sector", 3),
            field_name="params.stocks_per_sector",
        ),
        sector_weight_method=read_optional_str(
            params.get("sector_weight_method"),
        )
        or "equal_weight",
        stock_weight_method=read_optional_str(
            params.get("stock_weight_method"),
        )
        or "equal_weight",
        max_weight=read_float(
            params.get("max_weight", _DEFAULT_MAX_WEIGHT),
            field_name="params.max_weight",
        ),
        cash_target=read_float(
            params.get("cash_target", 0.0),
            field_name="params.cash_target",
        ),
        rebalance_freq=read_optional_str(params.get("rebalance_freq"))
        or resolve_rebalance_frequency(spec.execution.frequency),
        regime_config=deserialize_regime_config(params.get("regime_config")),
    )


def _as_str_tuple_from_params(
    params: dict[str, object],
    key: str,
    *,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    """从 params dict 中提取 str tuple，不存在时返回 default。"""
    value = params.get(key)
    if value is None:
        return default
    return as_str_tuple(value, field_name=f"params.{key}") or default


def _as_float_tuple_from_params(
    params: dict[str, object],
    key: str,
    *,
    default: tuple[float, ...],
) -> tuple[float, ...]:
    """从 params dict 中提取 float tuple，不存在时返回 default。"""
    value = params.get(key)
    if value is None:
        return default
    return as_float_tuple(value, field_name=f"params.{key}") or default
