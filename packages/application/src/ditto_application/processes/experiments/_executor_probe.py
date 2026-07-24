"""Fail-closed executor probe invocation for experiment planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import orjson
from ditto_analysis.experiments import canonical_payload
from ditto_strategy.alpha.parameters import CandidateParameter, ParameterValue
from ditto_strategy.models import StrategySpecRecord

from ditto_application.processes.experiments._planning_values import (
    BaselineInputValue,
)
from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments.planning import (
    BaselineDescriptor,
    BinderCandidatePlan,
    CandidateMatrixPlan,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
)
from ditto_application.processes.experiments.planning_probes import (
    ExperimentSnapshotIdentity,
    ResearchExecutorProbe,
    ResearchExecutorProbeRequest,
    ResearchExecutorProbeResult,
    is_canonical_identity,
)

__all__ = ["probe_executor"]


def _blocker(reason: str) -> ResearchExecutorProbeResult:
    return ResearchExecutorProbeResult(
        False,
        "REPRODUCIBILITY_FAILED",
        reason,
        "return an immutable typed executor probe result",
        None,
        None,
        (),
        (),
    )


def _exact_text(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _request_payload(
    request: ResearchExecutorProbeRequest,
) -> Mapping[str, object]:
    if type(request) is not ResearchExecutorProbeRequest:
        raise experiment_process_error(
            "executor request must use the exact request DTO"
        )
    strategy = request.strategy_record
    snapshot = request.snapshot_identity
    baseline = request.baseline
    candidates = request.candidates
    if (
        type(strategy) is not StrategySpecRecord
        or type(strategy.spec_json) is not dict
        or type(strategy.version) is not int
        or type(strategy.tags) is not tuple
        or not all(type(tag) is str for tag in strategy.tags)
        or not all(
            _exact_text(value)
            for value in (
                strategy.strategy_id,
                strategy.name,
                strategy.spec_hash,
                strategy.created_at,
            )
        )
        or type(snapshot) is not ExperimentSnapshotIdentity
        or type(baseline) is not BaselineDescriptor
        or type(candidates) is not tuple
        or not all(type(candidate) is BinderCandidatePlan for candidate in candidates)
    ):
        raise experiment_process_error(
            "executor request graph has a non-canonical node"
        )
    candidate_payloads: list[Mapping[str, object]] = []
    for candidate in candidates:
        if type(candidate.binder_parameters) is not tuple or not all(
            type(parameter) is CandidateParameter
            for parameter in candidate.binder_parameters
        ):
            raise experiment_process_error(
                "executor candidate graph has a non-canonical node"
            )
        candidate_payloads.append(
            {
                "ordinal": candidate.ordinal,
                "role": candidate.role.value,
                "candidate_hash": candidate.candidate_hash,
                "persistence_parameters": candidate.persistence_parameters,
                "binder_parameters": [
                    {"path": parameter.path, "value": parameter.value}
                    for parameter in candidate.binder_parameters
                ],
            }
        )
    baseline_payload = {
        "descriptor_type": baseline.descriptor_type,
        "payload": baseline.payload,
        "schema_version": baseline.schema_version,
    }
    return {
        "strategy_record": {
            "strategy_id": strategy.strategy_id,
            "name": strategy.name,
            "spec_json": strategy.spec_json,
            "version": strategy.version,
            "spec_hash": strategy.spec_hash,
            "created_at": strategy.created_at,
            "tags": list(strategy.tags),
        },
        "snapshot_identity": {
            "snapshot_id": snapshot.snapshot_id,
            "manifest_hash": snapshot.manifest_hash,
        },
        "baseline": baseline_payload,
        "candidates": candidate_payloads,
    }


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise experiment_process_error(f"{field_name} must be an object")
    return cast("dict[str, object]", value)


def _list(value: object, field_name: str) -> list[object]:
    if type(value) is not list:
        raise experiment_process_error(f"{field_name} must be a list")
    return cast("list[object]", value)


def _string(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise experiment_process_error(f"{field_name} must be a string")
    return value


def _integer(value: object, field_name: str) -> int:
    if type(value) is not int:
        raise experiment_process_error(f"{field_name} must be an integer")
    return value


def _isolated_request(
    source: ResearchExecutorProbeRequest,
) -> tuple[ResearchExecutorProbeRequest, bytes]:
    sealed = canonical_payload(_request_payload(source))
    decoded = _mapping(cast("object", orjson.loads(sealed.json_bytes)), "request")
    strategy = _mapping(decoded.get("strategy_record"), "strategy_record")
    snapshot = _mapping(decoded.get("snapshot_identity"), "snapshot_identity")
    baseline = _mapping(decoded.get("baseline"), "baseline")
    isolated = ResearchExecutorProbeRequest(
        strategy_record=StrategySpecRecord(
            strategy_id=_string(strategy.get("strategy_id"), "strategy_id"),
            name=_string(strategy.get("name"), "name"),
            spec_json=_mapping(strategy.get("spec_json"), "spec_json"),
            version=_integer(strategy.get("version"), "version"),
            spec_hash=_string(strategy.get("spec_hash"), "spec_hash"),
            created_at=_string(strategy.get("created_at"), "created_at"),
            tags=tuple(
                _string(tag, "tag") for tag in _list(strategy.get("tags"), "tags")
            ),
        ),
        snapshot_identity=ExperimentSnapshotIdentity(
            _string(snapshot.get("snapshot_id"), "snapshot_id"),
            _string(snapshot.get("manifest_hash"), "manifest_hash"),
        ),
        baseline=BaselineDescriptor(
            descriptor_type=_string(baseline.get("descriptor_type"), "descriptor_type"),
            payload=cast(
                "Mapping[str, BaselineInputValue]",
                _mapping(baseline.get("payload"), "baseline.payload"),
            ),
            schema_version=_integer(
                baseline.get("schema_version"), "baseline.schema_version"
            ),
        ),
        candidates=tuple(
            BinderCandidatePlan(
                ordinal=_integer(candidate.get("ordinal"), "candidate.ordinal"),
                binder_parameters=tuple(
                    CandidateParameter(
                        path=_string(parameter.get("path"), "parameter.path"),
                        value=cast("ParameterValue", parameter.get("value")),
                    )
                    for raw_parameter in _list(
                        candidate.get("binder_parameters"),
                        "candidate.binder_parameters",
                    )
                    for parameter in (_mapping(raw_parameter, "parameter"),)
                ),
            )
            for raw_candidate in _list(decoded.get("candidates"), "candidates")
            for candidate in (_mapping(raw_candidate, "candidate"),)
        ),
    )
    if canonical_payload(_request_payload(isolated)).json_bytes != sealed.json_bytes:
        raise experiment_process_error(
            "isolated executor request does not match its sealed graph"
        )
    return isolated, sealed.json_bytes


def _request_unchanged(
    request: ResearchExecutorProbeRequest,
    sealed_json: bytes,
) -> bool:
    try:
        return canonical_payload(_request_payload(request)).json_bytes == sealed_json
    except Exception:
        return False


def _normalize_result(raw_result: object) -> ResearchExecutorProbeResult:
    if type(raw_result) is not ResearchExecutorProbeResult:
        return _blocker("invalid_executor_probe_result")
    if raw_result.available is True and (
        raw_result.code is not None
        or raw_result.reason is not None
        or raw_result.remediation is not None
    ):
        return _blocker("invalid_executor_probe_result")
    raw_required_datasets = cast("object", raw_result.required_datasets)
    if type(raw_required_datasets) is tuple and all(
        is_canonical_identity(dataset_id)
        for dataset_id in cast("tuple[object, ...]", raw_required_datasets)
    ):
        return replace(
            raw_result,
            required_datasets=tuple(
                sorted(cast("tuple[str, ...]", raw_required_datasets))
            ),
        )
    return raw_result


def probe_executor(
    probe: ResearchExecutorProbe,
    request: ExperimentPlanningRequest,
    matrix: CandidateMatrixPlan,
) -> ResearchExecutorProbeResult:
    """Invoke one isolated build probe and reject request/result graph drift."""
    source = ResearchExecutorProbeRequest(
        request.strategy_record,
        request.snapshot_identity,
        matrix.baseline_candidate.descriptor,
        matrix.binder_candidates,
    )
    try:
        isolated, sealed_json = _isolated_request(source)
        if not _request_unchanged(source, sealed_json):
            return _blocker("executor_probe_request_drift")
        raw_result = cast("object", probe.probe(isolated))
    except Exception:  # Executor adapters are an untrusted fail-closed boundary.
        return _blocker("invalid_executor_probe_result")
    if not _request_unchanged(isolated, sealed_json) or not _request_unchanged(
        source, sealed_json
    ):
        return _blocker("executor_probe_mutated_request")
    return _normalize_result(raw_result)
