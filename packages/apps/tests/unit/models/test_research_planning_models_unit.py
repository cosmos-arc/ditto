"""Strict transport-model tests for canonical experiment planning documents."""

from __future__ import annotations

from copy import deepcopy

import pytest
from ditto_apps.models.research import ExperimentPlanningRequest
from pydantic import ValidationError


def _payload() -> dict[str, object]:
    return {
        "experiment_id": "exp-1",
        "research_cycle_id": "cycle-1",
        "research_cycle_hash": "a" * 64,
        "strategy": {
            "strategy_id": "strategy-1",
            "version": 2,
            "spec_hash": "b" * 64,
            "spec_json": {
                "name": "Strategy",
                "params": {"top_k": 10, "enabled": True},
            },
        },
        "snapshot": {
            "snapshot_id": "snapshot-1",
            "manifest_hash": "c" * 64,
        },
        "validation": {
            "trading_sessions": ["2026-07-30"],
        },
        "matrix": {
            "baseline": {
                "descriptor_type": "active-strategy",
                "payload": {"strategy_id": "strategy-1"},
                "schema_version": 1,
            },
            "axes": [
                {
                    "name": "selector.top_k",
                    "values": [{"type": "int", "value": 10}],
                }
            ],
            "candidate_limit": 4,
        },
        "promotion_objective": {
            "schema_id": "r3-promotion-objective",
            "schema_version": 1,
        },
        "dataset_requirements": [
            {
                "dataset_id": "etf_daily",
                "expected_snapshot_ids": ["provider-snapshot-1"],
                "requires_pit_universe": True,
                "certified_from": "2016-01-01",
            }
        ],
        "cost_model": {
            "bytes_per_run": 100,
            "bytes_per_trading_session": 2,
        },
        "budget": {
            "candidate_limit": 4,
            "fold_run_limit": 100,
            "trading_session_limit": 10_000,
            "disk_byte_limit": 1_000_000,
        },
        "seed": 42,
        "worker_count": 2,
        "failure_policy": "fail_fast",
        "created_at": "2026-07-30T00:00:00Z",
    }


def test_planning_request_preserves_complete_python_document() -> None:
    payload = _payload()

    request = ExperimentPlanningRequest.model_validate(payload)

    assert request.model_dump(mode="python") == payload


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"unknown": True}),
        lambda payload: payload["strategy"].update({"unknown": True}),
        lambda payload: payload["snapshot"].update({"unknown": True}),
        lambda payload: payload["matrix"].update({"unknown": True}),
        lambda payload: payload["matrix"]["baseline"].update({"unknown": True}),
        lambda payload: payload["dataset_requirements"][0].update({"unknown": True}),
        lambda payload: payload["budget"].update({"unknown": True}),
    ],
)
def test_planning_request_forbids_extra_fields_at_every_typed_boundary(
    mutate: object,
) -> None:
    payload = _payload()
    mutate(payload)

    with pytest.raises(ValidationError):
        ExperimentPlanningRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field_path", "value"),
    [
        (("strategy", "version"), "2"),
        (("matrix", "candidate_limit"), "4"),
        (("budget", "fold_run_limit"), 100.0),
        (("cost_model", "bytes_per_run"), True),
        (("seed",), "42"),
        (("worker_count",), True),
    ],
)
def test_planning_request_rejects_scalar_coercion(
    field_path: tuple[str, ...],
    value: object,
) -> None:
    payload = _payload()
    target = payload
    for key in field_path[:-1]:
        target = target[key]
    target[field_path[-1]] = value

    with pytest.raises(ValidationError):
        ExperimentPlanningRequest.model_validate(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_planning_request_rejects_non_finite_nested_json(value: float) -> None:
    payload = _payload()
    payload["strategy"]["spec_json"]["params"]["top_k"] = value

    with pytest.raises(ValidationError):
        ExperimentPlanningRequest.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("strategy", "not-an-object"),
        ("snapshot", []),
        ("validation", []),
        ("matrix", []),
        ("promotion_objective", []),
        ("dataset_requirements", {}),
        ("cost_model", []),
        ("budget", []),
    ],
)
def test_planning_request_rejects_invalid_nested_structure(
    field_name: str,
    value: object,
) -> None:
    payload = _payload()
    payload[field_name] = value

    with pytest.raises(ValidationError):
        ExperimentPlanningRequest.model_validate(payload)


def test_planning_request_rejects_non_string_nested_mapping_keys() -> None:
    payload = deepcopy(_payload())
    payload["strategy"]["spec_json"][1] = "invalid-key"

    with pytest.raises(ValidationError):
        ExperimentPlanningRequest.model_validate(payload)
