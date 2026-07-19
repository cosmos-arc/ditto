"""Runtime type guards for catalog and resolved backtest configuration."""

from typing import cast

from ditto_backtest.config import (
    validate_canonical_sha256,
    validate_effective_parameter_identity,
    validate_research_snapshot_identity,
    validate_spec_hash,
)
from ditto_strategy.alpha.parameters import CandidateParameter

from ditto_application.exceptions import AppProcessError


def _raise_identity_error(exc: ValueError, *, field_name: str) -> None:
    raise AppProcessError(
        str(exc),
        field_name=field_name,
        reason="invalid_canonical_identity",
    ) from exc


def require_research_snapshot_identity(
    snapshot_id: object,
    manifest_hash: object,
) -> None:
    """Map snapshot pair validation to the stable application error contract."""
    try:
        validate_research_snapshot_identity(snapshot_id, manifest_hash)
    except ValueError as exc:
        _raise_identity_error(exc, field_name="research_snapshot")


def require_resolved_strategy_identity(
    *,
    spec_hash: object,
    base_spec_hash: object,
    parameter_hash: object,
    effective_parameters: object,
) -> None:
    """Validate each resolved strategy identity with its exact field name."""
    try:
        validate_spec_hash(spec_hash)
    except ValueError as exc:
        _raise_identity_error(exc, field_name="spec_hash")
    try:
        validate_canonical_sha256(base_spec_hash, field_name="base_spec_hash")
    except ValueError as exc:
        _raise_identity_error(exc, field_name="base_spec_hash")
    try:
        validate_effective_parameter_identity(parameter_hash, effective_parameters)
    except ValueError as exc:
        _raise_identity_error(exc, field_name="parameter_hash")


def require_candidate_parameters(value: object) -> tuple[CandidateParameter, ...]:
    """Return a validated immutable candidate tuple."""
    if not isinstance(value, tuple):
        raise AppProcessError(
            "candidate_parameters must be tuple[CandidateParameter, ...]",
            field_name="candidate_parameters",
        )
    candidates: list[CandidateParameter] = []
    for item in cast(tuple[object, ...], value):
        if not isinstance(item, CandidateParameter):
            raise AppProcessError(
                "candidate_parameters must be tuple[CandidateParameter, ...]",
                field_name="candidate_parameters",
            )
        candidates.append(item)
    return tuple(candidates)


def require_resolved_backtest_config[ConfigT](
    value: object,
    *,
    expected_type: type[ConfigT],
) -> ConfigT:
    """Reject launch requests that have not acquired canonical strategy identity."""
    if not isinstance(value, expected_type):
        raise AppProcessError(
            "BacktestService requires resolved BacktestServiceConfig",
            field_name="config",
            reason="unresolved_strategy_identity",
        )
    return value
