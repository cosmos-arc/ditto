"""Transport-only idempotency and error mapping for research mutations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Never, Protocol

from ditto_application.exceptions import AppError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    canonical_resource_id,
)
from ditto_application.processes.experiments._coordinator_contract import (
    ExperimentControlReceipt,
)

from ditto_apps.api.errors import (
    APIError,
    BadRequestError,
    ConflictError,
    NotFoundError,
)
from ditto_apps.api.mutation_idempotency import mutation_idempotency
from ditto_apps.models.research import (
    ExperimentControlReceiptResponse,
    ExperimentControlRequest,
    ExperimentLaunchRequest,
    ExperimentRetryFoldRequest,
)

_CONTROL_NOT_FOUND_REASONS = frozenset({"experiment_not_found"})
_CONTROL_CONFLICT_REASONS = frozenset(
    {
        "stale_projection_revision",
        "stale_fold_revision",
        "operator_request_rejected",
    }
)
_CONTROL_CONFLICT_PREFIXES = (
    "illegal_experiment_state",
    "terminal_fold_retry",
    "experiment_desired_state_mismatch",
)


class BlockingRunner(Protocol):
    """Async adapter for one arbitrary blocking callable."""

    def __call__[**P, R](
        self,
        func: Callable[P, R],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> Awaitable[R]: ...


def launch_mutation_idempotency(
    request: ExperimentLaunchRequest,
    raw_key: str,
) -> MutationIdempotency:
    """Canonicalize one launch key against the complete request document."""
    return mutation_idempotency(
        operation_id="research_launch_experiment",
        resource_id=canonical_resource_id(
            "experiment",
            {"experiment_id": request.experiment_id},
        ),
        raw_key=raw_key,
        request_payload=request.model_dump(mode="json"),
    )


def control_mutation_idempotency(
    operation_id: str,
    experiment_id: str,
    request: ExperimentControlRequest,
    raw_key: str,
) -> MutationIdempotency:
    """Canonicalize one experiment-control key and optimistic revision."""
    return mutation_idempotency(
        operation_id=operation_id,
        resource_id=canonical_resource_id(
            "experiment",
            {"experiment_id": experiment_id},
        ),
        raw_key=raw_key,
        request_payload=request.model_dump(mode="json"),
    )


def retry_fold_mutation_idempotency(
    experiment_id: str,
    request: ExperimentRetryFoldRequest,
    raw_key: str,
) -> MutationIdempotency:
    """Canonicalize one fold retry key against its delimiter-safe target."""
    return mutation_idempotency(
        operation_id="research_retry_fold_experiment",
        resource_id=canonical_resource_id(
            "experiment_fold",
            {
                "experiment_id": experiment_id,
                "candidate_id": request.candidate_id,
                "fold_id": request.fold_id,
            },
        ),
        raw_key=raw_key,
        request_payload=request.model_dump(mode="json"),
    )


def raise_research_control_error(exc: AppError) -> Never:
    """Map control errors while preserving integrity failures as server errors."""
    reason = str(exc.details.get("reason", ""))
    code = str(exc.details.get("code", ""))
    message = str(exc)
    if code == "IDEMPOTENCY_KEY_REUSED":
        raise ConflictError(message, error_code=code) from exc
    if code == "IDEMPOTENCY_RECEIPT_INVALID":
        raise APIError(message, status_code=500, error_code=code) from exc
    if reason in _CONTROL_NOT_FOUND_REASONS or "not_found" in reason:
        raise NotFoundError(message) from exc
    if (
        reason in _CONTROL_CONFLICT_REASONS
        or any(reason.startswith(prefix) for prefix in _CONTROL_CONFLICT_PREFIXES)
        or message == "experiment control was persisted but notification failed"
    ):
        raise ConflictError(message) from exc
    raise BadRequestError(message) from exc


def mutation_occurred_at() -> datetime:
    """Return one timezone-aware server event time outside request hashing."""
    return datetime.now(UTC)


def to_control_receipt_response(
    receipt: ExperimentControlReceipt,
) -> ExperimentControlReceiptResponse:
    """Map the application control receipt without dropping durable fields."""
    return ExperimentControlReceiptResponse(
        experiment_id=receipt.experiment_id,
        status=receipt.status,
        desired_state=receipt.desired_state,
        revision=receipt.revision,
        occurred_at=receipt.occurred_at,
        live_run_ids=list(receipt.live_run_ids),
    )


async def run_research_control[C](
    handle: Callable[[C], ExperimentControlReceipt],
    command: C,
    *,
    runner: BlockingRunner,
) -> ExperimentControlReceipt:
    """Run one control handler and map its typed application failure."""
    try:
        return await runner(handle, command)
    except AppError as exc:
        raise_research_control_error(exc)


__all__ = [
    "control_mutation_idempotency",
    "launch_mutation_idempotency",
    "mutation_occurred_at",
    "raise_research_control_error",
    "retry_fold_mutation_idempotency",
    "run_research_control",
    "to_control_receipt_response",
]
