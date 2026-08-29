"""Typed failures for the dedicated Agent persistence boundary."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


class AgentPersistenceError(RuntimeError):
    """Base error that never exposes raw SQLite statements or payloads."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.details = MappingProxyType(dict(details or {}))


class AgentSchemaError(AgentPersistenceError):
    """The dedicated database is not in an approved schema state."""


class AgentDatabaseClosedError(AgentPersistenceError):
    """The nominal database wrapper has been permanently closed."""


class AgentIntegrityError(AgentPersistenceError):
    """Persisted immutable content is corrupt or inconsistent."""


class AgentConflictError(AgentPersistenceError):
    """An optimistic write or immutable replay conflicts with durable state."""


class IdempotencyConflictError(AgentConflictError):
    """An idempotency key was replayed with a different request hash."""


class LeaseLostError(AgentConflictError):
    """A worker no longer owns the supplied monotonic fencing token."""


class AuditChainError(AgentIntegrityError):
    """The append-only audit hash chain failed verification."""


__all__ = [
    "AgentConflictError",
    "AgentDatabaseClosedError",
    "AgentIntegrityError",
    "AgentPersistenceError",
    "AgentSchemaError",
    "AuditChainError",
    "IdempotencyConflictError",
    "LeaseLostError",
]
