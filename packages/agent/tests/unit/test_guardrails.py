from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.port import ModelToolKind, ModelToolSpec
from ditto_agent.runtime.budgets import BudgetLedger, BudgetLimits, ModelPricing
from ditto_agent.runtime.egress_policy import (
    EvidenceEgressPolicy,
    EvidenceEgressPolicyError,
)
from ditto_agent.runtime.guardrails import (
    GuardedEvidenceToolExecutor,
    ToolGuardrailViolation,
)
from ditto_agent.tools.registry import EvidenceToolRegistry


class _Clock:
    def __call__(self) -> float:
        return 10.0


def _context(
    *, egress_class: EgressClass = EgressClass.CLOUD_ALLOWED
) -> TemporalToolContext:
    return TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=datetime(2026, 8, 16, 7, tzinfo=UTC),
            knowledge_cutoff=datetime(2026, 8, 16, 6, 55, tzinfo=UTC),
            publication_cutoff=datetime(2026, 8, 16, 6, 50, tzinfo=UTC),
            source_snapshot_id="snapshot-1",
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH",),
            license_class="approved-research",
            egress_class=egress_class,
        )
    )


class _EvidenceTool:
    spec = ModelToolSpec(
        kind=ModelToolKind.FUNCTION,
        name="research_experiment_evidence",
        description="Read an experiment.",
        input_schema={
            "type": "object",
            "properties": {"experiment_id": {"type": "string"}},
            "required": ["experiment_id"],
            "additionalProperties": False,
        },
        requires_approval=False,
    )

    def __init__(self) -> None:
        self.invocations = 0

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        self.invocations += 1
        return EvidenceEnvelope.seal(
            evidence_id=f"evidence-{arguments['experiment_id']}",
            tool_name=self.spec.name,
            result={"status": "completed"},
            artifact_refs=("experiment:001:sha256:" + "a" * 64,),
            temporal_context=context,
            lineage=("experiment:001",),
        )


def _budget() -> BudgetLedger:
    return BudgetLedger(
        limits=BudgetLimits(
            max_turns=4,
            max_model_tokens=1_000,
            max_model_spend_usd=Decimal("0.10"),
            max_wall_time_seconds=30,
            max_retries=1,
        ),
        pricing=ModelPricing(
            input_usd_per_million=Decimal("1"),
            output_usd_per_million=Decimal("1"),
        ),
        monotonic=_Clock(),
    )


def _executor(
    tool: _EvidenceTool,
    *,
    context: TemporalToolContext | None = None,
    policy: EvidenceEgressPolicy | None = None,
) -> GuardedEvidenceToolExecutor:
    return GuardedEvidenceToolExecutor(
        registry=EvidenceToolRegistry(tools=(tool,)),
        context=context or _context(),
        authority_hash="a" * 64,
        allowed_tools=(tool.spec.name,),
        egress_policy=policy
        or EvidenceEgressPolicy(approved_license_classes=("approved-research",)),
        budget=_budget(),
    )


@pytest.mark.asyncio
async def test_guardrail_validates_authority_context_and_returns_sealed_payload() -> (
    None
):
    tool = _EvidenceTool()
    context = _context()
    executor = _executor(tool, context=context)
    executor.validate_run(
        authority_hash="a" * 64,
        context=context,
        tool_schema_hash=executor.tool_schema_hash,
    )

    payload = await executor.invoke(
        tool.spec.name,
        '{"experiment_id":"experiment-001"}',
        call_id="call-001",
    )

    assert payload["evidence_id"] == "evidence-experiment-001"
    assert payload["temporal_context_hash"] == executor.temporal_context_hash
    assert len(executor.executions) == 1
    assert executor.executions[0].call_id == "call-001"
    assert executor.executions[0].evidence.verify_integrity()
    assert tool.invocations == 1


@pytest.mark.pit
def test_guardrail_rejects_authority_context_or_tool_schema_drift() -> None:
    executor = _executor(_EvidenceTool())

    for values, reason in (
        (
            {
                "authority_hash": "b" * 64,
                "context": _context(),
                "tool_schema_hash": executor.tool_schema_hash,
            },
            "authority_mismatch",
        ),
        (
            {
                "authority_hash": "a" * 64,
                "context": _context(egress_class=EgressClass.LOCAL_ONLY),
                "tool_schema_hash": executor.tool_schema_hash,
            },
            "temporal_context_mismatch",
        ),
        (
            {
                "authority_hash": "a" * 64,
                "context": _context(),
                "tool_schema_hash": "b" * 64,
            },
            "tool_schema_mismatch",
        ),
    ):
        with pytest.raises(ToolGuardrailViolation) as error:
            executor.validate_run(**values)
        assert error.value.reason_code == reason


@pytest.mark.asyncio
async def test_context_override_and_duplicate_call_fail_before_dispatch() -> None:
    tool = _EvidenceTool()
    executor = _executor(tool)

    with pytest.raises(ToolGuardrailViolation) as wrong_tool:
        await executor.invoke("publish_strategy", "{}", call_id="call-001")
    with pytest.raises(ToolGuardrailViolation) as override:
        await executor.invoke(
            tool.spec.name,
            '{"experiment_id":"experiment-001","source_snapshot_id":"future"}',
            call_id="call-002",
        )

    await executor.invoke(
        tool.spec.name,
        '{"experiment_id":"experiment-001"}',
        call_id="call-003",
    )
    with pytest.raises(ToolGuardrailViolation) as duplicate:
        await executor.invoke(
            tool.spec.name,
            '{"experiment_id":"experiment-001"}',
            call_id="call-003",
        )

    assert wrong_tool.value.reason_code == "tool_not_allowed"
    assert override.value.reason_code == "trusted_context_override"
    assert duplicate.value.reason_code == "duplicate_tool_call_id"
    assert tool.invocations == 1


@pytest.mark.asyncio
async def test_egress_failure_never_returns_or_records_model_evidence() -> None:
    tool = _EvidenceTool()
    executor = _executor(
        tool,
        context=_context(egress_class=EgressClass.LOCAL_ONLY),
    )

    with pytest.raises(EvidenceEgressPolicyError):
        await executor.invoke(
            tool.spec.name,
            '{"experiment_id":"experiment-001"}',
            call_id="call-001",
        )

    assert executor.executions == ()
    assert tool.invocations == 1
