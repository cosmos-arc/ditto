"""Cross-link persisted certification evidence to its exact input window."""

from __future__ import annotations

from datetime import date
from typing import cast

from ditto_application.processes.experiments._process_error import (
    experiment_process_error,
)
from ditto_application.processes.experiments.planning_contracts import (
    ExperimentPreflightCheck,
)
from ditto_application.research_validation_protocol import (
    ValidationProtocolPlan,
    ValidationProtocolRequest,
)

__all__ = ["validate_certification_preimage"]


def _mapping(value: object, field_name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise experiment_process_error(f"{field_name} must be an object")
    return cast("dict[str, object]", value)


def _string(value: object, field_name: str) -> str:
    if type(value) is not str:
        raise experiment_process_error(f"{field_name} must be a string")
    return value


def _date(value: object, field_name: str) -> date:
    text = _string(value, field_name)
    parsed = date.fromisoformat(text)
    if parsed.isoformat() != text:
        raise experiment_process_error(f"{field_name} is not a canonical date")
    return parsed


def validate_certification_preimage(
    *,
    preflight: dict[str, object],
    protocol: ValidationProtocolRequest,
    validation: ValidationProtocolPlan,
    checks: tuple[ExperimentPreflightCheck, ...],
) -> None:
    """Require certification request, gate, and snapshot to share one window."""
    identities = _mapping(preflight.get("identities"), "identities")
    certification = _mapping(
        identities.get("certification"),
        "identities.certification",
    )
    if set(certification) != {
        "ready",
        "profile",
        "required_from",
        "required_to",
        "dataset_ids",
        "report_ids",
        "reason_codes",
        "snapshot_evidence",
    }:
        raise experiment_process_error("identities.certification has an invalid shape")
    holdout = validation.reserved_holdout
    if holdout is None:
        raise experiment_process_error(
            "launchable validation requires a reserved holdout"
        )
    expected_from = protocol.required_input_start
    expected_to = holdout.test_window.end
    required_from = _date(
        certification.get("required_from"),
        "identities.certification.required_from",
    )
    required_to = _date(
        certification.get("required_to"),
        "identities.certification.required_to",
    )
    snapshot = _mapping(
        certification.get("snapshot_evidence"),
        "identities.certification.snapshot_evidence",
    )
    snapshot_start = _date(
        snapshot.get("snapshot_start"),
        "identities.certification.snapshot_start",
    )
    snapshot_end = _date(
        snapshot.get("snapshot_end"),
        "identities.certification.snapshot_end",
    )
    certification_checks = tuple(
        check for check in checks if check.rule_id == "certification"
    )
    if len(certification_checks) != 1:
        raise experiment_process_error("preflight must contain one certification check")
    check = certification_checks[0]
    policy = _mapping(cast("object", check.policy), "certification.policy")
    observed = _mapping(cast("object", check.observed), "certification.observed")
    if (
        required_from != expected_from
        or required_to != expected_to
        or snapshot_start > required_from
        or snapshot_end < required_to
        or snapshot_end < snapshot_start
        or policy.get("required_from") != required_from.isoformat()
        or policy.get("required_to") != required_to.isoformat()
        or observed.get("snapshot_evidence") != snapshot
    ):
        raise experiment_process_error(
            "certification window does not match protocol inputs"
        )
