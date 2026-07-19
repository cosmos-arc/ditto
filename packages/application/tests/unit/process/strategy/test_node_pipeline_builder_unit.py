"""NodePipelineBuilder 的 constrained compiler 与 builtin adapter 测试。"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import polars as pl
import pytest
from ditto_application.builders.node_pipeline_builder import NodePipelineBuilder
from ditto_application.exceptions import AppBuilderError
from ditto_portfolio.rebalancing import AllocationStage
from ditto_strategy.alpha.builtins.filtering import RiskLockFilter
from ditto_strategy.alpha.builtins.scoring import ScoringMethod, ScoringStage
from ditto_strategy.alpha.builtins.selection import SelectionStage
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.node_registry import (
    NodeDescriptor,
    NodeRegistry,
    default_node_registry,
)
from ditto_strategy.alpha.pipeline import StrategyInputBundle, StrategyPipeline
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.alpha.spec_codec import adapt_legacy_strategy_spec
from ditto_strategy.alpha.specs import StrategySpec
from ditto_strategy.errors import StrategySpecError


def _builder() -> NodePipelineBuilder:
    return NodePipelineBuilder(registry=default_node_registry())


def _build(spec: StrategySpec) -> StrategyPipeline:
    resolved = adapt_legacy_strategy_spec(spec)
    return _builder().build(
        legacy_spec=spec,
        pipeline=resolved.pipeline,
        strategy_kind=resolved.strategy_kind,
    )


def test_all_seed_specs_compile_through_the_constrained_builder() -> None:
    """三个 legacy seed 都必须通过 registry/compiler，而非旁路 template factory。"""
    pipelines = {
        strategy_id: _build(spec) for strategy_id, spec in SEED_STRATEGY_SPECS.items()
    }

    assert tuple(pipelines) == tuple(SEED_STRATEGY_SPECS)
    assert all(
        isinstance(pipeline, StrategyPipeline) for pipeline in pipelines.values()
    )
    assert all(pipeline._stages for pipeline in pipelines.values())


def test_etf_seed_rank_then_combine_legacy_adapter_preserves_composite_scores() -> None:
    """legacy alias 使用 RAW；不得二次 rank 后改变 score-weight 权重。"""
    source = SEED_STRATEGY_SPECS["seed_etf_industry_rotation"]
    spec = replace(
        source,
        selector=replace(source.selector, params={"k": 3}),
        constraints=(),
        params={
            **source.params,
            "top_k": 3,
            "allocation_method": "score_weight",
            "scoring_ascending": False,
        },
    )
    pipeline = _build(spec)
    scoring = next(
        stage for stage in pipeline._stages if isinstance(stage, ScoringStage)
    )

    assert scoring.method is ScoringMethod.RAW

    composite_values = [0.25, 0.65, 0.675, 0.925]
    target = pipeline.run(
        StrategyContext(),
        StrategyInputBundle(
            trade_date="2026-07-19",
            strategy_id=spec.strategy_id,
            run_id="seed-golden",
            instruments=pl.DataFrame({"instrument_id": [1, 2, 3, 4]}),
            market_data=pl.DataFrame({"instrument_id": [1, 2, 3, 4]}),
            signal_values=pl.DataFrame(
                {
                    "instrument_id": [1, 2, 3, 4],
                    "signal_value": composite_values,
                },
            ),
        ),
    )

    assert set(target.positions) == {2, 3, 4}
    assert target.positions[4] == pytest.approx(0.275 / 0.3)
    assert target.positions[3] == pytest.approx(0.025 / 0.3)
    assert target.positions[2] == pytest.approx(0.0)


def test_stock_seed_pipeline_keeps_stable_builtin_stage_order() -> None:
    """stock golden path 经 adapter 后仍复用现有 stage 类型与顺序。"""
    pipeline = _build(SEED_STRATEGY_SPECS["seed_stock_selection_rotation"])
    stage_names = tuple(type(stage).__name__ for stage in pipeline._stages)

    assert stage_names[:5] == (
        "SignalStage",
        "TrendFilterStage",
        "ScoringStage",
        "RiskLockFilter",
        "SelectionStage",
    )
    assert isinstance(pipeline._stages[5], AllocationStage)


def test_stock_seed_rank_then_combine_preserves_factor_bridge_scores() -> None:
    """stock legacy adapter 不得再次 rank FactorBridge composite。"""
    source = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
    params = {key: value for key, value in source.params.items() if key != "max_weight"}
    params.update(
        {
            "allocation_method": "score_weight",
            "top_k": 3,
        },
    )
    spec = replace(
        source,
        selector=replace(source.selector, params={"k": 3}),
        constraints=(),
        params=params,
    )
    pipeline = _build(spec)

    composite_values = [0.25, 0.65, 0.675, 0.925]
    target = pipeline.run(
        StrategyContext(),
        StrategyInputBundle(
            trade_date="2026-07-19",
            strategy_id=spec.strategy_id,
            run_id="stock-seed-golden",
            instruments=pl.DataFrame({"instrument_id": [1, 2, 3, 4]}),
            market_data=pl.DataFrame({"instrument_id": [1, 2, 3, 4]}),
            signal_values=pl.DataFrame(
                {
                    "instrument_id": [1, 2, 3, 4],
                    "signal_value": composite_values,
                },
            ),
        ),
    )

    scoring = next(
        stage for stage in pipeline._stages if isinstance(stage, ScoringStage)
    )
    assert scoring.method is ScoringMethod.RAW
    assert set(target.positions) == {2, 3, 4}
    assert target.positions[4] == pytest.approx(0.275 / 0.3)
    assert target.positions[3] == pytest.approx(0.025 / 0.3)
    assert target.positions[2] == pytest.approx(0.0)


def test_stock_seed_unknown_scorer_fails_closed() -> None:
    """stock legacy adapter 也必须严格解析 scorer，而非静默忽略。"""
    source = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
    invalid = replace(
        source,
        scorer=replace(source.scorer, method="os.system"),
    )

    with pytest.raises(AppBuilderError, match="scoring_method"):
        _build(invalid)


def test_valid_scoring_override_precedes_legacy_default_scorer() -> None:
    """有效 override 保留历史优先级，不解析被覆盖的旧默认值。"""
    source = SEED_STRATEGY_SPECS["seed_etf_industry_rotation"]
    spec = replace(
        source,
        scorer=replace(source.scorer, method="equal_weight"),
        params={**source.params, "scoring_method": "rank"},
    )

    pipeline = _build(spec)

    scoring = next(
        stage for stage in pipeline._stages if isinstance(stage, ScoringStage)
    )
    assert scoring.method is ScoringMethod.RANK


def test_missing_scoring_override_falls_back_to_scorer_method() -> None:
    """缺失 override 时保持 legacy scorer.method 回退语义。"""
    source = SEED_STRATEGY_SPECS["seed_etf_industry_rotation"]
    spec = replace(
        source,
        scorer=replace(source.scorer, method="rank"),
        params={
            key: value
            for key, value in source.params.items()
            if key != "scoring_method"
        },
    )

    pipeline = _build(spec)

    scoring = next(
        stage for stage in pipeline._stages if isinstance(stage, ScoringStage)
    )
    assert scoring.method is ScoringMethod.RANK


@pytest.mark.parametrize(
    "invalid_value",
    [
        pytest.param(None, id="null"),
        pytest.param(7, id="non-string"),
        pytest.param("", id="empty"),
        pytest.param("os.system", id="unknown"),
    ],
)
def test_explicit_invalid_scoring_override_fails_closed(
    invalid_value: object,
) -> None:
    """显式 override 不得因值为 null 而被误判为未提供。"""
    source = SEED_STRATEGY_SPECS["seed_etf_industry_rotation"]
    invalid = replace(
        source,
        params={**source.params, "scoring_method": invalid_value},
    )

    with pytest.raises(AppBuilderError) as exc_info:
        _build(invalid)

    assert (
        "params.scoring_method" in str(exc_info.value)
        or exc_info.value.details.get("field_name") == "params.scoring_method"
    )


def test_explicit_null_scorer_method_fails_closed_when_type_is_bypassed() -> None:
    """即使上游绕过静态类型，scorer.method=null 也必须拒绝。"""
    source = SEED_STRATEGY_SPECS["seed_etf_industry_rotation"]
    invalid = replace(
        source,
        scorer=replace(source.scorer, method=cast(str, None)),
        params={
            key: value
            for key, value in source.params.items()
            if key != "scoring_method"
        },
    )

    with pytest.raises(StrategySpecError) as exc_info:
        _build(invalid)

    assert exc_info.value.details["reason"] == "invalid_node_config_type"
    assert exc_info.value.details["config_key"] == "method"


def test_stock_seed_unknown_allocation_method_still_fails_closed() -> None:
    """legacy bridge 不得因隔离 alpha validation 而放宽 allocation enum。"""
    source = SEED_STRATEGY_SPECS["seed_stock_selection_rotation"]
    invalid = replace(
        source,
        params={**source.params, "allocation_method": "os.system"},
    )

    with pytest.raises(StrategySpecError, match="allocation_method"):
        _build(invalid)


def test_selector_adapter_expands_system_guard_without_authoring_filter_node() -> None:
    """RiskLock 是 selector 前系统 guard，不作为普通 Filter 暴露。"""
    spec = SEED_STRATEGY_SPECS["seed_etf_industry_rotation"]
    resolved = adapt_legacy_strategy_spec(spec)

    assert all(node.category.value != "filter" for node in resolved.pipeline.nodes)

    pipeline = _build(spec)
    scoring_index = next(
        index
        for index, stage in enumerate(pipeline._stages)
        if isinstance(stage, ScoringStage)
    )
    assert isinstance(pipeline._stages[scoring_index + 1], RiskLockFilter)
    assert isinstance(pipeline._stages[scoring_index + 2], SelectionStage)


def test_unknown_implementation_key_fails_closed_without_dynamic_import() -> None:
    spec = SEED_STRATEGY_SPECS["seed_etf_industry_rotation"]
    resolved = adapt_legacy_strategy_spec(spec)
    descriptors = tuple(
        replace(descriptor, implementation_key="os.system")
        if descriptor.identity == "legacy.scorer@1"
        else descriptor
        for descriptor in default_node_registry().descriptors
    )
    assert all(isinstance(descriptor, NodeDescriptor) for descriptor in descriptors)
    builder = NodePipelineBuilder(registry=NodeRegistry(descriptors))

    with pytest.raises(AppBuilderError, match="implementation_key"):
        builder.build(
            legacy_spec=spec,
            pipeline=resolved.pipeline,
            strategy_kind=resolved.strategy_kind,
        )
