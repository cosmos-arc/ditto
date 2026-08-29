"""Durable, hash-bound HITL interruption and same-run recovery."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol

from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.approval_authorization import (
    ApprovalAuthorizationDependencies,
    AuthorizedToolApproval,
    authorize_tool_execution,
)
from ditto_agent.approval_codec import (
    MAX_CONTINUATION_BYTES,
    InterruptionBinding,
    ModelRequestIdentity,
    ResumeEnvelope,
    decode_action_payload,
    decode_envelope,
    reject_sensitive_keys,
)
from ditto_agent.approval_errors import (
    ApprovalRuntimeConflict,
    ApprovalRuntimeError,
    ApprovalRuntimeUnavailable,
    ApprovalRuntimeViolation,
)
from ditto_agent.contracts.approval import ApprovalAction, ApprovalRequest
from ditto_agent.contracts.runtime import RunStatus
from ditto_agent.models.port import (
    AgentModelPort,
    ApprovalDecision,
    ModelInterruption,
    ModelProviderError,
    ModelRequest,
    ModelResult,
    ModelToolSpec,
    ResumeModelRequest,
)
from ditto_agent.storage.sqlite.approval_batch_writer import ApprovalBatchWrite
from ditto_agent.storage.sqlite.errors import AgentPersistenceError
from ditto_agent.storage.sqlite.reader import AgentStoreReader
from ditto_agent.storage.sqlite.records import (
    ApprovalStatus,
    LeaseFence,
    StoredAgentRun,
    StoredApproval,
)
from ditto_agent.storage.sqlite.writer import AgentStoreWriter

_RESUME_LEASE_KIND = "agent_approval_resume"


class ApprovalActionResolver(Protocol):
    """Recompute one proposed action from current host-owned authority state."""

    def resolve(
        self,
        *,
        run_id: str,
        interruption: ModelInterruption,
        expires_at: datetime,
    ) -> ApprovalAction:
        """Return the complete current action for an exact interruption."""
        ...


ModelRequestResolver = Callable[[str], ModelRequest | None]


@dataclass(frozen=True, slots=True)
class ApprovalBatch:
    """New immutable approvals bound to one persisted provider continuation."""

    run_id: str
    approvals: tuple[ApprovalRequest, ...]
    continuation_hash: str


@dataclass(frozen=True, slots=True)
class ApprovalResumeOutcome:
    """Decision receipt and whether this caller won the single resume lease."""

    approval: StoredApproval
    resumed: bool
    result: ModelResult | None


@dataclass(frozen=True, slots=True)
class ApprovalRuntimeSettings:
    """Bounded approval expiry and single-resumer lease configuration."""

    approval_ttl: timedelta
    resume_lease_ttl: timedelta
    provider_timeout: timedelta = timedelta(seconds=30)

    def __post_init__(self) -> None:
        """Reject zero or negative expiry and lease windows."""
        if self.approval_ttl <= timedelta(0):
            raise ValueError("approval_ttl must be positive")
        if self.resume_lease_ttl <= timedelta(0):
            raise ValueError("resume_lease_ttl must be positive")
        if self.provider_timeout <= timedelta(0):
            raise ValueError("provider_timeout must be positive")
        if self.provider_timeout >= self.resume_lease_ttl:
            raise ValueError("provider_timeout must be shorter than resume_lease_ttl")


@dataclass(frozen=True, slots=True)
class _ReadyResume:
    envelope: ResumeEnvelope
    continuation_hash: str
    request: ModelRequest
    decisions: tuple[ApprovalDecision, ...]


class AgentApprovalRuntime:
    """Persist, decide, revalidate, and single-resume HITL interruptions."""

    def __init__(
        self,
        *,
        reader: AgentStoreReader,
        writer: AgentStoreWriter,
        model: AgentModelPort,
        request_resolver: ModelRequestResolver,
        action_resolver: ApprovalActionResolver,
        clock: Callable[[], datetime],
        settings: ApprovalRuntimeSettings,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._model = model
        self._request_resolver = request_resolver
        self._action_resolver = action_resolver
        self._clock = clock
        self._settings = settings

    @staticmethod
    def _validate_action(
        *,
        run_authority_hash: str,
        interruption: ModelInterruption,
        action: ApprovalAction,
        max_model_tokens: int,
        max_model_spend_usd: Decimal,
    ) -> None:
        if action.tool_name != interruption.tool_name:
            raise ApprovalRuntimeViolation(
                "approval action tool does not match the interruption",
                reason_code="agent_approval_action_mismatch",
            )
        if canonical_sha256(action.parameters) != canonical_sha256(
            interruption.arguments
        ):
            raise ApprovalRuntimeViolation(
                "approval action arguments do not match the interruption",
                reason_code="agent_approval_arguments_mismatch",
            )
        if action.authority_hash != run_authority_hash:
            raise ApprovalRuntimeViolation(
                "approval action authority does not match the run",
                reason_code="agent_approval_authority_mismatch",
            )
        if action.budget.max_model_tokens > max_model_tokens or (
            action.budget.max_model_spend_usd > max_model_spend_usd
        ):
            raise ApprovalRuntimeViolation(
                "approval action budget exceeds the run budget",
                reason_code="agent_approval_budget_exceeded",
            )

    @staticmethod
    def _request_id(
        *, run_id: str, interruption: ModelInterruption, action: ApprovalAction
    ) -> str:
        identity = canonical_sha256(
            {
                "run_id": run_id,
                "call_id": interruption.call_id,
                "action": action.canonical_payload(),
            }
        )
        return f"approval-{identity}"

    def suspend(
        self,
        *,
        request: ModelRequest,
        result: ModelResult,
        _expected_previous_continuation_hash: str | None = None,
    ) -> ApprovalBatch:
        """Persist one interruption batch before returning control to a human."""
        try:
            return self._suspend(
                request=request,
                result=result,
                expected_previous_continuation_hash=(
                    _expected_previous_continuation_hash
                ),
            )
        except AgentPersistenceError as exc:
            raise ApprovalRuntimeUnavailable(
                "approval suspension storage is unavailable",
                reason_code=exc.reason_code,
            ) from exc

    def _suspend(
        self,
        *,
        request: ModelRequest,
        result: ModelResult,
        expected_previous_continuation_hash: str | None,
    ) -> ApprovalBatch:
        if not result.interruptions or result.continuation is None:
            raise ValueError("suspension requires interruptions and continuation")
        run = self._reader.get_run(request.run_id)
        if run is None:
            raise ApprovalRuntimeConflict(
                "approval run does not exist",
                reason_code="agent_run_missing",
            )
        if run.status is not RunStatus.RUNNING:
            raise ApprovalRuntimeConflict(
                "approval suspension requires a running run",
                reason_code="agent_run_state_conflict",
            )
        tools = {tool.name: tool for tool in request.tools}
        now = self._clock()
        expires_at = now + self._settings.approval_ttl
        approvals: list[ApprovalRequest] = []
        bindings: list[InterruptionBinding] = []
        for interruption in result.interruptions:
            tool = tools.get(interruption.tool_name)
            if tool is None or not tool.requires_approval:
                raise ApprovalRuntimeViolation(
                    "interrupted tool is not registered for approval",
                    reason_code="agent_approval_tool_not_allowed",
                )
            action = self._action_resolver.resolve(
                run_id=request.run_id,
                interruption=interruption,
                expires_at=expires_at,
            )
            self._validate_action(
                run_authority_hash=run.authority_hash,
                interruption=interruption,
                action=action,
                max_model_tokens=run.max_model_tokens,
                max_model_spend_usd=run.max_model_spend_usd,
            )
            approval = ApprovalRequest.issue(
                request_id=self._request_id(
                    run_id=request.run_id,
                    interruption=interruption,
                    action=action,
                ),
                run_id=request.run_id,
                action=action,
            )
            approvals.append(approval)
            bindings.append(
                InterruptionBinding(
                    call_id=interruption.call_id,
                    tool_name=interruption.tool_name,
                    arguments_hash=canonical_sha256(interruption.arguments),
                    request_id=approval.request_id,
                    action_hash=approval.action_hash,
                )
            )
        reject_sensitive_keys(result.continuation.payload)
        envelope = ResumeEnvelope(
            run_id=request.run_id,
            request_identity=ModelRequestIdentity.from_request(request),
            continuation=result.continuation,
            interruptions=tuple(bindings),
        )
        payload = canonical_bytes(envelope.payload())
        if len(payload) > MAX_CONTINUATION_BYTES:
            raise ApprovalRuntimeViolation(
                "continuation exceeds the approved storage bound",
                reason_code="agent_continuation_too_large",
            )
        payload_hash = hashlib.sha256(payload).hexdigest()
        self._writer.store_approval_batch(
            ApprovalBatchWrite(
                requests=tuple(approvals),
                provider=result.continuation.provider,
                continuation_payload=payload,
                continuation_hash=payload_hash,
                expected_run_revision=run.revision,
                expected_previous_continuation_hash=(
                    expected_previous_continuation_hash
                ),
                occurred_at=now,
                event_payload_hash=canonical_sha256(
                    {
                        "run_id": request.run_id,
                        "approval_ids": tuple(item.request_id for item in approvals),
                        "action_hashes": tuple(item.action_hash for item in approvals),
                        "continuation_hash": payload_hash,
                    }
                ),
            )
        )
        return ApprovalBatch(
            run_id=request.run_id,
            approvals=tuple(approvals),
            continuation_hash=payload_hash,
        )

    def _load_envelope(self, run_id: str) -> tuple[ResumeEnvelope, str]:
        stored = self._reader.get_continuation(run_id)
        if stored is None:
            raise ApprovalRuntimeConflict(
                "approval continuation is missing",
                reason_code="agent_continuation_missing",
            )
        actual_hash = hashlib.sha256(stored.payload_json).hexdigest()
        if actual_hash != stored.payload_hash:
            raise ApprovalRuntimeViolation(
                "approval continuation hash is invalid",
                reason_code="agent_continuation_hash_mismatch",
            )
        envelope = decode_envelope(stored.payload_json)
        if envelope.run_id != run_id or envelope.request_identity.run_id != run_id:
            raise ApprovalRuntimeViolation(
                "approval continuation belongs to a different run",
                reason_code="agent_continuation_run_mismatch",
            )
        if envelope.continuation.provider != stored.provider:
            raise ApprovalRuntimeViolation(
                "approval continuation provider identity changed",
                reason_code="agent_continuation_provider_mismatch",
            )
        return envelope, stored.payload_hash

    def _resolve_request(
        self, run_id: str, expected: ModelRequestIdentity
    ) -> ModelRequest:
        request = self._request_resolver(run_id)
        if request is None or request.run_id != run_id:
            raise ApprovalRuntimeConflict(
                "current model request for the approval run is unavailable",
                reason_code="agent_resume_request_missing",
            )
        if ModelRequestIdentity.from_request(request) != expected:
            raise ApprovalRuntimeConflict(
                "current model request does not match persisted resume identity",
                reason_code="agent_resume_request_mismatch",
            )
        return request

    def _validated_decision(
        self,
        *,
        run_id: str,
        run: StoredAgentRun,
        binding: InterruptionBinding,
        tools: Mapping[str, ModelToolSpec],
        now: datetime,
    ) -> ApprovalDecision | None:
        stored = self._reader.get_approval(binding.request_id)
        if stored is None:
            raise ApprovalRuntimeViolation(
                "approval bound to continuation is missing",
                reason_code="agent_approval_missing",
            )
        if stored.run_id != run_id or stored.action_hash != binding.action_hash:
            raise ApprovalRuntimeViolation(
                "approval identity does not match its continuation binding",
                reason_code="agent_approval_binding_mismatch",
            )
        restored = decode_action_payload(stored.action_payload)
        if (
            restored.request_id != stored.request_id
            or restored.run_id != stored.run_id
            or restored.action_hash != stored.action_hash
        ):
            raise ApprovalRuntimeViolation(
                "approval action hash does not match durable state",
                reason_code="agent_approval_hash_mismatch",
            )
        if restored.tool_name != binding.tool_name or (
            canonical_sha256(restored.parameters) != binding.arguments_hash
        ):
            raise ApprovalRuntimeViolation(
                "approval arguments do not match the provider interruption",
                reason_code="agent_approval_arguments_mismatch",
            )
        tool = tools.get(binding.tool_name)
        if tool is None or not tool.requires_approval:
            raise ApprovalRuntimeViolation(
                "approved tool is no longer registered for approval",
                reason_code="agent_approval_tool_not_allowed",
            )
        interruption = ModelInterruption(
            call_id=binding.call_id,
            tool_name=binding.tool_name,
            arguments=restored.parameters,
        )
        current_action = self._action_resolver.resolve(
            run_id=run_id,
            interruption=interruption,
            expires_at=restored.expires_at,
        )
        self._validate_action(
            run_authority_hash=run.authority_hash,
            interruption=interruption,
            action=current_action,
            max_model_tokens=run.max_model_tokens,
            max_model_spend_usd=run.max_model_spend_usd,
        )
        current = ApprovalRequest.issue(
            request_id=restored.request_id,
            run_id=restored.run_id,
            action=current_action,
        )
        if current.action_hash != stored.action_hash:
            raise ApprovalRuntimeViolation(
                "approval action no longer matches current host authority",
                reason_code="agent_approval_action_changed",
            )
        if now >= restored.expires_at:
            raise ApprovalRuntimeViolation(
                "approval action expired before provider resume",
                reason_code="agent_approval_expired",
            )
        if stored.status is ApprovalStatus.PENDING:
            return None
        approved = stored.status is ApprovalStatus.APPROVED
        return ApprovalDecision(
            call_id=binding.call_id,
            approved=approved,
            rejection_message=(
                None if approved else "Rejected by the authorized Ditto operator."
            ),
        )

    def _validated_decisions(
        self,
        *,
        run_id: str,
        envelope: ResumeEnvelope,
        request: ModelRequest,
        now: datetime,
    ) -> tuple[ApprovalDecision, ...] | None:
        run = self._reader.get_run(run_id)
        if run is None:
            raise ApprovalRuntimeConflict(
                "approval run does not exist",
                reason_code="agent_run_missing",
            )
        tools = {tool.name: tool for tool in request.tools}
        decisions = tuple(
            self._validated_decision(
                run_id=run_id,
                run=run,
                binding=binding,
                tools=tools,
                now=now,
            )
            for binding in envelope.interruptions
        )
        if any(decision is None for decision in decisions):
            return None
        return tuple(decision for decision in decisions if decision is not None)

    def authorize_tool_execution(
        self,
        *,
        run_id: str,
        call_id: str,
        tool_name: str,
        arguments: Mapping[str, object],
    ) -> AuthorizedToolApproval:
        """Revalidate one approved action immediately before its side effect."""
        return authorize_tool_execution(
            dependencies=ApprovalAuthorizationDependencies(
                reader=self._reader,
                load_envelope=self._load_envelope,
                resolve_request=self._resolve_request,
                validate_decision=self._validated_decision,
                clock=self._clock,
            ),
            run_id=run_id,
            call_id=call_id,
            tool_name=tool_name,
            arguments=arguments,
        )

    def _ready_resume(self, run_id: str) -> _ReadyResume | None:
        envelope, continuation_hash = self._load_envelope(run_id)
        request = self._resolve_request(run_id, envelope.request_identity)
        decisions = self._validated_decisions(
            run_id=run_id,
            envelope=envelope,
            request=request,
            now=self._clock(),
        )
        if decisions is None:
            return None
        return _ReadyResume(
            envelope=envelope,
            continuation_hash=continuation_hash,
            request=request,
            decisions=decisions,
        )

    def _active_resume(self, run_id: str) -> _ReadyResume | None:
        """Return resumable state, treating consumed completed state as idempotent."""
        try:
            return self._ready_resume(run_id)
        except ApprovalRuntimeConflict as exc:
            run = self._reader.get_run(run_id)
            if (
                exc.reason_code == "agent_continuation_missing"
                and run is not None
                and run.status is RunStatus.COMPLETED
            ):
                return None
            raise

    def _preflight_decision(
        self,
        *,
        request_id: str,
        expected_action_hash: str,
        now: datetime,
    ) -> None:
        """Revalidate current host authority before making a decision terminal."""
        stored = self._reader.get_approval(request_id)
        if (
            stored is None
            or stored.action_hash != expected_action_hash
            or stored.status is not ApprovalStatus.PENDING
            or now >= stored.expires_at
        ):
            return
        envelope, _continuation_hash = self._load_envelope(stored.run_id)
        binding = next(
            (item for item in envelope.interruptions if item.request_id == request_id),
            None,
        )
        if binding is None:
            raise ApprovalRuntimeViolation(
                "approval is not bound to the active provider continuation",
                reason_code="agent_approval_binding_mismatch",
            )
        request = self._resolve_request(stored.run_id, envelope.request_identity)
        run = self._reader.get_run(stored.run_id)
        if run is None:
            raise ApprovalRuntimeConflict(
                "approval run does not exist",
                reason_code="agent_run_missing",
            )
        decision = self._validated_decision(
            run_id=stored.run_id,
            run=run,
            binding=binding,
            tools={tool.name: tool for tool in request.tools},
            now=now,
        )
        if decision is not None:
            raise ApprovalRuntimeConflict(
                "approval already has a terminal decision",
                reason_code="agent_approval_already_decided",
            )

    def _acquire_resume_lease(self, *, run_id: str, now: datetime) -> LeaseFence | None:
        owner_token = f"approval-resume-{uuid.uuid4().hex}"
        try:
            return self._writer.try_acquire_lease(
                resource_kind=_RESUME_LEASE_KIND,
                resource_id=run_id,
                owner_token=owner_token,
                now=now,
                lease_until=now + self._settings.resume_lease_ttl,
            )
        except AgentPersistenceError as exc:
            raise ApprovalRuntimeUnavailable(
                "approval resume storage is unavailable",
                reason_code=exc.reason_code,
            ) from exc

    def _transition_resume_started(self, ready: _ReadyResume) -> StoredAgentRun:
        run_id = ready.envelope.run_id
        run = self._reader.get_run(run_id)
        if run is None:
            raise ApprovalRuntimeConflict(
                "approval run does not exist",
                reason_code="agent_run_missing",
            )
        if run.status in {RunStatus.WAITING_APPROVAL, RunStatus.PAUSED}:
            return self._writer.transition_run(
                run_id=run_id,
                expected_revision=run.revision,
                target=RunStatus.RUNNING,
                occurred_at=self._clock(),
                event_type="approval_resume_started",
                event_payload_hash=canonical_sha256(
                    {
                        "run_id": run_id,
                        "continuation_hash": ready.continuation_hash,
                        "decisions": tuple(
                            {
                                "call_id": item.call_id,
                                "approved": item.approved,
                            }
                            for item in ready.decisions
                        ),
                    }
                ),
            )
        if run.status is not RunStatus.RUNNING:
            raise ApprovalRuntimeConflict(
                "approval run is not resumable",
                reason_code="agent_run_state_conflict",
            )
        return run

    def _pause_provider_failure(self, ready: _ReadyResume) -> None:
        run_id = ready.envelope.run_id
        current = self._reader.get_run(run_id)
        if current is None or current.status is not RunStatus.RUNNING:
            return
        self._writer.transition_run(
            run_id=run_id,
            expected_revision=current.revision,
            target=RunStatus.PAUSED,
            occurred_at=self._clock(),
            event_type="approval_resume_paused",
            event_payload_hash=canonical_sha256(
                {
                    "run_id": run_id,
                    "continuation_hash": ready.continuation_hash,
                    "reason": "model_provider_failed",
                }
            ),
        )

    async def _invoke_resume(self, ready: _ReadyResume) -> ModelResult:
        try:
            async with asyncio.timeout(self._settings.provider_timeout.total_seconds()):
                return await self._model.resume(
                    ResumeModelRequest(
                        request=ready.request,
                        continuation=ready.envelope.continuation,
                        decisions=ready.decisions,
                    )
                )
        except (TimeoutError, ModelProviderError) as exc:
            self._pause_provider_failure(ready)
            raise ApprovalRuntimeUnavailable(
                "approval provider resume failed",
                reason_code="agent_resume_provider_failed",
            ) from exc

    def _persist_resume_result(
        self, *, ready: _ReadyResume, result: ModelResult
    ) -> None:
        run_id = ready.envelope.run_id
        if result.interruptions:
            self.suspend(
                request=ready.request,
                result=result,
                _expected_previous_continuation_hash=ready.continuation_hash,
            )
            return
        current = self._reader.get_run(run_id)
        if current is None or current.status is not RunStatus.RUNNING:
            raise ApprovalRuntimeConflict(
                "resumed run lost its running state",
                reason_code="agent_run_state_conflict",
            )
        self._writer.complete_approval_resume(
            run_id=run_id,
            expected_run_revision=current.revision,
            expected_continuation_hash=ready.continuation_hash,
            occurred_at=self._clock(),
            event_payload_hash=canonical_sha256(
                {
                    "run_id": run_id,
                    "continuation_hash": ready.continuation_hash,
                    "final_output_hash": canonical_sha256(result.final_output),
                    "tool_calls": tuple(
                        {
                            "call_id": item.call_id,
                            "tool_name": item.tool_name,
                            "arguments_hash": canonical_sha256(item.arguments),
                        }
                        for item in result.tool_calls
                    ),
                    "usage": result.usage,
                }
            ),
        )

    async def _resume_with_lease(
        self, *, initial: _ReadyResume, lease: LeaseFence
    ) -> tuple[bool, ModelResult | None]:
        run_id = initial.envelope.run_id
        try:
            ready = self._active_resume(run_id)
            if ready is None:
                return False, None
            if ready.continuation_hash != initial.continuation_hash:
                raise ApprovalRuntimeViolation(
                    "approval continuation changed before resume",
                    reason_code="agent_continuation_hash_mismatch",
                )
            self._transition_resume_started(ready)
            result = await self._invoke_resume(ready)
            self._persist_resume_result(ready=ready, result=result)
            return True, result
        finally:
            try:
                self._writer.release_lease(lease, released_at=self._clock())
            except AgentPersistenceError:
                # Lease expiry remains a fail-safe recovery path; it cannot grant
                # tool authority or mutate an already authenticated decision.
                pass

    async def _try_resume(
        self,
        *,
        run_id: str,
    ) -> tuple[bool, ModelResult | None]:
        ready = self._active_resume(run_id)
        if ready is None:
            return False, None
        now = self._clock()
        lease = self._acquire_resume_lease(run_id=run_id, now=now)
        if lease is None:
            return False, None
        return await self._resume_with_lease(initial=ready, lease=lease)

    async def decide_and_resume(
        self,
        *,
        request_id: str,
        expected_action_hash: str,
        approved: bool,
        operator_id: str,
        reason: str | None,
    ) -> ApprovalResumeOutcome:
        """Append one decision and resume only when its entire batch is terminal."""
        decided_at = self._clock()
        self._preflight_decision(
            request_id=request_id,
            expected_action_hash=expected_action_hash,
            now=decided_at,
        )
        decided = self._writer.decide_approval(
            request_id=request_id,
            expected_action_hash=expected_action_hash,
            approved=approved,
            operator_id=operator_id,
            reason=reason,
            decided_at=decided_at,
        )
        resumed, result = await self._try_resume(run_id=decided.run_id)
        return ApprovalResumeOutcome(
            approval=decided,
            resumed=resumed,
            result=result,
        )

    async def resume_ready(self, run_id: str) -> bool:
        """Recover an already-decided batch after process restart or lease expiry."""
        resumed, _result = await self._try_resume(run_id=run_id)
        return resumed


__all__ = [
    "AgentApprovalRuntime",
    "ApprovalActionResolver",
    "ApprovalBatch",
    "ApprovalResumeOutcome",
    "ApprovalRuntimeConflict",
    "ApprovalRuntimeError",
    "ApprovalRuntimeSettings",
    "ApprovalRuntimeUnavailable",
    "ApprovalRuntimeViolation",
    "ModelRequestResolver",
]
