"""Persisted legacy StrategySpec decoding and explicit migration defaults."""

from __future__ import annotations

import warnings
from dataclasses import replace

from ditto_strategy.alpha.spec_codec import (
    adapt_legacy_strategy_spec,
    canonical_spec_hash,
    canonical_spec_payload,
)
from ditto_strategy.alpha.specs import ParamConstraint, StrategySpec
from ditto_strategy.alpha.templates import (
    ETFRotationConfig,
    ETFTrendSwingConfig,
    StockSelectionTrendConfig,
    get_etf_rotation_param_constraints,
    get_etf_trend_swing_param_constraints,
    get_sector_rotation_param_constraints,
)
from ditto_strategy.alpha.templates import (
    get_param_constraints as get_stock_selection_param_constraints,
)
from ditto_strategy.models import StrategySpecRecord

from ditto_application.strategy_spec_deserialization_components import (
    deserialize_constraints,
    deserialize_execution,
    deserialize_param_constraints,
    deserialize_scorer,
    deserialize_selector,
)
from ditto_application.strategy_spec_fields import (
    as_float_tuple,
    as_object_dict,
    as_str_tuple,
    read_float,
    read_optional_str,
    read_required_str,
)

__all__ = [
    "canonical_spec_hash_for_record",
    "canonical_spec_payload_for_record",
    "default_required_datasets_for_template",
    "deserialize_persisted_legacy_strategy_spec",
    "deserialize_strategy_spec",
    "inject_template_constraints",
    "resolve_rebalance_frequency",
]


def resolve_rebalance_frequency(frequency: str) -> str:
    """Map persisted execution frequency to the template's effective value."""
    return {
        "D": "daily",
        "W": "weekly",
        "M": "monthly",
    }.get(frequency, "daily")


def _legacy_parameter_constraints(
    template: str,
    declared: tuple[ParamConstraint, ...],
) -> tuple[ParamConstraint, ...]:
    if declared:
        return declared
    if template == "etf_rotation":
        return get_etf_rotation_param_constraints()
    if template == "etf_trend_swing":
        return get_etf_trend_swing_param_constraints()
    if template == "stock_selection":
        return get_stock_selection_param_constraints()
    if template == "stock_sector_rotation":
        return get_sector_rotation_param_constraints()
    return ()


def _normalize_legacy_parameter_numbers(
    params: dict[str, object],
    *,
    template: str,
    constraints: tuple[ParamConstraint, ...],
) -> dict[str, object]:
    """Restore declared float values after a JavaScript JSON round trip."""
    normalized = dict(params)
    for constraint in _legacy_parameter_constraints(template, constraints):
        value = normalized.get(constraint.name)
        if constraint.dtype == "float" and type(value) is int:
            normalized[constraint.name] = read_float(
                value,
                field_name=f"params.{constraint.name}",
            )
    return normalized


def deserialize_persisted_legacy_strategy_spec(
    record: StrategySpecRecord,
) -> StrategySpec:
    """Decode the legacy shape without injecting fields or defaults."""
    payload = as_object_dict(record.spec_json, field_name="spec_json")
    template = read_required_str(payload, "template")
    param_constraints = deserialize_param_constraints(payload)
    params = _normalize_legacy_parameter_numbers(
        as_object_dict(payload.get("params"), field_name="params"),
        template=template,
        constraints=param_constraints,
    )
    required_datasets = as_str_tuple(
        payload.get("required_datasets"),
        field_name="required_datasets",
    )
    if not required_datasets:
        message = f"Strategy {record.strategy_id} missing required_datasets"
        message += "; using template migration default"
        warnings.warn(message, stacklevel=2)
        required_datasets = default_required_datasets_for_template(template)
    return StrategySpec(
        strategy_id=read_optional_str(payload.get("strategy_id")) or record.strategy_id,
        name=read_optional_str(payload.get("name")) or record.name,
        template=template,
        universe=read_required_str(payload, "universe"),
        asset_class=read_required_str(payload, "asset_class"),
        scorer=deserialize_scorer(payload.get("scorer")),
        selector=deserialize_selector(payload.get("selector")),
        execution=deserialize_execution(payload.get("execution")),
        constraints=deserialize_constraints(payload),
        benchmark=read_optional_str(payload.get("benchmark")),
        params=params,
        param_constraints=param_constraints,
        tags=as_str_tuple(payload.get("tags"), field_name="tags") or record.tags,
        signal_expressions=as_str_tuple(
            payload.get("signal_expressions"),
            field_name="signal_expressions",
        ),
        signal_weights=as_float_tuple(
            payload.get("signal_weights"),
            field_name="signal_weights",
        ),
        required_datasets=required_datasets,
    )


def deserialize_strategy_spec(record: StrategySpecRecord) -> StrategySpec:
    """将 catalog 中的 ``spec_json`` 恢复为 ``StrategySpec``。"""
    return inject_template_constraints(
        deserialize_persisted_legacy_strategy_spec(record)
    )


def canonical_spec_payload_for_record(record: StrategySpecRecord) -> dict[str, object]:
    """
    计算 ``record.spec_json`` 的 canonical V2 payload.

    走 legacy deserialize → V2 adapt → ``canonical_spec_payload``，与
    ``canonical_spec_hash_for_record`` 同源，供 spec diff 复用同一规范化形态。
    """
    spec = deserialize_strategy_spec(record)
    v2 = adapt_legacy_strategy_spec(spec)
    return canonical_spec_payload(v2)


def canonical_spec_hash_for_record(record: StrategySpecRecord) -> str:
    """
    计算 ``record.spec_json`` 的 canonical V2 hash.

    委托 ``canonical_spec_hash``（与 ``canonical_spec_payload_for_record`` 共享
    同一 V2 payload 来源），与 backtest manifest 的 spec_hash 同源，保证
    governance 版本与回测版本内容寻址一致。
    """
    return canonical_spec_hash(
        adapt_legacy_strategy_spec(deserialize_strategy_spec(record))
    )


def default_required_datasets_for_template(template: str) -> tuple[str, ...]:
    """旧 spec 的兼容映射；新写入必须显式保存 required_datasets。"""
    if template in {"etf_rotation", "etf_trend_swing"}:
        return ("etf_daily",)
    if template == "stock_selection":
        return (
            "stock_daily",
            "adj_factor",
            "balance_sheet",
            "income_statement",
        )
    if template == "stock_sector_rotation":
        return ("stock_daily", "adj_factor")
    return ()


def inject_template_constraints(spec: StrategySpec) -> StrategySpec:
    """为模板型策略补齐缺失的参数约束元数据。"""
    if spec.param_constraints:
        return spec
    if spec.template == "etf_rotation":
        defaults = ETFRotationConfig()
        selector_k = spec.selector.params.get("k")
        return replace(
            spec,
            params={
                "allocation_method": defaults.allocation_method,
                "cash_target": defaults.cash_target,
                "top_k": defaults.top_k if selector_k is None else selector_k,
                **spec.params,
            },
            param_constraints=get_etf_rotation_param_constraints(),
        )
    if spec.template == "etf_trend_swing":
        defaults = ETFTrendSwingConfig()
        selector_k = spec.selector.params.get("k")
        return replace(
            spec,
            params={
                "allocation_method": defaults.allocation_method,
                "cash_target": defaults.cash_target,
                "lookback_window": defaults.lookback_window,
                "max_positions": (
                    defaults.max_positions if selector_k is None else selector_k
                ),
                "trailing_stop_pct": defaults.trailing_stop_pct,
                "trend_threshold": defaults.trend_threshold,
                **spec.params,
            },
            param_constraints=get_etf_trend_swing_param_constraints(),
        )
    if spec.template == "stock_selection":
        defaults = StockSelectionTrendConfig()
        selector_k = spec.selector.params.get("k")
        return replace(
            spec,
            params={
                "allocation_method": defaults.allocation_method,
                "cash_target": defaults.cash_target,
                "max_weight": defaults.max_weight,
                "rebalance_freq": resolve_rebalance_frequency(
                    spec.execution.frequency,
                ),
                "top_k": defaults.top_k if selector_k is None else selector_k,
                "trend_threshold": defaults.trend_threshold,
                **spec.params,
            },
            param_constraints=get_stock_selection_param_constraints(),
        )
    if spec.template == "stock_sector_rotation":
        return replace(
            spec,
            param_constraints=get_sector_rotation_param_constraints(),
        )
    return spec
