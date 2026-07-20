"""Strict decoder for persisted experiment preflight checks."""

from __future__ import annotations

from typing import cast

from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPreflightCheck,
    PreflightOutcome,
)

__all__ = ["decode_preflight_checks"]


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


def _optional_string(value: object, field_name: str) -> str | None:
    return None if value is None else _string(value, field_name)


def decode_preflight_checks(value: object) -> tuple[ExperimentPreflightCheck, ...]:
    """Decode the persisted ordered preflight-check collection exactly."""
    return tuple(
        ExperimentPreflightCheck(
            rule_id=_string(item.get("rule_id"), "check.rule_id"),
            outcome=PreflightOutcome(_string(item.get("outcome"), "check.outcome")),
            code=_optional_string(item.get("code"), "check.code"),
            reason=_optional_string(item.get("reason"), "check.reason"),
            remediation=_optional_string(item.get("remediation"), "check.remediation"),
            observed=_mapping(item.get("observed"), "check.observed"),
            policy=_mapping(item.get("policy"), "check.policy"),
        )
        for raw_item in _list(value, "preflight.checks")
        for item in (_mapping(raw_item, "preflight.check"),)
    )
