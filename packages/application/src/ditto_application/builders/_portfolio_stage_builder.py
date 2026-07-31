"""Build portfolio allocation and constraint stages from legacy strategy specs."""

from __future__ import annotations

from collections.abc import Hashable, Mapping
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
from ditto_strategy.alpha.protocols import DecisionStage
from ditto_strategy.alpha.specs import ConstraintSpec, StrategySpec

from ditto_application.builders._spec_deserializer import (
    read_bool,
    read_float,
    read_int,
    read_optional_float,
    read_optional_int,
    read_optional_str,
)
from ditto_application.exceptions import AppBuilderError

__all__ = ["build_portfolio_stages"]


def build_portfolio_stages(spec: StrategySpec) -> list[DecisionStage]:
    """Build allocation and constraint stages from one legacy strategy spec."""
    params = spec.params
    stages: list[DecisionStage] = []
    max_weight = read_optional_float(
        params.get("max_weight"),
        field_name="params.max_weight",
    )

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
