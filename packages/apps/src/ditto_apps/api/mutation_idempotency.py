"""HTTP boundary for required mutation idempotency keys."""

from __future__ import annotations

from typing import Annotated, Never

from ditto_application.exceptions import AppCommandError
from ditto_application.mutation_idempotency import (
    MutationIdempotency,
    build_mutation_idempotency,
)
from fastapi import Header

from ditto_apps.api.errors import UnprocessableEntityError

IdempotencyKeyHeader = Annotated[str, Header(alias="Idempotency-Key")]


def mutation_idempotency(
    *,
    operation_id: str,
    resource_id: str,
    raw_key: str,
    request_payload: object,
) -> MutationIdempotency:
    """Canonicalize the transport key exactly once and discard its raw value."""
    try:
        return build_mutation_idempotency(
            operation_id=operation_id,
            resource_id=resource_id,
            raw_key=raw_key,
            request_payload=request_payload,
        )
    except AppCommandError as exc:
        _raise_invalid_idempotency(exc)


def _raise_invalid_idempotency(exc: AppCommandError) -> Never:
    code = exc.details.get("code")
    error_code = code if isinstance(code, str) else "IDEMPOTENCY_KEY_INVALID"
    raise UnprocessableEntityError(str(exc), error_code=error_code) from exc


__all__ = [
    "IdempotencyKeyHeader",
    "mutation_idempotency",
]
