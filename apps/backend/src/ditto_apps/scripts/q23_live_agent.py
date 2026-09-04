"""Run real Q2/Q3 GLM briefs with explicitly minimized approved-research evidence."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import orjson
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.execution import AgentRunExecutionPlan
from ditto_agent.contracts.runtime import (
    AgentManifest,
    ModelProfile,
    RetentionClass,
    RunStatus,
)
from ditto_agent.contracts.temporal import (
    TemporalToolContext,
)
from ditto_agent.models.port import ModelToolSpec
from ditto_agent.runtime.service import (
    AgentRunCreateCommand,
    AgentRunExecuteCommand,
    AgentSessionCreateCommand,
)
from ditto_agent.tools._common import function_spec
from ditto_agent.tools.registry import EvidenceToolRegistry

from ditto_apps.registry.agent.database_provider import build_agent_database
from ditto_apps.registry.agent.model_provider import (
    AgentModelCredentialKind,
    AgentModelProviderKind,
    AgentModelProviderSettings,
    build_agent_model,
)
from ditto_apps.registry.agent.runtime import (
    PersistedAgentRuntime,
    PersistedAgentRuntimeOptions,
)
from ditto_apps.scripts.q23_live_agent_context import (
    _FOCUS_INSTRUMENT_CODE,
    _FOCUS_INSTRUMENT_ID,
    _context,
    _mapping,
    _parse_datetime,
    _required_text,
    _seal_minimal,
    _sequence,
    _snapshot_ids,
    minimal_market_payload,
    minimal_selection_payload,
    minimal_technical_payload,
)

__all__ = [
    "LiveBriefValidationError",
    "main",
    "minimal_market_payload",
    "minimal_selection_payload",
    "minimal_technical_payload",
]

_API_KEY_ENV = "DITTO_AGENT_GLM_VALIDATION_API_KEY"
_CREDENTIAL_KIND = AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION
_MODEL_SNAPSHOT = "glm-5.3-coding-plan-2026-09-01"
_MAX_MODEL_TOKENS = 8_192
_MAX_OUTPUT_TOKENS = 4_096


class LiveBriefValidationError(RuntimeError):
    """A real brief did not satisfy its minimized governed contract."""


@dataclass(frozen=True, slots=True)
class _BoundEvidenceTool:
    spec: ModelToolSpec
    envelope: EvidenceEnvelope
    expected_arguments: Mapping[str, object]

    def invoke(
        self,
        *,
        arguments: Mapping[str, object],
        context: TemporalToolContext,
    ) -> EvidenceEnvelope:
        if arguments != self.expected_arguments:
            raise ValueError("live brief tool arguments differ from host scope")
        if context != self.envelope.temporal_context:
            raise ValueError("live brief tool temporal context differs from host scope")
        return self.envelope


@dataclass(frozen=True, slots=True)
class _BriefSpec:
    output_kind: str
    context_type: str
    context_id: str
    objective: str
    tool: _BoundEvidenceTool
    required_output_fragments: tuple[str, ...]


def _artifact(path: Path) -> tuple[Mapping[str, object], str]:
    resolved = path.expanduser().resolve(strict=True)
    content = resolved.read_bytes()
    decoded = orjson.loads(content)
    payload = _mapping(decoded, field=f"live evidence {resolved.name}")
    if payload.get("passed") is not True:
        raise ValueError(f"live evidence is not passing: {resolved}")
    return payload, hashlib.sha256(content).hexdigest()


def _lineage(value: object) -> tuple[str, ...]:
    return tuple(
        _required_text(item, field="lineage item")
        for item in _sequence(value, field="lineage")
    )


def _brief_specs(q2_path: Path, q3_path: Path) -> tuple[_BriefSpec, ...]:
    q2, q2_hash = _artifact(q2_path)
    q3, q3_hash = _artifact(q3_path)
    market = _mapping(q2.get("market_context"), field="market_context")
    market_minimal = minimal_market_payload(market)
    market_context = _context(
        decision_time=_parse_datetime(market.get("as_of"), field="market as_of"),
        snapshot_ids=_snapshot_ids(market.get("source_snapshot_ids")),
        allowed_universe=("000300.SH", "000852.SH"),
    )
    market_agent = _mapping(q2.get("agent_evidence"), field="market agent evidence")
    market_tool = _BoundEvidenceTool(
        spec=function_spec(
            name="market_context_evidence",
            description="Read the host-redacted exact-PIT real MarketContext evidence.",
            properties={},
            required=(),
        ),
        envelope=_seal_minimal(
            tool_name="market_context_evidence",
            kind="market_context",
            payload=market_minimal,
            context=market_context,
            source_artifact_hash=q2_hash,
            lineage=(
                *_lineage(market_agent.get("lineage")),
                "redaction:approved-research-minimal-v1",
            ),
        ),
        expected_arguments={},
    )

    selection = _mapping(q3.get("stock_selection"), field="stock_selection")
    selection_minimal = minimal_selection_payload(selection)
    selection_context = _context(
        decision_time=_parse_datetime(selection.get("as_of"), field="selection as_of"),
        snapshot_ids=_snapshot_ids(selection.get("source_snapshot_ids")),
        allowed_universe=(_FOCUS_INSTRUMENT_CODE,),
    )
    q3_agent = _mapping(q3.get("agent_evidence"), field="Q3 agent evidence")
    selection_agent = _mapping(
        q3_agent.get("selection_run"), field="selection agent evidence"
    )
    selection_run_id = _required_text(selection.get("run_id"), field="selection run_id")
    selection_tool = _BoundEvidenceTool(
        spec=function_spec(
            name="selection_run_evidence",
            description="Read the host-redacted exact real SelectionRun evidence.",
            properties={"run_id": {"type": "string", "minLength": 1}},
            required=("run_id",),
        ),
        envelope=_seal_minimal(
            tool_name="selection_run_evidence",
            kind="selection_run",
            payload=selection_minimal,
            context=selection_context,
            source_artifact_hash=q3_hash,
            lineage=(
                *_lineage(selection_agent.get("lineage")),
                "redaction:approved-research-minimal-v1",
            ),
        ),
        expected_arguments={"run_id": selection_run_id},
    )

    technical_root = _mapping(q3.get("technical_analysis"), field="technical_analysis")
    technical = _mapping(technical_root.get("stock"), field="stock technical analysis")
    technical_minimal = minimal_technical_payload(technical)
    technical_context = _context(
        decision_time=_parse_datetime(technical.get("as_of"), field="technical as_of"),
        snapshot_ids=_snapshot_ids(technical.get("source_snapshot_ids")),
        allowed_universe=(_FOCUS_INSTRUMENT_CODE,),
    )
    technical_agent = _mapping(
        q3_agent.get("technical_analysis"), field="technical agent evidence"
    )
    technical_arguments = {
        "instrument_id": _FOCUS_INSTRUMENT_ID,
        "instrument_name": "贵州茅台",
        "instrument_code": _FOCUS_INSTRUMENT_CODE,
        "selection_run_id": selection_run_id,
    }
    technical_tool = _BoundEvidenceTool(
        spec=function_spec(
            name="instrument_technical_evidence",
            description=(
                "Read the host-redacted exact real technical-analysis evidence."
            ),
            properties={
                "instrument_id": {"type": "integer", "minimum": 1},
                "instrument_name": {"type": "string", "minLength": 1},
                "instrument_code": {"type": "string", "minLength": 1},
                "selection_run_id": {"type": "string", "minLength": 1},
            },
            required=(
                "instrument_id",
                "instrument_name",
                "instrument_code",
                "selection_run_id",
            ),
        ),
        envelope=_seal_minimal(
            tool_name="instrument_technical_evidence",
            kind="technical_analysis",
            payload=technical_minimal,
            context=technical_context,
            source_artifact_hash=q3_hash,
            lineage=(
                *_lineage(technical_agent.get("lineage")),
                "redaction:approved-research-minimal-v1",
            ),
        ),
        expected_arguments=technical_arguments,
    )

    return (
        _BriefSpec(
            output_kind="EvidenceBrief",
            context_type="market",
            context_id=_required_text(
                market.get("source_snapshot_set_id"), field="market snapshot set"
            ),
            objective=(
                "Call market_context_evidence exactly once. Produce an EvidenceBrief "
                "whose claims include the exact literals risk_on, degraded, and "
                "macro_surprise_score; distinguish facts from interpretation and do "
                "not invent any value absent from the tool result."
            ),
            tool=market_tool,
            required_output_fragments=("risk_on", "degraded", "macro_surprise_score"),
        ),
        _BriefSpec(
            output_kind="SelectionMemo",
            context_type="selection",
            context_id=selection_run_id,
            objective=(
                "Call selection_run_evidence exactly once with run_id "
                f"{selection_run_id}. Produce a SelectionMemo that includes the exact "
                "literals 深城交, 贵州茅台, and below_top_k; preserve ranks and the "
                "binding exclusion, and state that only top-three candidates were "
                "egressed."
            ),
            tool=selection_tool,
            required_output_fragments=("深城交", "贵州茅台", "below_top_k"),
        ),
        _BriefSpec(
            output_kind="TechnicalAnalysisBrief",
            context_type="instrument",
            context_id=_required_text(
                technical.get("snapshot_id"), field="technical snapshot"
            ),
            objective=(
                "Call instrument_technical_evidence exactly once with instrument_id "
                f"{_FOCUS_INSTRUMENT_ID}, instrument_name 贵州茅台, instrument_code "
                f"{_FOCUS_INSTRUMENT_CODE}, and selection_run_id {selection_run_id}. "
                "Produce a TechnicalAnalysisBrief that includes the exact literals "
                "1700.53, 1708.74, and missing_reference_series; report daily/weekly "
                "alignment and do not invent any level."
            ),
            tool=technical_tool,
            required_output_fragments=(
                "1700.53",
                "1708.74",
                "missing_reference_series",
            ),
        ),
    )


def _tool_schema_hash(registry: EvidenceToolRegistry) -> str:
    return canonical_sha256(
        tuple(
            {
                "kind": spec.kind,
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "requires_approval": spec.requires_approval,
            }
            for spec in registry.specs
        )
    )


def _manifest_for_brief(
    *,
    registry: EvidenceToolRegistry,
    output_kind: str,
) -> AgentManifest:
    """Bind one manifest to the exact least-privilege tool admitted for a brief."""
    prompt_hash = canonical_sha256(
        {"prompt": "personal-workstation-real-minimal-briefs", "version": 1}
    )
    return AgentManifest(
        manifest_id=f"personal-workstation-q23-live-glm-{output_kind.lower()}",
        agent_version="r5.1",
        prompt_version="real-minimal-briefs-v1",
        prompt_hash=prompt_hash,
        tool_schema_version="approved-research-minimal-v1",
        tool_schema_hash=_tool_schema_hash(registry),
        model_profile=ModelProfile.BALANCED,
        model_snapshot=_MODEL_SNAPSHOT,
    )


async def _execute(
    *,
    model_id: str,
    api_key: str,
    agent_data_root: Path,
    q2_evidence: Path,
    q3_evidence: Path,
) -> dict[str, object]:
    specs = _brief_specs(q2_evidence, q3_evidence)
    settings = AgentModelProviderSettings(
        provider=AgentModelProviderKind.GLM,
        model_calls_enabled=True,
        a4_approved=True,
        model_id=model_id,
        api_key=api_key,
        credential_kind=_CREDENTIAL_KIND,
        production_mode=False,
        reasoning_effort="high",
        approved_license_classes=("approved-research",),
    )
    bundle = build_agent_database(agent_data_root)
    now = datetime.now(UTC)
    try:
        outputs: list[dict[str, object]] = []
        total_tokens = 0
        for spec in specs:
            registry = EvidenceToolRegistry(tools=(spec.tool,))
            manifest = _manifest_for_brief(
                registry=registry,
                output_kind=spec.output_kind,
            )
            bundle.writer.put_manifest(manifest)
            runtime = PersistedAgentRuntime(
                reader=bundle.reader,
                writer=bundle.writer,
                manifest=manifest,
                clock=lambda: now,
                options=PersistedAgentRuntimeOptions(
                    provider_name=AgentModelProviderKind.GLM.value,
                    presentation_reader=bundle.presentation_reader,
                    presentation_writer=bundle.presentation_writer,
                    presentation_projector=bundle.presentation_projector,
                    episode_writer=bundle.episode_writer,
                    tool_registry=registry,
                    model_factory=lambda invoker: build_agent_model(
                        settings, tool_invoker=invoker
                    ),
                    approved_license_classes=("approved-research",),
                ),
            )
            session = runtime.create_session(
                AgentSessionCreateCommand(
                    retention_class=RetentionClass.AUDIT,
                    idempotency_key="q23-live-glm-approved-research-minimal-v1",
                )
            )
            plan = AgentRunExecutionPlan(
                temporal_context=spec.tool.envelope.temporal_context,
                allowed_tools=(spec.tool.spec.name,),
                max_output_tokens=_MAX_OUTPUT_TOKENS,
            )
            queued = runtime.create_run(
                AgentRunCreateCommand(
                    session_id=session.session_id,
                    objective=(
                        f"{spec.objective} The business-output label belongs inside "
                        "claim text, not as an extra JSON field. Your final response "
                        "must use no more than two concise claims; each claim must be "
                        "at most 700 characters and uncertainty at most 300 "
                        "characters. "
                        "It must be one JSON object with exactly two top-level keys: "
                        '{"claims":[{"claim":"<grounded business output>",'
                        '"evidence_refs":["'
                        f"{spec.tool.envelope.evidence_id}"
                        '"]}],"uncertainty":"<grounded uncertainty or none>"}. '
                        "Do not add output_kind, prose, or Markdown outside that JSON."
                    ),
                    authority_hash=plan.authority_hash,
                    max_model_tokens=_MAX_MODEL_TOKENS,
                    max_model_spend_usd=Decimal(0),
                    model_profile=ModelProfile.BALANCED,
                    idempotency_key=f"q23-{spec.output_kind}-{spec.context_id}",
                    execution_plan=plan,
                )
            )
            started = time.monotonic_ns()
            completed = await runtime.execute_run(
                AgentRunExecuteCommand(
                    run_id=queued.run_id,
                    expected_revision=queued.revision,
                )
            )
            latency_ms = (time.monotonic_ns() - started) // 1_000_000
            episode = bundle.episode_reader.get(f"episode-{completed.run_id}")
            if (
                completed.status is not RunStatus.COMPLETED
                or completed.output_summary is None
                or completed.output_summary.startswith("Refused:")
                or completed.guardrail is None
                or completed.guardrail.status != "passed"
                or completed.usage is None
                or completed.usage.tool_calls != 1
                or completed.evidence_refs != (spec.tool.envelope.evidence_id,)
                or len(completed.tool_records) != 1
                or episode is None
                or not episode.verify_manifest_hash()
                or not episode.verify_replay_identity()
            ):
                raise LiveBriefValidationError(
                    f"{spec.output_kind} did not satisfy governed completion"
                )
            if not all(
                fragment in completed.output_summary
                for fragment in spec.required_output_fragments
            ):
                raise LiveBriefValidationError(
                    f"{spec.output_kind} omitted required exact evidence facts"
                )
            total_tokens += completed.usage.total_tokens
            egress_payload = spec.tool.envelope.integrity_payload()
            outputs.append(
                {
                    "output_kind": spec.output_kind,
                    "context_type": spec.context_type,
                    "context_id": spec.context_id,
                    "run_id": completed.run_id,
                    "run_status": completed.status,
                    "output_summary": completed.output_summary,
                    "output_summary_hash": canonical_sha256(
                        {"output_summary": completed.output_summary}
                    ),
                    "evidence_refs": completed.evidence_refs,
                    "guardrail_status": completed.guardrail.status,
                    "usage": {
                        "model_attempts": completed.usage.model_attempts,
                        "model_turns": completed.usage.model_turns,
                        "tool_calls": completed.usage.tool_calls,
                        "retries": completed.usage.retries,
                        "total_tokens": completed.usage.total_tokens,
                    },
                    "latency_ms": latency_ms,
                    "egress": {
                        "license_class": "approved-research",
                        "egress_class": "cloud_allowed",
                        "redaction_profile": "approved-research-minimal-v1",
                        "excluded": (
                            "raw_provider_rows",
                            "ohlcv_rows",
                            "full_selection_universe",
                            "full_technical_indicator_matrix",
                        ),
                        "payload_bytes": len(canonical_bytes(egress_payload)),
                        "payload_hash": canonical_sha256(egress_payload),
                        "payload": egress_payload,
                    },
                    "episode_manifest_hash": episode.manifest_hash,
                    "episode_replay_identity": episode.replay_identity,
                    "episode_verified": True,
                }
            )
        return {
            "schema": "ditto.q23-live-agent-briefs.v1",
            "generated_at": now,
            "status": "passed",
            "passed": True,
            "provider": "glm",
            "model_id": model_id,
            "model_snapshot": _MODEL_SNAPSHOT,
            "credential_kind": _CREDENTIAL_KIND,
            "production_eligible": False,
            "approval": "user-approved-approved-research-minimal-egress",
            "outputs": tuple(outputs),
            "total_tokens": total_tokens,
            "criteria": {
                "q2_evidence_brief": True,
                "q3_selection_memo": True,
                "q3_technical_analysis_brief": True,
                "exact_evidence_citations": True,
                "minimal_egress": True,
                "no_real_order_capability": True,
            },
        }
    finally:
        bundle.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run real minimized Q2/Q3 GLM briefs")
    parser.add_argument("--model", choices=("glm-5.3",), required=True)
    parser.add_argument("--approval-a4", action="store_true")
    parser.add_argument("--agent-data-root", type=Path, required=True)
    parser.add_argument("--q2-evidence", type=Path, required=True)
    parser.add_argument("--q3-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _write(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(payload))


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] = os.environ,
) -> int:
    """Execute only the explicit user-approved, non-production GLM lane."""
    arguments = _parser().parse_args(argv)
    output = Path(arguments.output)
    model_id = str(arguments.model)
    if not bool(arguments.approval_a4):
        _write(
            output,
            {
                "schema": "ditto.q23-live-agent-briefs.v1",
                "status": "not_run",
                "passed": False,
                "reason_code": "a4_approval_required",
            },
        )
        return 5
    api_key = environment.get(_API_KEY_ENV)
    if api_key is None or not api_key.strip() or api_key != api_key.strip():
        _write(
            output,
            {
                "schema": "ditto.q23-live-agent-briefs.v1",
                "status": "not_run",
                "passed": False,
                "reason_code": "glm_validation_credential_missing",
            },
        )
        return 5
    try:
        payload = asyncio.run(
            _execute(
                model_id=model_id,
                api_key=api_key,
                agent_data_root=Path(arguments.agent_data_root),
                q2_evidence=Path(arguments.q2_evidence),
                q3_evidence=Path(arguments.q3_evidence),
            )
        )
    except Exception as exc:
        _write(
            output,
            {
                "schema": "ditto.q23-live-agent-briefs.v1",
                "status": "failed",
                "passed": False,
                "reason_code": "q23_live_agent_validation_failed",
                "failure_type": type(exc).__name__,
                "provider": "glm",
                "model_id": model_id,
                "production_eligible": False,
            },
        )
        return 1
    report_hash = canonical_sha256(payload)
    _write(output, {**payload, "report_hash": report_hash})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
