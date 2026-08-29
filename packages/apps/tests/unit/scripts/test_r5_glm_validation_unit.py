from __future__ import annotations

from collections.abc import AsyncIterator

import orjson
import pytest
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
from ditto_apps.scripts.r5_glm_validation import (
    GLMValidationError,
    SyntheticValidationToolInvoker,
    main,
    run_glm_validation,
)

_EVIDENCE_REF = "synthetic://glm-validation/experiment-001"


class _SyntheticSuccessModel:
    def __init__(
        self,
        invoker: ModelToolInvoker,
        *,
        usage: ModelUsage | None = None,
    ) -> None:
        self._invoker = invoker
        self._usage = usage or ModelUsage(
            requests=2, input_tokens=481, output_tokens=149
        )

    async def run(self, request: ModelRequest) -> ModelResult:
        assert request.tools[0].name == "experiment_summary"
        arguments = '{"experiment_id":"experiment-001"}'
        await self._invoker.invoke(
            "experiment_summary",
            arguments,
            call_id="call-glm-validation-001",
        )
        return ModelResult(
            final_output=f"validated; evidence: {_EVIDENCE_REF}",
            tool_calls=(
                ModelToolCall(
                    call_id="call-glm-validation-001",
                    tool_name="experiment_summary",
                    arguments={"experiment_id": "experiment-001"},
                ),
            ),
            usage=self._usage,
            interruptions=(),
            continuation=None,
        )

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        del request
        raise NotImplementedError

    async def resume(self, request: ResumeModelRequest) -> ModelResult:
        del request
        raise NotImplementedError


class _NoToolModel(_SyntheticSuccessModel):
    async def run(self, request: ModelRequest) -> ModelResult:
        del request
        return ModelResult(
            final_output="validated",
            tool_calls=(),
            usage=ModelUsage(requests=1, input_tokens=10, output_tokens=2),
            interruptions=(),
            continuation=None,
        )


@pytest.mark.asyncio
async def test_glm_validation_report_records_live_facts_without_raw_output() -> None:
    invoker = SyntheticValidationToolInvoker()
    model: AgentModelPort = _SyntheticSuccessModel(invoker)
    ticks = iter((1_000_000_000, 1_321_000_000))

    report = await run_glm_validation(
        model=model,
        model_id="glm-5.3",
        invoker=invoker,
        clock_ns=lambda: next(ticks),
    )
    payload = orjson.loads(report.to_bytes())

    assert payload["status"] == "passed"
    assert payload["provider"] == "glm"
    assert payload["model_id"] == "glm-5.3"
    assert payload["credential_kind"] == "glm_coding_plan_validation"
    assert payload["production_eligible"] is False
    assert payload["release_gate_passed"] is False
    assert payload["cost_evaluated"] is False
    assert payload["latency_ms"] == 321
    assert payload["usage"] == {
        "requests": 2,
        "input_tokens": 481,
        "output_tokens": 149,
        "total_tokens": 630,
    }
    assert payload["checks"] == {
        "exact_tool_called": True,
        "exact_arguments_used": True,
        "host_result_grounded": True,
        "no_interruption": True,
        "request_budget_respected": True,
    }
    assert payload["budget"] == {
        "max_provider_requests": 2,
        "max_total_tokens": 4096,
        "max_output_tokens": 1024,
        "max_turns": 3,
    }
    assert "final_output" not in payload
    assert "api_key" not in payload
    assert report.verify_report_hash()


@pytest.mark.asyncio
async def test_glm_validation_fails_closed_when_model_skips_host_tool() -> None:
    invoker = SyntheticValidationToolInvoker()

    with pytest.raises(GLMValidationError, match="exactly once"):
        await run_glm_validation(
            model=_NoToolModel(invoker),
            model_id="glm-5.3",
            invoker=invoker,
        )


@pytest.mark.asyncio
async def test_glm_validation_fails_closed_when_token_budget_is_exceeded() -> None:
    invoker = SyntheticValidationToolInvoker()
    model = _SyntheticSuccessModel(
        invoker,
        usage=ModelUsage(requests=2, input_tokens=4_000, output_tokens=500),
    )

    with pytest.raises(GLMValidationError, match="budget"):
        await run_glm_validation(
            model=model,
            model_id="glm-5.3",
            invoker=invoker,
        )


@pytest.mark.asyncio
async def test_glm_validation_fails_closed_when_output_budget_is_exceeded() -> None:
    invoker = SyntheticValidationToolInvoker()
    model = _SyntheticSuccessModel(
        invoker,
        usage=ModelUsage(requests=2, input_tokens=100, output_tokens=1_500),
    )

    with pytest.raises(GLMValidationError, match="budget"):
        await run_glm_validation(
            model=model,
            model_id="glm-5.3",
            invoker=invoker,
        )


def test_cli_does_not_read_secret_without_explicit_a4_flag(tmp_path) -> None:
    class GuardedEnvironment(dict[str, str]):
        def get(self, key: str, default: str | None = None) -> str | None:
            if key == "DITTO_AGENT_GLM_VALIDATION_API_KEY":
                raise AssertionError("credential read before approval")
            return super().get(key, default)

    output = tmp_path / "glm-not-run.json"

    exit_code = main(
        ("--model", "glm-5.3", "--output", str(output)),
        environment=GuardedEnvironment(),
    )
    payload = orjson.loads(output.read_bytes())

    assert exit_code == 5
    assert payload["status"] == "not_run"
    assert payload["approval_gate"] == "A4"
    assert payload["reason_code"] == "a4_approval_required"
    assert payload["api_key_read"] is False


def test_cli_uses_injected_builder_and_never_serializes_secret(tmp_path) -> None:
    output = tmp_path / "glm-passed.json"

    def builder(invoker: ModelToolInvoker, api_key: str) -> AgentModelPort:
        assert api_key == "secret-plan-key"
        return _SyntheticSuccessModel(invoker)

    exit_code = main(
        (
            "--model",
            "glm-5.3",
            "--approval-a4",
            "--output",
            str(output),
        ),
        environment={"DITTO_AGENT_GLM_VALIDATION_API_KEY": "secret-plan-key"},
        model_builder=builder,
    )
    payload = output.read_text()

    assert exit_code == 0
    assert "secret-plan-key" not in payload
    assert orjson.loads(payload)["status"] == "passed"
