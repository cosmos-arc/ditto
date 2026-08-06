"""Exact codec tests for published-baseline runtime evidence."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest
from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments import (
    _preflight_semantics as preflight_semantics,
)
from ditto_application.processes.experiments._baseline_runtime_evidence import (
    baseline_runtime_payload,
    decode_baseline_runtime_evidence,
)
from ditto_application.processes.experiments._preflight_checks import executor_check
from ditto_application.processes.experiments.baseline_planning import (
    resolve_planning_baseline,
)
from ditto_application.processes.experiments.baseline_registry import (
    default_baseline_registry,
)
from ditto_application.processes.experiments.planning import BaselineDescriptor
from ditto_application.processes.experiments.planning_probes import (
    BaselineRuntimeExecutorEvidence,
    ResearchDatasetRequirement,
    ResearchExecutorProbeResult,
)
from ditto_application.research_validation_contracts import RuntimeValidationEvidence


def _evidence() -> BaselineRuntimeExecutorEvidence:
    return BaselineRuntimeExecutorEvidence(
        base_spec_hash="a" * 64,
        resolved_spec_hash="b" * 64,
        parameter_hash="c" * 64,
        pipeline_execution_hash="d" * 64,
        compiled_factor_set_hash="e" * 64,
        max_lookback_sessions=64,
        node_registry_manifest_hash="f" * 64,
        factor_registry_manifest_hash="1" * 64,
        factor_binding_hashes=("2" * 64,),
    )


def test_baseline_runtime_lookback_round_trips_in_exact_payload() -> None:
    evidence = _evidence()

    payload = baseline_runtime_payload(evidence)

    assert payload == {
        "base_spec_hash": "a" * 64,
        "resolved_spec_hash": "b" * 64,
        "parameter_hash": "c" * 64,
        "pipeline_execution_hash": "d" * 64,
        "compiled_factor_set_hash": "e" * 64,
        "max_lookback_sessions": 64,
        "node_registry_manifest_hash": "f" * 64,
        "factor_registry_manifest_hash": "1" * 64,
        "factor_binding_hashes": ["2" * 64],
    }
    assert decode_baseline_runtime_evidence(payload) == evidence


@pytest.mark.parametrize(
    "value",
    [-1, True, 1.0],
    ids=("negative", "bool", "float"),
)
def test_baseline_runtime_codec_rejects_tampered_lookback(value: object) -> None:
    payload = dict(cast("dict[str, object]", baseline_runtime_payload(_evidence())))
    payload["max_lookback_sessions"] = value

    with pytest.raises(AppProcessError) as exc_info:
        decode_baseline_runtime_evidence(payload)

    assert exc_info.value.details["reason"] == (
        "baseline runtime max lookback must be a nonnegative integer"
    )


def test_preflight_semantics_rejects_baseline_lookback_above_global_envelope() -> None:
    runtime = RuntimeValidationEvidence(
        lane="etf_rotation",
        universe_id="csi_etf_broad",
        required_datasets=("etf_daily",),
        max_lookback_sessions=63,
        requires_pit_universe=True,
    )
    preflight = {
        "executor": {
            "available": True,
            "code": None,
            "reason": None,
            "remediation": None,
            "strategy_spec_hash": "3" * 64,
            "node_registry_manifest_hash": "4" * 64,
            "factor_registry_manifest_hash": "5" * 64,
            "factor_binding_hashes": ["2" * 64],
            "baseline_ref": "etf_current_active.v1",
            "baseline_descriptor_hash": "6" * 64,
            "baseline_registry_manifest_hash": "7" * 64,
            "baseline_exact_strategy_hash": "8" * 64,
            "baseline_runtime": baseline_runtime_payload(_evidence()),
            "required_datasets": ["etf_daily"],
            "candidates": [],
        }
    }
    work = cast(
        "object",
        SimpleNamespace(
            candidate_matrix=SimpleNamespace(
                binder_candidates=(),
                baseline_candidate=SimpleNamespace(
                    descriptor=SimpleNamespace(payload={"spec_hash": "a" * 64})
                ),
            )
        ),
    )

    with pytest.raises(AppProcessError) as exc_info:
        preflight_semantics._validate_executor(
            preflight=preflight,
            work=work,
            runtime=runtime,
        )

    assert exc_info.value.details["reason"] == (
        "persisted executor evidence is not launch-ready"
    )


def test_executor_gate_rejects_baseline_lookback_above_global_envelope() -> None:
    descriptor = BaselineDescriptor(
        descriptor_type="etf-current-active",
        payload={
            "strategy_id": "seed_etf_rotation",
            "version": 2,
            "spec_hash": "a" * 64,
        },
    )
    baseline = resolve_planning_baseline(descriptor, default_baseline_registry())
    result = ResearchExecutorProbeResult(
        available=True,
        code=None,
        reason=None,
        remediation=None,
        strategy_spec_hash="3" * 64,
        node_registry_manifest_hash="4" * 64,
        required_datasets=("etf_daily",),
        candidates=(),
        runtime_validation_evidence=RuntimeValidationEvidence(
            lane="etf_rotation",
            universe_id="csi_etf_broad",
            required_datasets=("etf_daily",),
            max_lookback_sessions=63,
            requires_pit_universe=True,
        ),
        baseline_ref=baseline.ref.identity,
        baseline_descriptor_hash=baseline.registration.descriptor.canonical_hash,
        baseline_registry_manifest_hash=baseline.registry_manifest_hash,
        baseline_exact_strategy_hash=baseline.exact_strategy.canonical_hash,
        factor_registry_manifest_hash="5" * 64,
        factor_binding_hashes=("2" * 64,),
        baseline_runtime=_evidence(),
    )
    matrix = cast(
        "object",
        SimpleNamespace(
            binder_candidates=(),
            baseline_candidate=SimpleNamespace(descriptor=descriptor),
        ),
    )
    request = cast(
        "object",
        SimpleNamespace(
            dataset_requirements=(
                ResearchDatasetRequirement("etf_daily", ("snapshot-1",)),
            )
        ),
    )

    check = executor_check(result, matrix, request)

    assert check.outcome.value == "fail"
    assert check.observed["baseline_evidence_valid"] is False
