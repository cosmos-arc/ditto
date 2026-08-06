"""Unit contracts for the one-shot R3 holdout claim authority."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime

import pytest
from ditto_analysis.errors import ExperimentSpecError
from ditto_analysis.experiments import CandidateId, ContentHash, ExperimentId

NOW = datetime(2026, 7, 22, 2, 0, tzinfo=UTC)


def _api() -> tuple[type[object], type[object], object]:
    """Import Task 12 contracts inside tests so the first run is a true RED."""
    from ditto_analysis.experiments.holdout import (
        HoldoutClaimAuthorityCommand,
        HoldoutSelectionReason,
        holdout_request_payload,
    )

    return (
        HoldoutClaimAuthorityCommand,
        HoldoutSelectionReason,
        holdout_request_payload,
    )


def _command() -> object:
    command_type, reason_type, _ = _api()
    return command_type(
        experiment_id=ExperimentId("experiment-1"),
        candidate_id=CandidateId("candidate-2"),
        expected_revision=7,
        expected_selection_evidence_hash=ContentHash("a" * 64),
        operator_confirmation="operator reviewed immutable evidence",
        selection_reason=reason_type(
            code="objective_review",
            summary="Candidate two won the registered objective review.",
        ),
        resolved_reproduction_fingerprint=ContentHash("b" * 64),
        occurred_at=NOW,
    )


def test_authority_command_accepts_no_caller_supplied_derived_identity() -> None:
    command = _command()

    assert {item.name for item in fields(command)} == {
        "experiment_id",
        "candidate_id",
        "expected_revision",
        "expected_selection_evidence_hash",
        "operator_confirmation",
        "selection_reason",
        "resolved_reproduction_fingerprint",
        "occurred_at",
        "event_detail_extension",
    }
    assert not hasattr(command, "research_cycle_id")
    assert not hasattr(command, "snapshot_id")
    assert not hasattr(command, "fold_id")
    assert not hasattr(command, "logical_run_id")


def test_holdout_request_payload_is_canonical_and_binds_selection_evidence() -> None:
    command = _command()
    _, _, payload_factory = _api()

    first = payload_factory(command)
    second = payload_factory(replace(command))

    assert first == second
    assert first == {
        "schema_version": 1,
        "expected_experiment_revision": 7,
        "expected_selection_evidence_hash": "a" * 64,
        "reason": {
            "code": "objective_review",
            "summary": "Candidate two won the registered objective review.",
        },
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_revision", -1),
        ("operator_confirmation", "  padded"),
        ("resolved_reproduction_fingerprint", "not-a-hash"),
        ("occurred_at", datetime(2026, 7, 22, 2, 0)),
    ],
)
def test_holdout_authority_command_rejects_ambiguous_inputs(
    field: str,
    value: object,
) -> None:
    command_type, reason_type, _ = _api()
    values: dict[str, object] = {
        "experiment_id": ExperimentId("experiment-1"),
        "candidate_id": CandidateId("candidate-2"),
        "expected_revision": 7,
        "expected_selection_evidence_hash": ContentHash("a" * 64),
        "operator_confirmation": "operator reviewed immutable evidence",
        "selection_reason": reason_type("objective_review", "Registered review."),
        "resolved_reproduction_fingerprint": ContentHash("b" * 64),
        "occurred_at": NOW,
    }
    values[field] = value

    with pytest.raises(ExperimentSpecError):
        command_type(**values)


def test_holdout_selection_reason_rejects_free_form_shape_drift() -> None:
    _, reason_type, _ = _api()

    with pytest.raises(ExperimentSpecError):
        reason_type(" objective_review", "Registered review.")
    with pytest.raises(ExperimentSpecError):
        reason_type("objective_review", "")
