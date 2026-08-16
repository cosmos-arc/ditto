"""HITL-only Author tools delegating every mutation to application commands."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, cast

import orjson
from ditto_application.agent_authoring_contracts import (
    AUTHOR_SAVE_STRATEGY_DRAFT,
    AUTHOR_SUBMIT_STRATEGY_REVIEW,
    AgentAuthoringCommandPort,
    AgentAuthoringCommandReceipt,
    AgentSaveStrategyDraftCommand,
    AgentSubmitStrategyReviewCommand,
)

from ditto_agent._canonical import canonical_sha256
from ditto_agent.contracts._validation import normalized_text
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import TemporalToolContext
from ditto_agent.models.port import ModelToolSpec
from ditto_agent.tools._common import Arguments, approval_function_spec

AUTHOR_WRITE_TOOL_NAMES = frozenset(
    {AUTHOR_SAVE_STRATEGY_DRAFT, AUTHOR_SUBMIT_STRATEGY_REVIEW}
)
_TEXT = {"type": "string", "minLength": 1}
_HASH = {"type": "string", "pattern": "^[0-9a-f]{64}$"}
_POSITIVE_INTEGER = {"type": "integer", "minimum": 1}


@dataclass(frozen=True, slots=True)
class AuthorWriteExecutionContext:
    """Trusted provider call identity injected outside model arguments."""

    run_id: str
    episode_id: str
    call_id: str

    def __post_init__(self) -> None:
        """Normalize and bind the episode identity to its run."""
        for field_name in ("run_id", "episode_id", "call_id"):
            object.__setattr__(
                self,
                field_name,
                normalized_text(getattr(self, field_name), field=field_name),
            )
        if self.episode_id != f"episode-{self.run_id}":
            raise ValueError("episode_id must be bound to run_id")


def _seal_receipt(
    *,
    tool_name: str,
    receipt: AgentAuthoringCommandReceipt,
    context: TemporalToolContext,
) -> EvidenceEnvelope:
    if not receipt.verify_integrity():
        raise ValueError("application command receipt hash mismatch")
    payload = receipt.canonical_payload()
    result: Mapping[str, object] = {
        "schema_version": 1,
        "kind": "agent_authoring_command_receipt",
        "receipt_hash": receipt.receipt_hash,
        "receipt": payload,
    }
    evidence_hash = canonical_sha256(
        {
            "tool_name": tool_name,
            "receipt_hash": receipt.receipt_hash,
            "temporal_context": context.canonical_payload(),
        }
    )
    return EvidenceEnvelope.seal(
        evidence_id=f"evidence-{evidence_hash}",
        tool_name=tool_name,
        result=result,
        artifact_refs=(f"command-receipt:sha256:{receipt.receipt_hash}",),
        temporal_context=context,
        lineage=(
            f"agent-run:{receipt.run_id}",
            f"agent-episode:{receipt.episode_id}",
            receipt.audit_identity,
            f"application-command:{receipt.audit_event_id}",
        ),
    )


class AuthorSaveStrategyDraftTool:
    """Save one immutable strategy draft after exact per-action approval."""

    spec = approval_function_spec(
        name=AUTHOR_SAVE_STRATEGY_DRAFT,
        description="Save one validated StrategySpec draft; never publish it.",
        properties={
            "strategy_id": _TEXT,
            "name": _TEXT,
            "spec_json": {"type": "object"},
            "base_version": {"type": ["integer", "null"], "minimum": 1},
            "tags": {"type": "array", "items": _TEXT, "uniqueItems": True},
        },
        required=("strategy_id", "name", "spec_json", "base_version", "tags"),
    )

    def __init__(self, *, commands: AgentAuthoringCommandPort) -> None:
        self._commands = commands

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
        execution: AuthorWriteExecutionContext,
    ) -> EvidenceEnvelope:
        """Delegate one approved draft save to the application command."""
        parsed = Arguments(
            arguments,
            required=(
                "strategy_id",
                "name",
                "spec_json",
                "base_version",
                "tags",
            ),
        )
        receipt = self._commands.save_strategy_draft(
            AgentSaveStrategyDraftCommand(
                strategy_id=parsed.text("strategy_id"),
                name=parsed.text("name"),
                spec_json=parsed.mapping("spec_json"),
                base_version=parsed.nullable_positive_integer("base_version"),
                tags=parsed.text_tuple("tags"),
                run_id=execution.run_id,
                episode_id=execution.episode_id,
                call_id=execution.call_id,
            )
        )
        return _seal_receipt(tool_name=self.spec.name, receipt=receipt, context=context)


class AuthorSubmitStrategyReviewTool:
    """Submit one exact draft version to review without publish authority."""

    spec = approval_function_spec(
        name=AUTHOR_SUBMIT_STRATEGY_REVIEW,
        description="Submit one exact strategy draft and review bundle for review.",
        properties={
            "strategy_id": _TEXT,
            "version": _POSITIVE_INTEGER,
            "bundle_hash": _HASH,
            "reason": _TEXT,
        },
        required=("strategy_id", "version", "bundle_hash", "reason"),
    )

    def __init__(self, *, commands: AgentAuthoringCommandPort) -> None:
        self._commands = commands

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
        execution: AuthorWriteExecutionContext,
    ) -> EvidenceEnvelope:
        """Delegate one approved review submission to application."""
        parsed = Arguments(
            arguments,
            required=("strategy_id", "version", "bundle_hash", "reason"),
        )
        receipt = self._commands.submit_strategy_review(
            AgentSubmitStrategyReviewCommand(
                strategy_id=parsed.text("strategy_id"),
                version=parsed.positive_integer("version"),
                bundle_hash=parsed.text("bundle_hash"),
                reason=parsed.text("reason"),
                run_id=execution.run_id,
                episode_id=execution.episode_id,
                call_id=execution.call_id,
            )
        )
        return _seal_receipt(tool_name=self.spec.name, receipt=receipt, context=context)


class AuthorWriteFunctionTool(Protocol):
    """Structural contract for formal Author write tools."""

    @property
    def spec(self) -> ModelToolSpec:
        """Return the provider declaration that requires approval."""
        ...

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
        execution: AuthorWriteExecutionContext,
    ) -> EvidenceEnvelope:
        """Execute one tool using host-supplied context and call identity."""
        ...


class AuthorWriteToolRegistry:
    """Exact formal-write allowlist; excludes all publish and trading actions."""

    def __init__(self, *, tools: Iterable[AuthorWriteFunctionTool]) -> None:
        index: dict[str, AuthorWriteFunctionTool] = {}
        for tool in tools:
            if tool.spec.name in index:
                raise ValueError(f"duplicate tool name: {tool.spec.name}")
            if tool.spec.name not in AUTHOR_WRITE_TOOL_NAMES:
                raise ValueError(f"author write tool is not allowed: {tool.spec.name}")
            if not tool.spec.requires_approval:
                raise ValueError("author write tools must require approval")
            index[tool.spec.name] = tool
        self._tools = MappingProxyType(index)

    @property
    def tools(self) -> Mapping[str, AuthorWriteFunctionTool]:
        """Return the immutable exact write-tool index."""
        return self._tools

    @property
    def specs(self) -> tuple[ModelToolSpec, ...]:
        """Return provider specs in stable registration order."""
        return tuple(tool.spec for tool in self._tools.values())

    def execute(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
        execution: AuthorWriteExecutionContext,
    ) -> EvidenceEnvelope:
        """Execute one allowlisted write with trusted host identity."""
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ValueError(f"author write tool is not allowed: {tool_name}")
        return tool.invoke(arguments=arguments, context=context, execution=execution)


@dataclass(frozen=True, slots=True)
class AuthorWriteToolExecution:
    """One application-receipt-backed side-effect execution."""

    call_id: str
    tool_name: str
    arguments_hash: str
    evidence: EvidenceEnvelope


class AuthorWriteToolInvoker:
    """Provider callback bound to one run, context, and exact write allowlist."""

    def __init__(
        self,
        *,
        registry: AuthorWriteToolRegistry,
        context: TemporalToolContext,
        run_id: str,
    ) -> None:
        self._registry = registry
        self._context = context
        self._run_id = normalized_text(run_id, field="run_id")
        self._episode_id = f"episode-{self._run_id}"
        self._executions: list[AuthorWriteToolExecution] = []
        self._call_ids: set[str] = set()

    @property
    def specs(self) -> tuple[ModelToolSpec, ...]:
        """Return the exact HITL declarations visible to the provider."""
        return self._registry.specs

    @property
    def executions(self) -> tuple[AuthorWriteToolExecution, ...]:
        """Return successfully receipt-backed executions."""
        return tuple(self._executions)

    async def invoke(
        self,
        tool_name: str,
        arguments_json: str,
        *,
        call_id: str,
    ) -> object:
        """Parse provider JSON and execute one run-bound formal write."""
        call_id = normalized_text(call_id, field="call_id")
        if call_id in self._call_ids:
            raise ValueError("duplicate author write tool call id")
        try:
            decoded: object = orjson.loads(arguments_json)
        except orjson.JSONDecodeError as exc:
            raise ValueError("author write arguments are not valid JSON") from exc
        if not isinstance(decoded, dict):
            raise ValueError("author write arguments must be an object")
        raw = cast("dict[object, object]", decoded)
        if not all(type(key) is str for key in raw):
            raise ValueError("author write arguments must have string keys")
        arguments = cast("dict[str, object]", raw)
        evidence = self._registry.execute(
            tool_name=tool_name,
            arguments=arguments,
            context=self._context,
            execution=AuthorWriteExecutionContext(
                run_id=self._run_id,
                episode_id=self._episode_id,
                call_id=call_id,
            ),
        )
        self._call_ids.add(call_id)
        self._executions.append(
            AuthorWriteToolExecution(
                call_id=call_id,
                tool_name=tool_name,
                arguments_hash=canonical_sha256(arguments),
                evidence=evidence,
            )
        )
        return {
            "evidence_id": evidence.evidence_id,
            "tool_name": evidence.tool_name,
            "result": evidence.result,
            "artifact_refs": evidence.artifact_refs,
            "lineage": evidence.lineage,
            "integrity_hash": evidence.integrity_hash,
        }


__all__ = [
    "AUTHOR_WRITE_TOOL_NAMES",
    "AuthorSaveStrategyDraftTool",
    "AuthorSubmitStrategyReviewTool",
    "AuthorWriteExecutionContext",
    "AuthorWriteFunctionTool",
    "AuthorWriteToolExecution",
    "AuthorWriteToolInvoker",
    "AuthorWriteToolRegistry",
]
