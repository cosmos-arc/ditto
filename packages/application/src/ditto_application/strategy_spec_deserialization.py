"""Stable public facade for catalog StrategySpec deserialization."""

from ditto_application.strategy_spec_canonical_diff import diff_canonical_payloads
from ditto_application.strategy_spec_deserialization_components import (
    _DEFAULT_MAX_WEIGHT,
    _DEFAULT_SLIPPAGE_BPS,
    _DEFAULT_TOP_K,
    _DEFAULT_TRAILING_STOP_PCT,
    _normalize_impact_model,
    deserialize_constraint,
    deserialize_constraints,
    deserialize_cost_model,
    deserialize_execution,
    deserialize_param_constraint,
    deserialize_param_constraints,
    deserialize_scorer,
    deserialize_selector,
)
from ditto_application.strategy_spec_legacy_deserialization import (
    canonical_spec_hash_for_record,
    canonical_spec_payload_for_record,
    default_required_datasets_for_template,
    deserialize_persisted_legacy_strategy_spec,
    deserialize_strategy_spec,
    inject_template_constraints,
    resolve_rebalance_frequency,
)
from ditto_application.strategy_spec_v2_deserialization import (
    deserialize_strategy_spec_v2,
)

__all__ = [
    "_DEFAULT_MAX_WEIGHT",
    "_DEFAULT_SLIPPAGE_BPS",
    "_DEFAULT_TOP_K",
    "_DEFAULT_TRAILING_STOP_PCT",
    "_normalize_impact_model",
    "canonical_spec_hash_for_record",
    "canonical_spec_payload_for_record",
    "default_required_datasets_for_template",
    "deserialize_constraint",
    "deserialize_constraints",
    "deserialize_cost_model",
    "deserialize_execution",
    "deserialize_param_constraint",
    "deserialize_param_constraints",
    "deserialize_persisted_legacy_strategy_spec",
    "deserialize_scorer",
    "deserialize_selector",
    "deserialize_strategy_spec",
    "deserialize_strategy_spec_v2",
    "diff_canonical_payloads",
    "inject_template_constraints",
    "resolve_rebalance_frequency",
]
