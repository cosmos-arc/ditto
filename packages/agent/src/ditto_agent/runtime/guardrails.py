"""Host-owned guardrails around every model-requested evidence tool call."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

import orjson

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.models.port import ModelToolCall, ModelToolSpec
from ditto_agent.runtime.budgets import BudgetLedger
from ditto_agent.runtime.egress_policy import EvidenceEgressPolicy, ModelEvidencePayload
from ditto_agent.tools.registry import EvidenceToolRegistry, ToolNotAllowedError

_TRUSTED_CONTEXT_FIELDS = frozenset(
    {
        "decision_time",
        "knowledge_cutoff",
        "publication_cutoff",
        "source_snapshot_id",
        "execution_eligible_at",
        "allowed_universe",
        "license_class",
        "egress_class",
        "temporal_context",
        "authority_hash",
    }
)


class ToolGuardrailViolation(PermissionError):
    """A model intent failed deterministic host admission."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True, slots=True)
class GuardedToolExecution:
    """One admitted, executed, egress-checked tool result."""

    call_id: str
    tool_name: str
    arguments_hash: str
    evidence: EvidenceEnvelope
    model_payload: Mapping[str, object]


def _model_payload(payload: ModelEvidencePayload) -> Mapping[str, object]:
    return MappingProxyType(
        {
            "evidence_id": payload.evidence_id,
            "tool_name": payload.tool_name,
            "result": payload.result,
            "artifact_refs": payload.artifact_refs,
            "lineage": payload.lineage,
            "temporal_context_hash": payload.temporal_context_hash,
            "integrity_hash": payload.integrity_hash,
            "payload_hash": payload.payload_hash,
        }
    )


class GuardedEvidenceToolExecutor:
    """Bind an exact read-only allowlist to trusted authority and PIT context."""

    def __init__(
        self,
        *,
        registry: EvidenceToolRegistry,
        context: TemporalToolContext,
        authority_hash: str,
        allowed_tools: tuple[str, ...],
        egress_policy: EvidenceEgressPolicy,
        budget: BudgetLedger,
    ) -> None:
        self._registry = registry.restrict(allowed_tools)
        self._context = context
        self._authority_hash = authority_hash
        self._egress_policy = egress_policy
        self._budget = budget
        self._specs = self._registry.specs
        self._tool_schema_hash = canonical_sha256(
            tuple(
                {
                    "kind": spec.kind,
                    "name": spec.name,
                    "description": spec.description,
                    "input_schema": spec.input_schema,
                    "requires_approval": spec.requires_approval,
                }
                for spec in self._specs
            )
        )
        self._temporal_context_hash = canonical_sha256(context.canonical_payload())
        self._executions: list[GuardedToolExecution] = []
        self._call_ids: set[str] = set()

    @property
    def specs(self) -> tuple[ModelToolSpec, ...]:
        """Return the exact tool schemas admitted for this run."""
        return self._specs

    @property
    def tool_schema_hash(self) -> str:
        """Return the canonical hash of the admitted schema set."""
        return self._tool_schema_hash

    @property
    def temporal_context_hash(self) -> str:
        """Return the canonical hash of the trusted host PIT context."""
        return self._temporal_context_hash

    @property
    def executions(self) -> tuple[GuardedToolExecution, ...]:
        """Return only successfully egress-checked executions."""
        return tuple(self._executions)

    def validate_run(
        self,
        *,
        authority_hash: str,
        context: TemporalToolContext,
        tool_schema_hash: str,
    ) -> None:
        """Fail closed if any host-bound run identity drifted."""
        if authority_hash != self._authority_hash:
            raise ToolGuardrailViolation("authority_mismatch")
        if canonical_sha256(context.canonical_payload()) != self._temporal_context_hash:
            raise ToolGuardrailViolation("temporal_context_mismatch")
        if tool_schema_hash != self._tool_schema_hash:
            raise ToolGuardrailViolation("tool_schema_mismatch")

    @staticmethod
    def _arguments(arguments_json: str) -> Mapping[str, object]:
        try:
            decoded: object = orjson.loads(arguments_json)
        except orjson.JSONDecodeError as exc:
            raise ToolGuardrailViolation("tool_arguments_invalid") from exc
        if not isinstance(decoded, dict):
            raise ToolGuardrailViolation("tool_arguments_invalid")
        raw = cast(dict[object, object], decoded)
        if not all(isinstance(key, str) for key in raw):
            raise ToolGuardrailViolation("tool_arguments_invalid")
        return cast(dict[str, object], raw)

    async def invoke(
        self,
        tool_name: str,
        arguments_json: str,
        *,
        call_id: str,
    ) -> Mapping[str, object]:
        """Execute one admitted intent with host context and minimal egress."""
        if tool_name not in {spec.name for spec in self._specs}:
            raise ToolGuardrailViolation("tool_not_allowed")
        if call_id in self._call_ids:
            raise ToolGuardrailViolation("duplicate_tool_call_id")
        arguments = self._arguments(arguments_json)
        if _TRUSTED_CONTEXT_FIELDS.intersection(arguments):
            raise ToolGuardrailViolation("trusted_context_override")
        self._budget.before_tool_call()
        call = ModelToolCall(
            call_id=call_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        try:
            evidence = self._registry.execute(call=call, context=self._context)
        except ToolNotAllowedError as exc:
            raise ToolGuardrailViolation("tool_not_allowed") from exc
        projected = self._egress_policy.prepare_for_model(
            (evidence,),
            context=self._context,
        )[0]
        payload = _model_payload(projected)
        self._call_ids.add(call_id)
        self._executions.append(
            GuardedToolExecution(
                call_id=call_id,
                tool_name=tool_name,
                arguments_hash=canonical_sha256(arguments),
                evidence=evidence,
                model_payload=payload,
            )
        )
        return payload


__all__ = [
    "GuardedEvidenceToolExecutor",
    "GuardedToolExecution",
    "ToolGuardrailViolation",
]
