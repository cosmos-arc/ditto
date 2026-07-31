"""模板配置构建函数 — 从 StrategySpec 构造各模板 Pipeline Config + Portfolio stages."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import cast

from ditto_portfolio.rebalancing import (
    AllocationStage,
    Constraint,
    ConstraintChecker,
    ConstraintStage,
    EqualWeightAllocator,
    IndustryMaxWeightConstraint,
    InverseVolAllocator,
    LiquidityConstraint,
    MaxPositionsConstraint,
    MaxTurnoverConstraint,
    MaxWeightConstraint,
    MeanVarianceAllocator,
    ScoreWeightAllocator,
    TradabilityConstraint,
)
from ditto_strategy.alpha.builtins.filtering import RiskLockFilter, TrendFilterStage
from ditto_strategy.alpha.builtins.scoring import (
    FactorScoreColumnBinding,
    ScoringMethod,
    ScoringStage,
)
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.builtins.signal import SignalStage
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.selection_evidence import SelectionEvidenceSink
from ditto_strategy.alpha.specs import ConstraintSpec, StrategySpec
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
from ditto_application.strategy_spec_deserialization import (
    resolve_rebalance_frequency,
)

__all__ = [
    "build_alpha_stages",
    "build_etf_rotation_config",
    "build_etf_trend_swing_config",
    "build_legacy_node_stage_groups",
    "build_portfolio_stages",
    "build_stock_sector_rotation_config",
    "build_stock_selection_trend_config",
    "resolve_rebalance_frequency",
    "resolve_scoring_method",
    "resolve_top_k",
]

_LEGACY_RANK_THEN_COMBINE = "rank_then_combine"
_LEGACY_STAGE_KEYS = (
    "legacy.factor_set.v1",
    "legacy.scorer.v1",
    "legacy.selector.v1",
    "legacy.allocator.v1",
)


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


# ---------------------------------------------------------------------------
# Alpha pipeline construction
# ---------------------------------------------------------------------------


def build_alpha_stages(
    spec: StrategySpec,
    *,
    evidence_sink: SelectionEvidenceSink | None = None,
) -> list[DecisionStage]:
    """根据模板类型构建 alpha pipeline stages。"""
    if spec.template == "etf_rotation":
        return build_etf_rotation_pipeline(build_etf_rotation_config(spec))
    if spec.template == "etf_trend_swing":
        return build_etf_trend_swing_pipeline(
            build_etf_trend_swing_config(spec),
        )
    if spec.template == "stock_selection":
        config = build_stock_selection_trend_config(spec)
        validate_stock_selection_config(config)
        return build_stock_selection_trend_pipeline(config, evidence_sink=evidence_sink)
    if spec.template == "stock_sector_rotation":
        config = build_stock_sector_rotation_config(spec)
        validate_sector_rotation_config(config)
        return build_stock_sector_rotation_pipeline(config)

    msg = f"不支持的策略模板: {spec.template}"
    raise AppBuilderError(msg)


def _legacy_runtime_spec(spec: StrategySpec) -> StrategySpec:
    """只在 v1 adapter 内把已完成 factor composite 的 scorer 映射为 RAW。"""
    scorer = spec.scorer
    params = spec.params
    changed = False
    if scorer.method == _LEGACY_RANK_THEN_COMBINE:
        scorer = replace(scorer, method=ScoringMethod.RAW.value)
        changed = True
    if params.get("scoring_method") == _LEGACY_RANK_THEN_COMBINE:
        params = {**params, "scoring_method": ScoringMethod.RAW.value}
        changed = True
    if not changed:
        return spec
    return replace(spec, scorer=scorer, params=params)


def _resolve_legacy_scoring_method(spec: StrategySpec) -> ScoringMethod:
    """严格验证 scorer 与可选 override，再返回 adapter 的有效 method。"""

    def _parse(raw_method: object, *, field_name: str) -> ScoringMethod:
        method = read_str_value(raw_method, field_name=field_name)
        try:
            return ScoringMethod(method)
        except ValueError as exc:
            msg = f"不支持的 scoring_method: {method}"
            raise AppBuilderError(
                msg,
                details={
                    "reason": "invalid_scoring_method",
                    "field_name": field_name,
                    "actual_value": method,
                },
            ) from exc

    if "scoring_method" in spec.params:
        return _parse(
            spec.params["scoring_method"],
            field_name="params.scoring_method",
        )
    return _parse(spec.scorer.method, field_name="scorer.method")


def _legacy_stock_selection_stage_groups(
    spec: StrategySpec,
    *,
    scoring_method: ScoringMethod,
    factor_bindings: tuple[FactorScoreColumnBinding, ...],
    evidence_sink: SelectionEvidenceSink | None,
) -> tuple[
    tuple[DecisionStage, ...],
    tuple[DecisionStage, ...],
    tuple[DecisionStage, ...],
    tuple[DecisionStage, ...],
]:
    """把 FactorBridge composite 接到 stock 既有 filter/selector/allocator。"""
    config = build_stock_selection_trend_config(spec)
    alpha_config = (
        replace(config, allocation_method="equal_weight")
        if config.allocation_method == "score_weight"
        else config
    )
    validate_stock_selection_config(alpha_config)
    alpha_pipeline = build_stock_selection_trend_pipeline(
        alpha_config, evidence_sink=evidence_sink
    )
    alpha_stages = tuple(alpha_pipeline)
    _, _, _, allocator = _legacy_alpha_slices(spec, alpha_stages)
    trend_filter = alpha_stages[1]
    if not isinstance(trend_filter, TrendFilterStage):
        msg = "stock legacy adapter requires TrendFilterStage at index 1"
        raise AppBuilderError(
            msg,
            details={
                "reason": "invalid_legacy_stage_shape",
                "template": spec.template,
                "actual_stage": type(trend_filter).__name__,
            },
        )
    return (
        (
            SignalStage(source_column="signal_value"),
            replace(trend_filter, signal_column="signal_value"),
        ),
        (
            ScoringStage(
                method=scoring_method,
                ascending=False,
                factor_bindings=factor_bindings,
                evidence_sink=evidence_sink,
            ),
        ),
        (
            RiskLockFilter(evidence_sink=evidence_sink),
            SelectionStage(top_k=config.top_k, evidence_sink=evidence_sink),
        ),
        allocator,
    )


def _legacy_alpha_slices(
    spec: StrategySpec,
    alpha_stages: tuple[DecisionStage, ...],
) -> tuple[
    tuple[DecisionStage, ...],
    tuple[DecisionStage, ...],
    tuple[DecisionStage, ...],
    tuple[DecisionStage, ...],
]:
    """按旧模板固定结构拆成 factor/scorer/selector/allocator expansions。"""
    if spec.template == "etf_rotation":
        return (
            alpha_stages[:1],
            alpha_stages[1:2],
            alpha_stages[2:4],
            alpha_stages[4:],
        )
    if spec.template == "etf_trend_swing":
        return (
            alpha_stages[:2],
            alpha_stages[2:3],
            alpha_stages[3:5],
            alpha_stages[5:],
        )
    if spec.template == "stock_selection":
        fusion = read_optional_str(spec.params.get("fusion")) or "simple"
        if fusion == "composite":
            return (
                alpha_stages[:2],
                (),
                alpha_stages[2:4],
                alpha_stages[4:],
            )
        return (
            alpha_stages[:2],
            alpha_stages[2:3],
            alpha_stages[3:5],
            alpha_stages[5:],
        )
    if spec.template == "stock_sector_rotation":
        return (
            alpha_stages[:1],
            alpha_stages[1:2],
            alpha_stages[2:4],
            alpha_stages[4:],
        )
    msg = f"不支持的策略模板: {spec.template}"
    raise AppBuilderError(msg)


def build_legacy_node_stage_groups(
    spec: StrategySpec,
    *,
    factor_bindings: tuple[FactorScoreColumnBinding, ...] = (),
    evidence_sink: SelectionEvidenceSink | None = None,
) -> Mapping[str, tuple[DecisionStage, ...]]:
    """把 legacy template factory 结果按稳定 implementation key 分组。"""
    runtime_spec = _legacy_runtime_spec(spec)
    scoring_method = _resolve_legacy_scoring_method(runtime_spec)
    if runtime_spec.template == "stock_selection":
        factor, scorer, selector, allocator_alpha = (
            _legacy_stock_selection_stage_groups(
                runtime_spec,
                scoring_method=scoring_method,
                factor_bindings=factor_bindings,
                evidence_sink=evidence_sink,
            )
        )
    else:
        alpha_stages = tuple(build_alpha_stages(runtime_spec))
        factor, scorer, selector, allocator_alpha = _legacy_alpha_slices(
            runtime_spec,
            alpha_stages,
        )
    groups: dict[str, tuple[DecisionStage, ...]] = dict.fromkeys(
        _LEGACY_STAGE_KEYS,
        (),
    )
    groups["legacy.factor_set.v1"] = factor
    groups["legacy.scorer.v1"] = scorer
    groups["legacy.selector.v1"] = selector
    groups["legacy.allocator.v1"] = (
        *allocator_alpha,
        *build_portfolio_stages(runtime_spec),
    )
    return MappingProxyType(groups)


# ---------------------------------------------------------------------------
# Portfolio stage construction
# ---------------------------------------------------------------------------


def build_portfolio_stages(spec: StrategySpec) -> list[DecisionStage]:
    """从 StrategySpec 构建 allocation + constraint stages。"""
    params = spec.params
    stages: list[DecisionStage] = []
    max_weight = read_optional_float(
        params.get("max_weight"),
        field_name="params.max_weight",
    )

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
        elif method == "mean_variance":
            allocator = MeanVarianceAllocator(
                cash_target=cash_target,
                max_weight=max_weight or 1.0,
            )
        else:
            allocator = EqualWeightAllocator(cash_target=cash_target)
        stages.append(AllocationStage(allocator=allocator))

    # Constraints
    constraint_list: list[Constraint] = []
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
    constraint_list.extend(_portfolio_constraints_from_params(params))
    constraint_list.extend(_portfolio_constraints_from_specs(spec.constraints))
    if constraint_list:
        stages.append(ConstraintStage(checker=ConstraintChecker(constraint_list)))

    return stages


def _portfolio_constraints_from_params(
    params: Mapping[str, object],
) -> list[Constraint]:
    constraints: list[Constraint] = []

    max_industry_weight = read_optional_float(
        params.get("max_industry_weight"),
        field_name="params.max_industry_weight",
    )
    if max_industry_weight is not None:
        constraints.append(
            IndustryMaxWeightConstraint(
                max_industry_weight=max_industry_weight,
                industry_column=read_optional_str(params.get("industry_column"))
                or "industry",
            ),
        )

    min_liquidity = read_optional_float(
        params.get("min_liquidity"),
        field_name="params.min_liquidity",
    )
    if min_liquidity is not None:
        constraints.append(
            LiquidityConstraint(
                min_liquidity=min_liquidity,
                liquidity_column=read_optional_str(params.get("liquidity_column"))
                or "avg_daily_turnover",
            ),
        )

    if _should_add_tradability_constraint(params):
        constraints.append(
            TradabilityConstraint(
                st_column=read_optional_str(params.get("st_column")) or "is_st",
                suspended_column=read_optional_str(params.get("suspended_column"))
                or "is_suspended",
            ),
        )

    max_turnover = read_optional_float(
        params.get("max_turnover"),
        field_name="params.max_turnover",
    )
    if max_turnover is not None:
        constraints.append(
            MaxTurnoverConstraint(
                max_turnover=max_turnover,
                previous_weights=_read_previous_weights(
                    params.get("previous_weights"),
                    field_name="params.previous_weights",
                ),
                previous_weight_column=read_optional_str(
                    params.get("previous_weight_column"),
                )
                or "previous_weight",
            ),
        )

    return constraints


def _portfolio_constraints_from_specs(
    specs: tuple[ConstraintSpec, ...],
) -> list[Constraint]:
    constraints: list[Constraint] = []
    for spec in specs:
        constraint = _portfolio_constraint_from_spec(spec)
        if constraint is not None:
            constraints.append(constraint)
    return constraints


def _portfolio_constraint_from_spec(spec: ConstraintSpec) -> Constraint | None:
    constraint_type = spec.type
    params = spec.params
    constraint: Constraint | None = None
    if constraint_type in {"max_weight", "max_weight_per_instrument"}:
        constraint = MaxWeightConstraint(
            constraint_id=constraint_type,
            priority=spec.priority,
            max_weight=_read_constraint_float(
                params,
                "max_weight",
                "value",
                field_name=f"constraints.{constraint_type}.max_weight",
            ),
        )
    elif constraint_type == "max_positions":
        constraint = MaxPositionsConstraint(
            constraint_id=constraint_type,
            priority=spec.priority,
            max_positions=_read_constraint_int(
                params,
                "max_positions",
                "value",
                field_name=f"constraints.{constraint_type}.max_positions",
            ),
        )
    elif constraint_type in {"max_industry_weight", "industry_max_weight"}:
        constraint = IndustryMaxWeightConstraint(
            constraint_id=constraint_type,
            priority=spec.priority,
            max_industry_weight=_read_constraint_float(
                params,
                "max_industry_weight",
                "value",
                field_name=f"constraints.{constraint_type}.max_industry_weight",
            ),
            industry_column=read_optional_str(params.get("industry_column"))
            or "industry",
        )
    elif constraint_type in {"min_liquidity", "liquidity"}:
        constraint = LiquidityConstraint(
            constraint_id=constraint_type,
            priority=spec.priority,
            min_liquidity=_read_constraint_float(
                params,
                "min_liquidity",
                "value",
                field_name=f"constraints.{constraint_type}.min_liquidity",
            ),
            liquidity_column=read_optional_str(params.get("liquidity_column"))
            or "avg_daily_turnover",
        )
    elif constraint_type in {"tradability", "exclude_non_tradable"}:
        constraint = TradabilityConstraint(
            constraint_id=constraint_type,
            priority=spec.priority,
            st_column=read_optional_str(params.get("st_column")) or "is_st",
            suspended_column=read_optional_str(params.get("suspended_column"))
            or "is_suspended",
        )
    elif constraint_type == "max_turnover":
        constraint = MaxTurnoverConstraint(
            constraint_id=constraint_type,
            priority=spec.priority,
            max_turnover=_read_constraint_float(
                params,
                "max_turnover",
                "value",
                field_name=f"constraints.{constraint_type}.max_turnover",
            ),
            previous_weights=_read_previous_weights(
                params.get("previous_weights"),
                field_name=f"constraints.{constraint_type}.previous_weights",
            ),
            previous_weight_column=read_optional_str(
                params.get("previous_weight_column"),
            )
            or "previous_weight",
        )
    return constraint


def _should_add_tradability_constraint(params: Mapping[str, object]) -> bool:
    raw = params.get("exclude_non_tradable")
    if raw is not None:
        return read_bool(raw, field_name="params.exclude_non_tradable")
    raw_exclude_st = params.get("exclude_st")
    raw_exclude_suspended = params.get("exclude_suspended")
    exclude_st = raw_exclude_st is not None and read_bool(
        raw_exclude_st,
        field_name="params.exclude_st",
    )
    exclude_suspended = raw_exclude_suspended is not None and read_bool(
        raw_exclude_suspended,
        field_name="params.exclude_suspended",
    )
    return exclude_st or exclude_suspended


def _read_constraint_float(
    params: Mapping[str, object],
    primary_name: str,
    fallback_name: str,
    *,
    field_name: str,
) -> float:
    raw = params.get(primary_name)
    if raw is None:
        raw = params.get(fallback_name)
    return read_float(raw, field_name=field_name)


def _read_constraint_int(
    params: Mapping[str, object],
    primary_name: str,
    fallback_name: str,
    *,
    field_name: str,
) -> int:
    raw = params.get(primary_name)
    if raw is None:
        raw = params.get(fallback_name)
    return read_int(raw, field_name=field_name)


def _read_previous_weights(
    raw_value: object,
    *,
    field_name: str,
) -> dict[Hashable, float] | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, Mapping):
        msg = f"{field_name} 必须是 object/dict"
        raise AppBuilderError(msg)
    result: dict[Hashable, float] = {}
    raw_mapping = cast("Mapping[Hashable, object]", raw_value)
    for key, value in raw_mapping.items():
        result[key] = read_float(value, field_name=f"{field_name}.{key}")
    return result


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
        winsorize_sigma=read_optional_float(
            params.get("winsorize_sigma"),
            field_name="params.winsorize_sigma",
        ),
        zscore=read_bool(
            params.get("zscore", False),
            field_name="params.zscore",
        ),
        neutralize_by=read_optional_str(params.get("neutralize_by")),
        fusion=read_optional_str(params.get("fusion")) or "simple",
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
