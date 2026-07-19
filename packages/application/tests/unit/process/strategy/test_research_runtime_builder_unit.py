"""Explicit research runtime assembly tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from inspect import signature
from typing import Any

import polars as pl
import pytest
from ditto_application.exceptions import AppBuilderError
from ditto_strategy.alpha.context import StrategyContext
from ditto_strategy.alpha.parameters import CandidateParameter, legacy_parameter_path
from ditto_strategy.alpha.pipeline import StrategyInputBundle
from ditto_strategy.alpha.seeds import SEED_STRATEGY_SPECS
from ditto_strategy.alpha.spec_codec import (
    adapt_legacy_strategy_spec,
    canonical_spec_payload,
)
from ditto_strategy.alpha.specs import (
    ParamConstraint,
    ScorerSpec,
    SelectorSpec,
    StrategySpec,
)
from ditto_strategy.models import StrategySpecRecord


def _legacy_spec() -> StrategySpec:
    return StrategySpec(
        strategy_id="research-etf",
        name="Research ETF",
        template="etf_rotation",
        universe="csi_etf_broad",
        asset_class="etf",
        scorer=ScorerSpec(method="rank"),
        selector=SelectorSpec(method="top_k", params={"k": 4}),
        params={
            "allocation_method": "equal_weight",
            "lookback": 20,
            "scoring_ascending": False,
            "top_k": 4,
        },
        param_constraints=(
            ParamConstraint(
                name="lookback",
                dtype="int",
                min_value=5,
                max_value=120,
                step=5,
            ),
            ParamConstraint(
                name="top_k",
                dtype="int",
                min_value=1,
                max_value=10,
                step=1,
            ),
        ),
        required_datasets=("etf_daily",),
    )


def _record(*, status: str = "draft", version: int = 3) -> StrategySpecRecord:
    spec = _legacy_spec()
    return StrategySpecRecord(
        strategy_id=spec.strategy_id,
        name=spec.name,
        spec_json=asdict(spec),
        version=version,
        status=status,
        tags=spec.tags,
    )


def _stock_record(
    *,
    params: dict[str, object] | None = None,
    selector_k: int | None = None,
) -> StrategySpecRecord:
    spec = StrategySpec(
        strategy_id="research-stock",
        name="Research stock selection",
        template="stock_selection",
        universe="all_a_shares",
        asset_class="equity",
        scorer=ScorerSpec(method="rank"),
        selector=SelectorSpec(
            method="top_k",
            params={} if selector_k is None else {"k": selector_k},
        ),
        params={} if params is None else params,
        required_datasets=("stock_daily",),
    )
    return StrategySpecRecord(
        strategy_id=spec.strategy_id,
        name=spec.name,
        spec_json=asdict(spec),
        version=1,
        status="draft",
        tags=spec.tags,
    )


def _snapshot() -> Any:
    from ditto_application.builders.research_runtime_builder import (
        ResearchSnapshotIdentity,
    )

    return ResearchSnapshotIdentity(
        snapshot_id="rds-20260718-etf-daily",
        manifest_hash="c" * 64,
    )


def _builder() -> object:
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    return ResearchRuntimeBuilder()


def _run_pipeline(runtime: object, *, run_id: str) -> object:
    pipeline = runtime.pipeline
    return pipeline.run(
        StrategyContext(),
        StrategyInputBundle(
            trade_date="2026-07-18",
            strategy_id="research-etf",
            run_id=run_id,
            instruments=pl.DataFrame({"instrument_id": [1, 2, 3, 4, 5]}),
            market_data=pl.DataFrame({"instrument_id": [1, 2, 3, 4, 5]}),
            signal_values=pl.DataFrame(
                {
                    "instrument_id": [1, 2, 3, 4, 5],
                    "signal_value": [0.1, 0.2, 0.3, 0.4, 0.5],
                },
            ),
        ),
    )


def test_research_builder_has_no_catalog_or_allow_unpublished_switch() -> None:
    """Research uses explicit versions instead of production catalog lookup flags."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    constructor_parameters = signature(ResearchRuntimeBuilder).parameters
    build_parameters = signature(ResearchRuntimeBuilder.build).parameters

    assert "catalog_service" not in constructor_parameters
    assert "allow_unpublished" not in constructor_parameters
    assert "allow_unpublished" not in build_parameters
    assert "record" in build_parameters


def test_research_builder_uses_explicit_record_candidate_and_snapshot() -> None:
    """One explicit draft version resolves all candidate and snapshot identities."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    record = _record(status="draft", version=7)
    record_before = deepcopy(record.spec_json)
    builder = ResearchRuntimeBuilder()

    runtime = builder.build(
        record=record,
        candidate_parameters=(
            CandidateParameter(path=legacy_parameter_path("top_k"), value=2),
            CandidateParameter(path=legacy_parameter_path("lookback"), value=30),
        ),
        snapshot_identity=_snapshot(),
    )

    assert runtime.strategy_id == "research-etf"
    assert runtime.strategy_version == 7
    assert runtime.legacy_spec.strategy_id == runtime.strategy_id
    assert runtime.base_spec.strategy_family_id == runtime.strategy_id
    assert runtime.resolved_spec.strategy_family_id == runtime.strategy_id
    assert runtime.version_status == "draft"
    assert runtime.snapshot_identity.snapshot_id == ("rds-20260718-etf-daily")
    assert runtime.base_spec_hash != runtime.resolved_spec_hash
    assert len(runtime.parameter_hash) == 64
    assert record.spec_json == record_before
    factor = next(
        node
        for node in runtime.resolved_spec.pipeline.nodes
        if node.node_id == "legacy_factor_set"
    )
    assert factor.config["params"]["top_k"] == 2
    assert factor.config["params"]["lookback"] == 30


def test_top_k_candidate_changes_the_real_pipeline_stage_and_result() -> None:
    """The candidate changes the existing executor, not only hashes or metadata."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )
    from ditto_strategy.alpha.builtins.selection import SelectionStage

    builder = ResearchRuntimeBuilder()
    baseline = builder.build(
        record=_record(),
        candidate_parameters=(),
        snapshot_identity=_snapshot(),
    )
    candidate = builder.build(
        record=_record(),
        candidate_parameters=(
            CandidateParameter(path=legacy_parameter_path("top_k"), value=2),
        ),
        snapshot_identity=_snapshot(),
    )
    baseline_selection = next(
        stage
        for stage in baseline.pipeline._stages
        if isinstance(stage, SelectionStage)
    )
    candidate_selection = next(
        stage
        for stage in candidate.pipeline._stages
        if isinstance(stage, SelectionStage)
    )

    baseline_target = _run_pipeline(baseline, run_id="baseline")
    candidate_target = _run_pipeline(candidate, run_id="candidate")

    assert baseline_selection.top_k == 4
    assert candidate_selection.top_k == 2
    assert len(baseline_target.positions) == 4
    assert len(candidate_target.positions) == 2


def test_stock_selection_materializes_true_tunable_defaults_before_binding() -> None:
    """Empty params expose complete real defaults; explicit values still win."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )
    from ditto_strategy.alpha.builtins.selection import SelectionStage

    builder = ResearchRuntimeBuilder()
    baseline = builder.build(
        record=_stock_record(),
        candidate_parameters=(),
        snapshot_identity=_snapshot(),
    )
    overridden = builder.build(
        record=_stock_record(
            params={
                "custom_not_tunable": "preserved",
                "rebalance_freq": "weekly",
                "top_k": 7,
            },
            selector_k=4,
        ),
        candidate_parameters=(),
        snapshot_identity=_snapshot(),
    )

    expected_baseline = {
        legacy_parameter_path("allocation_method"): "equal_weight",
        legacy_parameter_path("cash_target"): 0.0,
        legacy_parameter_path("max_weight"): 0.15,
        legacy_parameter_path("rebalance_freq"): "monthly",
        legacy_parameter_path("top_k"): 10,
        legacy_parameter_path("trend_threshold"): 0.0,
    }
    assert {
        item.path: item.value for item in baseline.effective_parameters
    } == expected_baseline
    baseline_selection = next(
        stage
        for stage in baseline.pipeline._stages
        if isinstance(stage, SelectionStage)
    )
    overridden_selection = next(
        stage
        for stage in overridden.pipeline._stages
        if isinstance(stage, SelectionStage)
    )
    overridden_effective = {
        item.path: item.value for item in overridden.effective_parameters
    }
    assert baseline_selection.top_k == 10
    assert overridden_selection.top_k == 7
    assert overridden_effective[legacy_parameter_path("top_k")] == 7
    assert overridden_effective[legacy_parameter_path("rebalance_freq")] == "weekly"
    assert legacy_parameter_path("custom_not_tunable") not in overridden_effective
    assert overridden.legacy_spec.params["custom_not_tunable"] == "preserved"


def test_lookback_candidate_changes_resolved_compiled_config_only() -> None:
    """Current legacy lookback is visible in compiled config without fake consumers."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    runtime = ResearchRuntimeBuilder().build(
        record=_record(),
        candidate_parameters=(
            CandidateParameter(path=legacy_parameter_path("lookback"), value=35),
        ),
        snapshot_identity=_snapshot(),
    )
    factor = next(
        node
        for node in runtime.resolved_spec.pipeline.nodes
        if node.node_id == "legacy_factor_set"
    )

    assert factor.config["params"]["lookback"] == 35
    assert {item.path: item.value for item in runtime.effective_parameters}[
        legacy_parameter_path("lookback")
    ] == 35


def test_research_builder_accepts_review_status_through_explicit_guard() -> None:
    """The pre-governance guard explicitly admits draft and review versions."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    runtime = ResearchRuntimeBuilder().build(
        record=_record(status="review"),
        candidate_parameters=(),
        snapshot_identity=_snapshot(),
    )

    assert runtime.version_status == "review"


@pytest.mark.parametrize(
    "invalid_version",
    [
        pytest.param(True, id="boolean"),
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
    ],
)
def test_research_builder_rejects_non_positive_exact_record_version(
    invalid_version: object,
) -> None:
    """An explicit research record always carries one positive integer version."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    record = replace(_record(), version=invalid_version)  # type: ignore[arg-type]

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchRuntimeBuilder().build(
            record=record,
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "invalid_research_version_record"
    assert exc_info.value.details["path"] == "record.version"


@pytest.mark.parametrize("invalid_strategy_id", ["", " "])
def test_research_builder_rejects_empty_record_strategy_identity(
    invalid_strategy_id: str,
) -> None:
    """The catalog record identity must be non-empty and canonical."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchRuntimeBuilder().build(
            record=replace(_record(), strategy_id=invalid_strategy_id),
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "invalid_research_strategy_identity"
    assert exc_info.value.details["path"] == "record.strategy_id"


def test_research_builder_rejects_legacy_payload_family_mismatch() -> None:
    """A legacy payload cannot substitute a different family under the record ID."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    record = _record()
    payload = deepcopy(record.spec_json)
    payload["strategy_id"] = "different-family"

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchRuntimeBuilder().build(
            record=replace(record, spec_json=payload),
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "research_strategy_identity_mismatch"
    assert exc_info.value.details["path"] == "spec_json.strategy_id"
    assert exc_info.value.details["record_strategy_id"] == "research-etf"
    assert exc_info.value.details["payload_strategy_family_id"] == "different-family"


@pytest.mark.parametrize("payload_identity", [None, "", " "])
def test_research_builder_requires_explicit_legacy_payload_identity(
    payload_identity: str | None,
) -> None:
    """A record ID cannot silently replace a missing legacy payload family."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    record = _record()
    payload = deepcopy(record.spec_json)
    if payload_identity is None:
        payload.pop("strategy_id")
    else:
        payload["strategy_id"] = payload_identity

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchRuntimeBuilder().build(
            record=replace(record, spec_json=payload),
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "invalid_research_strategy_identity"
    assert exc_info.value.details["path"] == "spec_json.strategy_id"


def test_research_builder_rejects_native_v2_family_mismatch_before_gate() -> None:
    """Native unsupported status cannot mask a record/payload family mismatch."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    adapted = adapt_legacy_strategy_spec(_legacy_spec())
    payload = canonical_spec_payload(adapted)
    payload.update(
        strategy_family_id="different-family",
        name=adapted.name,
        metadata=dict(adapted.metadata),
        tags=[],
    )
    record = StrategySpecRecord(
        strategy_id="research-etf",
        name=adapted.name,
        spec_json=payload,
        version=1,
        status="draft",
    )

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchRuntimeBuilder().build(
            record=record,
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "research_strategy_identity_mismatch"
    assert exc_info.value.details["path"] == "spec_json.strategy_family_id"


def test_custom_research_guard_cannot_broaden_draft_review_status_boundary() -> None:
    """Extension guards may narrow policy but cannot admit production statuses."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    class AllowAllGuard:
        def ensure_buildable(self, record: StrategySpecRecord) -> None:
            del record

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchRuntimeBuilder(version_guard=AllowAllGuard()).build(
            record=_record(status="published"),
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "research_version_not_buildable"
    assert exc_info.value.details["path"] == "record.status"


def test_research_builder_rejects_published_version_without_boolean_bypass() -> None:
    """Production state is outside the research version guard boundary."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchRuntimeBuilder().build(
            record=_record(status="published"),
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "research_version_not_buildable"


def test_research_builder_fails_closed_for_native_v2_without_executor() -> None:
    """Task3 does not pretend arbitrary native V2 nodes have a runtime executor."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    adapted = adapt_legacy_strategy_spec(_legacy_spec())
    payload = canonical_spec_payload(adapted)
    payload.update(name=adapted.name, metadata=dict(adapted.metadata), tags=[])
    record = StrategySpecRecord(
        strategy_id=adapted.strategy_family_id,
        name=adapted.name,
        spec_json=payload,
        version=1,
        status="draft",
    )

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchRuntimeBuilder().build(
            record=record,
            candidate_parameters=(),
            snapshot_identity=_snapshot(),
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "native_v2_executor_unavailable"


def test_research_builder_preserves_parameter_error_contract() -> None:
    """Application mapping keeps stable SPEC_INVALID details from strategy binding."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchRuntimeBuilder().build(
            record=_record(),
            candidate_parameters=(
                CandidateParameter(path=legacy_parameter_path("top_k"), value=99),
            ),
            snapshot_identity=_snapshot(),
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "parameter_above_max"


@pytest.mark.parametrize(
    ("strategy_id", "expected_values"),
    [
        pytest.param(
            "seed_etf_industry_rotation",
            {
                "allocation_method": "equal_weight",
                "cash_target": 0.0,
                "top_k": 5,
            },
            id="etf-rotation",
        ),
        pytest.param(
            "seed_etf_trend_swing",
            {
                "allocation_method": "equal_weight",
                "cash_target": 0.0,
                "lookback_window": 20,
                "max_positions": 3,
                "trailing_stop_pct": 0.08,
                "trend_threshold": 0.0,
            },
            id="etf-trend-swing",
        ),
    ],
)
def test_etf_legacy_records_inject_only_registered_template_parameters(
    strategy_id: str,
    expected_values: dict[str, object],
) -> None:
    """ETF migration expands getter-declared defaults, not arbitrary params."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchRuntimeBuilder,
    )

    spec = SEED_STRATEGY_SPECS[strategy_id]
    record = StrategySpecRecord(
        strategy_id=spec.strategy_id,
        name=spec.name,
        spec_json=asdict(spec),
        version=1,
        status="draft",
        tags=spec.tags,
    )

    runtime = ResearchRuntimeBuilder().build(
        record=record,
        candidate_parameters=(),
        snapshot_identity=_snapshot(),
    )

    effective = {
        item.path.removeprefix(
            "/pipeline/nodes/legacy_factor_set/config/params/",
        ): item.value
        for item in runtime.effective_parameters
    }
    assert effective == expected_values
    assert "vol_window" not in effective
    assert "fast_period" not in effective


@pytest.mark.parametrize("snapshot_id", ["", " ", 42])
def test_research_snapshot_identity_is_explicit_and_certified(
    snapshot_id: object,
) -> None:
    """The seam requires an opaque certified snapshot identity, not a placeholder."""
    from ditto_application.builders.research_runtime_builder import (
        ResearchSnapshotIdentity,
    )

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchSnapshotIdentity(
            snapshot_id=snapshot_id,  # type: ignore[arg-type]
            manifest_hash="c" * 64,
        )

    assert exc_info.value.details["code"] == "SPEC_INVALID"
    assert exc_info.value.details["reason"] == "invalid_research_snapshot_identity"


@pytest.mark.parametrize("manifest_hash", ["", "c" * 16, "C" * 64, "z" * 64])
def test_research_snapshot_manifest_hash_is_required_and_canonical(
    manifest_hash: str,
) -> None:
    from ditto_application.builders.research_runtime_builder import (
        ResearchSnapshotIdentity,
    )

    with pytest.raises(AppBuilderError) as exc_info:
        ResearchSnapshotIdentity(
            snapshot_id="rds-20260718-etf-daily",
            manifest_hash=manifest_hash,
        )

    assert exc_info.value.details["reason"] == "invalid_research_snapshot_identity"
