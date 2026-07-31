"""Strict I/O-free decoder for canonical experiment planning documents."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import NoReturn, cast

import orjson
from ditto_kernel.exceptions import DittoError
from ditto_strategy.models import StrategySpecRecord

from ditto_application.exceptions import AppProcessError
from ditto_application.processes.experiments._planning_request_identity import (
    validate_planning_request_graph,
)
from ditto_application.processes.experiments._preflight_decode_values import (
    decode_integer,
    decode_mapping,
    decode_string,
)
from ditto_application.processes.experiments._preflight_validation_codec import (
    decode_validation_protocol,
)
from ditto_application.processes.experiments.planning import (
    ExperimentBudgetSpec,
    ResourceCostModel,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPlanningRequest,
    decode_canonical_promotion_objective,
    decode_experiment_failure_policy,
    derive_canonical_research_cycle_hash,
)
from ditto_application.processes.experiments.planning_document_codec import (
    candidate_matrix_spec_payload,
    decode_candidate_matrix_spec,
    decode_dataset_requirements,
)
from ditto_application.processes.experiments.planning_probes import (
    ExperimentSnapshotIdentity,
    PlanningIdentityInput,
    ResearchDatasetRequirement,
    is_canonical_content_hash,
    is_canonical_identity,
    validate_planning_identity,
)
from ditto_application.strategy_spec_deserialization import (
    canonical_spec_hash_for_record,
)

__all__ = ["build_experiment_planning_request"]

_TOP_LEVEL_KEYS = {
    "experiment_id",
    "research_cycle_id",
    "research_cycle_hash",
    "strategy",
    "snapshot",
    "validation",
    "matrix",
    "promotion_objective",
    "dataset_requirements",
    "cost_model",
    "budget",
    "seed",
    "worker_count",
    "failure_policy",
    "created_at",
}
_STRATEGY_KEYS = {"strategy_id", "version", "spec_hash", "spec_json"}
_SNAPSHOT_KEYS = {"snapshot_id", "manifest_hash"}
_COST_MODEL_KEYS = {"bytes_per_run", "bytes_per_trading_session"}
_BUDGET_KEYS = {
    "candidate_limit",
    "fold_run_limit",
    "trading_session_limit",
    "disk_byte_limit",
}
_UTC_SUFFIX = "Z"

type _JsonScalar = None | bool | int | float | str
type _JsonValue = _JsonScalar | list["_JsonValue"] | dict[str, "_JsonValue"]


def _invalid(reason: str) -> NoReturn:
    raise AppProcessError(
        "experiment planning document is invalid",
        details={"code": "SPEC_INVALID", "reason": reason},
    )


def _detach_json(
    value: object,
    *,
    active: set[int] | None = None,
) -> _JsonValue:
    """Copy exact JSON values and reject ambiguous or stateful containers."""
    if value is None or type(value) in {bool, int, str}:
        return cast("_JsonScalar", value)
    if type(value) is float:
        if not math.isfinite(value):
            _invalid("non_finite_planning_document_value")
        return value
    active_ids: set[int] = set() if active is None else active
    if type(value) in {dict, MappingProxyType}:
        container_id = id(value)
        if container_id in active_ids:
            _invalid("cyclic_planning_document_value")
        active_ids.add(container_id)
        try:
            result: dict[str, _JsonValue] = {}
            for key, item in cast("Mapping[object, object]", value).items():
                if type(key) is not str:
                    _invalid("invalid_planning_document_mapping_key")
                result[key] = _detach_json(item, active=active_ids)
            return result
        finally:
            active_ids.remove(container_id)
    if type(value) is list:
        items = cast("list[object]", value)
        container_id = id(items)
        if container_id in active_ids:
            _invalid("cyclic_planning_document_value")
        active_ids.add(container_id)
        try:
            return [_detach_json(item, active=active_ids) for item in items]
        finally:
            active_ids.remove(container_id)
    _invalid("invalid_planning_document_value_type")


def _document_copy(document: Mapping[str, object]) -> dict[str, object]:
    if type(document) not in {dict, MappingProxyType}:
        _invalid("planning_document_must_be_an_exact_mapping")
    detached = _detach_json(document)
    if type(detached) is not dict:
        _invalid("planning_document_must_be_an_object")
    return cast("dict[str, object]", detached)


def _exact_object(
    value: object,
    *,
    field_name: str,
    keys: set[str],
) -> dict[str, object]:
    payload = decode_mapping(value, field_name)
    if set(payload) != keys:
        _invalid(f"invalid_{field_name}_shape")
    return payload


def _decode_field[DecodedT](
    field_name: str,
    decoder: Callable[[], DecodedT],
) -> DecodedT:
    try:
        return decoder()
    except AppProcessError:
        _invalid(f"invalid_planning_document_{field_name}")
    except (DittoError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AppProcessError(
            "experiment planning document is invalid",
            details={
                "code": "SPEC_INVALID",
                "reason": f"invalid_planning_document_{field_name}",
            },
        ) from exc


def _same_canonical_json(left: object, right: object) -> bool:
    try:
        return orjson.dumps(
            _detach_json(left),
            option=orjson.OPT_SORT_KEYS,
        ) == orjson.dumps(
            _detach_json(right),
            option=orjson.OPT_SORT_KEYS,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise AppProcessError(
            "experiment planning document is invalid",
            details={
                "code": "SPEC_INVALID",
                "reason": "invalid_canonical_planning_document_value",
            },
        ) from exc


def _canonical_string(value: object, field_name: str) -> str:
    text = decode_string(value, field_name)
    if not is_canonical_identity(text):
        _invalid(f"invalid_{field_name}")
    return text


def _canonical_hash(value: object, field_name: str) -> str:
    text = decode_string(value, field_name)
    if not is_canonical_content_hash(text):
        _invalid(f"invalid_{field_name}")
    return text


def _created_at(value: object) -> datetime:
    text = decode_string(value, "created_at")
    if not text.endswith(_UTC_SUFFIX):
        _invalid("invalid_created_at")
    try:
        parsed = datetime.fromisoformat(f"{text[:-1]}+00:00")
    except ValueError as exc:
        raise AppProcessError(
            "experiment planning document is invalid",
            details={"code": "SPEC_INVALID", "reason": "invalid_created_at"},
        ) from exc
    if (
        parsed.utcoffset() != UTC.utcoffset(parsed)
        or f"{parsed.isoformat().removesuffix('+00:00')}Z" != text
    ):
        _invalid("invalid_created_at")
    return parsed


def _strategy_record(
    value: object,
    *,
    created_at_text: str,
) -> StrategySpecRecord:
    payload = _exact_object(
        value,
        field_name="strategy",
        keys=_STRATEGY_KEYS,
    )
    strategy_id = _canonical_string(payload.get("strategy_id"), "strategy_id")
    version = decode_integer(payload.get("version"), "strategy.version")
    if version <= 0:
        _invalid("invalid_strategy_version")
    supplied_hash = _canonical_hash(payload.get("spec_hash"), "strategy_spec_hash")
    spec_json = decode_mapping(payload.get("spec_json"), "strategy.spec_json")
    name = _canonical_string(spec_json.get("name"), "strategy_spec_name")
    raw_tags = spec_json.get("tags", [])
    if type(raw_tags) is not list:
        _invalid("invalid_strategy_spec_tags")
    raw_tag_items = cast("list[object]", raw_tags)
    if any(type(item) is not str for item in raw_tag_items):
        _invalid("invalid_strategy_spec_tags")
    tags = tuple(cast("str", item) for item in raw_tag_items)
    record = StrategySpecRecord(
        strategy_id=strategy_id,
        name=name,
        spec_json=cast("dict[str, object]", _detach_json(spec_json)),
        spec_hash=supplied_hash,
        version=version,
        created_at=created_at_text,
        tags=tags,
    )
    canonical_hash = canonical_spec_hash_for_record(record)
    if supplied_hash != canonical_hash:
        _invalid("strategy_spec_hash_mismatch")
    return record


def _snapshot_identity(value: object) -> ExperimentSnapshotIdentity:
    payload = _exact_object(
        value,
        field_name="snapshot",
        keys=_SNAPSHOT_KEYS,
    )
    return ExperimentSnapshotIdentity(
        snapshot_id=_canonical_string(
            payload.get("snapshot_id"),
            "snapshot_id",
        ),
        manifest_hash=_canonical_hash(
            payload.get("manifest_hash"),
            "snapshot_manifest_hash",
        ),
    )


def _dataset_requirements(
    value: object,
) -> tuple[ResearchDatasetRequirement, ...]:
    requirements = decode_dataset_requirements(value)
    canonical = [
        item.as_payload()
        for item in sorted(requirements, key=lambda item: item.dataset_id)
    ]
    if not requirements or not _same_canonical_json(value, canonical):
        _invalid("noncanonical_dataset_requirements")
    return tuple(sorted(requirements, key=lambda item: item.dataset_id))


def _cost_model(value: object) -> ResourceCostModel:
    payload = _exact_object(
        value,
        field_name="cost_model",
        keys=_COST_MODEL_KEYS,
    )
    return ResourceCostModel(
        bytes_per_run=decode_integer(
            payload.get("bytes_per_run"),
            "cost_model.bytes_per_run",
        ),
        bytes_per_trading_session=decode_integer(
            payload.get("bytes_per_trading_session"),
            "cost_model.bytes_per_trading_session",
        ),
    )


def _budget(value: object) -> ExperimentBudgetSpec:
    payload = _exact_object(
        value,
        field_name="budget",
        keys=_BUDGET_KEYS,
    )
    return ExperimentBudgetSpec(
        candidate_limit=decode_integer(
            payload.get("candidate_limit"),
            "budget.candidate_limit",
        ),
        fold_run_limit=decode_integer(
            payload.get("fold_run_limit"),
            "budget.fold_run_limit",
        ),
        trading_session_limit=decode_integer(
            payload.get("trading_session_limit"),
            "budget.trading_session_limit",
        ),
        disk_byte_limit=decode_integer(
            payload.get("disk_byte_limit"),
            "budget.disk_byte_limit",
        ),
    )


def _build(document: Mapping[str, object]) -> ExperimentPlanningRequest:
    payload = _document_copy(document)
    if set(payload) != _TOP_LEVEL_KEYS:
        _invalid("invalid_planning_document_shape")
    created_at_text = decode_string(payload.get("created_at"), "created_at")
    created_at = _created_at(created_at_text)
    strategy = _decode_field(
        "strategy",
        lambda: _strategy_record(
            payload.get("strategy"),
            created_at_text=created_at_text,
        ),
    )
    snapshot = _decode_field(
        "snapshot",
        lambda: _snapshot_identity(payload.get("snapshot")),
    )
    validation = _decode_field(
        "validation",
        lambda: decode_validation_protocol(payload.get("validation")),
    )
    matrix = _decode_field(
        "matrix",
        lambda: decode_candidate_matrix_spec(payload.get("matrix")),
    )
    if not _same_canonical_json(
        payload.get("matrix"),
        candidate_matrix_spec_payload(matrix),
    ):
        _invalid("noncanonical_planning_document_matrix")
    objective = _decode_field(
        "promotion_objective",
        lambda: decode_canonical_promotion_objective(
            payload.get("promotion_objective")
        ),
    )
    requirements = _decode_field(
        "dataset_requirements",
        lambda: _dataset_requirements(payload.get("dataset_requirements")),
    )
    cost_model = _decode_field(
        "cost_model",
        lambda: _cost_model(payload.get("cost_model")),
    )
    budget = _decode_field(
        "budget",
        lambda: _budget(payload.get("budget")),
    )
    failure_policy = _decode_field(
        "failure_policy",
        lambda: decode_experiment_failure_policy(payload.get("failure_policy")),
    )
    request = ExperimentPlanningRequest(
        experiment_id=_canonical_string(
            payload.get("experiment_id"),
            "experiment_id",
        ),
        research_cycle_id=_canonical_string(
            payload.get("research_cycle_id"),
            "research_cycle_id",
        ),
        research_cycle_hash=_canonical_hash(
            payload.get("research_cycle_hash"),
            "research_cycle_hash",
        ),
        strategy_record=strategy,
        snapshot_identity=snapshot,
        validation_request=validation,
        matrix_spec=matrix,
        promotion_objective=objective,
        dataset_requirements=requirements,
        cost_model=cost_model,
        budget=budget,
        seed=decode_integer(payload.get("seed"), "seed"),
        worker_count=decode_integer(payload.get("worker_count"), "worker_count"),
        failure_policy=failure_policy,
        created_at=created_at,
    )
    validate_planning_request_graph(request)
    validate_planning_identity(
        PlanningIdentityInput(
            request.experiment_id,
            request.research_cycle_id,
            request.research_cycle_hash,
            request.strategy_record,
            request.snapshot_identity,
            request.dataset_requirements,
            request.created_at,
        )
    )
    if validation.planning_decision_date != created_at.date():
        _invalid("planning_decision_date_created_at_mismatch")
    expected_cycle_hash = derive_canonical_research_cycle_hash(
        strategy_family_id=strategy.strategy_id,
        validation_request=validation,
    )
    if request.research_cycle_hash != expected_cycle_hash:
        _invalid("research_cycle_hash_mismatch")
    return request


def build_experiment_planning_request(
    document: Mapping[str, object],
) -> ExperimentPlanningRequest:
    """Decode one complete canonical planning document without I/O."""
    try:
        return _build(document)
    except AppProcessError:
        raise
    except (DittoError, KeyError, TypeError, ValueError, OverflowError) as exc:
        raise AppProcessError(
            "experiment planning document is invalid",
            details={
                "code": "SPEC_INVALID",
                "reason": "invalid_planning_document",
            },
        ) from exc
