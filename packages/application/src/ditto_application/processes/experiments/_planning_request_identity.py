"""Canonical identity for caller-owned experiment planning inputs."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType
from typing import NoReturn, cast

import orjson
from ditto_strategy.models import StrategySpecRecord

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._planning_values import (
    BaselineInputValue,
)
from ditto_application.processes.experiments.planning import (
    BaselineCandidatePlan,
    BaselineDescriptor,
    CandidateMatrixSpec,
    ExperimentBudgetSpec,
    ExperimentFailurePolicy,
    ParameterAxis,
    ResourceCostModel,
    inspect_candidate_matrix_size,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
    declare_trial_family,
    seal_promotion_objective,
)
from ditto_application.processes.experiments.planning_probes import (
    ExperimentSnapshotIdentity,
    ResearchDatasetRequirement,
)
from ditto_application.research_validation_protocol import (
    ValidationProtocolRequest,
    canonical_validation_protocol_payload,
)

__all__ = ["planning_request_hash", "validate_planning_request_graph"]


def _invalid(reason: str) -> NoReturn:
    raise AppProcessError(
        "planning request has no stable canonical identity",
        details={"code": "SPEC_INVALID", "reason": reason},
    )


def _plain(value: object, *, active: set[int] | None = None) -> object:
    """Copy only exact JSON containers; reject stateful protocol impostors."""
    if value is None or type(value) in {bool, int, str}:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _invalid("non_finite_planning_request_value")
        return value
    active_ids: set[int] = set() if active is None else active
    if type(value) in {dict, MappingProxyType}:
        container_id = id(value)
        if container_id in active_ids:
            _invalid("cyclic_planning_request_value")
        active_ids.add(container_id)
        try:
            mapping = cast("Mapping[object, object]", value)
            plain: dict[str, object] = {}
            for key, item in mapping.items():
                if type(key) is not str:
                    _invalid("invalid_planning_request_mapping_key")
                plain[key] = _plain(item, active=active_ids)
            return plain
        finally:
            active_ids.remove(container_id)
    if type(value) in {tuple, list}:
        container_id = id(value)
        if container_id in active_ids:
            _invalid("cyclic_planning_request_value")
        active_ids.add(container_id)
        try:
            return [
                _plain(item, active=active_ids)
                for item in cast("tuple[object, ...] | list[object]", value)
            ]
        finally:
            active_ids.remove(container_id)
    _invalid("invalid_planning_request_value_type")


def _parameter_type(value: object) -> str:
    if type(value) is bool:
        return "bool"
    if type(value) is int:
        return "int"
    if type(value) is float:
        return "float"
    return "string"


def _matrix_payload(matrix: CandidateMatrixSpec) -> Mapping[str, object]:
    return {
        "baseline": {
            "descriptor_type": matrix.baseline.descriptor_type,
            "payload": _plain(matrix.baseline.payload),
            "schema_version": matrix.baseline.schema_version,
        },
        "axes": [
            {
                "name": axis.name,
                "values": [
                    {"type": _parameter_type(value), "value": value}
                    for value in axis.values
                ],
            }
            for axis in matrix.axes
        ],
        "candidate_limit": matrix.candidate_limit,
    }


def _validated_matrix_payload(matrix: CandidateMatrixSpec) -> Mapping[str, object]:
    """Rebuild nested matrix nodes and reject stale derived identities."""
    raw_baseline_payload: object = matrix.baseline.payload
    raw_axes: object = matrix.axes
    if (
        type(matrix) is not CandidateMatrixSpec
        or type(matrix.baseline) is not BaselineDescriptor
        or type(raw_baseline_payload) is not MappingProxyType
        or type(matrix.baseline.canonical_json) is not str
        or type(raw_axes) is not tuple
    ):
        _invalid("invalid_planning_request_matrix_graph")
    raw_axis_items = cast("tuple[object, ...]", raw_axes)
    if any(type(axis) is not ParameterAxis for axis in raw_axis_items):
        _invalid("invalid_planning_request_matrix_graph")
    axes = cast("tuple[ParameterAxis, ...]", raw_axis_items)
    if any(type(axis.values) is not tuple for axis in axes):
        _invalid("invalid_planning_request_matrix_graph")
    rebuilt_baseline = BaselineDescriptor(
        descriptor_type=matrix.baseline.descriptor_type,
        payload=cast("Mapping[str, BaselineInputValue]", raw_baseline_payload),
        schema_version=matrix.baseline.schema_version,
    )
    rebuilt_axes = tuple(ParameterAxis(axis.name, axis.values) for axis in axes)
    rebuilt = CandidateMatrixSpec(
        baseline=rebuilt_baseline,
        axes=rebuilt_axes,
        candidate_limit=matrix.candidate_limit,
    )
    payload = _matrix_payload(matrix)
    rebuilt_payload = _matrix_payload(rebuilt)
    if (
        matrix.baseline.canonical_json != rebuilt_baseline.canonical_json
        or orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
        != orjson.dumps(rebuilt_payload, option=orjson.OPT_SORT_KEYS)
    ):
        _invalid("noncanonical_planning_request_matrix_graph")
    return payload


def _validated_request_graph(
    request: object,
) -> tuple[
    ExperimentPlanningRequest,
    Mapping[str, object],
    Mapping[str, object],
    Mapping[str, object],
]:
    """Seal all caller-owned nodes before any read-side probe may run."""
    if type(request) is not ExperimentPlanningRequest:
        _invalid("invalid_planning_request_type")
    exact_request = request
    strategy = exact_request.strategy_record
    snapshot = exact_request.snapshot_identity
    validation = exact_request.validation_request
    matrix = exact_request.matrix_spec
    objective = exact_request.promotion_objective
    requirements = exact_request.dataset_requirements
    cost = exact_request.cost_model
    budget = exact_request.budget
    if (
        type(strategy) is not StrategySpecRecord
        or type(snapshot) is not ExperimentSnapshotIdentity
        or type(validation) is not ValidationProtocolRequest
        or type(matrix) is not CandidateMatrixSpec
        or type(requirements) is not tuple
        or not requirements
        or any(type(item) is not ResearchDatasetRequirement for item in requirements)
        or type(cost) is not ResourceCostModel
        or type(budget) is not ExperimentBudgetSpec
        or type(exact_request.failure_policy) is not ExperimentFailurePolicy
        or type(exact_request.created_at) is not datetime
        or type(exact_request.seed) is not int
        or exact_request.seed < 0
        or type(exact_request.worker_count) is not int
        or exact_request.worker_count not in (2, 4)
    ):
        _invalid("invalid_planning_request_graph")
    strategy_fields = (
        strategy.strategy_id,
        strategy.name,
        strategy.status,
        strategy.created_at,
        strategy.updated_at,
    )
    if (
        not all(type(value) is str for value in strategy_fields)
        or type(strategy.version) is not int
        or type(strategy.tags) is not tuple
        or any(type(value) is not str for value in strategy.tags)
        or type(strategy.spec_json) is not dict
    ):
        _invalid("invalid_strategy_record_identity")
    _plain(strategy.spec_json)
    ExperimentSnapshotIdentity(snapshot.snapshot_id, snapshot.manifest_hash)
    rebuilt_requirements = tuple(
        ResearchDatasetRequirement(
            item.dataset_id,
            item.expected_snapshot_ids,
            item.requires_pit_universe,
            item.certified_from,
        )
        for item in requirements
    )
    if any(
        (
            original.dataset_id,
            original.expected_snapshot_ids,
            original.requires_pit_universe,
            original.certified_from,
        )
        != (
            rebuilt.dataset_id,
            rebuilt.expected_snapshot_ids,
            rebuilt.requires_pit_universe,
            rebuilt.certified_from,
        )
        for original, rebuilt in zip(
            requirements,
            rebuilt_requirements,
            strict=True,
        )
    ):
        _invalid("noncanonical_planning_request_dataset_requirement")
    ResourceCostModel(cost.bytes_per_run, cost.bytes_per_trading_session)
    ExperimentBudgetSpec(
        budget.candidate_limit,
        budget.fold_run_limit,
        budget.trading_session_limit,
        budget.disk_byte_limit,
    )
    matrix_payload = _validated_matrix_payload(matrix)
    if matrix.candidate_limit != budget.candidate_limit:
        _invalid("planning_request_candidate_limit_mismatch")
    sealed_objective, objective_payload = seal_promotion_objective(objective)
    matrix_size = inspect_candidate_matrix_size(matrix)
    baseline = BaselineCandidatePlan(matrix.baseline)
    expected_baseline_id = ":".join(
        (
            exact_request.experiment_id,
            "candidate",
            str(baseline.ordinal),
            baseline.candidate_hash,
        )
    )
    if str(sealed_objective.baseline_candidate_id) != expected_baseline_id:
        _invalid("promotion_baseline_candidate_mismatch")
    if not matrix_size.exceeds_limit:
        expected_family = declare_trial_family(
            experiment_id=exact_request.experiment_id,
            matrix_spec=matrix,
            family_id=sealed_objective.trial_family.family_id,
            prior_members=sealed_objective.trial_family.prior_members,
        )
        if (
            sealed_objective.trial_family.current_members
            != expected_family.current_members
        ):
            _invalid("promotion_current_trial_family_mismatch")
    protocol_payload = canonical_validation_protocol_payload(validation)
    return exact_request, matrix_payload, protocol_payload, objective_payload


def validate_planning_request_graph(request: object) -> None:
    """Revalidate the exact complete request graph without performing I/O."""
    _validated_request_graph(request)


def _request_payload(request: ExperimentPlanningRequest) -> Mapping[str, object]:
    request, matrix_payload, protocol_payload, objective_payload = (
        _validated_request_graph(request)
    )
    strategy = request.strategy_record
    requirements = request.dataset_requirements
    return {
        "experiment_id": request.experiment_id,
        "research_cycle_id": request.research_cycle_id,
        "research_cycle_hash": request.research_cycle_hash,
        "strategy_record": {
            "strategy_id": strategy.strategy_id,
            "name": strategy.name,
            "spec_json": _plain(strategy.spec_json),
            "version": strategy.version,
            "status": strategy.status,
            "created_at": strategy.created_at,
            "updated_at": strategy.updated_at,
            "tags": list(strategy.tags),
        },
        "snapshot_identity": {
            "snapshot_id": request.snapshot_identity.snapshot_id,
            "manifest_hash": request.snapshot_identity.manifest_hash,
        },
        "validation_protocol": protocol_payload,
        "matrix_spec": matrix_payload,
        "promotion_objective": objective_payload,
        "dataset_requirements": [
            item.as_payload()
            for item in sorted(
                requirements,
                key=lambda requirement: requirement.dataset_id,
            )
        ],
        "cost_model": {
            "bytes_per_run": request.cost_model.bytes_per_run,
            "bytes_per_trading_session": (request.cost_model.bytes_per_trading_session),
        },
        "budget": {
            "candidate_limit": request.budget.candidate_limit,
            "fold_run_limit": request.budget.fold_run_limit,
            "trading_session_limit": request.budget.trading_session_limit,
            "disk_byte_limit": request.budget.disk_byte_limit,
        },
        "seed": request.seed,
        "worker_count": request.worker_count,
        "failure_policy": request.failure_policy.value,
        "created_at": request.created_at.isoformat(),
    }


def planning_request_hash(request: ExperimentPlanningRequest) -> str:
    """Hash every caller-local planning input without invoking external probes."""
    encoded = orjson.dumps(_request_payload(request), option=orjson.OPT_SORT_KEYS)
    returned = orjson.dumps(_request_payload(request), option=orjson.OPT_SORT_KEYS)
    if returned != encoded:
        raise AppProcessError(
            "planning request mutated while sealing its identity",
            details={
                "code": "REPRODUCIBILITY_FAILED",
                "reason": "planning_request_identity_mutated",
            },
        )
    return hashlib.sha256(encoded).hexdigest()
