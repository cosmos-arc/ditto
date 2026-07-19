"""Runtime type guards for catalog and resolved backtest configuration."""

from typing import cast

from ditto_strategy.alpha.parameters import CandidateParameter

from ditto_application.exceptions import AppProcessError


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
