"""Canonical StrategySpec identity 的固定向量与完整叶变更门。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest
from ditto_kernel.order import OrderType
from ditto_kernel.strategy import ImpactModel
from ditto_strategy.alpha.nodes import (
    NodeCategory,
    NodeInstance,
    NodeRef,
    PipelineSpec,
)
from ditto_strategy.alpha.spec_codec import (
    adapt_legacy_strategy_spec,
    canonical_spec_bytes,
    canonical_spec_hash,
)
from ditto_strategy.alpha.specs import (
    ConstraintSpec,
    CostModelSpec,
    ExecutionSpec,
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
    StrategyKind,
    StrategySpec,
    StrategySpecV2,
)

_NATIVE_CANONICAL_BYTES = (
    b'{"parameter_schema":[{"allowed_values":[],"dtype":"int",'
    b'"max_value":120.0,"min_value":20.0,'
    b'"name":"pipeline.nodes.factors.config.lookback","step":20.0}],'
    b'"pipeline":{"nodes":[{"category":"universe",'
    b'"config":{"asset_class":"stock","universe_id":"csi_a_share"},'
    b'"enabled":true,"node_id":"universe","node_type":"builtin.universe",'
    b'"node_version":"1"},{"category":"factor_set",'
    b'"config":{"lookback":60,"weights":{"momentum":0.6,"value":0.4}},'
    b'"enabled":true,"node_id":"factors","node_type":"builtin.factor_set",'
    b'"node_version":"2"},{"category":"scorer",'
    b'"config":{"method":"rank_then_combine"},"enabled":true,'
    b'"node_id":"scorer","node_type":"builtin.scorer",'
    b'"node_version":"1"}],'
    b'"sequence":["universe","factors","scorer"]},"schema_version":2,'
    b'"strategy_family_id":"family-stock-alpha",'
    b'"strategy_kind":"stock_selection"}'
)
_NATIVE_CANONICAL_SHA256 = (
    "1a1ee761cf1994d6da92a95067cbd84fb08f4dc3fc2e172bfe70436c1e9d855e"
)

_LEGACY_CANONICAL_BYTES = (
    b'{"parameter_schema":[{"allowed_values":[],"dtype":"int",'
    b'"max_value":120.0,"min_value":20.0,"name":"lookback","step":20.0}],'
    b'"pipeline":{"nodes":[{"category":"universe",'
    b'"config":{"asset_class":"etf","benchmark":"000300.SH",'
    b'"universe":"csi_etf_broad"},"enabled":true,'
    b'"node_id":"legacy_universe","node_type":"legacy.universe",'
    b'"node_version":"1"},{"category":"factor_set",'
    b'"config":{"params":{"cash_target":0.05,"lookback":60},'
    b'"required_datasets":["etf_daily"],'
    b'"signal_expressions":["momentum_1m","volatility_factor"],'
    b'"signal_weights":[0.7,0.3],"template":"etf_rotation"},'
    b'"enabled":true,"node_id":"legacy_factor_set",'
    b'"node_type":"legacy.factor_set","node_version":"1"},'
    b'{"category":"scorer","config":{"method":"rank_then_combine",'
    b'"params":{"ascending":false}},"enabled":true,'
    b'"node_id":"legacy_scorer","node_type":"legacy.scorer",'
    b'"node_version":"1"},{"category":"selector",'
    b'"config":{"method":"top_k","params":{"k":3}},"enabled":true,'
    b'"node_id":"legacy_selector","node_type":"legacy.selector",'
    b'"node_version":"1"},{"category":"allocator",'
    b'"config":{"constraints":[{"params":{"max_weight":0.4},'
    b'"priority":1,"type":"max_weight_per_instrument"}]},"enabled":true,'
    b'"node_id":"legacy_allocator","node_type":"legacy.allocator",'
    b'"node_version":"1"},{"category":"execution_assumption",'
    b'"config":{"cost_model":{"commission_rate":0.0003,'
    b'"impact_model":"none","slippage_bps":3.0},'
    b'"default_order_type":"market","frequency":"W","method":"calendar"},'
    b'"enabled":true,"node_id":"legacy_execution",'
    b'"node_type":"legacy.execution_assumption","node_version":"1"},'
    b'{"category":"validation",'
    b'"config":{"legacy_contract":"strategy_spec_v1"},"enabled":true,'
    b'"node_id":"legacy_validation","node_type":"legacy.validation",'
    b'"node_version":"1"}],'
    b'"sequence":["legacy_universe","legacy_factor_set","legacy_scorer",'
    b'"legacy_selector","legacy_allocator","legacy_execution",'
    b'"legacy_validation"]},"schema_version":2,'
    b'"strategy_family_id":"legacy-etf-alpha","strategy_kind":"etf_rotation"}'
)
_LEGACY_CANONICAL_SHA256 = (
    "78f80388e06ef267cd8bb34af2f9e8365aff395c7db8c0f898b61911a367ede0"
)


def _make_native_spec(*, reverse_config_keys: bool = False) -> StrategySpecV2:
    factor_config = (
        {"weights": {"value": 0.4, "momentum": 0.6}, "lookback": 60}
        if not reverse_config_keys
        else {"lookback": 60, "weights": {"momentum": 0.6, "value": 0.4}}
    )
    nodes = (
        NodeInstance(
            node_id="universe",
            ref=NodeRef("builtin.universe", "1"),
            category=NodeCategory.UNIVERSE,
            config={"universe_id": "csi_a_share", "asset_class": "stock"},
        ),
        NodeInstance(
            node_id="factors",
            ref=NodeRef("builtin.factor_set", "2"),
            category=NodeCategory.FACTOR_SET,
            config=factor_config,
        ),
        NodeInstance(
            node_id="scorer",
            ref=NodeRef("builtin.scorer", "1"),
            category=NodeCategory.SCORER,
            config={"method": "rank_then_combine"},
        ),
    )
    return StrategySpecV2(
        schema_version=2,
        strategy_family_id="family-stock-alpha",
        strategy_kind=StrategyKind.STOCK_SELECTION,
        name="股票多因子",
        pipeline=PipelineSpec(
            nodes=nodes,
            sequence=("universe", "factors", "scorer"),
        ),
        parameter_schema=(
            ParamConstraint(
                name="pipeline.nodes.factors.config.lookback",
                dtype="int",
                min_value=20,
                max_value=120,
                step=20,
            ),
        ),
        metadata={"layout": {"x": 10, "y": 20}, "description": "UI only"},
        tags=("draft", "research"),
    )


def _make_legacy_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="legacy-etf-alpha",
        name="Legacy ETF Alpha",
        template="etf_rotation",
        universe="csi_etf_broad",
        asset_class="etf",
        scorer=ScorerSpec(
            method="rank_then_combine",
            params={"ascending": False},
        ),
        selector=SelectorSpec(method="top_k", params={"k": 3}),
        execution=ExecutionSpec(
            frequency="W",
            method="calendar",
            cost_model=CostModelSpec(
                commission_rate=0.0003,
                slippage_bps=3.0,
            ),
            default_order_type=OrderType.MARKET,
        ),
        constraints=(
            ConstraintSpec(
                type="max_weight_per_instrument",
                params={"max_weight": 0.4},
                priority=1,
            ),
        ),
        benchmark="000300.SH",
        params={"lookback": 60, "cash_target": 0.05},
        param_constraints=(
            ParamConstraint(
                name="lookback",
                dtype="int",
                min_value=20,
                max_value=120,
                step=20,
            ),
        ),
        tags=("legacy", "ui-tag"),
        signal_expressions=("momentum_1m", "volatility_factor"),
        signal_weights=(0.7, 0.3),
        required_datasets=("etf_daily",),
    )


def _make_native_spec_with_filter_order(
    filter_order: tuple[str, str],
) -> StrategySpecV2:
    """构造两个同 category filter，使 sequence 顺序变化仍满足固定语法。"""
    base = _make_native_spec()
    scorer = next(node for node in base.pipeline.nodes if node.node_id == "scorer")
    filters = (
        NodeInstance(
            node_id="filter_liquidity",
            ref=NodeRef("builtin.filter.liquidity", "1"),
            category=NodeCategory.FILTER,
            config={"minimum_turnover": 10_000_000},
        ),
        NodeInstance(
            node_id="filter_status",
            ref=NodeRef("builtin.filter.status", "1"),
            category=NodeCategory.FILTER,
            config={"exclude_st": True},
        ),
    )
    nodes = (*base.pipeline.nodes[:-1], *filters, scorer)
    return replace(
        base,
        pipeline=PipelineSpec(
            nodes=nodes,
            sequence=("universe", "factors", *filter_order, "scorer"),
        ),
    )


def _with_schema_version_identity(spec: StrategySpecV2) -> StrategySpecV2:
    """Schema version 只允许 2；绕过构造器验证以证明 codec 仍绑定该叶。"""
    changed = replace(spec)
    object.__setattr__(changed, "schema_version", 3)
    return changed


def _with_factor_node(
    spec: StrategySpecV2,
    mutate: Callable[[NodeInstance], NodeInstance],
) -> StrategySpecV2:
    nodes = tuple(
        mutate(node) if node.node_id == "factors" else node
        for node in spec.pipeline.nodes
    )
    return replace(spec, pipeline=replace(spec.pipeline, nodes=nodes))


def _with_factor_node_id(spec: StrategySpecV2) -> StrategySpecV2:
    nodes = tuple(
        replace(node, node_id="factor_set") if node.node_id == "factors" else node
        for node in spec.pipeline.nodes
    )
    sequence = tuple(
        "factor_set" if node_id == "factors" else node_id
        for node_id in spec.pipeline.sequence
    )
    return replace(
        spec,
        pipeline=replace(spec.pipeline, nodes=nodes, sequence=sequence),
    )


def _with_parameter(
    spec: StrategySpecV2,
    mutate: Callable[[ParamConstraint], ParamConstraint],
) -> StrategySpecV2:
    return replace(spec, parameter_schema=(mutate(spec.parameter_schema[0]),))


def _with_execution(
    spec: StrategySpec,
    mutate: Callable[[ExecutionSpec], ExecutionSpec],
) -> StrategySpec:
    return replace(spec, execution=mutate(spec.execution))


def _with_cost_model(
    spec: StrategySpec,
    mutate: Callable[[CostModelSpec], CostModelSpec],
) -> StrategySpec:
    return _with_execution(
        spec,
        lambda execution: replace(
            execution,
            cost_model=mutate(execution.cost_model),
        ),
    )


def _with_constraint(
    spec: StrategySpec,
    mutate: Callable[[ConstraintSpec], ConstraintSpec],
) -> StrategySpec:
    return replace(spec, constraints=(mutate(spec.constraints[0]),))


def _with_legacy_parameter(
    spec: StrategySpec,
    mutate: Callable[[ParamConstraint], ParamConstraint],
) -> StrategySpec:
    return replace(spec, param_constraints=(mutate(spec.param_constraints[0]),))


def test_native_v2_canonical_known_answer_vector() -> None:
    """原生 V2 的 bytes 与 SHA-256 必须匹配独立硬编码向量。"""
    spec = _make_native_spec()

    assert canonical_spec_bytes(spec) == _NATIVE_CANONICAL_BYTES
    assert canonical_spec_hash(spec) == _NATIVE_CANONICAL_SHA256


def test_legacy_adapter_canonical_known_answer_vector() -> None:
    """Legacy adapter 的 bytes 与 SHA-256 必须匹配独立硬编码向量。"""
    adapted = adapt_legacy_strategy_spec(_make_legacy_spec())

    assert canonical_spec_bytes(adapted) == _LEGACY_CANONICAL_BYTES
    assert canonical_spec_hash(adapted) == _LEGACY_CANONICAL_SHA256


@pytest.mark.parametrize(
    ("leaf_name", "mutate"),
    [
        pytest.param(
            "schema_version", _with_schema_version_identity, id="schema-version"
        ),
        pytest.param(
            "strategy_family_id",
            lambda spec: replace(spec, strategy_family_id="other-family"),
            id="strategy-family-id",
        ),
        pytest.param(
            "strategy_kind",
            lambda spec: replace(spec, strategy_kind=StrategyKind.ETF_ROTATION),
            id="strategy-kind",
        ),
        pytest.param("node_id", _with_factor_node_id, id="node-id"),
        pytest.param(
            "node_category",
            lambda spec: _with_factor_node(
                spec,
                lambda node: replace(node, category=NodeCategory.FILTER),
            ),
            id="node-category",
        ),
        pytest.param(
            "node_type",
            lambda spec: _with_factor_node(
                spec,
                lambda node: replace(
                    node,
                    ref=replace(node.ref, node_type="builtin.factor_set.changed"),
                ),
            ),
            id="node-type",
        ),
        pytest.param(
            "node_version",
            lambda spec: _with_factor_node(
                spec,
                lambda node: replace(node, ref=replace(node.ref, version="3")),
            ),
            id="node-version",
        ),
        pytest.param(
            "node_config",
            lambda spec: _with_factor_node(
                spec,
                lambda node: replace(
                    node,
                    config={"lookback": 120, "weights": {"momentum": 1.0}},
                ),
            ),
            id="node-config",
        ),
        pytest.param(
            "node_enabled",
            lambda spec: _with_factor_node(
                spec,
                lambda node: replace(node, enabled=False),
            ),
            id="node-enabled",
        ),
        pytest.param(
            "parameter_name",
            lambda spec: _with_parameter(
                spec,
                lambda parameter: replace(parameter, name="lookback"),
            ),
            id="parameter-name",
        ),
        pytest.param(
            "parameter_dtype",
            lambda spec: _with_parameter(
                spec,
                lambda parameter: replace(parameter, dtype="float"),
            ),
            id="parameter-dtype",
        ),
        pytest.param(
            "parameter_min_value",
            lambda spec: _with_parameter(
                spec,
                lambda parameter: replace(parameter, min_value=10),
            ),
            id="parameter-minimum",
        ),
        pytest.param(
            "parameter_max_value",
            lambda spec: _with_parameter(
                spec,
                lambda parameter: replace(parameter, max_value=240),
            ),
            id="parameter-maximum",
        ),
        pytest.param(
            "parameter_step",
            lambda spec: _with_parameter(
                spec,
                lambda parameter: replace(parameter, step=10),
            ),
            id="parameter-step",
        ),
        pytest.param(
            "parameter_allowed_values",
            lambda spec: _with_parameter(
                spec,
                lambda parameter: replace(
                    parameter,
                    allowed_values=("20", "60", "120"),
                ),
            ),
            id="parameter-allowed-values",
        ),
    ],
)
def test_native_every_execution_identity_leaf_changes_hash(
    leaf_name: str,
    mutate: Callable[[StrategySpecV2], StrategySpecV2],
) -> None:
    """每个原生 V2 execution identity 叶变化都必须改变 digest。"""
    baseline_hash = canonical_spec_hash(_make_native_spec())

    assert canonical_spec_hash(mutate(_make_native_spec())) != baseline_hash, leaf_name


def test_native_valid_pipeline_sequence_order_changes_hash() -> None:
    """同 category 的合法节点换序仍是 execution identity 变化。"""
    first = _make_native_spec_with_filter_order(
        ("filter_liquidity", "filter_status"),
    )
    second = _make_native_spec_with_filter_order(
        ("filter_status", "filter_liquidity"),
    )

    assert canonical_spec_hash(first) != canonical_spec_hash(second)


@pytest.mark.parametrize(
    ("leaf_name", "mutate"),
    [
        pytest.param(
            "strategy_id",
            lambda spec: replace(spec, strategy_id="legacy-etf-beta"),
            id="strategy-id",
        ),
        pytest.param(
            "strategy_kind",
            lambda spec: replace(spec, template="stock_selection"),
            id="strategy-kind",
        ),
        pytest.param(
            "template",
            lambda spec: replace(spec, template="etf_trend_swing"),
            id="template",
        ),
        pytest.param(
            "universe",
            lambda spec: replace(spec, universe="other_universe"),
            id="universe",
        ),
        pytest.param(
            "asset_class",
            lambda spec: replace(spec, asset_class="stock"),
            id="asset-class",
        ),
        pytest.param(
            "scorer_method",
            lambda spec: replace(
                spec,
                scorer=replace(spec.scorer, method="zscore"),
            ),
            id="scorer-method",
        ),
        pytest.param(
            "scorer_params",
            lambda spec: replace(
                spec,
                scorer=replace(spec.scorer, params={"ascending": True}),
            ),
            id="scorer-params",
        ),
        pytest.param(
            "selector_method",
            lambda spec: replace(
                spec,
                selector=replace(spec.selector, method="threshold"),
            ),
            id="selector-method",
        ),
        pytest.param(
            "selector_params",
            lambda spec: replace(
                spec,
                selector=replace(spec.selector, params={"k": 5}),
            ),
            id="selector-params",
        ),
        pytest.param(
            "execution_frequency",
            lambda spec: _with_execution(
                spec,
                lambda execution: replace(execution, frequency="M"),
            ),
            id="execution-frequency",
        ),
        pytest.param(
            "execution_method",
            lambda spec: _with_execution(
                spec,
                lambda execution: replace(execution, method="signal_change_pct"),
            ),
            id="execution-method",
        ),
        pytest.param(
            "commission_rate",
            lambda spec: _with_cost_model(
                spec,
                lambda cost: replace(cost, commission_rate=0.0005),
            ),
            id="cost-commission-rate",
        ),
        pytest.param(
            "slippage_bps",
            lambda spec: _with_cost_model(
                spec,
                lambda cost: replace(cost, slippage_bps=5.0),
            ),
            id="cost-slippage-bps",
        ),
        pytest.param(
            "impact_model",
            lambda spec: _with_cost_model(
                spec,
                lambda cost: replace(cost, impact_model=ImpactModel.VOLUME_SHARE),
            ),
            id="cost-impact-model",
        ),
        pytest.param(
            "default_order_type",
            lambda spec: _with_execution(
                spec,
                lambda execution: replace(
                    execution,
                    default_order_type=OrderType.LIMIT,
                ),
            ),
            id="default-order-type",
        ),
        pytest.param(
            "constraint_type",
            lambda spec: _with_constraint(
                spec,
                lambda constraint: replace(constraint, type="max_turnover"),
            ),
            id="constraint-type",
        ),
        pytest.param(
            "constraint_params",
            lambda spec: _with_constraint(
                spec,
                lambda constraint: replace(
                    constraint,
                    params={"max_weight": 0.2},
                ),
            ),
            id="constraint-params",
        ),
        pytest.param(
            "constraint_priority",
            lambda spec: _with_constraint(
                spec,
                lambda constraint: replace(constraint, priority=2),
            ),
            id="constraint-priority",
        ),
        pytest.param(
            "benchmark",
            lambda spec: replace(spec, benchmark="000905.SH"),
            id="benchmark",
        ),
        pytest.param(
            "params",
            lambda spec: replace(
                spec,
                params={"lookback": 120, "cash_target": 0.05},
            ),
            id="params",
        ),
        pytest.param(
            "parameter_name",
            lambda spec: _with_legacy_parameter(
                spec,
                lambda parameter: replace(parameter, name="window"),
            ),
            id="parameter-name",
        ),
        pytest.param(
            "parameter_dtype",
            lambda spec: _with_legacy_parameter(
                spec,
                lambda parameter: replace(parameter, dtype="float"),
            ),
            id="parameter-dtype",
        ),
        pytest.param(
            "parameter_min_value",
            lambda spec: _with_legacy_parameter(
                spec,
                lambda parameter: replace(parameter, min_value=10),
            ),
            id="parameter-minimum",
        ),
        pytest.param(
            "parameter_max_value",
            lambda spec: _with_legacy_parameter(
                spec,
                lambda parameter: replace(parameter, max_value=240),
            ),
            id="parameter-maximum",
        ),
        pytest.param(
            "parameter_step",
            lambda spec: _with_legacy_parameter(
                spec,
                lambda parameter: replace(parameter, step=10),
            ),
            id="parameter-step",
        ),
        pytest.param(
            "parameter_allowed_values",
            lambda spec: _with_legacy_parameter(
                spec,
                lambda parameter: replace(
                    parameter,
                    allowed_values=("20", "60", "120"),
                ),
            ),
            id="parameter-allowed-values",
        ),
        pytest.param(
            "signal_expressions",
            lambda spec: replace(
                spec,
                signal_expressions=("momentum_3m", "volatility_factor"),
            ),
            id="signal-expressions",
        ),
        pytest.param(
            "signal_weights",
            lambda spec: replace(spec, signal_weights=(0.6, 0.4)),
            id="signal-weights",
        ),
        pytest.param(
            "required_datasets",
            lambda spec: replace(
                spec,
                required_datasets=("etf_daily", "adj_factor"),
            ),
            id="required-datasets",
        ),
    ],
)
def test_legacy_every_execution_semantic_leaf_changes_hash(
    leaf_name: str,
    mutate: Callable[[StrategySpec], StrategySpec],
) -> None:
    """Legacy adapter 必须绑定每个实际执行语义组和内部叶。"""
    baseline_hash = canonical_spec_hash(
        adapt_legacy_strategy_spec(_make_legacy_spec()),
    )
    changed_hash = canonical_spec_hash(
        adapt_legacy_strategy_spec(mutate(_make_legacy_spec())),
    )

    assert changed_hash != baseline_hash, leaf_name


def test_native_semantic_canonicalization_and_ui_exclusions_remain_stable() -> None:
    """Mapping 顺序等价且 UI name/metadata/tags 不改变 execution identity。"""
    baseline = _make_native_spec()
    equivalent = replace(
        _make_native_spec(reverse_config_keys=True),
        name="仅 UI 重命名",
        metadata={"layout": {"x": 999}, "color": "blue"},
        tags=("favorite", "published"),
    )

    assert canonical_spec_bytes(equivalent) == canonical_spec_bytes(baseline)
    assert canonical_spec_hash(equivalent) == canonical_spec_hash(baseline)


def test_legacy_semantic_canonicalization_and_ui_exclusions_remain_stable() -> None:
    """Legacy mapping 顺序等价且 UI name/tags 不改变 execution identity。"""
    baseline = _make_legacy_spec()
    equivalent = replace(
        baseline,
        name="仅 UI 重命名",
        tags=("favorite", "published"),
        params={"cash_target": 0.05, "lookback": 60},
    )

    assert canonical_spec_hash(
        adapt_legacy_strategy_spec(equivalent),
    ) == canonical_spec_hash(adapt_legacy_strategy_spec(baseline))
