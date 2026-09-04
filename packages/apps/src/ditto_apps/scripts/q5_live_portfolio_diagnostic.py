"""Run one real GLM PortfolioDiagnostic over minimized approved-research evidence."""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import orjson
from ditto_agent._canonical import canonical_bytes, canonical_sha256
from ditto_agent.contracts.evidence import EvidenceEnvelope
from ditto_agent.contracts.execution import AgentRunExecutionPlan
from ditto_agent.contracts.portfolio import (
    PortfolioDiagnostic,
    PortfolioDiagnosticDraft,
    PortfolioNumericClaim,
    validate_portfolio_diagnostic,
)
from ditto_agent.contracts.runtime import (
    AgentManifest,
    ModelProfile,
    RetentionClass,
    RunStatus,
)
from ditto_agent.contracts.temporal import (
    EgressClass,
    TemporalContextInput,
    TemporalToolContext,
)
from ditto_agent.models.port import ModelToolSpec
from ditto_agent.runtime.service import (
    AgentRunCreateCommand,
    AgentRunExecuteCommand,
    AgentSessionCreateCommand,
)
from ditto_agent.tools._common import function_spec
from ditto_agent.tools.portfolio_comparison import PortfolioComparisonEvidenceTool
from ditto_agent.tools.registry import EvidenceToolRegistry
from ditto_application.catalog_freshness import aggregate_source_snapshot_ids
from ditto_application.queries.portfolio_comparison_evidence import (
    PortfolioComparisonEvidenceQueryFacade,
)

from ditto_apps.operations.q4_live_account_acceptance import (
    atomic_write_json,
    canonical_hash,
    load_json,
    parse_timestamp,
)
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
from ditto_apps.registry.container import make_app_container
from ditto_apps.registry.infra.config import preload_runtime_secrets

__all__ = [
    "LivePortfolioDiagnosticError",
    "minimal_portfolio_payload",
    "validate_model_portfolio_diagnostic",
]

_API_KEY_ENV = "DITTO_AGENT_GLM_VALIDATION_API_KEY"
_CREDENTIAL_KIND = AgentModelCredentialKind.GLM_CODING_PLAN_VALIDATION
_MODEL_SNAPSHOT = "glm-5.3-coding-plan-2026-09-02"
_MAX_MODEL_TOKENS = 16_384
_MAX_OUTPUT_TOKENS = 4_096
_TOOL_NAME = "portfolio_comparison_evidence"
_REDACTION_PROFILE = "approved-research-portfolio-minimal-v1"
_IDENTITY_FIELDS = (
    "strategy_id",
    "model_portfolio_id",
    "paper_account_id",
    "manual_account_id",
    "paper_session_id",
)
_PORTFOLIO_FIELDS = (
    "portfolio_id",
    "portfolio_kind",
    "total_value",
    "cash",
    "cash_weight",
    "invested_weight",
    "realized_pnl",
    "unrealized_pnl",
    "fees",
    "pending_event_count",
    "alert_codes",
)
_POSITION_FIELDS = (
    "instrument_id",
    "quantity",
    "last_price",
    "market_value",
    "weight",
    "average_cost_value",
    "realized_pnl",
    "unrealized_pnl",
    "fees",
    "industry",
)
_DRIFT_FIELDS = (
    "comparison_kind",
    "baseline_portfolio_id",
    "observed_portfolio_id",
    "total_abs_drift_bps",
    "cash_drift_bps",
)
_DRIFT_ITEM_FIELDS = (
    "instrument_id",
    "baseline_weight",
    "observed_weight",
    "drift_weight",
    "drift_bps",
)
_ATTRIBUTION_FIELDS = (
    "unfilled_bps",
    "slippage_amount",
    "fee_amount",
    "risk_blocked_bps",
    "user_choice_bps",
)
_REQUIRED_NUMERIC_PATHS = frozenset(
    {
        "model_vs_paper.attribution.unfilled_bps",
        "model_vs_paper.attribution.fee_amount",
        "model_vs_manual.attribution.user_choice_bps",
    }
)


class LivePortfolioDiagnosticError(RuntimeError):
    """A live portfolio diagnostic did not satisfy the governed contract."""


def _mapping(value: object, *, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(
        type(key) is str for key in cast("Mapping[object, object]", value)
    ):
        raise ValueError(f"{field} must be a string-keyed object")
    return cast("Mapping[str, object]", value)


def _sequence(value: object, *, field: str) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{field} must be an array")
    return tuple(cast("Sequence[object]", value))


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be canonical text")
    return value


def _project(value: Mapping[str, object], fields: tuple[str, ...]) -> dict[str, object]:
    return {field: value[field] for field in fields if field in value}


def _minimal_portfolio(value: object, *, field: str) -> dict[str, object]:
    portfolio = _mapping(value, field=field)
    positions = tuple(
        _project(_mapping(item, field=f"{field}.position"), _POSITION_FIELDS)
        for item in _sequence(portfolio.get("positions"), field=f"{field}.positions")
    )
    return {**_project(portfolio, _PORTFOLIO_FIELDS), "positions": positions}


def _minimal_drift(value: object, *, field: str) -> dict[str, object]:
    drift = _mapping(value, field=field)
    attribution = _mapping(drift.get("attribution"), field=f"{field}.attribution")
    missing = tuple(item for item in _ATTRIBUTION_FIELDS if item not in attribution)
    if missing:
        raise ValueError(f"{field}.attribution fields are missing: {missing}")
    items = tuple(
        _project(_mapping(item, field=f"{field}.item"), _DRIFT_ITEM_FIELDS)
        for item in _sequence(drift.get("items"), field=f"{field}.items")
    )
    return {
        **_project(drift, _DRIFT_FIELDS),
        "items": items,
        "attribution": _project(attribution, _ATTRIBUTION_FIELDS),
    }


def minimal_portfolio_payload(value: Mapping[str, object]) -> dict[str, object]:
    """Project only exact comparison math, excluding provider rows and journals."""
    required = (
        "as_of",
        "valuation_snapshot_id",
        "source_snapshot_ids",
        "model",
        "paper",
        "manual",
        "model_vs_paper",
        "model_vs_manual",
        "paper_vs_manual",
    )
    missing = tuple(field for field in required if field not in value)
    if missing:
        raise ValueError(f"portfolio comparison fields are missing: {missing}")
    return {
        "as_of": value["as_of"],
        "valuation_snapshot_id": value["valuation_snapshot_id"],
        "source_snapshot_ids": _sequence(
            value["source_snapshot_ids"], field="source_snapshot_ids"
        ),
        "model": _minimal_portfolio(value["model"], field="model"),
        "paper": _minimal_portfolio(value["paper"], field="paper"),
        "manual": _minimal_portfolio(value["manual"], field="manual"),
        "model_vs_paper": _minimal_drift(
            value["model_vs_paper"], field="model_vs_paper"
        ),
        "model_vs_manual": _minimal_drift(
            value["model_vs_manual"], field="model_vs_manual"
        ),
        "paper_vs_manual": _minimal_drift(
            value["paper_vs_manual"], field="paper_vs_manual"
        ),
    }


def _texts(value: object, *, field: str, required: bool = False) -> tuple[str, ...]:
    items = _sequence(value, field=field)
    result = tuple(_text(item, field=f"{field} item") for item in items)
    if required and not result:
        raise ValueError(f"{field} cannot be empty")
    return result


def validate_model_portfolio_diagnostic(
    output_summary: str,
    *,
    evidence: EvidenceEnvelope,
) -> PortfolioDiagnostic:
    """Parse one model claim and require exact host-validated numeric citations."""
    decoded = orjson.loads(output_summary)
    payload = _mapping(decoded, field="portfolio diagnostic")
    expected_fields = {
        "summary",
        "facts",
        "interpretations",
        "uncertainties",
        "numeric_claims",
        "evidence_refs",
    }
    if set(payload) != expected_fields:
        raise ValueError("portfolio diagnostic fields do not match the closed schema")
    numeric_claims = tuple(
        PortfolioNumericClaim(
            evidence_ref=_text(
                _mapping(item, field="numeric claim").get("evidence_ref"),
                field="numeric claim evidence_ref",
            ),
            path=_text(
                _mapping(item, field="numeric claim").get("path"),
                field="numeric claim path",
            ),
            value=_text(
                _mapping(item, field="numeric claim").get("value"),
                field="numeric claim value",
            ),
        )
        for item in _sequence(payload.get("numeric_claims"), field="numeric_claims")
    )
    paths = {item.path for item in numeric_claims}
    if not paths >= _REQUIRED_NUMERIC_PATHS:
        raise ValueError("portfolio diagnostic omitted required numeric paths")
    draft = PortfolioDiagnosticDraft(
        summary=_text(payload.get("summary"), field="summary"),
        facts=_texts(payload.get("facts"), field="facts", required=True),
        interpretations=_texts(payload.get("interpretations"), field="interpretations"),
        uncertainties=_texts(payload.get("uncertainties"), field="uncertainties"),
        numeric_claims=numeric_claims,
        evidence_refs=_texts(
            payload.get("evidence_refs"), field="evidence_refs", required=True
        ),
    )
    return validate_portfolio_diagnostic(draft, evidence=(evidence,))


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
            raise ValueError("portfolio tool arguments differ from the host scope")
        if context != self.envelope.temporal_context:
            raise ValueError("portfolio tool temporal context differs from host scope")
        return self.envelope


def _tool_spec() -> ModelToolSpec:
    text = {"type": "string", "minLength": 1}
    return function_spec(
        name=_TOOL_NAME,
        description=(
            "Read the host-minimized exact-PIT Model, Paper, and Manual comparison."
        ),
        properties=dict.fromkeys(_IDENTITY_FIELDS, text),
        required=_IDENTITY_FIELDS,
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


def _manifest(registry: EvidenceToolRegistry) -> AgentManifest:
    return AgentManifest(
        manifest_id="personal-workstation-q5-live-glm-portfolio-diagnostic",
        agent_version="r5.1",
        prompt_version="q5-portfolio-diagnostic-v3",
        prompt_hash=canonical_sha256(
            {"prompt": "q5-portfolio-diagnostic-minimal", "version": 3}
        ),
        tool_schema_version=_REDACTION_PROFILE,
        tool_schema_hash=_tool_schema_hash(registry),
        model_profile=ModelProfile.BALANCED,
        model_snapshot=_MODEL_SNAPSHOT,
    )


def _acceptance(path: Path) -> tuple[Mapping[str, object], str]:
    payload = load_json(path.expanduser().resolve(strict=True), field="Q5 acceptance")
    evidence_hash = _text(payload.get("evidence_hash"), field="evidence_hash")
    body = {key: value for key, value in payload.items() if key != "evidence_hash"}
    if (
        payload.get("schema") != "ditto.q5-live-portfolio-acceptance.v1"
        or payload.get("status") != "passed"
        or payload.get("passed") is not True
        or canonical_hash(body) != evidence_hash
    ):
        raise ValueError("Q5 portfolio acceptance is not a valid passing artifact")
    return payload, evidence_hash


def _context_and_arguments(
    acceptance: Mapping[str, object],
) -> tuple[TemporalToolContext, dict[str, object]]:
    request = _mapping(acceptance.get("comparison_request"), field="comparison_request")
    provider = _mapping(acceptance.get("provider"), field="provider")
    snapshots = tuple(
        _text(item, field="source snapshot")
        for item in _sequence(
            request.get("source_snapshot_ids"), field="source_snapshot_ids"
        )
    )
    snapshot_set = aggregate_source_snapshot_ids(snapshots)
    if snapshot_set is None:
        raise ValueError("portfolio acceptance lacks a source snapshot set")
    decision_time = parse_timestamp(provider.get("observed_at"), field="observed_at")
    context = TemporalToolContext.from_host(
        TemporalContextInput(
            decision_time=decision_time,
            knowledge_cutoff=decision_time,
            publication_cutoff=decision_time,
            source_snapshot_id=snapshot_set,
            execution_eligible_at="not_applicable",
            allowed_universe=("510300.SH", "518880.SH"),
            license_class="approved-research",
            egress_class=EgressClass.CLOUD_ALLOWED,
        )
    )
    arguments: dict[str, object] = {
        field: _text(request.get(field), field=field) for field in _IDENTITY_FIELDS
    }
    return context, arguments


def _minimal_envelope(
    full: EvidenceEnvelope,
    *,
    acceptance_hash: str,
) -> EvidenceEnvelope:
    raw = _mapping(full.result.get("payload"), field="portfolio evidence payload")
    payload = minimal_portfolio_payload(raw)
    payload_hash = canonical_sha256(payload)
    result: Mapping[str, object] = {
        "schema_version": 1,
        "kind": "portfolio_comparison",
        "redaction_profile": _REDACTION_PROFILE,
        "payload": payload,
    }
    lineage = (
        *full.lineage,
        f"q5-acceptance:sha256:{acceptance_hash}",
        f"redaction:{_REDACTION_PROFILE}",
    )
    evidence_id = f"evidence-{canonical_sha256({'result': result, 'lineage': lineage})}"
    return EvidenceEnvelope.seal(
        evidence_id=evidence_id,
        tool_name=_TOOL_NAME,
        result=result,
        artifact_refs=(
            *full.artifact_refs,
            f"minimal-egress:sha256:{payload_hash}",
        ),
        temporal_context=full.temporal_context,
        lineage=lineage,
    )


def _assert_frozen_comparison(
    full: EvidenceEnvelope,
    *,
    acceptance: Mapping[str, object],
) -> None:
    live = minimal_portfolio_payload(
        _mapping(full.result.get("payload"), field="live portfolio evidence payload")
    )
    frozen = minimal_portfolio_payload(
        _mapping(acceptance.get("comparison"), field="accepted portfolio comparison")
    )
    if canonical_sha256(live) != canonical_sha256(frozen):
        raise LivePortfolioDiagnosticError(
            "live portfolio comparison drifted from Q5 acceptance"
        )


def _objective(arguments: Mapping[str, object], evidence_id: str) -> str:
    identity = ", ".join(f"{key}={value}" for key, value in arguments.items())
    return "".join(
        (
            "Call portfolio_comparison_evidence exactly once with ",
            identity,
            ". Then return exactly one grounded claim. The claim text itself must be ",
            "a compact JSON object with exactly summary, facts, interpretations, ",
            "uncertainties, numeric_claims, and evidence_refs. ",
            "Use one to three facts. ",
            "facts, interpretations, uncertainties, numeric_claims, and evidence_refs ",
            "must each be JSON arrays, even when empty. ",
            "summary must be a JSON string. ",
            "Every number in facts must have a numeric_claim containing evidence_ref, ",
            "the exact dotted payload path, and the exact string value. Include the ",
            "paths model_vs_paper.attribution.unfilled_bps, ",
            "model_vs_paper.attribution.fee_amount, and ",
            "model_vs_manual.attribution.user_choice_bps. evidence_refs must contain ",
            f"only {evidence_id}. Distinguish facts from interpretation and do not ",
            "invent weights, orders, or recommendations. The outer response must be ",
            "one JSON object with exactly claims and uncertainty. claims must be a ",
            "JSON array containing exactly one object with exactly claim and ",
            "evidence_refs; claim must be a JSON string whose contents are the ",
            "compact ",
            "inner JSON object, and that outer evidence_refs must be a JSON array ",
            f"containing only {evidence_id}. ",
            "uncertainty must be a JSON string or null. ",
            "Put no Markdown or prose outside the outer JSON.",
        )
    )


def _diagnostic_payload(value: PortfolioDiagnostic) -> dict[str, object]:
    payload = asdict(value)
    payload["output_kind"] = "PortfolioDiagnostic"
    return payload


async def _execute(
    *,
    model_id: str,
    api_key: str,
    agent_data_root: Path,
    acceptance_path: Path,
) -> dict[str, object]:
    acceptance, acceptance_hash = _acceptance(acceptance_path)
    context, arguments = _context_and_arguments(acceptance)
    container = make_app_container()
    try:
        full = PortfolioComparisonEvidenceTool(
            facade=container.get(PortfolioComparisonEvidenceQueryFacade)
        ).invoke(arguments=arguments, context=context)
    finally:
        container.close()
    _assert_frozen_comparison(full, acceptance=acceptance)
    minimal = _minimal_envelope(full, acceptance_hash=acceptance_hash)
    registry = EvidenceToolRegistry(
        tools=(
            _BoundEvidenceTool(
                spec=_tool_spec(),
                envelope=minimal,
                expected_arguments=arguments,
            ),
        )
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
                idempotency_key=f"q5-portfolio-diagnostic-{acceptance_hash}",
            )
        )
        plan = AgentRunExecutionPlan(
            temporal_context=context,
            allowed_tools=(_TOOL_NAME,),
            max_output_tokens=_MAX_OUTPUT_TOKENS,
        )
        queued = runtime.create_run(
            AgentRunCreateCommand(
                session_id=session.session_id,
                objective=_objective(arguments, minimal.evidence_id),
                authority_hash=plan.authority_hash,
                max_model_tokens=_MAX_MODEL_TOKENS,
                max_model_spend_usd=Decimal(0),
                model_profile=ModelProfile.BALANCED,
                idempotency_key=f"q5-portfolio-diagnostic-run-{acceptance_hash}",
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
        if (
            completed.status is not RunStatus.COMPLETED
            or completed.output_summary is None
            or completed.guardrail is None
            or completed.guardrail.status != "passed"
            or completed.usage is None
            or completed.usage.tool_calls != 1
            or completed.evidence_refs != (minimal.evidence_id,)
            or len(completed.tool_records) != 1
            or episode is None
            or not episode.verify_manifest_hash()
            or not episode.verify_replay_identity()
        ):
            raise LivePortfolioDiagnosticError(
                "PortfolioDiagnostic did not satisfy governed completion"
            )
        diagnostic = validate_model_portfolio_diagnostic(
            completed.output_summary,
            evidence=minimal,
        )
        egress = minimal.integrity_payload()
        return {
            "schema": "ditto.q5-live-portfolio-diagnostic.v1",
            "generated_at": now,
            "status": "passed",
            "passed": True,
            "provider": "glm",
            "model_id": model_id,
            "model_snapshot": _MODEL_SNAPSHOT,
            "approval": "user-approved-approved-research-minimal-egress",
            "q5_acceptance_hash": acceptance_hash,
            "run": {
                "run_id": completed.run_id,
                "session_id": session.session_id,
                "status": completed.status,
                "guardrail_status": completed.guardrail.status,
                "latency_ms": latency_ms,
                "usage": {
                    "model_attempts": completed.usage.model_attempts,
                    "model_turns": completed.usage.model_turns,
                    "tool_calls": completed.usage.tool_calls,
                    "retries": completed.usage.retries,
                    "total_tokens": completed.usage.total_tokens,
                },
                "episode_manifest_hash": episode.manifest_hash,
                "episode_replay_identity": episode.replay_identity,
                "episode_verified": True,
            },
            "diagnostic": _diagnostic_payload(diagnostic),
            "egress": {
                "license_class": "approved-research",
                "egress_class": "cloud_allowed",
                "redaction_profile": _REDACTION_PROFILE,
                "excluded": (
                    "raw_provider_rows",
                    "provider_payloads",
                    "account_journal_events",
                    "account_free_text",
                ),
                "payload_bytes": len(canonical_bytes(egress)),
                "payload_hash": canonical_sha256(egress),
                "payload": egress,
            },
            "safety": {
                "broker_connections": 0,
                "real_orders": 0,
                "account_or_target_mutations": 0,
                "agent_write_tools": 0,
            },
        }
    finally:
        database.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("glm-5.3",), required=True)
    parser.add_argument("--approval-a4", action="store_true")
    parser.add_argument("--agent-data-root", type=Path, required=True)
    parser.add_argument("--portfolio-acceptance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def _write(path: Path, payload: Mapping[str, object]) -> None:
    normalized = orjson.loads(canonical_bytes(payload))
    atomic_write_json(
        path.expanduser().resolve(),
        _mapping(normalized, field="diagnostic report"),
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    environment: Mapping[str, str] = os.environ,
) -> int:
    """Execute only the approved non-production GLM diagnostic lane."""
    arguments = _parser().parse_args(argv)
    output = Path(arguments.output)
    if not bool(arguments.approval_a4):
        _write(
            output,
            {
                "schema": "ditto.q5-live-portfolio-diagnostic.v1",
                "status": "not_run",
                "passed": False,
                "reason_code": "a4_approval_required",
            },
        )
        return 5
    if environment is os.environ:
        preload_runtime_secrets()
    api_key = environment.get(_API_KEY_ENV)
    if api_key is None or not api_key.strip() or api_key != api_key.strip():
        _write(
            output,
            {
                "schema": "ditto.q5-live-portfolio-diagnostic.v1",
                "status": "not_run",
                "passed": False,
                "reason_code": "glm_validation_credential_missing",
            },
        )
        return 5
    try:
        payload = asyncio.run(
            _execute(
                model_id=str(arguments.model),
                api_key=api_key,
                agent_data_root=Path(arguments.agent_data_root),
                acceptance_path=Path(arguments.portfolio_acceptance),
            )
        )
    except Exception as exc:
        _write(
            output,
            {
                "schema": "ditto.q5-live-portfolio-diagnostic.v1",
                "status": "failed",
                "passed": False,
                "reason_code": "q5_live_portfolio_diagnostic_failed",
                "failure_type": type(exc).__name__,
                "provider": "glm",
                "model_id": str(arguments.model),
                "production_eligible": False,
            },
        )
        return 1
    _write(output, {**payload, "report_hash": canonical_sha256(payload)})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
