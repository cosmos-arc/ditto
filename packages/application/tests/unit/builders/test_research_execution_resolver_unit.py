"""Narrow fail-closed tests for durable execution reconstruction helpers."""

from __future__ import annotations

import hashlib
from datetime import date
from inspect import signature
from io import BytesIO
from types import SimpleNamespace
from typing import cast

import orjson
import polars as pl
import pytest
from ditto_analysis.experiments import canonical_payload
from ditto_application.builders import (
    _research_execution_bindings as execution_bindings,
)
from ditto_application.builders import research_execution_resolver as execution_resolver
from ditto_application.builders.research_factor_registry import ResearchFactorBinding
from ditto_application.builders.research_runtime_builder import ResearchStrategyRuntime
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.execution.factor_bridge import (
    FactorBridge,
    compiled_expressions_execution_hash,
)
from ditto_application.processes.experiments._execution_resolution_evidence import (
    DurableLaunchEvidence,
    FrozenResearchExecutionInputs,
)
from ditto_application.processes.experiments.baseline_registry import (
    BaselinePlanRequest,
    BaselineRef,
    default_baseline_registry,
)
from ditto_application.processes.experiments.execution_bundle import (
    ContentAddressedResearchInput,
    ExactBenchmarkBinding,
    ResearchSnapshotBinding,
)
from ditto_application.processes.experiments.execution_contracts import (
    ExactResearchSnapshot,
    ExactStrategyIdentity,
    ExactUniverseIdentity,
    ResearchAssetLane,
)
from ditto_application.processes.experiments.research_policy_artifact import (
    VerifiedInstrumentRulesArtifact,
)
from ditto_application.processes.experiments.research_snapshot_manifest import (
    VerifiedResearchSnapshotManifest,
)
from ditto_features.expression.contracts import CompileIdentity

_RULES_SCHEMA_V1: dict[str, pl.DataType] = {
    "instrument_code": pl.String,
    "instrument_id": pl.Int64,
    "asset_class": pl.String,
    "exchange": pl.String,
    "currency": pl.String,
    "tick_size": pl.Float64,
    "lot_size": pl.Int64,
    "multiplier": pl.Float64,
    "board_segment": pl.String,
    "lifecycle_state": pl.String,
    "ipo_date": pl.Date,
    "delisting_date": pl.Date,
    "as_of_date": pl.Date,
    "known_at": pl.Date,
    "settlement_cycle": pl.Int64,
    "fund_settlement_cycle": pl.Int64,
    "price_limit_pct": pl.Float64,
    "order_types_supported": pl.List(pl.String),
    "call_auction_sessions": pl.List(pl.String),
    "commission_rate": pl.Float64,
    "min_commission": pl.Float64,
    "stamp_duty_rate": pl.Float64,
    "transfer_fee_rate": pl.Float64,
    "source_snapshot_id": pl.String,
}


def _rules_artifact(
    *,
    instrument_code: str = "000300.SH",
    instrument_id: int = 3_000_001,
    source_snapshot_id: str = "provider-1",
    as_of_date: date = date(2026, 1, 1),
    known_at: date = date(2025, 12, 31),
) -> VerifiedInstrumentRulesArtifact:
    frame = pl.DataFrame(
        {
            "instrument_code": [instrument_code],
            "instrument_id": [instrument_id],
            "asset_class": ["index"],
            "exchange": ["XSHG"],
            "currency": ["CNY"],
            "tick_size": [0.01],
            "lot_size": [100],
            "multiplier": [1.0],
            "board_segment": ["index"],
            "lifecycle_state": ["normal"],
            "ipo_date": [date(2005, 4, 8)],
            "delisting_date": [None],
            "as_of_date": [as_of_date],
            "known_at": [known_at],
            "settlement_cycle": [1],
            "fund_settlement_cycle": [0],
            "price_limit_pct": [0.1],
            "order_types_supported": [["market", "limit"]],
            "call_auction_sessions": [["open", "close"]],
            "commission_rate": [0.0003],
            "min_commission": [5.0],
            "stamp_duty_rate": [0.0],
            "transfer_fee_rate": [0.00001],
            "source_snapshot_id": [source_snapshot_id],
        },
        schema=_RULES_SCHEMA_V1,
    )
    buffer = BytesIO()
    frame.write_parquet(buffer)
    artifact_bytes = buffer.getvalue()
    schema_fields = tuple((name, str(dtype)) for name, dtype in frame.schema.items())
    return VerifiedInstrumentRulesArtifact(
        input_evidence=ContentAddressedResearchInput(
            "instrument_rules",
            "instrument_rules",
            hashlib.sha256(artifact_bytes).hexdigest(),
            hashlib.sha256(orjson.dumps(schema_fields)).hexdigest(),
        ),
        artifact_bytes=artifact_bytes,
    )


def _snapshot_manifest(
    inputs: tuple[ContentAddressedResearchInput, ...],
    *,
    dataset_id: str,
    source_snapshot_ids: tuple[str, ...],
    snapshot_id: str = "snapshot-1",
) -> VerifiedResearchSnapshotManifest:
    payload = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "dataset_id": dataset_id,
        "source_snapshot_ids": sorted(source_snapshot_ids),
        "known_at_policy": "sample_time",
        "builder_version": "builder-v1",
        "inputs": [
            dict(item.as_payload())
            for item in sorted(inputs, key=lambda item: item.input_id)
        ],
    }
    raw = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return VerifiedResearchSnapshotManifest(
        exact_snapshot=ExactResearchSnapshot(
            snapshot_id,
            hashlib.sha256(raw).hexdigest(),
        ),
        manifest_bytes=raw,
    )


def test_frozen_inputs_cannot_self_report_factor_versions() -> None:
    assert (
        "factor_versions"
        not in signature(execution_resolver.FrozenResearchExecutionInputs).parameters
    )
    assert (
        "snapshot_binding"
        not in signature(execution_resolver.FrozenResearchExecutionInputs).parameters
    )


def _synthetic_baseline_inputs(
    *extra_inputs: ContentAddressedResearchInput,
) -> execution_resolver.FrozenResearchExecutionInputs:
    membership_hash = "1" * 64
    instrument_rules = _rules_artifact()
    inputs = (
        ContentAddressedResearchInput(
            "bars",
            "bars",
            "3" * 64,
            "4" * 64,
        ),
        ContentAddressedResearchInput(
            "calendar",
            "calendar",
            "5" * 64,
            "6" * 64,
        ),
        ContentAddressedResearchInput(
            "membership",
            "membership",
            membership_hash,
            "7" * 64,
        ),
        instrument_rules.input_evidence,
        *extra_inputs,
    )
    return execution_resolver.FrozenResearchExecutionInputs(
        snapshot_manifest=_snapshot_manifest(
            inputs,
            dataset_id="research-stock",
            source_snapshot_ids=("provider-1",),
        ),
        universe=ExactUniverseIdentity("pit-stock", membership_hash),
        membership_projection_hash="a" * 64,
        instrument_rules=instrument_rules,
    )


def test_synthetic_stock_baseline_controls_come_only_from_frozen_plan() -> None:
    inputs = _synthetic_baseline_inputs()
    registry = default_baseline_registry()
    plan = registry.plan(
        BaselinePlanRequest(
            baseline_ref=BaselineRef("stock_universe_equal_weight", 1),
            snapshot=inputs.snapshot_binding.exact_snapshot,
            universe=inputs.universe,
        )
    )

    binding = execution_bindings.build_synthetic_baseline_backtest_binding(plan, inputs)

    assert binding.rebalance_frequency == "fold_schedule"
    assert binding.rebalance_policy.implementation_key == (
        "research.baseline.fold_schedule"
    )
    assert binding.execution_planner.implementation_key.endswith(".market")
    assert binding.benchmark is None


def test_synthetic_stock_baseline_ignores_unconsumed_snapshot_factors() -> None:
    inputs = _synthetic_baseline_inputs(
        ContentAddressedResearchInput(
            "momentum@1",
            "factor",
            "b" * 64,
            "c" * 64,
        )
    )
    registry = default_baseline_registry()
    plan = registry.plan(
        BaselinePlanRequest(
            baseline_ref=BaselineRef("stock_universe_equal_weight", 1),
            snapshot=inputs.snapshot_binding.exact_snapshot,
            universe=inputs.universe,
        )
    )
    binding = execution_bindings.build_synthetic_baseline_backtest_binding(plan, inputs)

    assert binding.rebalance_frequency == "fold_schedule"
    assert any(
        item.artifact_kind == "factor" for item in inputs.snapshot_binding.inputs
    )


def test_runtime_binding_consumes_factor_subset_of_complete_snapshot() -> None:
    compile_identity = CompileIdentity(
        compile_input_hash="a" * 64,
        operator_fingerprint="b" * 64,
        compiler_fingerprint="c" * 64,
        cache_key="d" * 64,
        engine_codegen_version="polars-codegen-v1",
        analysis_version="factor-analysis-v1",
        polars_version="1.0.0",
        expr_serialization_format="polars-expr-v1",
        operator_versions=(("rank", "1"),),
        global_compile_flags=("grain=1d",),
    )
    used = ResearchFactorBinding(
        factor_id="momentum_1m",
        version=1,
        spec_hash="e" * 64,
        compile_identity=compile_identity,
        compiled_expression_hash="f" * 64,
        analysis_execution_hash="d" * 64,
    )
    used_artifact = ContentAddressedResearchInput(
        "momentum_1m@1",
        "factor",
        "1" * 64,
        "2" * 64,
    )
    unused_artifact = ContentAddressedResearchInput(
        "quality_roe@2",
        "factor",
        "3" * 64,
        "4" * 64,
    )
    snapshot = ResearchSnapshotBinding(
        exact_snapshot=ExactResearchSnapshot("snapshot-1", "5" * 64),
        dataset_id="research-stock",
        source_snapshot_ids=("provider-1",),
        known_at_policy="sample_time",
        builder_version="builder-v1",
        inputs=(used_artifact, unused_artifact),
    )
    exact = ExactStrategyIdentity("stock-selection", 1, "6" * 64)
    runtime = cast(
        "ResearchStrategyRuntime",
        SimpleNamespace(
            base_spec_hash=exact.spec_hash,
            used_factor_bindings=(used,),
            resolved_spec_hash="7" * 64,
            parameter_hash="8" * 64,
            node_registry_manifest_hash="9" * 64,
            pipeline_execution_hash="a" * 64,
            factor_registry_manifest_hash="0" * 64,
            compiled_expressions=None,
        ),
    )

    binding = execution_bindings.build_strategy_execution_binding(
        runtime,
        exact=exact,
        snapshot=snapshot,
        parameters=(),
    )

    assert binding.factor_versions == (("momentum_1m", 1),)
    assert binding.factor_bindings[0].artifact == used_artifact


def test_candidate_runtime_rejects_actual_lookback_above_persisted_envelope() -> None:
    compiled = FactorBridge().compile_and_validate(
        expressions=("ts_mean(close, 21)",),
        weights=(1.0,),
    )
    runtime = cast(
        "ResearchStrategyRuntime",
        SimpleNamespace(
            legacy_spec=SimpleNamespace(
                universe="csi_etf_broad",
                required_datasets=("etf_daily",),
            ),
            resolved_spec=SimpleNamespace(
                strategy_kind=SimpleNamespace(value="etf_rotation")
            ),
            node_registry_manifest_hash="4" * 64,
            factor_registry_manifest_hash="5" * 64,
            used_factor_bindings=(SimpleNamespace(binding_hash="2" * 64),),
            compiled_expressions=compiled,
        ),
    )
    launch = cast(
        "DurableLaunchEvidence",
        SimpleNamespace(
            executor={
                "runtime_validation_evidence": {
                    "lane": "etf_rotation",
                    "universe_id": "csi_etf_broad",
                    "required_datasets": ["etf_daily"],
                    "max_lookback_sessions": 21,
                },
                "node_registry_manifest_hash": "4" * 64,
                "factor_registry_manifest_hash": "5" * 64,
                "factor_binding_hashes": ["2" * 64],
            }
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        execution_bindings.require_candidate_runtime_parity(runtime, launch)

    assert exc_info.value.details["reason"] == (
        "candidate_runtime_lookback_exceeds_validation_envelope"
    )


def test_published_baseline_rejects_execution_time_lookback_drift() -> None:
    preflight_compiled = FactorBridge().compile_and_validate(
        expressions=("ts_mean(close, 20)",),
        weights=(1.0,),
    )
    execution_compiled = FactorBridge().compile_and_validate(
        expressions=("ts_mean(close, 21)",),
        weights=(1.0,),
    )
    exact = ExactStrategyIdentity("seed_etf_rotation", 2, "a" * 64)
    runtime = cast(
        "ResearchStrategyRuntime",
        SimpleNamespace(
            strategy_id=exact.strategy_id,
            strategy_version=exact.version,
            base_spec_hash=exact.spec_hash,
            resolved_spec_hash="b" * 64,
            parameter_hash="c" * 64,
            pipeline_execution_hash="d" * 64,
            node_registry_manifest_hash="4" * 64,
            factor_registry_manifest_hash="5" * 64,
            used_factor_bindings=(SimpleNamespace(binding_hash="2" * 64),),
            compiled_expressions=execution_compiled,
            legacy_spec=SimpleNamespace(
                universe="csi_etf_broad",
                required_datasets=("etf_daily",),
            ),
            resolved_spec=SimpleNamespace(
                strategy_kind=SimpleNamespace(value="etf_rotation")
            ),
        ),
    )
    launch = cast(
        "DurableLaunchEvidence",
        SimpleNamespace(
            executor={
                "runtime_validation_evidence": {
                    "lane": "etf_rotation",
                    "universe_id": "csi_etf_broad",
                    "required_datasets": ["etf_daily"],
                    "max_lookback_sessions": 21,
                },
                "baseline_runtime": {
                    "base_spec_hash": exact.spec_hash,
                    "resolved_spec_hash": "b" * 64,
                    "parameter_hash": "c" * 64,
                    "pipeline_execution_hash": "d" * 64,
                    "compiled_factor_set_hash": compiled_expressions_execution_hash(
                        preflight_compiled
                    ),
                    "max_lookback_sessions": 21,
                    "node_registry_manifest_hash": "4" * 64,
                    "factor_registry_manifest_hash": "5" * 64,
                    "factor_binding_hashes": ["2" * 64],
                },
            }
        ),
    )
    inputs = cast(
        "FrozenResearchExecutionInputs",
        SimpleNamespace(universe=SimpleNamespace(universe_id="csi_etf_broad")),
    )

    with pytest.raises(AppProcessError) as exc_info:
        execution_bindings.require_baseline_runtime_parity(
            runtime,
            launch,
            inputs,
            exact=exact,
            expected_lane=ResearchAssetLane.ETF,
        )

    assert exc_info.value.details["reason"] == "baseline_runtime_lookback_drift"


@pytest.mark.parametrize(
    ("declared", "expected"),
    [("D", "daily"), ("W", "weekly"), ("M", "monthly")],
)
def test_runtime_rebalance_frequency_has_an_exact_engine_mapping(
    declared: str,
    expected: str,
) -> None:
    runtime = cast(
        "ResearchStrategyRuntime",
        SimpleNamespace(
            legacy_spec=SimpleNamespace(
                execution=SimpleNamespace(frequency=declared),
            ),
        ),
    )

    assert execution_bindings.resolve_runtime_rebalance_frequency(runtime) == expected


def test_runtime_rebalance_frequency_rejects_quarterly_engine_fallback() -> None:
    runtime = cast(
        "ResearchStrategyRuntime",
        SimpleNamespace(
            legacy_spec=SimpleNamespace(
                execution=SimpleNamespace(frequency="Q"),
            ),
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        execution_bindings.resolve_runtime_rebalance_frequency(runtime)

    assert exc_info.value.details == {
        "code": "REPRODUCIBILITY_FAILED",
        "reason": "unsupported_research_rebalance_frequency",
        "declared_frequency": "Q",
    }


def test_runtime_benchmark_is_derived_only_from_verified_rules_and_bars() -> None:
    instrument_rules = _rules_artifact(source_snapshot_id="provider-snapshot-1")
    bars = ContentAddressedResearchInput(
        input_id="bars",
        artifact_kind="bars",
        content_hash="c" * 64,
        schema_hash="d" * 64,
    )
    calendar = ContentAddressedResearchInput(
        "calendar",
        "calendar",
        "e" * 64,
        "f" * 64,
    )
    membership = ContentAddressedResearchInput(
        "membership",
        "membership",
        "1" * 64,
        "2" * 64,
    )
    runtime = cast(
        "ResearchStrategyRuntime",
        SimpleNamespace(
            legacy_spec=SimpleNamespace(benchmark="000300.SH"),
        ),
    )
    inputs = execution_resolver.FrozenResearchExecutionInputs(
        snapshot_manifest=_snapshot_manifest(
            (instrument_rules.input_evidence, bars, calendar, membership),
            dataset_id="research-etf",
            source_snapshot_ids=("provider-snapshot-1",),
        ),
        universe=ExactUniverseIdentity("etf-universe", "1" * 64),
        membership_projection_hash="2" * 64,
        instrument_rules=instrument_rules,
    )

    benchmark = execution_bindings.build_runtime_benchmark(
        runtime,
        inputs,
        knowledge_date=date(2026, 1, 1),
    )
    assert type(benchmark) is ExactBenchmarkBinding
    assert benchmark.instrument_id == 3_000_001
    assert benchmark.mapping_input == instrument_rules.input_evidence
    assert benchmark.bars_input == bars
    assert benchmark.instrument_identity_hash == str(
        canonical_payload(
            {
                "instrument_code": "000300.SH",
                "instrument_id": 3_000_001,
                "mapping_input": instrument_rules.input_evidence.as_payload(),
            }
        ).content_hash
    )

    with pytest.raises(AppProcessError) as exc_info:
        execution_bindings.build_runtime_benchmark(
            cast(
                "ResearchStrategyRuntime",
                SimpleNamespace(
                    legacy_spec=SimpleNamespace(benchmark="000905.SH"),
                ),
            ),
            inputs,
            knowledge_date=date(2026, 1, 1),
        )

    assert exc_info.value.details["reason"] == "instrument_code_not_found"


def test_runtime_benchmark_rejects_future_only_code_mapping() -> None:
    instrument_rules = _rules_artifact(
        source_snapshot_id="provider-snapshot-1",
        as_of_date=date(2026, 1, 2),
        known_at=date(2026, 1, 2),
    )
    bars = ContentAddressedResearchInput(
        "bars",
        "bars",
        "c" * 64,
        "d" * 64,
    )
    inputs = execution_resolver.FrozenResearchExecutionInputs(
        snapshot_manifest=_snapshot_manifest(
            (
                instrument_rules.input_evidence,
                bars,
                ContentAddressedResearchInput(
                    "calendar", "calendar", "e" * 64, "f" * 64
                ),
                ContentAddressedResearchInput(
                    "membership", "membership", "1" * 64, "2" * 64
                ),
            ),
            dataset_id="research-etf",
            source_snapshot_ids=("provider-snapshot-1",),
        ),
        universe=ExactUniverseIdentity("etf-universe", "1" * 64),
        membership_projection_hash="2" * 64,
        instrument_rules=instrument_rules,
    )
    runtime = cast(
        "ResearchStrategyRuntime",
        SimpleNamespace(legacy_spec=SimpleNamespace(benchmark="000300.SH")),
    )

    with pytest.raises(AppProcessError) as exc_info:
        execution_bindings.build_runtime_benchmark(
            runtime,
            inputs,
            knowledge_date=date(2026, 1, 1),
        )

    assert (
        exc_info.value.details["reason"]
        == "instrument_code_not_known_at_knowledge_date"
    )


def test_frozen_inputs_reject_rules_artifact_not_declared_by_snapshot() -> None:
    inputs = _synthetic_baseline_inputs()
    poisoned_rules = _rules_artifact(instrument_code="000905.SH")

    with pytest.raises(AppProcessError) as exc_info:
        execution_resolver.FrozenResearchExecutionInputs(
            snapshot_manifest=inputs.snapshot_manifest,
            universe=inputs.universe,
            membership_projection_hash=inputs.membership_projection_hash,
            instrument_rules=poisoned_rules,
        )

    assert exc_info.value.details["reason"] == "instrument_rules_evidence_drift"


def test_frozen_inputs_reject_unbound_rules_row_provenance() -> None:
    inputs = _synthetic_baseline_inputs()
    poisoned_rules = _rules_artifact(source_snapshot_id="unbound-provider")
    snapshot_manifest = _snapshot_manifest(
        tuple(
            poisoned_rules.input_evidence
            if item.artifact_kind == "instrument_rules"
            else item
            for item in inputs.snapshot_binding.inputs
        ),
        dataset_id=inputs.snapshot_binding.dataset_id,
        source_snapshot_ids=inputs.snapshot_binding.source_snapshot_ids,
    )

    with pytest.raises(AppProcessError) as exc_info:
        execution_resolver.FrozenResearchExecutionInputs(
            snapshot_manifest=snapshot_manifest,
            universe=inputs.universe,
            membership_projection_hash=inputs.membership_projection_hash,
            instrument_rules=poisoned_rules,
        )

    assert exc_info.value.details["reason"] == (
        "instrument_rules_source_snapshot_drift"
    )
