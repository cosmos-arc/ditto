"""Composition-root runtime over Agent-owned SQLite adapters."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Never

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.runtime import (
    AgentManifest,
    AgentRun,
    AgentSession,
    RunStatus,
)
from ditto_agent.runtime.service import (
    AgentApprovalDecision,
    AgentApprovalDecisionCommand,
    AgentEventView,
    AgentInvalidRequest,
    AgentRequestConflict,
    AgentResourceNotFound,
    AgentRunCancelCommand,
    AgentRunCreateCommand,
    AgentRuntimePort,
    AgentRuntimeUnavailable,
    AgentRunView,
    AgentSessionCreateCommand,
    AgentSessionView,
    ApprovalDecisionKind,
    ApprovalDecisionStatus,
)
from ditto_agent.runtime.state_machine import InvalidRunTransition
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentPersistenceError,
)
from ditto_agent.storage.sqlite.reader import AgentStoreReader
from ditto_agent.storage.sqlite.records import (
    ApprovalStatus,
    IdempotencyDisposition,
    StoredAgentRun,
    StoredApproval,
    StoredRunEvent,
)
from ditto_agent.storage.sqlite.writer import AgentStoreWriter

_SESSION_SCOPE = "agent.session.create"
_RUN_SCOPE = "agent.run.create"
_IDENTITY_NAMESPACE = uuid.UUID("db5b9277-cfb4-5c61-98f2-65472fe1e8ca")


def _identity(kind: str, key: str, request_hash: str) -> str:
    value = uuid.uuid5(_IDENTITY_NAMESPACE, f"{kind}:{key}:{request_hash}")
    return f"{kind}-{value.hex}"


def _run_view(run: StoredAgentRun) -> AgentRunView:
    return AgentRunView(
        run_id=run.run_id,
        session_id=run.session_id,
        status=run.status,
        objective_hash=run.objective_hash,
        authority_hash=run.authority_hash,
        max_model_tokens=run.max_model_tokens,
        max_model_spend_usd=run.max_model_spend_usd,
        model_profile=run.model_profile,
        manifest_hash=run.manifest_hash,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        revision=run.revision,
    )


def _event_view(event: StoredRunEvent) -> AgentEventView:
    return AgentEventView(
        event_id=event.event_id,
        run_id=event.run_id,
        run_sequence=event.run_sequence,
        event_type=event.event_type,
        payload_hash=event.payload_hash,
        occurred_at=event.occurred_at,
        prev_hash=event.prev_hash,
        event_hash=event.event_hash,
    )


def _approval_view(approval: StoredApproval) -> AgentApprovalDecision:
    if approval.decided_at is None or approval.operator_id is None:
        raise AgentRuntimeUnavailable("agent_approval_receipt_invalid")
    status = {
        ApprovalStatus.APPROVED: ApprovalDecisionStatus.APPROVED,
        ApprovalStatus.REJECTED: ApprovalDecisionStatus.REJECTED,
    }.get(approval.status)
    if status is None:
        raise AgentRuntimeUnavailable("agent_approval_receipt_invalid")
    return AgentApprovalDecision(
        approval_id=approval.request_id,
        run_id=approval.run_id,
        action_hash=approval.action_hash,
        status=status,
        operator_id=approval.operator_id,
        reason=approval.reason,
        decided_at=approval.decided_at,
    )


def _raise_persistence(exc: AgentPersistenceError) -> Never:
    if isinstance(exc, AgentConflictError):
        raise AgentRequestConflict(
            str(exc),
            reason_code=exc.reason_code,
        ) from exc
    raise AgentRuntimeUnavailable(exc.reason_code) from exc


class DisabledAgentRuntime(AgentRuntimePort):
    """Fail-closed runtime used while the R5 Agent feature flag is disabled."""

    def _unavailable(self) -> Never:
        raise AgentRuntimeUnavailable("agent_feature_disabled")

    def create_session(self, command: AgentSessionCreateCommand) -> AgentSessionView:
        """Reject session creation while the feature is disabled."""
        self._unavailable()

    def create_run(self, command: AgentRunCreateCommand) -> AgentRunView:
        """Reject run creation while the feature is disabled."""
        self._unavailable()

    def get_run(self, run_id: str) -> AgentRunView:
        """Reject run reads while the feature is disabled."""
        self._unavailable()

    def list_run_events(
        self, run_id: str, *, after_event_id: int | None = None
    ) -> tuple[AgentEventView, ...]:
        """Reject event reads while the feature is disabled."""
        self._unavailable()

    def cancel_run(self, command: AgentRunCancelCommand) -> AgentRunView:
        """Reject cancellation while the feature is disabled."""
        self._unavailable()

    def decide_approval(
        self, command: AgentApprovalDecisionCommand
    ) -> AgentApprovalDecision:
        """Reject approval decisions while the feature is disabled."""
        self._unavailable()


class PersistedAgentRuntime(AgentRuntimePort):
    """Durable session/run use cases with idempotency and revision fences."""

    def __init__(
        self,
        *,
        reader: AgentStoreReader,
        writer: AgentStoreWriter,
        manifest: AgentManifest,
        clock: Callable[[], datetime],
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._manifest = manifest
        self._clock = clock

    def create_session(self, command: AgentSessionCreateCommand) -> AgentSessionView:
        """Create or replay a session under its durable request hash."""
        try:
            request_hash = canonical_sha256(
                {"retention_class": command.retention_class}
            )
            reservation = self._writer.reserve_idempotency(
                scope=_SESSION_SCOPE,
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
                occurred_at=self._clock(),
            )
            result_id = reservation.record.result_identity
            if reservation.disposition is IdempotencyDisposition.REPLAY and result_id:
                durable = self._reader.get_session(result_id)
                if durable is None:
                    raise AgentRuntimeUnavailable("agent_idempotency_result_missing")
                return AgentSessionView(
                    session_id=durable.session_id,
                    created_at=durable.created_at,
                    retention_class=durable.retention_class,
                )
            session = self._writer.create_session(
                AgentSession(
                    session_id=_identity(
                        "session", command.idempotency_key, request_hash
                    ),
                    created_at=reservation.record.created_at,
                    retention_class=command.retention_class,
                )
            )
            self._writer.complete_idempotency(
                scope=_SESSION_SCOPE,
                idempotency_key=command.idempotency_key,
                expected_request_hash=request_hash,
                result_identity=session.session_id,
                occurred_at=self._clock(),
            )
        except ValueError as exc:
            raise AgentInvalidRequest(
                "Agent session request is invalid",
                reason_code="agent_request_invalid",
            ) from exc
        except AgentPersistenceError as exc:
            _raise_persistence(exc)
        return AgentSessionView(
            session_id=session.session_id,
            created_at=session.created_at,
            retention_class=session.retention_class,
        )

    def create_run(self, command: AgentRunCreateCommand) -> AgentRunView:
        """Create or replay a queued run without persisting its raw objective."""
        try:
            session = self._reader.get_session(command.session_id)
            if session is None:
                raise AgentResourceNotFound(
                    "Agent session does not exist",
                    reason_code="agent_session_missing",
                )
            if command.model_profile is not self._manifest.model_profile:
                raise AgentInvalidRequest(
                    "Agent model profile is not configured for this runtime",
                    reason_code="agent_model_profile_unavailable",
                )
            request_hash = canonical_sha256(
                {
                    "session_id": command.session_id,
                    "objective": command.objective,
                    "authority_hash": command.authority_hash,
                    "max_model_tokens": command.max_model_tokens,
                    "max_model_spend_usd": command.max_model_spend_usd,
                    "model_profile": command.model_profile,
                }
            )
            reservation = self._writer.reserve_idempotency(
                scope=_RUN_SCOPE,
                idempotency_key=command.idempotency_key,
                request_hash=request_hash,
                occurred_at=self._clock(),
            )
            result_id = reservation.record.result_identity
            if reservation.disposition is IdempotencyDisposition.REPLAY and result_id:
                durable = self._reader.get_run(result_id)
                if durable is None:
                    raise AgentRuntimeUnavailable("agent_idempotency_result_missing")
                return _run_view(durable)
            run = self._writer.create_run(
                AgentRun(
                    run_id=_identity("run", command.idempotency_key, request_hash),
                    session_id=command.session_id,
                    status=RunStatus.QUEUED,
                    objective=command.objective,
                    authority_hash=command.authority_hash,
                    max_model_tokens=command.max_model_tokens,
                    max_model_spend_usd=command.max_model_spend_usd,
                    model_profile=command.model_profile,
                    manifest_hash=self._manifest.manifest_hash,
                    created_at=reservation.record.created_at,
                )
            )
            if not self._reader.list_run_events(run.run_id):
                self._writer.append_run_event(
                    run_id=run.run_id,
                    event_type="run_queued",
                    payload_hash=canonical_sha256(
                        {
                            "run_id": run.run_id,
                            "manifest_hash": run.manifest_hash,
                        }
                    ),
                    occurred_at=run.created_at,
                )
            self._writer.complete_idempotency(
                scope=_RUN_SCOPE,
                idempotency_key=command.idempotency_key,
                expected_request_hash=request_hash,
                result_identity=run.run_id,
                occurred_at=self._clock(),
            )
        except (AgentInvalidRequest, AgentResourceNotFound):
            raise
        except ValueError as exc:
            raise AgentInvalidRequest(
                "Agent run request is invalid",
                reason_code="agent_request_invalid",
            ) from exc
        except AgentPersistenceError as exc:
            _raise_persistence(exc)
        return _run_view(run)

    def get_run(self, run_id: str) -> AgentRunView:
        """Read one run or fail closed with a typed missing identity."""
        try:
            run = self._reader.get_run(run_id)
        except AgentPersistenceError as exc:
            _raise_persistence(exc)
        if run is None:
            raise AgentResourceNotFound(
                "Agent run does not exist",
                reason_code="agent_run_missing",
            )
        return _run_view(run)

    def list_run_events(
        self,
        run_id: str,
        *,
        after_event_id: int | None = None,
    ) -> tuple[AgentEventView, ...]:
        """Read only persisted events after an optional global event ID."""
        if after_event_id is not None and after_event_id < 0:
            raise ValueError("after_event_id must be non-negative")
        self.get_run(run_id)
        try:
            events = self._reader.list_run_events(run_id)
        except AgentPersistenceError as exc:
            _raise_persistence(exc)
        return tuple(
            _event_view(event)
            for event in events
            if after_event_id is None or event.event_id > after_event_id
        )

    def cancel_run(self, command: AgentRunCancelCommand) -> AgentRunView:
        """Cancel one queued/running run and append its durable event."""
        try:
            occurred_at = self._clock()
            run = self._writer.transition_run(
                run_id=command.run_id,
                expected_revision=command.expected_revision,
                target=RunStatus.CANCELLED,
                occurred_at=occurred_at,
                event_type="run_cancelled",
                event_payload_hash=canonical_sha256(
                    {
                        "run_id": command.run_id,
                        "revision": command.expected_revision + 1,
                    }
                ),
            )
        except InvalidRunTransition as exc:
            raise AgentRequestConflict(
                str(exc), reason_code="agent_run_state_conflict"
            ) from exc
        except AgentPersistenceError as exc:
            if exc.reason_code == "agent_run_missing":
                raise AgentResourceNotFound(
                    str(exc), reason_code=exc.reason_code
                ) from exc
            _raise_persistence(exc)
        return _run_view(run)

    def decide_approval(
        self,
        command: AgentApprovalDecisionCommand,
    ) -> AgentApprovalDecision:
        """Persist an approve/reject decision over the exact action hash."""
        try:
            approval = self._writer.decide_approval(
                request_id=command.approval_id,
                expected_action_hash=command.expected_action_hash,
                approved=command.decision is ApprovalDecisionKind.APPROVE,
                operator_id=command.operator_id,
                reason=command.reason,
                decided_at=self._clock(),
            )
        except AgentPersistenceError as exc:
            if exc.reason_code == "agent_approval_missing":
                raise AgentResourceNotFound(
                    str(exc), reason_code=exc.reason_code
                ) from exc
            _raise_persistence(exc)
        return _approval_view(approval)


__all__ = ["DisabledAgentRuntime", "PersistedAgentRuntime"]
