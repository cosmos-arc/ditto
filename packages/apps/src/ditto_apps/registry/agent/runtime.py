"""Composition-root runtime over Agent-owned SQLite adapters."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Never, cast

import orjson
from ditto_agent._canonical import canonical_sha256
from ditto_agent.approval_runtime import (
    AgentApprovalRuntime,
    ApprovalRuntimeConflict,
    ApprovalRuntimeUnavailable,
    ApprovalRuntimeViolation,
)
from ditto_agent.contracts.runtime import (
    AgentManifest,
    AgentRun,
    AgentSession,
    RunStatus,
)
from ditto_agent.presentation import (
    AgentContextPresentation,
    AgentGuardrailPresentation,
    AgentPresentationError,
    AgentRunPresentation,
)
from ditto_agent.runtime.service import (
    AgentApprovalDecision,
    AgentApprovalDecisionCommand,
    AgentApprovalListView,
    AgentApprovalStatus,
    AgentApprovalView,
    AgentCapabilityView,
    AgentEventView,
    AgentInvalidRequest,
    AgentRequestConflict,
    AgentResourceNotFound,
    AgentRunCancelCommand,
    AgentRunCreateCommand,
    AgentRunListView,
    AgentRuntimePort,
    AgentRuntimeState,
    AgentRuntimeUnavailable,
    AgentRunView,
    AgentSessionCreateCommand,
    AgentSessionListView,
    AgentSessionView,
    ApprovalDecisionKind,
    ApprovalDecisionStatus,
)
from ditto_agent.runtime.state_machine import InvalidRunTransition
from ditto_agent.storage.sqlite.errors import (
    AgentConflictError,
    AgentPersistenceError,
)
from ditto_agent.storage.sqlite.presentation_store import (
    AgentPresentationReader,
    AgentPresentationWriter,
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

from ditto_apps.registry.agent.runtime_presenters import run_view as _run_view

_SESSION_SCOPE = "agent.session.create"
_RUN_SCOPE = "agent.run.create"
_MAX_PAGE_SIZE = 100
_IDENTITY_NAMESPACE = uuid.UUID("db5b9277-cfb4-5c61-98f2-65472fe1e8ca")


def _identity(kind: str, key: str, request_hash: str) -> str:
    value = uuid.uuid5(_IDENTITY_NAMESPACE, f"{kind}:{key}:{request_hash}")
    return f"{kind}-{value.hex}"


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


def _page_bounds(limit: int, offset: int) -> None:
    if type(limit) is not int or limit < 1 or limit > _MAX_PAGE_SIZE:
        raise AgentInvalidRequest(
            "Agent page limit is invalid", reason_code="agent_pagination_invalid"
        )
    if type(offset) is not int or offset < 0:
        raise AgentInvalidRequest(
            "Agent page offset is invalid", reason_code="agent_pagination_invalid"
        )


def _context_filter(
    context_type: str | None,
    context_id: str | None,
) -> AgentContextPresentation | None:
    if (context_type is None) != (context_id is None):
        raise AgentInvalidRequest(
            "Agent context filters must be supplied together",
            reason_code="agent_context_filter_incomplete",
        )
    if context_type is None or context_id is None:
        return None
    try:
        return AgentContextPresentation(
            context_type=context_type,
            context_id=context_id,
        )
    except ValueError as exc:
        raise AgentInvalidRequest(
            "Agent context filter is invalid",
            reason_code="agent_context_filter_invalid",
        ) from exc


def _approval_status(approval: StoredApproval, *, now: datetime) -> AgentApprovalStatus:
    if approval.status is ApprovalStatus.APPROVED:
        return AgentApprovalStatus.APPROVED
    if approval.status is ApprovalStatus.REJECTED:
        return AgentApprovalStatus.REJECTED
    if approval.expires_at <= now:
        return AgentApprovalStatus.EXPIRED
    return AgentApprovalStatus.PENDING


def _approval_projection(
    approval: StoredApproval, *, now: datetime
) -> AgentApprovalView:
    try:
        decoded = orjson.loads(approval.action_payload)
    except orjson.JSONDecodeError as exc:
        raise AgentRuntimeUnavailable("agent_approval_projection_invalid") from exc
    if not isinstance(decoded, dict):
        raise AgentRuntimeUnavailable("agent_approval_projection_invalid")
    payload = cast("dict[str, object]", decoded)
    action_type = payload.get("action_kind")
    target_identity = payload.get("subject_identity")
    if type(action_type) is not str or type(target_identity) is not str:
        raise AgentRuntimeUnavailable("agent_approval_projection_invalid")
    return AgentApprovalView(
        approval_id=approval.request_id,
        run_id=approval.run_id,
        action_type=action_type,
        target_identity=target_identity,
        action_payload=payload,
        action_hash=approval.action_hash,
        status=_approval_status(approval, now=now),
        requested_at=approval.requested_at,
        expires_at=approval.expires_at,
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

    def __init__(
        self,
        reason_code: str = "agent_feature_disabled",
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._reason_code = reason_code
        self._clock = clock or (lambda: datetime.now(UTC))

    def get_capabilities(self) -> AgentCapabilityView:
        """Keep status readable even though all runtime actions fail closed."""
        feature_disabled = self._reason_code == "agent_feature_disabled"
        return AgentCapabilityView(
            enabled=False,
            runtime_state=(
                AgentRuntimeState.DISABLED
                if feature_disabled
                else AgentRuntimeState.DEGRADED
            ),
            provider=None,
            available_profiles=(),
            default_profile=None,
            degradation_reason=self._reason_code,
            checked_at=self._clock(),
        )

    def list_sessions(self, *, limit: int, offset: int) -> AgentSessionListView:
        """Return a stable empty history when no store is configured."""
        _page_bounds(limit, offset)
        return AgentSessionListView(items=(), total=0, limit=limit, offset=offset)

    def list_runs(
        self,
        *,
        status: RunStatus | None,
        session_id: str | None,
        context_type: str | None,
        context_id: str | None,
        limit: int,
        offset: int,
    ) -> AgentRunListView:
        """Return a stable empty history when no store is configured."""
        _page_bounds(limit, offset)
        _context_filter(context_type, context_id)
        return AgentRunListView(items=(), total=0, limit=limit, offset=offset)

    def get_approval(self, approval_id: str) -> AgentApprovalView:
        """Reject unknown approval reads while no store is configured."""
        self._unavailable()

    def list_approvals(
        self,
        *,
        status: AgentApprovalStatus | None,
        run_id: str | None,
        limit: int,
        offset: int,
    ) -> AgentApprovalListView:
        """Return a stable empty inbox when no store is configured."""
        _page_bounds(limit, offset)
        return AgentApprovalListView(items=(), total=0, limit=limit, offset=offset)

    def _unavailable(self) -> Never:
        raise AgentRuntimeUnavailable(self._reason_code)

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


@dataclass(frozen=True, slots=True)
class PersistedAgentRuntimeOptions:
    """Optional runtime collaborators kept behind one composition-root value."""

    approval_runtime: AgentApprovalRuntime | None = None
    provider_name: str = "configured"
    presentation_reader: AgentPresentationReader | None = None
    presentation_writer: AgentPresentationWriter | None = None


class PersistedAgentRuntime(AgentRuntimePort):
    """Durable session/run use cases with idempotency and revision fences."""

    def __init__(
        self,
        *,
        reader: AgentStoreReader,
        writer: AgentStoreWriter,
        manifest: AgentManifest,
        clock: Callable[[], datetime],
        options: PersistedAgentRuntimeOptions | None = None,
    ) -> None:
        resolved_options = options or PersistedAgentRuntimeOptions()
        self._reader = reader
        self._writer = writer
        self._manifest = manifest
        self._clock = clock
        self._approval_runtime = resolved_options.approval_runtime
        self._provider_name = resolved_options.provider_name
        self._presentation_reader = resolved_options.presentation_reader
        self._presentation_writer = resolved_options.presentation_writer

    def _project_run(self, run: StoredAgentRun) -> AgentRunView:
        if self._presentation_reader is None:
            return _run_view(run)
        try:
            presentation = self._presentation_reader.get(run.run_id)
        except AgentPresentationError as exc:
            raise AgentRuntimeUnavailable(exc.reason_code) from exc
        if presentation is None:
            return _run_view(
                run,
                projection_reason="agent_presentation_missing",
            )
        return _run_view(run, presentation=presentation)

    def _latest_event_cursor(self, run_id: str) -> int:
        events = self._reader.list_run_events(run_id)
        return events[-1].event_id if events else 0

    def _ensure_initial_projection(
        self,
        run: StoredAgentRun,
        command: AgentRunCreateCommand,
    ) -> None:
        if self._presentation_writer is None:
            return
        try:
            existing = (
                self._presentation_reader.get(run.run_id)
                if self._presentation_reader is not None
                else None
            )
            if existing is not None:
                return
            self._presentation_writer.put(
                AgentRunPresentation(
                    run_id=run.run_id,
                    objective=command.objective,
                    context=command.context,
                    status=run.status,
                    output_summary=None,
                    tool_records=(),
                    evidence_refs=(),
                    artifact_refs=(),
                    guardrail=AgentGuardrailPresentation(
                        status="unknown",
                        reason_code=None,
                    ),
                    usage=None,
                    failure_code=None,
                    projection_version=1,
                    updated_at=run.created_at,
                    event_cursor=self._latest_event_cursor(run.run_id),
                )
            )
        except AgentPresentationError as exc:
            raise AgentRuntimeUnavailable(exc.reason_code) from exc

    def _advance_projection_status(
        self,
        run: StoredAgentRun,
        *,
        updated_at: datetime,
    ) -> None:
        if self._presentation_reader is None or self._presentation_writer is None:
            return
        try:
            presentation = self._presentation_reader.get(run.run_id)
            if presentation is None:
                return
            self._presentation_writer.put(
                replace(
                    presentation,
                    status=run.status,
                    projection_version=presentation.projection_version + 1,
                    updated_at=updated_at,
                    event_cursor=self._latest_event_cursor(run.run_id),
                )
            )
        except AgentPresentationError as exc:
            raise AgentRuntimeUnavailable(exc.reason_code) from exc

    def get_capabilities(self) -> AgentCapabilityView:
        """Return the configured public profile without model credentials."""
        return AgentCapabilityView(
            enabled=True,
            runtime_state=AgentRuntimeState.AVAILABLE,
            provider=self._provider_name,
            available_profiles=(self._manifest.model_profile,),
            default_profile=self._manifest.model_profile,
            degradation_reason=None,
            checked_at=self._clock(),
        )

    def list_sessions(self, *, limit: int, offset: int) -> AgentSessionListView:
        """List durable sessions without depending on caller-held IDs."""
        _page_bounds(limit, offset)
        try:
            sessions = self._reader.list_sessions()
        except AgentPersistenceError as exc:
            _raise_persistence(exc)
        items = tuple(
            AgentSessionView(
                session_id=session.session_id,
                created_at=session.created_at,
                retention_class=session.retention_class,
            )
            for session in sessions[offset : offset + limit]
        )
        return AgentSessionListView(
            items=items,
            total=len(sessions),
            limit=limit,
            offset=offset,
        )

    def list_runs(
        self,
        *,
        status: RunStatus | None,
        session_id: str | None,
        context_type: str | None,
        context_id: str | None,
        limit: int,
        offset: int,
    ) -> AgentRunListView:
        """List durable runs with explicit equality filters."""
        _page_bounds(limit, offset)
        context_filter = _context_filter(context_type, context_id)
        try:
            runs = self._reader.list_runs()
        except AgentPersistenceError as exc:
            _raise_persistence(exc)
        projected = tuple(
            self._project_run(run)
            for run in runs
            if (status is None or run.status is status)
            and (session_id is None or run.session_id == session_id)
        )
        filtered = tuple(
            run
            for run in projected
            if context_filter is None or run.context == context_filter
        )
        return AgentRunListView(
            items=filtered[offset : offset + limit],
            total=len(filtered),
            limit=limit,
            offset=offset,
        )

    def get_approval(self, approval_id: str) -> AgentApprovalView:
        """Read one exact action payload or fail closed."""
        try:
            approval = self._reader.get_approval(approval_id)
        except AgentPersistenceError as exc:
            _raise_persistence(exc)
        if approval is None:
            raise AgentResourceNotFound(
                "Agent approval does not exist",
                reason_code="agent_approval_missing",
            )
        return _approval_projection(approval, now=self._clock())

    def list_approvals(
        self,
        *,
        status: AgentApprovalStatus | None,
        run_id: str | None,
        limit: int,
        offset: int,
    ) -> AgentApprovalListView:
        """List exact approval subjects including computed expiry."""
        _page_bounds(limit, offset)
        now = self._clock()
        try:
            approvals = self._reader.list_approvals()
        except AgentPersistenceError as exc:
            _raise_persistence(exc)
        projected = tuple(
            _approval_projection(approval, now=now)
            for approval in approvals
            if run_id is None or approval.run_id == run_id
        )
        filtered = tuple(
            approval
            for approval in projected
            if status is None or approval.status is status
        )
        return AgentApprovalListView(
            items=filtered[offset : offset + limit],
            total=len(filtered),
            limit=limit,
            offset=offset,
        )

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
            request_payload: dict[str, object] = {
                "session_id": command.session_id,
                "objective": command.objective,
                "authority_hash": command.authority_hash,
                "max_model_tokens": command.max_model_tokens,
                "max_model_spend_usd": command.max_model_spend_usd,
                "model_profile": command.model_profile,
            }
            if command.context is not None:
                request_payload["context"] = command.context
            request_hash = canonical_sha256(request_payload)
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
                self._ensure_initial_projection(durable, command)
                return self._project_run(durable)
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
        self._ensure_initial_projection(run, command)
        return self._project_run(run)

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
        return self._project_run(run)

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
        self._advance_projection_status(run, updated_at=occurred_at)
        return self._project_run(run)

    def decide_approval(
        self,
        command: AgentApprovalDecisionCommand,
    ) -> AgentApprovalDecision:
        """Persist an approve/reject decision over the exact action hash."""
        try:
            if self._approval_runtime is None:
                pending = self._reader.get_approval(command.approval_id)
                if pending is not None and (
                    self._reader.get_continuation(pending.run_id) is not None
                ):
                    raise AgentRuntimeUnavailable("agent_approval_resume_unconfigured")
                approval = self._writer.decide_approval(
                    request_id=command.approval_id,
                    expected_action_hash=command.expected_action_hash,
                    approved=command.decision is ApprovalDecisionKind.APPROVE,
                    operator_id=command.operator_id,
                    reason=command.reason,
                    decided_at=self._clock(),
                )
            else:
                outcome = asyncio.run(
                    self._approval_runtime.decide_and_resume(
                        request_id=command.approval_id,
                        expected_action_hash=command.expected_action_hash,
                        approved=(command.decision is ApprovalDecisionKind.APPROVE),
                        operator_id=command.operator_id,
                        reason=command.reason,
                    )
                )
                approval = outcome.approval
        except ApprovalRuntimeUnavailable as exc:
            raise AgentRuntimeUnavailable(exc.reason_code) from exc
        except (ApprovalRuntimeConflict, ApprovalRuntimeViolation) as exc:
            raise AgentRequestConflict(str(exc), reason_code=exc.reason_code) from exc
        except AgentPersistenceError as exc:
            if exc.reason_code == "agent_approval_missing":
                raise AgentResourceNotFound(
                    str(exc), reason_code=exc.reason_code
                ) from exc
            _raise_persistence(exc)
        return _approval_view(approval)


__all__ = [
    "DisabledAgentRuntime",
    "PersistedAgentRuntime",
    "PersistedAgentRuntimeOptions",
]
