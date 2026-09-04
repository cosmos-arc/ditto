"""Run one synthetic GLM validation without claiming release acceptance."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import orjson
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts._validation import normalized_text, sha256_hex
from ditto_agent.models.glm_adapter import GLM_RESPONSES_BASE_URL
from ditto_agent.models.port import (
    AgentModelPort,
    ModelRequest,
    ModelToolCall,
    ModelToolInvoker,
    ModelToolKind,
    ModelToolSpec,
    ModelUsage,
)

from ditto_apps.registry.agent.model_provider import (
    AgentModelCredentialKind,
    AgentModelProviderKind,
    AgentModelProviderSettings,
    build_agent_model,
)

_API_KEY_ENV = "DITTO_AGENT_GLM_VALIDATION_API_KEY"
_EXPERIMENT_ID = "experiment-001"
_EVIDENCE_REF = "synthetic://glm-validation/experiment-001"
_CREDENTIAL_KIND = AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION
_MAX_PROVIDER_REQUESTS = 2
_MAX_TOTAL_TOKENS = 4_096
_MAX_OUTPUT_TOKENS = 1_024
_MAX_TURNS = 3
type _ModelBuilder = Callable[[ModelToolInvoker, str], AgentModelPort]


class GLMValidationError(RuntimeError):
    """The live smoke did not satisfy its exact synthetic contract."""


class SyntheticValidationToolInvoker:
    """Serve one fixed non-user-data tool result and retain call identities."""

    def __init__(self) -> None:
        self._calls: list[tuple[str, Mapping[str, object], str]] = []

    @property
    def calls(self) -> tuple[tuple[str, Mapping[str, object], str], ...]:
        """Return calls observed at the host execution boundary."""
        return tuple(self._calls)

    async def invoke(
        self,
        tool_name: str,
        arguments_json: str,
        *,
        call_id: str,
    ) -> object:
        """Accept only the fixed experiment_summary validation call."""
        try:
            decoded: object = orjson.loads(arguments_json)
        except orjson.JSONDecodeError as exc:
            raise GLMValidationError(
                "validation tool arguments are invalid JSON"
            ) from exc
        if not isinstance(decoded, dict):
            raise GLMValidationError("validation tool arguments must be an object")
        arguments = cast(dict[object, object], decoded)
        if tool_name != "experiment_summary" or arguments != {
            "experiment_id": _EXPERIMENT_ID
        }:
            raise GLMValidationError("validation tool call differs from exact scope")
        normalized_call_id = normalized_text(call_id, field="call_id")
        normalized_arguments = cast(Mapping[str, object], dict(arguments))
        self._calls.append((tool_name, normalized_arguments, normalized_call_id))
        return {
            "experiment_id": _EXPERIMENT_ID,
            "status": "validated",
            "evidence_ref": _EVIDENCE_REF,
        }


@dataclass(frozen=True, slots=True)
class GLMValidationReport:
    """Hash-addressed facts from one GLM Coding Plan validation smoke."""

    model_id: str
    latency_ms: int
    usage: ModelUsage
    final_output_hash: str
    report_hash: str = field(init=False)

    def __post_init__(self) -> None:
        """Validate measured fields and derive the report identity."""
        object.__setattr__(
            self, "model_id", normalized_text(self.model_id, field="model_id")
        )
        if isinstance(self.latency_ms, bool) or self.latency_ms < 0:
            raise ValueError("latency_ms must be a non-negative integer")
        object.__setattr__(
            self,
            "final_output_hash",
            sha256_hex(self.final_output_hash, field="final_output_hash"),
        )
        object.__setattr__(self, "report_hash", canonical_sha256(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "status": "passed",
            "provider": "glm",
            "endpoint": GLM_RESPONSES_BASE_URL,
            "model_id": self.model_id,
            "credential_kind": _CREDENTIAL_KIND,
            "dataset": "synthetic-no-user-data-v1",
            "production_eligible": False,
            "release_gate_passed": False,
            "cost_evaluated": False,
            "latency_ms": self.latency_ms,
            "budget": {
                "max_provider_requests": _MAX_PROVIDER_REQUESTS,
                "max_total_tokens": _MAX_TOTAL_TOKENS,
                "max_output_tokens": _MAX_OUTPUT_TOKENS,
                "max_turns": _MAX_TURNS,
            },
            "usage": {
                "requests": self.usage.requests,
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
                "total_tokens": self.usage.total_tokens,
            },
            "checks": {
                "exact_tool_called": True,
                "exact_arguments_used": True,
                "host_result_grounded": True,
                "no_interruption": True,
                "request_budget_respected": True,
            },
            "final_output_hash": self.final_output_hash,
        }

    def to_bytes(self) -> bytes:
        """Serialize the complete canonical report without raw model content."""
        return canonical_bytes({**self._payload(), "report_hash": self.report_hash})

    def verify_report_hash(self) -> bool:
        """Recompute the report identity from every persisted fact."""
        return self.report_hash == canonical_sha256(self._payload())


def _request() -> ModelRequest:
    return ModelRequest(
        run_id="glm-validation-smoke-001",
        agent_name="ditto-glm-validation",
        instructions=(
            "Call experiment_summary exactly once with experiment_id "
            "experiment-001. Then report the returned status and cite the exact "
            "evidence_ref. Do not invent any other facts."
        ),
        input_text="Validate the synthetic experiment.",
        max_turns=_MAX_TURNS,
        max_output_tokens=_MAX_OUTPUT_TOKENS,
        tools=(
            ModelToolSpec(
                kind=ModelToolKind.FUNCTION,
                name="experiment_summary",
                description="Read one synthetic experiment validation summary.",
                input_schema={
                    "type": "object",
                    "properties": {"experiment_id": {"type": "string"}},
                    "required": ["experiment_id"],
                    "additionalProperties": False,
                },
                requires_approval=False,
            ),
        ),
    )


def _exact_model_call(call: ModelToolCall) -> bool:
    return call.tool_name == "experiment_summary" and dict(call.arguments) == {
        "experiment_id": _EXPERIMENT_ID
    }


async def run_glm_validation(
    *,
    model: AgentModelPort,
    model_id: str,
    invoker: SyntheticValidationToolInvoker,
    clock_ns: Callable[[], int] = time.monotonic_ns,
) -> GLMValidationReport:
    """Execute and verify one real model/tool/host/result validation loop."""
    started_ns = clock_ns()
    result = await model.run(_request())
    finished_ns = clock_ns()
    if finished_ns < started_ns:
        raise GLMValidationError("validation clock moved backwards")
    if len(invoker.calls) != 1 or len(result.tool_calls) != 1:
        raise GLMValidationError(
            "validation must call the exact host tool exactly once"
        )
    host_name, host_arguments, _host_call_id = invoker.calls[0]
    if host_name != "experiment_summary" or dict(host_arguments) != {
        "experiment_id": _EXPERIMENT_ID
    }:
        raise GLMValidationError("validation host call differs from exact scope")
    if not _exact_model_call(result.tool_calls[0]):
        raise GLMValidationError("validation model call differs from exact scope")
    if result.interruptions or result.continuation is not None:
        raise GLMValidationError("validation unexpectedly requires an interruption")
    output = result.final_output
    if (
        not isinstance(output, str)
        or "validated" not in output.lower()
        or _EVIDENCE_REF not in output
    ):
        raise GLMValidationError("validation output is not grounded in the host result")
    if (
        result.usage.requests != _MAX_PROVIDER_REQUESTS
        or result.usage.total_tokens <= 0
        or result.usage.total_tokens > _MAX_TOTAL_TOKENS
        or result.usage.output_tokens > _MAX_OUTPUT_TOKENS
    ):
        raise GLMValidationError("validation provider usage exceeded its exact budget")
    return GLMValidationReport(
        model_id=model_id,
        latency_ms=(finished_ns - started_ns) // 1_000_000,
        usage=result.usage,
        final_output_hash=canonical_sha256({"final_output": output}),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run synthetic GLM validation")
    parser.add_argument("--model", choices=("glm-5.3", "glm-5-turbo"), required=True)
    parser.add_argument("--approval-a4", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _not_run_payload(*, model_id: str, reason_code: str) -> bytes:
    return canonical_bytes(
        {
            "schema_version": 1,
            "status": "not_run",
            "approval_gate": "A4",
            "reason_code": reason_code,
            "provider": "glm",
            "model_id": model_id,
            "credential_kind": _CREDENTIAL_KIND,
            "production_eligible": False,
            "release_gate_passed": False,
            "api_key_read": reason_code != "a4_approval_required",
            "live_endpoint_called": False,
        }
    )


def _default_builder(*, model_id: str) -> _ModelBuilder:
    def build(invoker: ModelToolInvoker, api_key: str) -> AgentModelPort:
        return build_agent_model(
            AgentModelProviderSettings(
                provider=AgentModelProviderKind.GLM,
                model_calls_enabled=True,
                a4_approved=True,
                model_id=model_id,
                api_key=api_key,
                credential_kind=_CREDENTIAL_KIND,
                production_mode=False,
            ),
            tool_invoker=invoker,
        )

    return build


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] = os.environ,
    model_builder: _ModelBuilder | None = None,
) -> int:
    """Run the explicit A4 validation lane and persist only safe evidence."""
    arguments = _parser().parse_args(argv)
    model_id = str(arguments.model)
    output = Path(arguments.output)
    if not bool(arguments.approval_a4):
        output.write_bytes(
            _not_run_payload(
                model_id=model_id,
                reason_code="a4_approval_required",
            )
        )
        return 5
    api_key = environment.get(_API_KEY_ENV)
    if api_key is None or not api_key.strip() or api_key != api_key.strip():
        output.write_bytes(
            _not_run_payload(
                model_id=model_id,
                reason_code="glm_validation_credential_missing",
            )
        )
        return 5
    invoker = SyntheticValidationToolInvoker()
    builder = model_builder or _default_builder(model_id=model_id)
    try:
        report = asyncio.run(
            run_glm_validation(
                model=builder(invoker, api_key),
                model_id=model_id,
                invoker=invoker,
            )
        )
    except Exception as exc:
        output.write_bytes(
            canonical_bytes(
                {
                    "schema_version": 1,
                    "status": "failed",
                    "reason_code": "glm_validation_failed",
                    "failure_type": type(exc).__name__,
                    "provider": "glm",
                    "model_id": model_id,
                    "credential_kind": _CREDENTIAL_KIND,
                    "production_eligible": False,
                    "release_gate_passed": False,
                }
            )
        )
        return 1
    output.write_bytes(report.to_bytes())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "GLMValidationError",
    "GLMValidationReport",
    "SyntheticValidationToolInvoker",
    "main",
    "run_glm_validation",
]
