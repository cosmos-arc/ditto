"""Real Q5 Author proposal over minimized, holdout-blind research evidence."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import orjson
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts.execution import AgentRunExecutionPlan
from ditto_agent.contracts.runtime import (
    AgentManifest,
    ModelProfile,
    RetentionClass,
    RunStatus,
)
from ditto_agent.runtime.service import (
    AgentRunCreateCommand,
    AgentRunExecuteCommand,
    AgentSessionCreateCommand,
)
from ditto_agent.tools._common import function_spec
from ditto_agent.tools.registry import EvidenceToolRegistry
from ditto_application.mutation_idempotency import canonical_request_hash

from ditto_apps.registry.agent.database_provider import build_agent_database
from ditto_apps.registry.agent.model_provider import (
    AgentModelProviderKind,
    AgentModelProviderSettings,
    build_agent_model,
)
from ditto_apps.registry.agent.runtime import (
    PersistedAgentRuntime,
    PersistedAgentRuntimeOptions,
)
from ditto_apps.scripts.q5_live_agent_author_support import (
    _API_KEY_ENV,
    _AUTHOR_SPEC_TEMPLATE,
    _CREDENTIAL_KIND,
    _EXPECTED_TOOL_CALL_COUNT,
    _MAX_MODEL_TOKENS,
    _MAX_OUTPUT_TOKENS,
    _MODEL_SNAPSHOT,
    _STRATEGY_ID,
    _STRATEGY_NAME,
    LiveAuthorValidationError,
    _api_data,
    _BoundContextTool,
    _CapturingAuthorDraftTool,
    _context,
    _mapping,
    _NoBaseCatalog,
    _parse_datetime,
    _plain_mapping,
    _q3_selection,
    _seal_section,
    _validate_author_spec,
    minimal_author_context,
)

__all__ = [
    "_AUTHOR_SPEC_TEMPLATE",
    "_CapturingAuthorDraftTool",
    "_NoBaseCatalog",
    "_context",
    "_validate_author_spec",
    "main",
    "minimal_author_context",
]


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


def _manifest(registry: EvidenceToolRegistry) -> AgentManifest:
    return AgentManifest(
        manifest_id="personal-workstation-q5-live-glm-author",
        agent_version="r5.1",
        prompt_version="q5-author-proposal-v2",
        prompt_hash=canonical_sha256(
            {"prompt": "q5-author-minimal-holdout-blind", "version": 2}
        ),
        tool_schema_version="q5-author-minimal-v2",
        tool_schema_hash=_tool_schema_hash(registry),
        model_profile=ModelProfile.BALANCED,
        model_snapshot=_MODEL_SNAPSHOT,
    )


def _objective(
    *,
    selection_run_id: str,
    research_case_id: str,
    technical_snapshot_id: str,
    evidence_ids: tuple[str, str, str],
) -> str:
    return (
        "First read the three minimized evidence tools exactly once each; call "
        "selection_run_evidence with run_id "
        f"{selection_run_id}, market_context_evidence with no arguments, and "
        "instrument_technical_evidence with instrument_id 2001724, "
        "instrument_name 华安易富黄金ETF, instrument_code 518880.SH, "
        f"selection_run_id {selection_run_id}, research_case_id {research_case_id}, "
        f"and snapshot_id {technical_snapshot_id}. You may issue those three reads "
        "together. "
        "Then call author_draft_strategy exactly once. Choose lookback from "
        "[126,252], vol_window from [20,60], and signal_weights_choice from "
        '["balanced","momentum_tilt"]. The host will compose and validate the '
        "complete frozen StrategySpec from those three values. Use the minimized "
        "evidence to make the choices. Do not add code, prose fields, provider "
        "rows, other instruments, datasets, signals, or any holdout fact. After "
        "the valid draft "
        "preview, return one JSON object with exactly claims and uncertainty. The "
        f"claim must include {_STRATEGY_ID}, valid, and cite both the exact context "
        "evidence ids "
        f"{evidence_ids[0]}, {evidence_ids[1]}, {evidence_ids[2]} and the exact "
        "author preview evidence id."
    )


def _exact_save_request(spec: Mapping[str, object]) -> dict[str, object]:
    arguments: dict[str, object] = {
        "strategy_id": _STRATEGY_ID,
        "name": _STRATEGY_NAME,
        "spec_json": _plain_mapping(spec),
        "base_version": None,
        "tags": ["agent-authored", "etf", "gold", "q5"],
    }
    return {
        "tool_name": "author_save_strategy_draft",
        "arguments": arguments,
        "arguments_hash": canonical_request_hash(arguments),
        "requires_exact_approval": True,
        "status": "pending_operator_approval",
    }


async def _execute(
    *,
    model_id: str,
    api_key: str,
    agent_data_root: Path,
    q3_evidence: Path,
    research_case_path: Path,
    market_path: Path,
    technical_path: Path,
) -> dict[str, object]:
    selection, selection_hash = _q3_selection(q3_evidence)
    research_case, case_hash = _api_data(research_case_path)
    market, market_hash = _api_data(market_path)
    technical, technical_hash = _api_data(technical_path)
    minimized = minimal_author_context(
        selection=selection,
        research_case=research_case,
        market=market,
        technical=technical,
    )
    decision_time = _parse_datetime(technical.get("as_of"), field="technical.as_of")
    context = _context(payload=minimized, decision_time=decision_time)
    lineage = cast("Mapping[str, str]", minimized["lineage"])
    selection_payload = {
        "holdout_excluded": True,
        "selection": minimized["selection"],
        "research_case": minimized["research_case"],
    }
    selection_envelope = _seal_section(
        tool_name="selection_run_evidence",
        kind="selection_research_context",
        payload=selection_payload,
        context=context,
        source_hashes=(selection_hash, case_hash),
        lineage=(lineage["selection_run_id"], lineage["research_case_id"]),
    )
    market_envelope = _seal_section(
        tool_name="market_context_evidence",
        kind="market_context",
        payload=cast("Mapping[str, object]", minimized["market_context"]),
        context=context,
        source_hashes=(market_hash,),
        lineage=(lineage["market_context_feature_set_id"],),
    )
    technical_envelope = _seal_section(
        tool_name="instrument_technical_evidence",
        kind="technical_analysis",
        payload=cast("Mapping[str, object]", minimized["technical"]),
        context=context,
        source_hashes=(technical_hash,),
        lineage=(
            lineage["selection_run_id"],
            lineage["research_case_id"],
            lineage["technical_snapshot_id"],
        ),
    )
    selection_arguments = {"run_id": lineage["selection_run_id"]}
    technical_arguments = {
        "instrument_id": 2_001_724,
        "instrument_name": "华安易富黄金ETF",
        "instrument_code": "518880.SH",
        "selection_run_id": lineage["selection_run_id"],
        "research_case_id": lineage["research_case_id"],
        "snapshot_id": lineage["technical_snapshot_id"],
    }
    selection_tool = _BoundContextTool(
        spec=function_spec(
            name="selection_run_evidence",
            description=(
                "Read the host-minimized exact SelectionRun and derived ResearchCase."
            ),
            properties={"run_id": {"type": "string", "minLength": 1}},
            required=("run_id",),
        ),
        envelope=selection_envelope,
        expected_arguments=selection_arguments,
    )
    market_tool = _BoundContextTool(
        spec=function_spec(
            name="market_context_evidence",
            description="Read the host-minimized exact-PIT MarketContext.",
            properties={},
            required=(),
        ),
        envelope=market_envelope,
        expected_arguments={},
    )
    technical_tool = _BoundContextTool(
        spec=function_spec(
            name="instrument_technical_evidence",
            description=(
                "Read the host-minimized exact technical snapshot for the bound ETF."
            ),
            properties={
                "instrument_id": {"type": "integer", "minimum": 1},
                "instrument_name": {"type": "string", "minLength": 1},
                "instrument_code": {"type": "string", "minLength": 1},
                "selection_run_id": {"type": "string", "minLength": 1},
                "research_case_id": {"type": "string", "minLength": 1},
                "snapshot_id": {"type": "string", "minLength": 1},
            },
            required=tuple(technical_arguments),
        ),
        envelope=technical_envelope,
        expected_arguments=technical_arguments,
    )
    author_tool = _CapturingAuthorDraftTool()
    registry = EvidenceToolRegistry(
        tools=(selection_tool, market_tool, technical_tool, author_tool)
    )
    manifest = _manifest(registry)
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
    database = build_agent_database(agent_data_root)
    now = datetime.now(UTC)
    try:
        database.writer.put_manifest(manifest)
        runtime = PersistedAgentRuntime(
            reader=database.reader,
            writer=database.writer,
            manifest=manifest,
            clock=lambda: now,
            options=PersistedAgentRuntimeOptions(
                provider_name=AgentModelProviderKind.GLM.value,
                presentation_reader=database.presentation_reader,
                presentation_writer=database.presentation_writer,
                presentation_projector=database.presentation_projector,
                episode_writer=database.episode_writer,
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
                idempotency_key="q5-live-glm-author-approved-research-minimal-v2",
            )
        )
        plan = AgentRunExecutionPlan(
            temporal_context=context,
            allowed_tools=(
                selection_tool.spec.name,
                market_tool.spec.name,
                technical_tool.spec.name,
                author_tool.spec.name,
            ),
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )
        queued = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective=_objective(
                    selection_run_id=lineage["selection_run_id"],
                    research_case_id=lineage["research_case_id"],
                    technical_snapshot_id=lineage["technical_snapshot_id"],
                    evidence_ids=(
                        selection_envelope.evidence_id,
                        market_envelope.evidence_id,
                        technical_envelope.evidence_id,
                    ),
                ),
                authority_hash=plan.authority_hash,
                max_model_tokens=_MAX_MODEL_TOKENS,
                max_model_spend_usd=Decimal(0),
                model_profile=ModelProfile.BALANCED,
                idempotency_key=(
                    "q5-live-glm-author-v2-" + canonical_sha256(minimized)
                ),
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
        episode = database.episode_reader.get(f"episode-{completed.run_id}")
        if author_tool.rejection_reason is not None:
            raise LiveAuthorValidationError(author_tool.rejection_reason)
        if (
            completed.status is not RunStatus.COMPLETED
            or completed.guardrail is None
            or completed.guardrail.status != "passed"
            or completed.usage is None
            or completed.usage.tool_calls != _EXPECTED_TOOL_CALL_COUNT
            or author_tool.arguments is None
            or author_tool.evidence is None
            or episode is None
            or not episode.verify_manifest_hash()
            or not episode.verify_replay_identity()
        ):
            raise LiveAuthorValidationError(
                "Q5 Author did not satisfy governed proposal completion"
            )
        spec = _mapping(author_tool.arguments["spec_json"], field="captured spec")
        preview_payload = _mapping(
            author_tool.evidence.result.get("payload"), field="author preview payload"
        )
        if preview_payload.get("valid") is not True:
            raise LiveAuthorValidationError("Q5 Author preview is not valid")
        return {
            "schema": "ditto.q5-live-agent-author-proposal.v1",
            "generated_at": now.isoformat(),
            "status": "passed",
            "passed": True,
            "provider": "glm",
            "model_id": model_id,
            "model_snapshot": _MODEL_SNAPSHOT,
            "production_eligible": False,
            "approval": "user-approved-approved-research-minimal-egress",
            "holdout_excluded": True,
            "run_id": completed.run_id,
            "run_status": completed.status,
            "output_summary": completed.output_summary,
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
                    "holdout",
                    "raw_provider_rows",
                    "ohlcv_rows",
                    "full_selection_universe",
                    "full_technical_indicator_matrix",
                ),
                "payload_bytes": len(canonical_bytes(minimized)),
                "payload_hash": canonical_sha256(minimized),
                "payload": minimized,
            },
            "proposal": {
                "strategy_id": _STRATEGY_ID,
                "spec_json": _plain_mapping(spec),
                "canonical_hash": preview_payload.get("canonical_hash"),
                "preview_evidence_id": author_tool.evidence.evidence_id,
                "preview_payload_hash": author_tool.evidence.result.get("payload_hash"),
                "publishable": False,
            },
            "exact_save_request": _exact_save_request(spec),
            "episode_manifest_hash": episode.manifest_hash,
            "episode_replay_identity": episode.replay_identity,
            "episode_verified": True,
        }
    finally:
        database.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the real holdout-blind Q5 GLM Author proposal"
    )
    parser.add_argument("--model", choices=("glm-5.3",), required=True)
    parser.add_argument("--approval-a4", action="store_true")
    parser.add_argument("--agent-data-root", type=Path, required=True)
    parser.add_argument("--q3-evidence", type=Path, required=True)
    parser.add_argument("--research-case", type=Path, required=True)
    parser.add_argument("--market-context", type=Path, required=True)
    parser.add_argument("--technical", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _write(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS))


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] = os.environ,
) -> int:
    """Execute only the explicitly approved, non-production GLM proposal lane."""
    arguments = _parser().parse_args(argv)
    output = Path(arguments.output)
    model_id = str(arguments.model)
    if not bool(arguments.approval_a4):
        _write(
            output,
            {
                "schema": "ditto.q5-live-agent-author-proposal.v1",
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
                "schema": "ditto.q5-live-agent-author-proposal.v1",
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
                q3_evidence=Path(arguments.q3_evidence),
                research_case_path=Path(arguments.research_case),
                market_path=Path(arguments.market_context),
                technical_path=Path(arguments.technical),
            )
        )
    except Exception as exc:
        failure_detail = (
            str(exc)[:256] if isinstance(exc, LiveAuthorValidationError) else None
        )
        _write(
            output,
            {
                "schema": "ditto.q5-live-agent-author-proposal.v1",
                "status": "failed",
                "passed": False,
                "reason_code": "q5_live_agent_author_failed",
                "failure_type": type(exc).__name__,
                **(
                    {"failure_detail": failure_detail}
                    if failure_detail is not None
                    else {}
                ),
                "provider": "glm",
                "model_id": model_id,
                "production_eligible": False,
            },
        )
        return 1
    _write(output, {**payload, "report_hash": canonical_sha256(payload)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
