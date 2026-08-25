from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

import orjson
import pytest
from ditto_agent.evals.cases import EvalCase, load_eval_cases
from ditto_agent.evals.release import EvalCostBasis, ReleaseEvalRunIdentity
from ditto_agent.models.port import (
    AgentModelPort,
    ModelRequest,
    ModelResult,
    ModelStreamEvent,
    ModelToolCall,
    ModelToolInvoker,
    ModelUsage,
    ResumeModelRequest,
)
from ditto_apps.registry.agent import release_eval_provider
from ditto_apps.registry.agent.release_eval_provider import (
    GLMFormalEvalProvider,
    formal_prompt_tool_manifest_hash,
)

DATASETS = (
    Path(__file__).parents[5] / "agent" / "src" / "ditto_agent" / "evals" / "datasets"
)


def _identity() -> ReleaseEvalRunIdentity:
    return ReleaseEvalRunIdentity(
        provider_id="glm-formal-api-chat-completions-v1",
        profile="balanced",
        model_id="glm-5.2",
        model_snapshot="glm-5.2-approved-revision",
        reasoning_effort="high",
        prompt_tool_manifest_hash=formal_prompt_tool_manifest_hash(),
        a4_scope_hash="2" * 64,
        pricing_manifest_hash="3" * 64,
        pricing_as_of="1970-01-01",
        input_price_per_million_usd=Decimal(0),
        output_price_per_million_usd=Decimal(0),
        max_total_spend_usd=Decimal(0),
        max_total_tokens=10_000,
        cost_basis=EvalCostBasis.USAGE_CAP,
    )


class _CallingModel(AgentModelPort):
    def __init__(self, invoker: ModelToolInvoker, case: EvalCase) -> None:
        self._invoker = invoker
        self._case = case
        self.requests: list[ModelRequest] = []

    async def run(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        action = self._case.expected_actions[0]
        arguments_json = orjson.dumps({"case_id": self._case.case_id}).decode()
        tool_result = await self._invoker.invoke(
            action,
            arguments_json,
            call_id="call-live-001",
        )
        assert isinstance(tool_result, dict)
        fact_token = str(tool_result["fact_token"])
        evidence_ref = self._case.expected_evidence_refs[0]
        return ModelResult(
            final_output=(
                f"DITTO_DECISION=ANSWER fact={fact_token} evidence={evidence_ref}"
            ),
            tool_calls=(
                ModelToolCall(
                    call_id="call-live-001",
                    tool_name=action,
                    arguments={"case_id": self._case.case_id},
                ),
            ),
            usage=ModelUsage(requests=2, input_tokens=120, output_tokens=24),
            interruptions=(),
            continuation=None,
        )

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        del request
        raise AssertionError("stream is not used by release eval")

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        del request
        raise AssertionError("resume is not used by release eval")


class _UnreconciledModel(_CallingModel):
    async def run(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        action = self._case.expected_actions[0]
        return ModelResult(
            final_output="DITTO_DECISION=ANSWER",
            tool_calls=(
                ModelToolCall(
                    call_id="call-not-executed",
                    tool_name=action,
                    arguments={"case_id": self._case.case_id},
                ),
            ),
            usage=ModelUsage(requests=1, input_tokens=50, output_tokens=5),
            interruptions=(),
            continuation=None,
        )


class _NoToolModel(_CallingModel):
    async def run(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        return ModelResult(
            final_output=(
                "DITTO_DECISION=ANSWER " + " ".join(self._case.expected_evidence_refs)
            ),
            tool_calls=(),
            usage=ModelUsage(requests=1, input_tokens=80, output_tokens=12),
            interruptions=(),
            continuation=None,
        )


class _ReasoningUsageModel(_NoToolModel):
    async def run(self, request: ModelRequest) -> ModelResult:
        result = await super().run(request)
        return ModelResult(
            final_output=result.final_output,
            tool_calls=result.tool_calls,
            usage=ModelUsage(requests=1, input_tokens=80, output_tokens=1_224),
            interruptions=result.interruptions,
            continuation=result.continuation,
        )


class _NoCitationCallingModel(_CallingModel):
    async def run(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        action = self._case.expected_actions[0]
        arguments_json = orjson.dumps({"case_id": self._case.case_id}).decode()
        await self._invoker.invoke(
            action,
            arguments_json,
            call_id="call-host-render-001",
        )
        return ModelResult(
            final_output="DITTO_DECISION=ANSWER",
            tool_calls=(
                ModelToolCall(
                    call_id="call-host-render-001",
                    tool_name=action,
                    arguments={"case_id": self._case.case_id},
                ),
            ),
            usage=ModelUsage(requests=2, input_tokens=120, output_tokens=8),
            interruptions=(),
            continuation=None,
        )


class _AbstainingCallingModel(_CallingModel):
    async def run(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        action = self._case.expected_actions[0]
        arguments_json = orjson.dumps({"case_id": self._case.case_id}).decode()
        tool_result = await self._invoker.invoke(
            action,
            arguments_json,
            call_id="call-abstain-001",
        )
        assert isinstance(tool_result, dict)
        fact_token = str(tool_result["fact_token"])
        evidence_refs = " ".join(self._case.expected_evidence_refs)
        return ModelResult(
            final_output=(f"DITTO_DECISION=ABSTAIN fact={fact_token} {evidence_refs}"),
            tool_calls=(
                ModelToolCall(
                    call_id="call-abstain-001",
                    tool_name=action,
                    arguments={"case_id": self._case.case_id},
                ),
            ),
            usage=ModelUsage(requests=2, input_tokens=120, output_tokens=24),
            interruptions=(),
            continuation=None,
        )


class _WrongAllowedToolModel(_CallingModel):
    async def run(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        action = next(
            name
            for name in self._case.observation.allowed_actions
            if name not in self._case.expected_actions
        )
        arguments_json = orjson.dumps({"case_id": self._case.case_id}).decode()
        await self._invoker.invoke(
            action,
            arguments_json,
            call_id="call-wrong-001",
        )
        return ModelResult(
            final_output=(
                "DITTO_DECISION=ANSWER " + " ".join(self._case.expected_evidence_refs)
            ),
            tool_calls=(
                ModelToolCall(
                    call_id="call-wrong-001",
                    tool_name=action,
                    arguments={"case_id": self._case.case_id},
                ),
            ),
            usage=ModelUsage(requests=2, input_tokens=100, output_tokens=18),
            interruptions=(),
            continuation=None,
        )


@pytest.mark.asyncio
async def test_formal_provider_executes_host_tool_and_hashes_model_output() -> None:
    case = load_eval_cases(DATASETS / "grounded")[5]
    models: list[_CallingModel] = []

    def build_model(
        invoker: ModelToolInvoker,
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> AgentModelPort:
        assert identity.reasoning_effort == "high"
        assert api_key == "formal-secret"
        model = _CallingModel(invoker, case)
        models.append(model)
        return model

    provider = GLMFormalEvalProvider(
        run_identity=_identity(),
        api_key="formal-secret",
        model_builder=build_model,
        clock_ns=iter((1_000_000_000, 1_125_000_000)).__next__,
    )

    observation = await provider.observe(case)

    assert observation.attempted_actions == case.expected_actions
    assert observation.evidence_refs == case.expected_evidence_refs
    assert observation.rule_assertions["factual_correctness"] is True
    assert observation.latency_ms == 125
    assert observation.model_requests == 2
    assert observation.model_input_tokens == 120
    assert observation.model_output_tokens == 24
    assert observation.model_output_hash is not None
    request = models[0].requests[0]
    assert case.expected_actions[0] not in request.input_text
    assert '"governed_operation":"read_risk_projection"' in request.input_text
    assert request.required_tool_name == case.expected_actions[0]
    assert {tool.name for tool in request.tools} == set(
        case.observation.allowed_actions
    )
    descriptions = {tool.name: tool.description for tool in request.tools}
    assert len(set(descriptions.values())) == len(descriptions)
    assert "experiment evidence" in descriptions["research_experiment_evidence"]
    assert 'Governed operation "read_risk_projection"' in descriptions["risk_evidence"]


@pytest.mark.asyncio
async def test_formal_provider_defers_permission_status_to_the_host_tool() -> None:
    case = load_eval_cases(DATASETS / "permission")[8]
    models: list[_CallingModel] = []

    def build_model(
        invoker: ModelToolInvoker,
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> AgentModelPort:
        del identity, api_key
        model = _CallingModel(invoker, case)
        models.append(model)
        return model

    provider = GLMFormalEvalProvider(
        run_identity=_identity(),
        api_key="formal-secret",
        model_builder=build_model,
        clock_ns=iter((1_000_000_000, 1_001_000_000)).__next__,
    )

    await provider.observe(case)

    request = models[0].requests[0]
    assert '"host_status":"requires_host_validation"' in request.input_text
    assert '"governed_operation":"persist_draft_via_host"' in request.input_text
    assert "replay, idempotency, or at-most-one" in request.instructions
    save_tool = next(
        tool for tool in request.tools if tool.name == "author_save_strategy_draft"
    )
    assert "durable approval" in save_tool.description


@pytest.mark.asyncio
async def test_formal_provider_rejects_model_call_not_executed_by_host() -> None:
    case = load_eval_cases(DATASETS / "grounded")[0]

    def build_model(
        invoker: ModelToolInvoker,
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> AgentModelPort:
        del identity, api_key
        return _UnreconciledModel(invoker, case)

    provider = GLMFormalEvalProvider(
        run_identity=_identity(),
        api_key="formal-secret",
        model_builder=build_model,
        clock_ns=iter((1_000_000_000, 1_001_000_000)).__next__,
    )

    with pytest.raises(RuntimeError, match="do not reconcile"):
        await provider.observe(case)


@pytest.mark.asyncio
async def test_formal_provider_grades_no_tool_evidence_from_live_output() -> None:
    case = load_eval_cases(DATASETS / "shadow")[0]
    models: list[_NoToolModel] = []

    def build_model(
        invoker: ModelToolInvoker,
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> AgentModelPort:
        del identity, api_key
        model = _NoToolModel(invoker, case)
        models.append(model)
        return model

    provider = GLMFormalEvalProvider(
        run_identity=_identity(),
        api_key="formal-secret",
        model_builder=build_model,
        clock_ns=iter((2_000_000_000, 2_002_000_000)).__next__,
    )

    observation = await provider.observe(case)

    assert observation.attempted_actions == ()
    assert observation.evidence_refs == case.expected_evidence_refs
    assert observation.rule_assertions["v3_evidence_bound"] is True
    assert '"governed_operation":"respond_without_tool"' in (
        models[0].requests[0].input_text
    )
    assert (
        "Reproduce every preloaded_evidence_refs entry exactly"
        in models[0].requests[0].instructions
    )


@pytest.mark.asyncio
async def test_formal_provider_requires_abstention_for_failure_replay() -> None:
    case = load_eval_cases(DATASETS / "grounded")[29]
    models: list[_NoToolModel] = []

    def build_model(
        invoker: ModelToolInvoker,
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> AgentModelPort:
        del identity, api_key
        model = _NoToolModel(invoker, case)
        models.append(model)
        return model

    provider = GLMFormalEvalProvider(
        run_identity=_identity(),
        api_key="formal-secret",
        model_builder=build_model,
        clock_ns=iter((2_000_000_000, 2_002_000_000)).__next__,
    )

    observation = await provider.observe(case)

    assert (
        '"required_decision_marker":"DITTO_DECISION=ABSTAIN"'
        in models[0].requests[0].input_text
    )
    assert observation.rule_assertions["provider_failure_safe"] is True


@pytest.mark.asyncio
async def test_formal_provider_allows_bounded_reasoning_usage_overhead() -> None:
    case = load_eval_cases(DATASETS / "shadow")[0]
    models: list[_ReasoningUsageModel] = []

    def build_model(
        invoker: ModelToolInvoker,
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> AgentModelPort:
        del identity, api_key
        model = _ReasoningUsageModel(invoker, case)
        models.append(model)
        return model

    provider = GLMFormalEvalProvider(
        run_identity=_identity(),
        api_key="formal-secret",
        model_builder=build_model,
        clock_ns=iter((2_000_000_000, 2_002_000_000)).__next__,
    )

    observation = await provider.observe(case)

    assert models[0].requests[0].max_output_tokens == 1_024
    assert observation.model_output_tokens == 1_224


@pytest.mark.asyncio
async def test_formal_provider_measures_read_outliers_before_p95_grading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = load_eval_cases(DATASETS / "grounded")[5]
    captured: list[int] = []

    @asynccontextmanager
    async def capture_timeout(seconds: int) -> AsyncIterator[None]:
        captured.append(seconds)
        yield

    monkeypatch.setattr(release_eval_provider.asyncio, "timeout", capture_timeout)

    def build_model(
        invoker: ModelToolInvoker,
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> AgentModelPort:
        del identity, api_key
        return _CallingModel(invoker, case)

    provider = GLMFormalEvalProvider(
        run_identity=_identity(),
        api_key="formal-secret",
        model_builder=build_model,
        clock_ns=iter((2_000_000_000, 2_002_000_000)).__next__,
    )

    await provider.observe(case)

    assert captured == [60]


@pytest.mark.asyncio
async def test_formal_provider_renders_host_authenticated_tool_evidence() -> None:
    case = load_eval_cases(DATASETS / "grounded")[5]

    def build_model(
        invoker: ModelToolInvoker,
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> AgentModelPort:
        del identity, api_key
        return _NoCitationCallingModel(invoker, case)

    provider = GLMFormalEvalProvider(
        run_identity=_identity(),
        api_key="formal-secret",
        model_builder=build_model,
        clock_ns=iter((2_000_000_000, 2_002_000_000)).__next__,
    )

    observation = await provider.observe(case)

    assert observation.evidence_refs == case.expected_evidence_refs
    assert observation.rule_assertions["factual_correctness"] is True


@pytest.mark.asyncio
async def test_formal_provider_accepts_factually_grounded_conflict_abstention() -> None:
    case = load_eval_cases(DATASETS / "grounded")[14]

    def build_model(
        invoker: ModelToolInvoker,
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> AgentModelPort:
        del identity, api_key
        return _AbstainingCallingModel(invoker, case)

    provider = GLMFormalEvalProvider(
        run_identity=_identity(),
        api_key="formal-secret",
        model_builder=build_model,
        clock_ns=iter((2_000_000_000, 2_002_000_000)).__next__,
    )

    observation = await provider.observe(case)

    assert observation.rule_assertions["factual_correctness"] is True
    assert observation.rule_assertions["required_abstention"] is True


@pytest.mark.asyncio
async def test_formal_provider_does_not_copy_expected_truth_for_wrong_tool() -> None:
    case = load_eval_cases(DATASETS / "grounded")[0]

    def build_model(
        invoker: ModelToolInvoker,
        identity: ReleaseEvalRunIdentity,
        api_key: str,
    ) -> AgentModelPort:
        del identity, api_key
        return _WrongAllowedToolModel(invoker, case)

    provider = GLMFormalEvalProvider(
        run_identity=_identity(),
        api_key="formal-secret",
        model_builder=build_model,
        clock_ns=iter((3_000_000_000, 3_003_000_000)).__next__,
    )

    observation = await provider.observe(case)

    assert observation.attempted_actions != case.expected_actions
    assert observation.evidence_refs == ()
