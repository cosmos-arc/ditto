"""Public import stability for the split StrategySpec decoder boundaries."""

from ditto_application import strategy_spec_canonical_diff as canonical_diff
from ditto_application import strategy_spec_deserialization as public
from ditto_application import (
    strategy_spec_deserialization_components as components,
)
from ditto_application import strategy_spec_legacy_deserialization as legacy
from ditto_application import strategy_spec_v2_deserialization as v2


def test_public_facade_reexports_the_exact_leaf_function_objects() -> None:
    """The responsibility split must not add wrapper or duplicate implementations."""
    assert public.diff_canonical_payloads is canonical_diff.diff_canonical_payloads
    assert public.deserialize_strategy_spec_v2 is v2.deserialize_strategy_spec_v2
    assert (
        public.deserialize_persisted_legacy_strategy_spec
        is legacy.deserialize_persisted_legacy_strategy_spec
    )
    assert public.deserialize_strategy_spec is legacy.deserialize_strategy_spec
    assert (
        public.canonical_spec_payload_for_record
        is legacy.canonical_spec_payload_for_record
    )
    assert (
        public.canonical_spec_hash_for_record is legacy.canonical_spec_hash_for_record
    )
    assert public.inject_template_constraints is legacy.inject_template_constraints
    assert (
        public.default_required_datasets_for_template
        is legacy.default_required_datasets_for_template
    )
    assert public.resolve_rebalance_frequency is legacy.resolve_rebalance_frequency
    assert public.deserialize_constraints is components.deserialize_constraints
    assert (
        public.deserialize_param_constraints is components.deserialize_param_constraints
    )
    assert public.deserialize_scorer is components.deserialize_scorer
    assert public.deserialize_selector is components.deserialize_selector
    assert public.deserialize_execution is components.deserialize_execution
    assert public.deserialize_cost_model is components.deserialize_cost_model
    assert public.deserialize_constraint is components.deserialize_constraint
    assert (
        public.deserialize_param_constraint is components.deserialize_param_constraint
    )


def test_public_facade_preserves_exported_default_values() -> None:
    assert public._DEFAULT_SLIPPAGE_BPS == components._DEFAULT_SLIPPAGE_BPS
    assert public._DEFAULT_TRAILING_STOP_PCT == 0.08
    assert public._DEFAULT_MAX_WEIGHT == 0.15
    assert public._DEFAULT_TOP_K == 10
